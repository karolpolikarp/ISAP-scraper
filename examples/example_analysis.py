#!/usr/bin/env python3
"""
Przykład analizy i raportowania danych z ISAP
"""

from isap_scraper import ISAPScraper
import pandas as pd
import json
from collections import Counter
from datetime import datetime


def analyze_acts_by_year(scraper: ISAPScraper):
    """
    Analiza liczby aktów prawnych według lat
    """
    print("\n=== Analiza aktów według lat ===\n")

    stats = scraper.get_statistics()
    years_data = stats['by_year']

    # Sortuj według roku
    sorted_years = sorted(years_data.items(), key=lambda x: x[0])

    print("Rok   | Liczba aktów")
    print("------|-------------")
    for year, count in sorted_years:
        print(f"{year} | {count:>12}")

    return years_data


def analyze_acts_by_type(scraper: ISAPScraper):
    """
    Analiza liczby aktów według typu (Ustawa, Rozporządzenie, Obwieszczenie, ...)
    """
    print("\n=== Analiza aktów według typu ===\n")

    stats = scraper.get_statistics()
    types_data = stats['by_type']

    print(f"{'Typ aktu':40} | Liczba aktów")
    print("-" * 40 + "-|-------------")
    for act_type, count in sorted(types_data.items(), key=lambda x: -x[1]):
        print(f"{str(act_type):40} | {count:>12}")

    # Podział według wydawcy (DU/MP)
    print("\nWedług wydawcy:")
    for pub, count in sorted(stats['by_publisher'].items()):
        desc = {'DU': 'Dziennik Ustaw', 'MP': 'Monitor Polski'}.get(pub, 'Nieznany')
        print(f"  {pub} ({desc}): {count}")

    return types_data


def analyze_replacement_chain(scraper: ISAPScraper, act_id: str):
    """
    Analiza łańcucha zastąpień dla konkretnego aktu
    """
    print(f"\n=== Łańcuch zastąpień dla aktu {act_id} ===\n")

    # Znajdź akt w bazie
    act = None
    for key, data in scraper.db['acts'].items():
        if data['id'] == act_id:
            act = data
            break

    if not act:
        print("Akt nie znaleziony w bazie")
        return

    # Wyświetl informacje o akcie
    print(f"Tytuł: {act.get('title', 'Brak tytułu')}")
    print(f"Status: {act.get('status', 'nieznany')}")

    # Znajdź akty zastępowane przez ten akt
    if act.get('replaces'):
        print(f"\nTen akt zastępuje:")
        for replaced_id in act['replaces']:
            for key, data in scraper.db['acts'].items():
                if data['id'] == replaced_id:
                    print(f"  - {data.get('title', 'Brak tytułu')}")

    # Znajdź akty zastępujące ten akt
    replacing_acts = []
    for key, data in scraper.db['acts'].items():
        if data.get('replaces') and act_id in data['replaces']:
            replacing_acts.append(data)

    if replacing_acts:
        print(f"\nTen akt został zastąpiony przez:")
        for replacing_act in replacing_acts:
            print(f"  - {replacing_act.get('title', 'Brak tytułu')}")


def find_most_amended_acts(scraper: ISAPScraper, limit: int = 10):
    """
    Znajdź najczęściej zmieniane akty prawne
    """
    print(f"\n=== Top {limit} najczęściej zmienianych aktów ===\n")

    # Zlicz ile razy każdy akt jest wymieniony jako zastępowany
    replacement_counts = Counter()

    for key, act in scraper.db['acts'].items():
        if act.get('replaces'):
            for replaced_id in act['replaces']:
                replacement_counts[replaced_id] += 1

    # Wyświetl top N
    if not replacement_counts:
        print("Brak danych o zastąpieniach")
        return

    for i, (act_id, count) in enumerate(replacement_counts.most_common(limit), 1):
        # Znajdź tytuł aktu
        title = "Nieznany"
        for key, data in scraper.db['acts'].items():
            if data['id'] == act_id:
                title = data.get('title', 'Brak tytułu')
                break

        print(f"{i}. Zmieniano {count} razy")
        print(f"   ID: {act_id}")
        print(f"   Tytuł: {title[:80]}...")
        print()


