# 🚀 Szybki Start - ISAP Scraper

## Instalacja w 3 krokach

### 1. Zainstaluj zależności

```bash
pip install -r requirements.txt
```

### 2. Opcjonalnie: Dostosuj konfigurację

Edytuj `config.yaml` jeśli chcesz zmienić zakres lat lub typy aktów:

```yaml
year_range:
  start: 2020  # Zmień na rok, od którego chcesz pobierać
  end: null    # null = do teraz

act_types:
  - WDU  # Dziennik Ustaw
  - WMP  # Monitor Polski
```

### 3. Uruchom scraper

```bash
# Pobierz wszystkie akty prawne
python isap_scraper.py --mode scrape-all
```

## Najważniejsze komendy

### Pobranie wszystkich aktów

```bash
python isap_scraper.py --mode scrape-all
```

⏱️ Pierwszy raz: 2-4 godziny
💾 Zapisuje do: `data/acts_database.json`

### Sprawdzenie nowych aktów

```bash
python isap_scraper.py --mode check-new --days 7
```

⏱️ Czas: 2-5 minut
✅ Znajdzie akty z ostatnich 7 dni

### Znalezienie zastąpionych aktów

```bash
python isap_scraper.py --mode find-replaced
```

⏱️ Czas: 10-30 minut
⚠️ Wykryje akty uchylone/zastąpione

### Eksport do CSV

```bash
python isap_scraper.py --mode export --output moje_akty.csv
```

📊 Eksportuje wszystkie akty do pliku CSV

### Statystyki

```bash
python isap_scraper.py --mode stats
```

📈 Pokaże statystyki bazy danych

## Automatyczne monitorowanie

### Sprawdź raz (teraz)

```bash
python monitor.py --mode once
```

### Uruchom ciągłe monitorowanie (działa w tle)

```bash
python monitor.py --mode continuous
```

🔄 Będzie sprawdzał co 24h (konfigurowalny w `config.yaml`)

### Cron (sprawdzaj codziennie o 6:00)

Dodaj do crontab (`crontab -e`):

```cron
0 6 * * * cd /ścieżka/do/isapscrap && python3 monitor.py --mode once
```

## Użycie w kodzie Python

```python
from isap_scraper import ISAPScraper

# Utwórz scraper
scraper = ISAPScraper('config.yaml')

# Sprawdź nowe akty
new_acts = scraper.check_for_new_acts(days_back=7)

print(f"Znaleziono {len(new_acts)} nowych aktów!")

# Eksportuj
scraper.export_to_csv('akty.csv')
```

## Przykłady

Zobacz katalog `examples/` dla bardziej zaawansowanych przykładów:

- `example_basic_usage.py` - Podstawowe użycie
- `example_monitoring.py` - Monitorowanie z powiadomieniami
- `example_analysis.py` - Analiza danych

## Struktura danych

Dane są zapisywane w `data/acts_database.json`:

```json
{
  "acts": {
    "WDU_2025_123456": {
      "id": "123456",
      "type": "WDU",
      "year": 2025,
      "title": "Ustawa o...",
      "status": "active",
      "url": "https://..."
    }
  }
}
```

## Rozwiązywanie problemów

### Błąd "Access denied"

Zwiększ opóźnienia w `config.yaml`:

```yaml
rate_limiting:
  requests_per_second: 1  # było: 2
```

### Scraper nic nie znajduje

1. Sprawdź logi w `logs/`
2. Upewnij się, że ISAP jest dostępny
3. Sprawdź konfigurację `config.yaml`

### Brakuje katalogu

Katalogi tworzone automatycznie przy pierwszym uruchomieniu:
- `data/` - dane i cache
- `logs/` - logi

## Więcej informacji

📖 Pełna dokumentacja: [README.md](README.md)

🐛 Problemy? Sprawdź logi w `logs/`

💡 Pytania? Przeczytaj FAQ w README.md
