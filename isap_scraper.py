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
        session.headers.update({
            'User-Agent': 'ISAP-Scraper/2.0 (+https://github.com/karolpolikarp/ISAP-scraper)',
            'Accept': 'application/json',
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

    def _get_json(self, path: str, retries: int = None):
        """
        Wykonaj zapytanie GET do API i zwróć sparsowany JSON.

        Args:
            path: Ścieżka względem api_url (np. '/acts/DU/2024') lub pełny URL
            retries: Liczba prób (None = z konfiguracji)

        Returns:
            Sparsowany JSON (dict/list) albo None w przypadku błędu / pustej odpowiedzi
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

                response = self.session.get(url, timeout=30)

                if response.status_code == 404:
                    return None
                response.raise_for_status()

                if not response.text.strip():
                    return None
                return response.json()

            except (requests.RequestException, json.JSONDecodeError) as e:
                self.logger.warning(f"Próba {attempt + 1}/{retries} nieudana dla {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(self.config['rate_limiting']['retry_delay'])
                else:
                    self.logger.error(f"Wszystkie próby nieudane dla {url}")
                    return None

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
                        choices=['scrape-all', 'check-new', 'find-replaced', 'export', 'stats'],
                        default='scrape-all',
                        help='Tryb działania')
    parser.add_argument('--days', type=int, default=7,
                        help='Liczba dni wstecz (dla check-new)')
    parser.add_argument('--output', help='Plik wyjściowy (dla export)')

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