def export_detailed_report(scraper: ISAPScraper, output_file: str):
    """
    Eksportuj szczegółowy raport do JSON
    """
    print(f"\n=== Tworzenie szczegółowego raportu ===\n")

    stats = scraper.get_statistics()

    report = {
        'generated_at': datetime.now().isoformat(),
        'summary': {
            'total_acts': stats['total_acts'],
            'by_type': stats['by_type'],
            'by_year': stats['by_year'],
            'by_status': stats['by_status']
        },
        'recent_acts': [],
        'replaced_acts': [],
        'active_acts_sample': []
    }

    # Znajdź najnowsze akty (ostatnie 30)
    all_acts = list(scraper.db['acts'].values())
    sorted_acts = sorted(
        all_acts,
        key=lambda x: x.get('scraped_at', ''),
        reverse=True
    )

    report['recent_acts'] = [
        {
            'id': act['id'],
            'type': act.get('type'),
            'year': act.get('year'),
            'title': act.get('title'),
            'url': act.get('url')
        }
        for act in sorted_acts[:30]
    ]

    # Znajdź akty, które utraciły moc
    replaced = [act for act in all_acts if act.get('inForce') == 'NOT_IN_FORCE']
    report['replaced_acts'] = [
        {
            'id': act['id'],
            'type': act.get('type'),
            'year': act.get('year'),
            'title': act.get('title'),
            'status_details': act.get('status_details')
        }
        for act in replaced[:50]
    ]

    # Próbka aktów obowiązujących
    active = [act for act in all_acts if act.get('inForce') == 'IN_FORCE' or act.get('status') == 'obowiązujący']
    report['active_acts_sample'] = [
        {
            'id': act['id'],
            'type': act.get('type'),
            'year': act.get('year'),
            'title': act.get('title')
        }
        for act in active[:100]
    ]

    # Zapisz raport
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Raport zapisany do: {output_file}")
    print(f"Rozmiar raportu: {len(json.dumps(report)) / 1024:.2f} KB")


def create_pandas_analysis(scraper: ISAPScraper):
    """
    Analiza z wykorzystaniem pandas
    """
    print("\n=== Analiza z pandas ===\n")

    # Konwertuj bazę na DataFrame
    acts_list = []
    for key, act in scraper.db['acts'].items():
        acts_list.append({
            'key': key,
            'id': act.get('id'),
            'type': act.get('type'),
            'year': act.get('year'),
            'title': act.get('title'),
            'status': act.get('status'),
            'has_replaces': bool(act.get('replaces'))
        })

    df = pd.DataFrame(acts_list)

    print("Podstawowe statystyki:")
    print(df.describe())

    print("\n\nLiczba aktów według typu:")
    print(df['type'].value_counts())

    print("\n\nLiczba aktów według roku (ostatnie 10 lat):")
    year_counts = df['year'].value_counts().sort_index(ascending=False).head(10)
    print(year_counts)

    print("\n\nLiczba aktów według statusu:")
    print(df['status'].value_counts())

    print("\n\nProcent aktów z relacjami zastąpienia:")
    replacement_pct = (df['has_replaces'].sum() / len(df)) * 100
    print(f"{replacement_pct:.2f}%")

    return df


def main():
    print("=== ISAP Scraper - Przykład analizy danych ===\n")

    # Utwórz scraper
    scraper = ISAPScraper('../config.yaml')

    # Wykonaj różne analizy
    analyze_acts_by_year(scraper)
    analyze_acts_by_type(scraper)
    find_most_amended_acts(scraper, limit=10)

    # Analiza z pandas
    df = create_pandas_analysis(scraper)

    # Eksportuj szczegółowy raport
    export_detailed_report(scraper, '../data/detailed_report.json')

    # Przykład analizy łańcucha zastąpień (wymaga konkretnego ID)
    # analyze_replacement_chain(scraper, 'WDU20200001234')

    print("\n=== Zakończono ===")


if __name__ == '__main__':
    main()
