#!/usr/bin/env python3
"""
Przykład podstawowego użycia ISAP Scrapera
"""

from isap_scraper import ISAPScraper

def main():
    print("=== ISAP Scraper - Przykład podstawowego użycia ===\n")

    # Utwórz scraper
    print("1. Inicjalizacja scrapera...")
    scraper = ISAPScraper('../config.yaml')

    # Pobierz statystyki
    print("\n2. Statystyki bazy danych:")
    stats = scraper.get_statistics()
    print(f"   - Łącznie aktów: {stats['total_acts']}")
    print(f"   - Obowiązujących: {stats['by_status'].get('obowiązujący', 0)}")
    print(f"   - Podział wg wydawcy: {stats['by_publisher']}")
    print(f"   - Ostatnia aktualizacja: {stats['last_update']}")

    # Pobierz akty z konkretnego roku
    print("\n3. Pobieranie aktów z roku 2025...")
    acts_2025 = scraper.scrape_acts_by_year(2025, publisher='DU')
    print(f"   Znaleziono: {len(acts_2025)} aktów")

    # Wyświetl pierwsze 5 aktów
    if acts_2025:
        print("\n   Przykładowe akty:")
        for act in acts_2025[:5]:
            print(f"   - {act.get('title', 'Brak tytułu')}")

    # Sprawdź nowe akty z ostatnich 7 dni
    print("\n4. Sprawdzanie nowych aktów (ostatnie 7 dni)...")
    new_acts = scraper.check_for_new_acts(days_back=7)
    print(f"   Nowych aktów: {len(new_acts)}")

    if new_acts:
        print("\n   Nowe akty:")
        for act in new_acts[:5]:
            print(f"   - {act.get('type')}/{act.get('year')}: {act.get('title', 'Brak tytułu')}")

    # Eksportuj do CSV
    print("\n5. Eksport do CSV...")
    csv_file = scraper.export_to_csv('../data/export_example.csv')
    print(f"   Zapisano do: {csv_file}")

    print("\n=== Zakończono ===")


if __name__ == '__main__':
    main()
