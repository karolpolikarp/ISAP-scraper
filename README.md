# ISAP Scraper - Scraper Aktów Prawnych Sejmu RP

Automatyczny scraper do pobierania i monitorowania aktów prawnych z Internetowego Systemu Aktów Prawnych (ISAP) Sejmu Rzeczypospolitej Polskiej.

## Funkcjonalności

 **Pobieranie aktów prawnych**
- Automatyczne pobieranie wszystkich aktualnych aktów prawnych
- Obsługa różnych typów aktów (Dziennik Ustaw, Monitor Polski)
- Konfigurowalny zakres lat

✅ **Monitorowanie zmian**
- Codzienne sprawdzanie nowych aktów prawnych
- Wykrywanie aktów zastąpionych/uchylonych
- Automatyczne powiadomienia

✅ **Eksport danych**
- Eksport do CSV
- Zapisywanie w bazie JSON
- Pełne logi operacji

## Instalacja

### Wymagania
- Python 3.8 lub nowszy
- pip

### Instalacja zależności

```bash
pip install -r requirements.txt
```

## Konfiguracja

Edytuj plik `config.yaml` aby dostosować scraper do swoich potrzeb:

```yaml
# Typy aktów do pobierania
act_types:
  - WDU  # Dziennik Ustaw
  - WMP  # Monitor Polski

# Zakres lat
year_range:
  start: 2020
  end: null  # null = do bieżącego roku

# Monitorowanie
monitoring:
  enabled: true
  interval_hours: 24
```

## Użycie

### 1. Pobranie wszystkich aktualnych aktów prawnych

```bash
python isap_scraper.py --mode scrape-all
```

To polecenie:
- Pobierze wszystkie akty prawne zgodnie z konfiguracją
- Zapisze je w bazie danych `data/acts_database.json`
- Może zająć kilka godzin przy pierwszym uruchomieniu

### 2. Sprawdzenie nowych aktów prawnych

```bash
python isap_scraper.py --mode check-new --days 7
```

To sprawdzi akty z ostatnich 7 dni i znajdzie nowe akty, których nie ma jeszcze w bazie.

### 3. Znalezienie zastąpionych aktów

```bash
python isap_scraper.py --mode find-replaced
```

To sprawdzi, które akty zostały zastąpione, uchylone lub straciły moc obowiązującą.

### 4. Eksport do CSV

```bash
python isap_scraper.py --mode export --output akty.csv
```

Wyeksportuje wszystkie akty z bazy do pliku CSV.

### 5. Statystyki

```bash
python isap_scraper.py --mode stats
```

Wyświetli statystyki bazy aktów prawnych.

## Automatyczne monitorowanie

### Uruchomienie monitora jednorazowo

```bash
python monitor.py --mode once
```

### Uruchomienie ciągłego monitorowania

```bash
python monitor.py --mode continuous
```

Monitor będzie działał w tle i sprawdzał nowe akty zgodnie z harmonogramem w konfiguracji (domyślnie co 24 godziny).

### Uruchomienie jako usługa systemowa (Linux)

Utwórz plik `/etc/systemd/system/isap-monitor.service`:

```ini
[Unit]
Description=ISAP Monitor
After=network.target

[Service]
Type=simple
User=twoj_user
WorkingDirectory=/sciezka/do/isapscrap
ExecStart=/usr/bin/python3 /sciezka/do/isapscrap/monitor.py --mode continuous
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```

Następnie:

```bash
sudo systemctl daemon-reload
sudo systemctl enable isap-monitor
sudo systemctl start isap-monitor
```

### Harmonogram cron (alternatywa)

Dodaj do crontab (`crontab -e`):

```cron
# Sprawdzaj nowe akty codziennie o 6:00
0 6 * * * cd /sciezka/do/isapscrap && /usr/bin/python3 monitor.py --mode once
```

## Struktura projektu

```
isapscrap/
├── config.yaml              # Konfiguracja
├── requirements.txt         # Zależności Python
├── isap_scraper.py         # Główny scraper
├── monitor.py              # Monitor automatyczny
├── README.md               # Ta dokumentacja
├── data/                   # Dane (tworzone automatycznie)
│   ├── acts_database.json  # Baza aktów
│   └── cache/              # Cache
├── logs/                   # Logi (tworzone automatycznie)
└── examples/               # Przykłady użycia
```

## API Scrapera

### Podstawowe użycie w kodzie Python

```python
from isap_scraper import ISAPScraper

# Utwórz scraper
scraper = ISAPScraper('config.yaml')

# Pobierz akty z konkretnego roku
acts_2025 = scraper.scrape_acts_by_year(2025, act_type='WDU')

# Sprawdź nowe akty
new_acts = scraper.check_for_new_acts(days_back=7)

# Pobierz szczegóły aktu
details = scraper.get_act_details('WDU20250001234')

# Znajdź zastąpione akty
replaced = scraper.find_replaced_acts()

# Eksportuj do CSV
scraper.export_to_csv('output.csv')

# Pobierz statystyki
stats = scraper.get_statistics()
print(f"Łącznie aktów: {stats['total_acts']}")
```

