#!/usr/bin/env python3
"""
ISAP Scraper - klient oficjalnego API ELI Sejmu RP (Akty Prawne)

Pobiera metadane aktów prawnych z publicznego API:
    https://api.sejm.gov.pl/eli

Wersja 2.0 — przepisana z kruchego scrapowania HTML strony isap.sejm.gov.pl
(blokowanej przez WAF Incapsula) na oficjalne, stabilne API JSON.
"""

import requests
import json
import os
import re
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
from pathlib import Path
import yaml
import pandas as pd
from tqdm import tqdm


# Statusy oznaczające, że akt utracił moc obowiązującą
REPEALED_STATUSES = {
    'uchylony',
    'uchylony wykazem',
    'uznany za uchylony',
    'wygaśnięcie aktu',
    'brak mocy prawnej',
    'nieobowiązujący - przyczyna nieustalona',
    'nieobowiązujący - uchylona podstawa prawna',
    'wydane z naruszeniem prawa',
}


class ISAPScraper:
    """Klient API ELI dla systemu ISAP Sejmu RP"""

    def __init__(self, config_path: str = "config.yaml"):
        """
        Inicjalizacja klienta

        Args:
            config_path: Ścieżka do pliku konfiguracyjnego
        """
        self.config = self._load_config(config_path)
        self._setup_directories()
        self._setup_logging()
        self.api_url = self.config.get('api_url', 'https://api.sejm.gov.pl/eli').rstrip('/')
        self.base_url = self.config.get('base_url', 'https://isap.sejm.gov.pl').rstrip('/')
        self.session = self._create_session()
        self.db = self._load_database()

    def _load_config(self, config_path: str) -> dict:
        """Wczytaj konfigurację z pliku YAML"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _setup_directories(self):
        """Utwórz wymagane katalogi"""
        for dir_key in ['data_dir', 'cache_dir', 'logs_dir']:
            dir_path = self.config.get(dir_key)
            if dir_path:
                Path(dir_path).mkdir(parents=True, exist_ok=True)

    def _setup_logging(self):
        """Konfiguracja logowania"""
        log_file = os.path.join(
            self.config['logs_dir'],
            f"isap_scraper_{datetime.now().strftime('%Y%m%d')}.log"
        )

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _create_session(self) -> requests.Session:
        """Utwórz sesję HTTP z odpowiednimi nagłówkami"""
        session = requests.Session()
        # UA przeglądarkowy — backend endpointów text.html/text.pdf bywa za WAF-em
        # i odrzuca nietypowe klienty; JSON-owe metadane akceptują dowolny UA.
        session.headers.update({
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/124.0 Safari/537.36'),
            'Accept-Language': 'pl,en;q=0.7',
        })
        return session

    def _publishers(self) -> List[str]:
        """Lista kodów wydawców z konfiguracji (z kompatybilnością wsteczną)"""
        # Preferowany klucz: publishers (DU, MP). Starsze configi: act_types (WDU, WMP...).
        publishers = self.config.get('publishers')
        if publishers:
            return publishers
        # Mapowanie starych kodów ISAP na kody wydawców ELI
        legacy_map = {'WDU': 'DU', 'WMP': 'MP', 'WDU_UE': 'DU', 'DU': 'DU', 'MP': 'MP'}
        result = []
        for code in self.config.get('act_types', ['DU', 'MP']):
            mapped = legacy_map.get(code, code)
            if mapped not in result:
                result.append(mapped)
        return result

    def _load_database(self) -> dict:
        """Wczytaj lokalną bazę danych aktów prawnych"""
        db_file = self.config['db_file']
        if os.path.exists(db_file):
            with open(db_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'acts': {},
            'metadata': {
                'last_update': None,
                'total_acts': 0
            }
        }

    def _save_database(self):
        """Zapisz bazę danych do pliku"""
        self.db['metadata']['last_update'] = datetime.now().isoformat()
        self.db['metadata']['total_acts'] = len(self.db['acts'])

        db_file = self.config['db_file']
        with open(db_file, 'w', encoding='utf-8') as f:
            json.dump(self.db, f, ensure_ascii=False, indent=2)

    def _request(self, path: str, retries: int = None) -> Optional[requests.Response]:
        """
        Wykonaj zapytanie GET do API z obsługą retry i rate limiting.

        Args:
            path: Ścieżka względem api_url (np. '/acts/DU/2024') lub pełny URL
            retries: Liczba prób (None = z konfiguracji)

        Returns:
            Obiekt Response albo None (404 / błąd / wyczerpane próby)
        """
        if retries is None:
            retries = self.config['rate_limiting']['retry_attempts']

        url = path if path.startswith('http') else f"{self.api_url}{path}"

        for attempt in range(retries):
            try:
                # Rate limiting
                rps = self.config['rate_limiting']['requests_per_second']
                if rps:
                    time.sleep(1 / rps)

                response = self.session.get(url, timeout=60)

                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response

            except requests.RequestException as e:
                self.logger.warning(f"Próba {attempt + 1}/{retries} nieudana dla {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(self.config['rate_limiting']['retry_delay'])
                else:
                    self.logger.error(f"Wszystkie próby nieudane dla {url}")
                    return None

        return None

    def _get_json(self, path: str, retries: int = None):
        """
        Wykonaj zapytanie GET i zwróć sparsowany JSON (albo None).
        """
        response = self._request(path, retries)
        if response is None or not response.text.strip():
            return None
        try:
            return response.json()
        except json.JSONDecodeError as e:
            self.logger.error(f"Niepoprawny JSON z {path}: {e}")
            return None

    def get_publishers(self) -> List[Dict]:
        """Pobierz listę dostępnych wydawców (Dziennik Ustaw, Monitor Polski, ...)"""
        data = self._get_json('/acts')
        return data or []

    def get_years_list(self, publisher: str = "DU") -> List[int]:
        """
        Pobierz listę dostępnych lat dla danego wydawcy

        Args:
            publisher: Kod wydawcy (DU, MP)

        Returns:
            Lista lat (malejąco)
        """
        data = self._get_json(f'/acts/{publisher}')
        if not data:
            return []
        years = data.get('years', [])
        return sorted(years, reverse=True)

    def _map_act(self, item: Dict, publisher: str = None) -> Dict:
        """Zmapuj rekord z API (ActInfo/Act) na wewnętrzny format bazy"""
        address = item.get('address')
        pub = item.get('publisher') or publisher
        act = {
            'address': address,
            'id': address,  # alias dla kompatybilności
            'publisher': pub,
            'type': item.get('type'),
            'year': item.get('year'),
            'pos': item.get('pos'),
            'volume': item.get('volume'),
            'title': item.get('title'),
            'displayAddress': item.get('displayAddress'),
            'ELI': item.get('ELI'),
            'status': item.get('status'),
            'inForce': item.get('inForce'),
            'announcementDate': item.get('announcementDate'),
            'promulgation': item.get('promulgation'),
            'changeDate': item.get('changeDate'),
            'textHTML': item.get('textHTML'),
            'textPDF': item.get('textPDF'),
            'url': f"{self.base_url}/isap.nsf/DocDetails.xsp?id={address}" if address else None,
            'api_url': f"{self.api_url}/acts/{address}" if address else None,
            'scraped_at': datetime.now().isoformat(),
        }
        return act

    def scrape_acts_by_year(self, year: int, publisher: str = "DU") -> List[Dict]:
        """
        Pobierz listę aktów prawnych dla danego roku i wydawcy

        Args:
            year: Rok
            publisher: Kod wydawcy (DU, MP)

        Returns:
            Lista słowników z danymi aktów
        """
        self.logger.info(f"Pobieram akty {publisher} z roku {year}")

        data = self._get_json(f'/acts/{publisher}/{year}')
        if not data:
            return []

        items = data.get('items', [])
        acts = [self._map_act(it, publisher) for it in items]
        self.logger.info(f"Znaleziono {len(acts)} aktów dla {publisher}/{year}")
        return acts

    def get_act_details(self, address: str) -> Optional[Dict]:
        """
        Pobierz pełne szczegóły aktu prawnego (z polami inForce, references, ...)

        Args:
            address: Adres publikacyjny aktu (np. WDU20240001984)

        Returns:
            Słownik ze szczegółami albo None
        """
        data = self._get_json(f'/acts/{address}')
        if not data:
            return None

        details = self._map_act(data)
        # Dodatkowe pola dostępne tylko w szczegółach
        details['entryIntoForce'] = data.get('entryIntoForce')
        details['repealDate'] = data.get('repealDate')
        details['releasedBy'] = data.get('releasedBy')
        details['keywords'] = data.get('keywords')
        details['references'] = data.get('references')

        # Wyciągnij listę aktów, które ten akt uchyla/zmienia
        refs = data.get('references') or {}
        replaces = []
        for ref_type, ref_list in refs.items():
            if 'uchyla' in ref_type.lower() or 'zmienia' in ref_type.lower():
                for r in ref_list:
                    if r.get('id'):
                        replaces.append(r['id'])
        if replaces:
            details['replaces'] = replaces

        return details

    # --- Pełne teksty aktów (PDF / HTML) ---
    #
    # Rzeczywistość ELI API (zweryfikowana na żywo):
    #   * text.pdf  — dostępny niemal zawsze (render dokumentu, nie tekst per-artykuł)
    #   * text.html — tylko gdy metadana textHTML == True
    #   * text.html/{tree} (np. 'art=1') — czysty pojedynczy artykuł, ale działa
    #     tylko dla aktów z artykułami adresowalnymi na poziomie głównym (zwykłe
    #     ustawy). Dla tekstów jednolitych kodeksów (publikowanych jako
    #     Obwieszczenie) bare 'art=N' nie trafia, a najnowsze teksty jednolite
    #     bywają PDF-only (textHTML == False) — wtedy text.html zwraca pusty body.

    def _texts_dir(self) -> str:
        d = self.config.get('download', {}).get('texts_dir') \
            or os.path.join(self.config['data_dir'], 'texts')
        Path(d).mkdir(parents=True, exist_ok=True)
        return d

    def download_act_text(self, act: Dict, fmt: str = 'pdf', overwrite: bool = False) -> Optional[str]:
        """
        Pobierz pełny tekst aktu (pdf/html) i zapisz na dysk.

        Args:
            act: słownik aktu z bazy (wymaga pól publisher, year, pos, address)
            fmt: 'pdf' albo 'html'
            overwrite: nadpisać istniejący plik

        Returns:
            Ścieżka zapisanego pliku albo None (brak tekstu w danym formacie)
        """
        address = act.get('address')
        pub, year, pos = act.get('publisher'), act.get('year'), act.get('pos')
        if not (address and pub and year is not None and pos is not None):
            return None

        ext = 'pdf' if fmt == 'pdf' else 'html'
        flag = 'textPDF' if fmt == 'pdf' else 'textHTML'
        # Jeśli metadane jednoznacznie mówią, że tekstu nie ma — nie marnuj zapytania
        if act.get(flag) is False:
            return None

        out_path = os.path.join(self._texts_dir(), f"{address}.{ext}")
        if os.path.exists(out_path) and not overwrite:
            return out_path

        response = self._request(f"/acts/{pub}/{year}/{pos}/text.{ext}")
        if response is None or not response.content or not response.content.strip():
            # pusty body = tekst niedostępny w tym formacie (np. PDF-only dla html)
            return None

        if ext == 'html':
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(response.text)
        else:
            with open(out_path, 'wb') as f:
                f.write(response.content)
        return out_path

    def get_act_article(self, act: Dict, tree: str) -> Optional[str]:
        """
        Pobierz pojedynczy fragment aktu jako HTML (np. tree='art=1').

        Działa dla aktów z textHTML == True, których elementy są adresowalne
        na poziomie głównym (zwykłe ustawy). Dla aktów PDF-only lub tekstów
        jednolitych w formie obwieszczenia zwraca None.

        Args:
            act: słownik aktu (publisher, year, pos)
            tree: ścieżka fragmentu wg API, np. 'art=415' albo
                  'rozdzial=1/art=4/para=1/ustep=3'

        Returns:
            HTML fragmentu albo None
        """
        pub, year, pos = act.get('publisher'), act.get('year'), act.get('pos')
        if not (pub and year is not None and pos is not None):
            return None
        if act.get('textHTML') is False:
            return None
        response = self._request(f"/acts/{pub}/{year}/{pos}/text.html/{tree}")
        if response is None or not response.text.strip():
            return None
        return response.text

    def get_act_struct(self, act: Dict):
        """Pobierz strukturę aktu (drzewo: działy, rozdziały, artykuły, ...)."""
        pub, year, pos = act.get('publisher'), act.get('year'), act.get('pos')
        if not (pub and year is not None and pos is not None):
            return None
        return self._get_json(f"/acts/{pub}/{year}/{pos}/struct")

    # Mapowanie typów ze /struct na nazwy poziomów w ścieżce tree akceptowanej
    # przez API. Typy spoza mapy (np. 'part' = Część) trafiają do ścieżki bez zmian.
    _STRUCT_TREE_MAP = {
        'book': 'ksiega', 'titl': 'tytul', 'bran': 'dzial', 'chpt': 'rozdzial',
        'schp': 'oddzial', 'art': 'art', 'arti': 'art', 'artykul': 'art',
        'pass': 'ustep', 'para': 'paragraf', 'pint': 'punkt', 'lett': 'litera',
    }

    def _build_article_paths(self, struct) -> Dict[str, str]:
        """
        Zmapuj numer artykułu na ścieżkę tree, np.
        '100' -> 'dzial=II/rozdzial=1/art=100', albo dla KC
        '33_1' -> 'ksiega=PIERWSZA/part=OGÓLNA/tytul=II/dzial=II/art=33_1'.

        Buduje pełną ścieżkę z hierarchii (księga/część/tytuł/dział/rozdział/...),
        pomijając jedynie bezimienne węzły-wrappery (np. 'Treść ustawy').
        """
        paths: Dict[str, str] = {}

        def walk(nodes, chain):
            for node in nodes:
                chain2 = chain + [node]
                if node.get('type') in ('art', 'arti', 'artykul'):
                    num = (node.get('name') or '').strip()
                    if num:
                        segs = []
                        for x in chain2:
                            name = x.get('name')
                            if not name:          # bezimienny wrapper — pomiń
                                continue
                            typ = self._STRUCT_TREE_MAP.get(x.get('type'), x.get('type'))
                            segs.append(f"{typ}={name}")
                        paths[num] = '/'.join(segs)
                if node.get('children'):
                    walk(node['children'], chain2)

        nodes = struct if isinstance(struct, list) else (struct.get('children', []) if struct else [])
        walk(nodes, [])
        return paths

    # Indeks górny (np. art. 33¹) — API zapisuje go w strukturze jako '33_1'
    _SUPERSCRIPTS = {'⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
                     '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9'}

    @classmethod
    def _article_number_candidates(cls, number) -> List[str]:
        """
        Warianty zapisu numeru artykułu z indeksem górnym. Pozwala podać artykuł
        naturalnie ('33¹', '33(1)', '33 1') — w strukturze API jest to '33_1'.
        """
        s = str(number).strip()
        cands = [s]
        # indeks górny unicode -> _N  (np. '33¹' -> '33_1')
        norm = re.sub('[⁰¹²³⁴⁵⁶⁷⁸⁹]+',
                      lambda m: '_' + ''.join(cls._SUPERSCRIPTS[ch] for ch in m.group()),
                      s)
        # nawiasy/spacje wokół indeksu: '33(1)', '33[1]', '33 1' -> '33_1'
        norm = re.sub(r'\s*[\(\[]\s*(\w+?)\s*[\)\]]', r'_\1', norm)
        norm = re.sub(r'(\d)\s+(\w)$', r'\1_\2', norm)
        for c in (norm, norm.replace(' ', '')):
            if c not in cands:
                cands.append(c)
        return cands

    def get_article(self, act: Dict, number) -> Optional[str]:
        """
        Pobierz pojedynczy artykuł po numerze (np. 100, '13a', '33¹') jako HTML.

        Rozwiązuje ścieżkę przez strukturę aktu (/struct), więc działa także dla
        ustaw z działami i rozdziałami — w przeciwieństwie do get_act_article(),
        która wymaga znajomości pełnej ścieżki. Akceptuje indeks górny w różnych
        zapisach ('33¹', '33(1)', '33_1'). Zwraca None, gdy akt jest PDF-only
        albo nie zawiera artykułu o danym numerze.

        Args:
            act: słownik aktu (publisher, year, pos)
            number: numer artykułu (int lub str, np. '13a', '33¹')

        Returns:
            HTML artykułu albo None
        """
        if act.get('textHTML') is False:
            return None
        struct = self.get_act_struct(act)
        if not struct:
            return None
        paths = self._build_article_paths(struct)
        for key in self._article_number_candidates(number):
            if key in paths:
                return self.get_act_article(act, paths[key])
        return None

    def fetch_texts(self, formats: List[str] = None, overwrite: bool = False,
                    limit: int = None) -> Dict[str, int]:
        """
        Pobierz pełne teksty aktów z bazy (PDF i/lub HTML).

        Args:
            formats: lista formatów ('pdf', 'html'); None = z konfiguracji
            overwrite: nadpisywać istniejące pliki
            limit: maksymalna liczba aktów do przetworzenia (None = wszystkie)

        Returns:
            Słownik {format: liczba pobranych plików}
        """
        if formats is None:
            formats = self.config.get('download', {}).get('text_formats', ['pdf'])

        acts = list(self.db['acts'].values())
        if limit:
            acts = acts[:limit]

        counts = {fmt: 0 for fmt in formats}
        self.logger.info(f"Pobieram pełne teksty ({', '.join(formats)}) dla {len(acts)} aktów")

        for act in tqdm(acts, desc="Pobieranie tekstów"):
            for fmt in formats:
                path = self.download_act_text(act, fmt, overwrite)
                if path:
                    act.setdefault('text_files', {})[fmt] = path
                    counts[fmt] += 1
            self.db['acts'][act['address']] = act

        self._save_database()
        self.logger.info(f"Pobrano teksty: {counts}")
        return counts

    def scrape_all_acts(self) -> int:
        """
        Pobierz metadane wszystkich aktów prawnych zgodnie z konfiguracją

        Returns:
            Liczba nowych aktów dodanych do bazy
        """
        self.logger.info("Rozpoczynam pobieranie wszystkich aktów prawnych")

        year_start = self.config['year_range']['start']
        year_end = self.config['year_range']['end'] or datetime.now().year
        fetch_details = self.config.get('download', {}).get('fetch_details', False)

        total_new_acts = 0

        for publisher in self._publishers():
            self.logger.info(f"Pobieram akty wydawcy {publisher}")

            available_years = self.get_years_list(publisher)
            years_to_scrape = [y for y in available_years if year_start <= y <= year_end]

            for year in tqdm(years_to_scrape, desc=f"Lata {publisher}"):
                acts = self.scrape_acts_by_year(year, publisher)

                for act in acts:
                    act_key = act['address']
                    if not act_key:
                        continue

                    if act_key not in self.db['acts']:
                        # Opcjonalnie dociągnij pełne szczegóły (wolniejsze)
                        if fetch_details:
                            details = self.get_act_details(act_key)
                            if details:
                                act.update(details)
                        self.db['acts'][act_key] = act
                        total_new_acts += 1
                    else:
                        # Zaktualizuj status i datę sprawdzenia
                        existing = self.db['acts'][act_key]
                        existing['status'] = act.get('status')
                        existing['changeDate'] = act.get('changeDate')
                        existing['last_checked'] = datetime.now().isoformat()

                # Zapisuj bazę po każdym roku
                self._save_database()

        self.logger.info(f"Zakończono pobieranie. Nowych aktów: {total_new_acts}")
        return total_new_acts

    def check_for_new_acts(self, days_back: int = 7) -> List[Dict]:
        """
        Sprawdź nowe akty prawne z ostatnich dni (po dacie ogłoszenia)

        Args:
            days_back: Ile dni wstecz sprawdzić

        Returns:
            Lista nowych aktów
        """
        self.logger.info(f"Sprawdzam nowe akty z ostatnich {days_back} dni")

        cutoff = (datetime.now() - timedelta(days=days_back)).date()
        current_year = datetime.now().year
        years_to_check = [current_year]
        # Na przełomie roku sprawdź też poprzedni rok
        if datetime.now().timetuple().tm_yday <= days_back + 5:
            years_to_check.append(current_year - 1)

        new_acts = []

        for publisher in self._publishers():
            for year in years_to_check:
                acts = self.scrape_acts_by_year(year, publisher)

                for act in acts:
                    act_key = act['address']
                    if not act_key or act_key in self.db['acts']:
                        continue

                    # Filtr po dacie ogłoszenia
                    ann = act.get('announcementDate')
                    if ann:
                        try:
                            if datetime.strptime(ann, '%Y-%m-%d').date() < cutoff:
                                continue
                        except ValueError:
                            pass

                    self.db['acts'][act_key] = act
                    new_acts.append(act)
                    self.logger.info(f"Nowy akt: {act.get('displayAddress')} — {act.get('title', '')[:80]}")

        self._save_database()
        return new_acts

    def find_replaced_acts(self) -> List[Dict]:
        """
        Znajdź akty, które utraciły moc obowiązującą (uchylone/wygasłe).

        Aktualizuje status aktów w bazie na podstawie aktualnych danych z API.

        Returns:
            Lista aktów, które przestały obowiązywać
        """
        self.logger.info("Sprawdzam akty, które utraciły moc obowiązującą")

        replaced_acts = []

        active_keys = [
            k for k, a in self.db['acts'].items()
            if a.get('inForce') != 'NOT_IN_FORCE'
            and (a.get('status') or '').lower() not in REPEALED_STATUSES
        ]

        for act_key in tqdm(active_keys, desc="Sprawdzanie statusów"):
            act_data = self.db['acts'][act_key]
            details = self.get_act_details(act_data['address'])
            if not details:
                continue

            status = (details.get('status') or '').lower()
            in_force = details.get('inForce')

            # Zaktualizuj status w bazie
            act_data['status'] = details.get('status')
            act_data['inForce'] = in_force

            if in_force == 'NOT_IN_FORCE' or status in REPEALED_STATUSES:
                act_data['status_details'] = details.get('status')
                act_data['repealDate'] = details.get('repealDate')
                replaced_acts.append(act_data)
                self.logger.info(f"Utracił moc: {act_data.get('displayAddress')} ({details.get('status')})")

        self._save_database()
        return replaced_acts

    def export_to_csv(self, output_file: str = None):
        """
        Eksportuj bazę aktów do CSV

        Args:
            output_file: Ścieżka do pliku wyjściowego
        """
        if output_file is None:
            output_file = os.path.join(
                self.config['data_dir'],
                f"acts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )

        acts_list = []
        for act_key, act_data in self.db['acts'].items():
            # Usuń złożone/długie pola, które źle wyglądają w CSV
            export_data = {
                k: v for k, v in act_data.items()
                if k not in ('references', 'full_html')
            }
            export_data['act_key'] = act_key
            acts_list.append(export_data)

        df = pd.DataFrame(acts_list)
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        self.logger.info(f"Wyeksportowano {len(acts_list)} aktów do {output_file}")

        return output_file

    def get_statistics(self) -> Dict:
        """
        Pobierz statystyki bazy aktów

        Returns:
            Słownik ze statystykami
        """
        stats = {
            'total_acts': len(self.db['acts']),
            'by_publisher': {},
            'by_type': {},
            'by_year': {},
            'by_status': {},
            'last_update': self.db['metadata'].get('last_update')
        }

        for act_key, act_data in self.db['acts'].items():
            publisher = act_data.get('publisher', 'unknown')
            stats['by_publisher'][publisher] = stats['by_publisher'].get(publisher, 0) + 1

            act_type = act_data.get('type', 'unknown')
            stats['by_type'][act_type] = stats['by_type'].get(act_type, 0) + 1

            year = act_data.get('year', 'unknown')
            stats['by_year'][str(year)] = stats['by_year'].get(str(year), 0) + 1

            status = act_data.get('status', 'unknown')
            stats['by_status'][status] = stats['by_status'].get(status, 0) + 1

        return stats


def main():
    """Główna funkcja programu"""
    import argparse

    parser = argparse.ArgumentParser(
        description='ISAP Scraper - klient API ELI aktów prawnych Sejmu RP'
    )
    parser.add_argument('--config', default='config.yaml',
                        help='Ścieżka do pliku konfiguracyjnego')
    parser.add_argument('--mode',
                        choices=['scrape-all', 'check-new', 'find-replaced',
                                 'fetch-texts', 'export', 'stats'],
                        default='scrape-all',
                        help='Tryb działania')
    parser.add_argument('--days', type=int, default=7,
                        help='Liczba dni wstecz (dla check-new)')
    parser.add_argument('--output', help='Plik wyjściowy (dla export)')
    parser.add_argument('--format', choices=['pdf', 'html', 'both'],
                        help='Format pełnych tekstów (dla fetch-texts)')
    parser.add_argument('--limit', type=int,
                        help='Maks. liczba aktów do przetworzenia (dla fetch-texts)')
    parser.add_argument('--overwrite', action='store_true',
                        help='Nadpisuj istniejące pliki tekstów')

    args = parser.parse_args()

    scraper = ISAPScraper(args.config)

    if args.mode == 'scrape-all':
        scraper.scrape_all_acts()

    elif args.mode == 'check-new':
        new_acts = scraper.check_for_new_acts(args.days)
        print(f"\nZnaleziono {len(new_acts)} nowych aktów:")
        for act in new_acts:
            print(f"  - {act.get('displayAddress')}: {act.get('title', 'Brak tytułu')}")

    elif args.mode == 'find-replaced':
        replaced = scraper.find_replaced_acts()
        print(f"\nZnaleziono {len(replaced)} aktów, które utraciły moc:")
        for act in replaced:
            print(f"  - {act.get('displayAddress')}: {act.get('title', 'Brak tytułu')}")
            print(f"    Status: {act.get('status_details', act.get('status', 'nieznany'))}")

    elif args.mode == 'fetch-texts':
        formats = {'both': ['pdf', 'html']}.get(args.format, [args.format]) if args.format else None
        counts = scraper.fetch_texts(formats=formats, overwrite=args.overwrite, limit=args.limit)
        print(f"\nPobrane pełne teksty: {counts}")
        print(f"Zapisane w: {scraper._texts_dir()}")

    elif args.mode == 'export':
        output_file = scraper.export_to_csv(args.output)
        print(f"\nWyeksportowano dane do: {output_file}")

    elif args.mode == 'stats':
        stats = scraper.get_statistics()
        print("\n=== Statystyki bazy aktów prawnych ===")
        print(f"Łącznie aktów: {stats['total_acts']}")
        print(f"Ostatnia aktualizacja: {stats['last_update']}")

        print("\nPodział według wydawcy:")
        for pub, count in sorted(stats['by_publisher'].items()):
            print(f"  {pub}: {count}")

        print("\nPodział według statusu:")
        for status, count in sorted(stats['by_status'].items(), key=lambda x: -x[1]):
            print(f"  {status}: {count}")

        print("\nPodział według lat (ostatnie 5 lat):")
        years_sorted = sorted(stats['by_year'].items(), reverse=True)[:5]
        for year, count in years_sorted:
            print(f"  {year}: {count}")


if __name__ == '__main__':
    main()
