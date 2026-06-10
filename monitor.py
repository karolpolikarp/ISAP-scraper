#!/usr/bin/env python3
"""
ISAP Monitor - Automatyczne monitorowanie nowych aktów prawnych
"""

import schedule
import time
import logging
from datetime import datetime
from isap_api import ISAPClient
import json
import os
from typing import List, Dict


class ISAPMonitor:
    """Klasa do automatycznego monitorowania aktów prawnych"""

    def __init__(self, config_path: str = "config.yaml"):
        """
        Inicjalizacja monitora

        Args:
            config_path: Ścieżka do pliku konfiguracyjnego
        """
        self.scraper = ISAPClient(config_path)
        self.config = self.scraper.config
        self._setup_logging()

    def _setup_logging(self):
        """Konfiguracja logowania dla monitora"""
        log_file = os.path.join(
            self.config['logs_dir'],
            f"isap_monitor_{datetime.now().strftime('%Y%m%d')}.log"
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

    def check_and_notify(self):
        """Sprawdź nowe akty i wyślij powiadomienie"""
        self.logger.info("Rozpoczynam sprawdzanie nowych aktów")

        try:
            # Sprawdź nowe akty z ostatnich 2 dni
            new_acts = self.scraper.check_for_new_acts(days_back=2)

            if new_acts:
                self.logger.info(f"Znaleziono {len(new_acts)} nowych aktów")
                self._save_new_acts_report(new_acts)

                if self.config['monitoring'].get('notification_enabled'):
                    self._send_notification(new_acts)
            else:
                self.logger.info("Brak nowych aktów")

            # Sprawdź zastąpione akty
            replaced_acts = self.scraper.find_replaced_acts()
            if replaced_acts:
                self.logger.info(f"Znaleziono {len(replaced_acts)} zastąpionych aktów")
                self._save_replaced_acts_report(replaced_acts)

        except Exception as e:
            self.logger.error(f"Błąd podczas monitorowania: {e}", exc_info=True)

    def _save_new_acts_report(self, new_acts: List[Dict]):
        """Zapisz raport z nowymi aktami"""
        report_file = os.path.join(
            self.config['data_dir'],
            f"new_acts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'count': len(new_acts),
                'acts': new_acts
            }, f, ensure_ascii=False, indent=2)

        self.logger.info(f"Zapisano raport nowych aktów: {report_file}")

    def _save_replaced_acts_report(self, replaced_acts: List[Dict]):
        """Zapisz raport z zastąpionymi aktami"""
        report_file = os.path.join(
            self.config['data_dir'],
            f"replaced_acts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'count': len(replaced_acts),
                'acts': replaced_acts
            }, f, ensure_ascii=False, indent=2)

        self.logger.info(f"Zapisano raport zastąpionych aktów: {report_file}")

    def _send_notification(self, new_acts: List[Dict]):
        """
        Wyślij powiadomienie o nowych aktach (do implementacji)

        Args:
            new_acts: Lista nowych aktów
        """
        # TODO: Implementacja wysyłania e-maili lub innych powiadomień
        self.logger.info(f"Powiadomienie: {len(new_acts)} nowych aktów")

        # Przykład treści powiadomienia
        message = f"Znaleziono {len(new_acts)} nowych aktów prawnych:\n\n"
        for act in new_acts[:10]:  # Maksymalnie 10 w powiadomieniu
            message += f"- {act.get('type')}/{act.get('year')}: {act.get('title', 'Brak tytułu')}\n"

        if len(new_acts) > 10:
            message += f"\n... i {len(new_acts) - 10} więcej"

        self.logger.info(message)

    def run_once(self):
        """Uruchom monitorowanie jednorazowo"""
        self.check_and_notify()

    def run_continuous(self):
        """Uruchom ciągłe monitorowanie według harmonogramu"""
        interval_hours = self.config['monitoring'].get('interval_hours', 24)

        # Zaplanuj zadanie
        schedule.every(interval_hours).hours.do(self.check_and_notify)

        self.logger.info(f"Monitor uruchomiony. Sprawdzanie co {interval_hours} godzin.")

        # Wykonaj pierwsze sprawdzenie od razu
        self.check_and_notify()

        # Pętla główna
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Sprawdzaj harmonogram co minutę
        except KeyboardInterrupt:
            self.logger.info("Monitor zatrzymany przez użytkownika")


def main():
    """Główna funkcja programu"""
    import argparse

    parser = argparse.ArgumentParser(
        description='ISAP Monitor - Automatyczne monitorowanie aktów prawnych'
    )
    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Ścieżka do pliku konfiguracyjnego'
    )
    parser.add_argument(
        '--mode',
        choices=['once', 'continuous'],
        default='once',
        help='Tryb działania: once (raz) lub continuous (ciągły)'
    )

    args = parser.parse_args()

    monitor = ISAPMonitor(args.config)

    if args.mode == 'once':
        monitor.run_once()
    else:
        monitor.run_continuous()


if __name__ == '__main__':
    main()