## Struktura bazy danych

Baza danych to plik JSON o strukturze:

```json
{
  "acts": {
    "WDU_2025_123456": {
      "id": "123456",
      "type": "WDU",
      "year": 2025,
      "title": "Ustawa o...",
      "url": "https://isap.sejm.gov.pl/...",
      "status": "active",
      "publication_date": "2025-01-15",
      "scraped_at": "2025-01-20T10:30:00",
      "replaces": ["WDU20200012345"],
      ...
    }
  },
  "metadata": {
    "last_update": "2025-01-20T10:30:00",
    "total_acts": 15000
  }
}
```

## Typy aktów prawnych

- **WDU** - Dziennik Ustaw (główne akty prawne)
- **WMP** - Monitor Polski (akty niższego rzędu)
- **WDU_UE** - Dziennik Ustaw - prawo Unii Europejskiej

## Statusy aktów

- `active` - Akt obowiązujący
- `replaced` - Akt zastąpiony/uchylony
- `unknown` - Status nieznany

## Rozwiązywanie problemów

### Błąd "Access denied" lub "403"

Może to oznaczać, że ISAP blokuje zbyt częste zapytania. Rozwiązania:

1. Zwiększ opóźnienie między zapytaniami w `config.yaml`:
   ```yaml
   rate_limiting:
     requests_per_second: 1  # zmniejsz z 2 na 1
   ```

2. Uruchom scraper w godzinach nocnych

3. Użyj proxy lub VPN

### Błąd parsowania HTML

Struktura strony ISAP może się zmienić. W takim przypadku:

1. Sprawdź logi w katalogu `logs/`
2. Zaktualizuj metody parsowania w `isap_scraper.py`
3. Zgłoś issue na GitHubie

### Brak nowych aktów mimo że powinny być

1. Sprawdź czy konfiguracja zawiera odpowiednie typy aktów
2. Sprawdź zakres lat w konfiguracji
3. Uruchom z flagą debug: `python isap_scraper.py --mode check-new --days 30`

## Przykłady zastosowań

### 1. Monitoring zmian w prawie dla kancelarii prawnej

```bash
# Codzienne sprawdzanie nowych aktów
python monitor.py --mode continuous
```

### 2. Budowa bazy wiedzy prawnej

```python
from isap_scraper import ISAPScraper

scraper = ISAPScraper()
scraper.scrape_all_acts()
scraper.export_to_csv('baza_prawa.csv')

# Import do bazy danych SQL, Elasticsearch, etc.
```

### 3. Alerting o zmianach w konkretnych dziedzinach

```python
from isap_scraper import ISAPScraper

scraper = ISAPScraper()
new_acts = scraper.check_for_new_acts(days_back=1)

# Filtruj akty zawierające konkretne słowa kluczowe
keywords = ['podatkowy', 'VAT', 'podatek']
relevant_acts = [
    act for act in new_acts
    if any(keyword in act.get('title', '').lower() for keyword in keywords)
]

if relevant_acts:
    # Wyślij powiadomienie
    print(f"Znaleziono {len(relevant_acts)} nowych aktów dotyczących podatków!")
```

## Wydajność

- **Pierwsze pobranie** (20 lat danych): ~2-4 godziny
- **Sprawdzenie nowych aktów**: ~2-5 minut
- **Sprawdzenie zastąpionych**: ~10-30 minut (zależnie od liczby aktów)

## Limitacje

- Scraper działa na podstawie publicznej strony ISAP, nie oficjalnego API
- Struktura HTML może się zmienić, co wymaga aktualizacji parsera
- Rate limiting: domyślnie 2 zapytania na sekundę
- Brak obsługi pełnego tekstu aktów (tylko metadane)

## Planowane funkcjonalności

- [ ] Pobieranie pełnych tekstów aktów (PDF)
- [ ] Integracja z API Sejmu (gdy będzie dostępne)
- [ ] Analiza zmian między wersjami aktów
- [ ] Powiadomienia e-mail/Slack
- [ ] Web UI do przeglądania bazy
- [ ] Docker container
- [ ] REST API

## Licencja

MIT License

## Autor

Claude (Anthropic)

## Wsparcie

W razie problemów:
1. Sprawdź dokumentację
2. Przejrzyj logi w katalogu `logs/`
3. Utwórz issue na GitHubie

## Disclaimer

Ten scraper służy wyłącznie do celów edukacyjnych i badawczych. Przestrzegaj regulaminu korzystania z serwisu ISAP. Autor nie ponosi odpowiedzialności za nadużycia.
