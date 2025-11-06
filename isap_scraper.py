#!/usr/bin/env python3
"""
ISAP Scraper - Scraper dla Internetowego Systemu Aktów Prawnych Sejmu RP
Autor: Claude
Wersja: 1.0
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import logging
from pathlib import Path
import yaml
from urllib.parse import urljoin
import pandas as pd
from tqdm import tqdm


class ISAPScraper:
    """Główna klasa scrapera dla systemu ISAP"""

    def __init__(self, config_path: str = "config.yaml"):
        """
        Inicjalizacja scrapera

        Args:
            config_path: Ścieżka do pliku konfiguracyjnego
        """
        self.config = self._load_config(config_path)
        self._setup_directories()
        self._setup_logging()
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pl,en-US;q=0.7,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
        return session

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

    def _make_request(self, url: str, retries: int = None) -> Optional[requests.Response]:
        """
        Wykonaj zapytanie HTTP z obsługą retry i rate limiting

        Args:
            url: URL do pobrania
            retries: Liczba prób (None = użyj z konfiguracji)

        Returns:
            Response object lub None w przypadku błędu
        """
        if retries is None:
            retries = self.config['rate_limiting']['retry_attempts']

        for attempt in range(retries):
            try:
                # Rate limiting
                time.sleep(1 / self.config['rate_limiting']['requests_per_second'])

                response = self.session.get(url, timeout=30)
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

    def get_years_list(self, act_type: str = "WDU") -> List[int]:
        """
        Pobierz listę dostępnych lat dla danego typu aktu

        Args:
            act_type: Typ aktu (WDU, WMP, etc.)

        Returns:
            Lista lat
        """
        url = f"{self.config['base_url']}/isap.nsf/ByYear.xsp?type={act_type}"
        response = self._make_request(url)

        if not response:
            return []

        soup = BeautifulSoup(response.content, 'lxml')
        years = []

        # Szukaj linków do lat
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'year=' in href:
                try:
                    year = int(href.split('year=')[1].split('&')[0])
                    if year not in years:
                        years.append(year)
                except (ValueError, IndexError):
                    continue

        return sorted(years, reverse=True)

    def scrape_acts_by_year(self, year: int, act_type: str = "WDU") -> List[Dict]:
        """
        Pobierz akty prawne dla danego roku

        Args:
            year: Rok
            act_type: Typ aktu

        Returns:
            Lista słowników z danymi aktów
        """
        self.logger.info(f"Pobieram akty {act_type} z roku {year}")

        url = f"{self.config['base_url']}/isap.nsf/ByYear.xsp?type={act_type}&year={year}"
        response = self._make_request(url)

        if not response:
            return []

        soup = BeautifulSoup(response.content, 'lxml')
        acts = []

        # Parsuj tabelę z aktami
        # Struktura może się różnić, więc szukamy różnych wzorców
        for row in soup.find_all(['tr', 'div'], class_=lambda x: x and 'row' in x.lower() if x else False):
            act_data = self._parse_act_row(row, year, act_type)
            if act_data:
                acts.append(act_data)

        # Jeśli nie znaleziono w tabelach, szukaj linków
        if not acts:
            for link in soup.find_all('a', href=True):
                if 'DocDetails.xsp' in link['href'] or 'download.xsp' in link['href']:
                    act_data = self._parse_act_link(link, year, act_type)
                    if act_data:
                        acts.append(act_data)

        self.logger.info(f"Znaleziono {len(acts)} aktów dla {act_type}/{year}")
        return acts

    def _parse_act_row(self, row, year: int, act_type: str) -> Optional[Dict]:
        """Parsuj wiersz tabeli z aktem prawnym"""
        try:
            links = row.find_all('a', href=True)
            if not links:
                return None

            main_link = links[0]
            href = main_link['href']

            if 'id=' in href:
                act_id = href.split('id=')[1].split('&')[0]
            else:
                return None

            title = main_link.get_text(strip=True)

            # Szukaj dodatkowych informacji w wierszu
            cells = row.find_all(['td', 'div'])

            act_data = {
                'id': act_id,
                'type': act_type,
                'year': year,
                'title': title,
                'url': urljoin(self.config['base_url'], href),
                'scraped_at': datetime.now().isoformat(),
                'status': 'active'
            }

            # Próba wyciągnięcia numeru i daty
            for cell in cells:
                text = cell.get_text(strip=True)
                if text and len(text) < 100:  # Krótkie teksty mogą być metadanymi
                    if 'poz.' in text.lower():
                        act_data['position'] = text
                    elif any(month in text.lower() for month in ['stycznia', 'lutego', 'marca', 'kwietnia', 'maja', 'czerwca', 'lipca', 'sierpnia', 'września', 'października', 'listopada', 'grudnia']):
                        act_data['publication_date'] = text

            return act_data

        except Exception as e:
            self.logger.debug(f"Błąd parsowania wiersza: {e}")
            return None

    def _parse_act_link(self, link, year: int, act_type: str) -> Optional[Dict]:
        """Parsuj link do aktu prawnego"""
        try:
            href = link['href']

            if 'id=' in href:
                act_id = href.split('id=')[1].split('&')[0]
            else:
                return None

            title = link.get_text(strip=True)

            if not title or len(title) < 5:
                return None

            return {
                'id': act_id,
                'type': act_type,
                'year': year,
                'title': title,
                'url': urljoin(self.config['base_url'], href),
                'scraped_at': datetime.now().isoformat(),
                'status': 'active'
            }

        except Exception as e:
            self.logger.debug(f"Błąd parsowania linku: {e}")
            return None

    def get_act_details(self, act_id: str) -> Optional[Dict]:
        """
        Pobierz szczegóły aktu prawnego

        Args:
            act_id: ID aktu

        Returns:
            Słownik ze szczegółami
        """
        url = f"{self.config['base_url']}/isap.nsf/DocDetails.xsp?id={act_id}"
        response = self._make_request(url)

        if not response:
            return None

        soup = BeautifulSoup(response.content, 'lxml')

        details = {
            'id': act_id,
            'full_html': response.text if self.config['download']['save_html'] else None,
        }

        # Parsuj metadane
        for label in soup.find_all(['dt', 'label', 'strong']):
            label_text = label.get_text(strip=True).lower()
            value_elem = label.find_next_sibling()

            if value_elem:
                value = value_elem.get_text(strip=True)

                if 'tytuł' in label_text:
                    details['title'] = value
                elif 'data' in label_text:
                    details['date'] = value
                elif 'status' in label_text:
                    details['status'] = value
                elif 'organ' in label_text:
                    details['issuing_body'] = value

        # Szukaj tekstów zastępowanych/zmienianych
        for link in soup.find_all('a', href=True):
            link_text = link.get_text(strip=True).lower()
            if 'zastępuje' in link_text or 'zmienia' in link_text:
                if 'replaces' not in details:
                    details['replaces'] = []
                href = link['href']
                if 'id=' in href:
                    replaced_id = href.split('id=')[1].split('&')[0]
                    details['replaces'].append(replaced_id)

        return details

    def scrape_all_acts(self) -> int:
        """
        Pobierz wszystkie akty prawne zgodnie z konfiguracją

        Returns:
            Liczba pobranych aktów
        """
        self.logger.info("Rozpoczynam pobieranie wszystkich aktów prawnych")

        year_start = self.config['year_range']['start']
        year_end = self.config['year_range']['end'] or datetime.now().year

        total_new_acts = 0

        for act_type in self.config['act_types']:
            self.logger.info(f"Pobieram akty typu {act_type}")

            # Pobierz dostępne lata
            available_years = self.get_years_list(act_type)

            # Filtruj według konfiguracji
            years_to_scrape = [
                year for year in available_years
                if year_start <= year <= year_end
            ]

            for year in tqdm(years_to_scrape, desc=f"Lata {act_type}"):
                acts = self.scrape_acts_by_year(year, act_type)

                for act in tqdm(acts, desc=f"Akty {year}", leave=False):
                    act_key = f"{act_type}_{year}_{act['id']}"

                    # Sprawdź czy akt już istnieje
                    if act_key not in self.db['acts']:
                        # Pobierz szczegóły
                        details = self.get_act_details(act['id'])
                        if details:
                            act.update(details)

                        self.db['acts'][act_key] = act
                        total_new_acts += 1
                    else:
                        # Aktualizuj datę ostatniego sprawdzenia
                        self.db['acts'][act_key]['last_checked'] = datetime.now().isoformat()

                # Zapisuj bazę po każdym roku
                self._save_database()

        self.logger.info(f"Zakończono pobieranie. Nowych aktów: {total_new_acts}")
        return total_new_acts

    def check_for_new_acts(self, days_back: int = 7) -> List[Dict]:
        """
        Sprawdź nowe akty prawne z ostatnich dni

        Args:
            days_back: Ile dni wstecz sprawdzić

        Returns:
            Lista nowych aktów
        """
        self.logger.info(f"Sprawdzam nowe akty z ostatnich {days_back} dni")

        current_year = datetime.now().year
        new_acts = []

        for act_type in self.config['act_types']:
            # Sprawdź tylko bieżący rok i poprzedni
            for year in [current_year, current_year - 1]:
                acts = self.scrape_acts_by_year(year, act_type)

                for act in acts:
                    act_key = f"{act_type}_{year}_{act['id']}"

                    if act_key not in self.db['acts']:
                        # Nowy akt!
                        details = self.get_act_details(act['id'])
                        if details:
                            act.update(details)

                        self.db['acts'][act_key] = act
                        new_acts.append(act)
                        self.logger.info(f"Znaleziono nowy akt: {act.get('title', act_key)}")

        self._save_database()
        return new_acts

    def find_replaced_acts(self) -> List[Dict]:
        """
        Znajdź akty, które zostały zastąpione

        Returns:
            Lista zastąpionych aktów
        """
        self.logger.info("Sprawdzam zastąpione akty")

        replaced_acts = []

        for act_key, act_data in self.db['acts'].items():
            if act_data.get('status') == 'active':
                # Sprawdź szczegóły aktu
                details = self.get_act_details(act_data['id'])

                if details and details.get('status'):
                    status = details['status'].lower()
                    if 'uchylony' in status or 'zastąpiony' in status or 'nieobowiązujący' in status:
                        act_data['status'] = 'replaced'
                        act_data['status_details'] = details['status']
                        replaced_acts.append(act_data)
                        self.logger.info(f"Akt zastąpiony: {act_data.get('title', act_key)}")

                # Sprawdź relacje zastąpienia
                if details and details.get('replaces'):
                    for replaced_id in details['replaces']:
                        # Znajdź zastąpiony akt w bazie
                        for other_key, other_act in self.db['acts'].items():
                            if other_act['id'] == replaced_id and other_act.get('status') == 'active':
                                other_act['status'] = 'replaced'
                                other_act['replaced_by'] = act_key
                                replaced_acts.append(other_act)

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

        # Przygotuj dane do eksportu
        acts_list = []
        for act_key, act_data in self.db['acts'].items():
            # Usuń długie pola HTML
            export_data = {k: v for k, v in act_data.items() if k != 'full_html'}
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
            'by_type': {},
            'by_year': {},
            'by_status': {
                'active': 0,
                'replaced': 0,
                'unknown': 0
            },
            'last_update': self.db['metadata'].get('last_update')
        }

        for act_key, act_data in self.db['acts'].items():
            # Statystyki według typu
            act_type = act_data.get('type', 'unknown')
            stats['by_type'][act_type] = stats['by_type'].get(act_type, 0) + 1

            # Statystyki według roku
            year = act_data.get('year', 'unknown')
            stats['by_year'][str(year)] = stats['by_year'].get(str(year), 0) + 1

            # Statystyki według statusu
            status = act_data.get('status', 'unknown')
            if status in stats['by_status']:
                stats['by_status'][status] += 1
            else:
                stats['by_status']['unknown'] += 1

        return stats


def main():
    """Główna funkcja programu"""
    import argparse

    parser = argparse.ArgumentParser(
        description='ISAP Scraper - Scraper aktów prawnych z systemu ISAP Sejmu RP'
    )
    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Ścieżka do pliku konfiguracyjnego'
    )
    parser.add_argument(
        '--mode',
        choices=['scrape-all', 'check-new', 'find-replaced', 'export', 'stats'],
        default='scrape-all',
        help='Tryb działania scrapera'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Liczba dni wstecz (dla check-new)'
    )
    parser.add_argument(
        '--output',
        help='Plik wyjściowy (dla export)'
    )

    args = parser.parse_args()

    # Utwórz scraper
    scraper = ISAPScraper(args.config)

    # Wykonaj akcję
    if args.mode == 'scrape-all':
        scraper.scrape_all_acts()

    elif args.mode == 'check-new':
        new_acts = scraper.check_for_new_acts(args.days)
        print(f"\nZnaleziono {len(new_acts)} nowych aktów:")
        for act in new_acts:
            print(f"  - {act.get('type')}/{act.get('year')}: {act.get('title', 'Brak tytułu')}")

    elif args.mode == 'find-replaced':
        replaced = scraper.find_replaced_acts()
        print(f"\nZnaleziono {len(replaced)} zastąpionych aktów:")
        for act in replaced:
            print(f"  - {act.get('type')}/{act.get('year')}: {act.get('title', 'Brak tytułu')}")
            print(f"    Status: {act.get('status_details', 'nieznany')}")

    elif args.mode == 'export':
        output_file = scraper.export_to_csv(args.output)
        print(f"\nWyeksportowano dane do: {output_file}")

    elif args.mode == 'stats':
        stats = scraper.get_statistics()
        print("\n=== Statystyki bazy aktów prawnych ===")
        print(f"Łącznie aktów: {stats['total_acts']}")
        print(f"Ostatnia aktualizacja: {stats['last_update']}")

        print("\nPodział według typu:")
        for act_type, count in sorted(stats['by_type'].items()):
            print(f"  {act_type}: {count}")

        print("\nPodział według statusu:")
        for status, count in stats['by_status'].items():
            print(f"  {status}: {count}")

        print("\nPodział według lat (ostatnie 5 lat):")
        years_sorted = sorted(stats['by_year'].items(), reverse=True)[:5]
        for year, count in years_sorted:
            print(f"  {year}: {count}")


if __name__ == '__main__':
    main()
