# 🚀 Szybki Start - ISAP Scraper

Klient oficjalnego API ELI Sejmu RP (`https://api.sejm.gov.pl/eli`).

## Instalacja w 3 krokach 

### 1. Zainstaluj zależności

```bash
pip install -r requirements.txt
```

### 2. Opcjonalnie: Dostosuj konfigurację

Edytuj `config.yaml`, jeśli chcesz zmienić zakres lat lub wydawców:

```yaml
year_range:
  start: 2020  # Rok, od którego pobierać
  end: null    # null = do teraz

publishers:
  - DU  # Dziennik Ustaw
  - MP  # Monitor Polski
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

⏱️ Kilkanaście sekund (jedno zapytanie API na rocznik)
💾 Zapisuje do: `data/acts_database.json`

### Sprawdzenie nowych aktów

```bash
python isap_scraper.py --mode check-new --days 7
```

⏱️ Kilka sekund
✅ Znajdzie akty ogłoszone w ostatnich 7 dniach

### Znalezienie aktów, które utraciły moc

```bash
python isap_scraper.py --mode find-replaced
```

⚠️ Wykryje akty uchylone/wygasłe (na podstawie pola `inForce` z API)

### Pobranie pełnych tekstów aktów

```bash
python isap_scraper.py --mode fetch-texts --format pdf --limit 50
```

📄 Zapisuje treść aktów (PDF/HTML) do `data/texts/`. Akty PDF-only same pomijają
HTML. Szczegóły i ograniczenia: patrz README → „Pełne teksty aktów".

### Eksport do CSV

```bash
python isap_scraper.py --mode export --output moje_akty.csv
```

📊 Eksportuje wszystkie akty do pliku CSV

### Statystyki

```bash
python isap_scraper.py --mode stats
```

📈 Pokaże podział według wydawcy, statusu i lat

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

```cron
0 6 * * * cd /ścieżka/do/ISAP-scraper && python3 monitor.py --mode once
```

## Użycie w kodzie Python

```python
from isap_scraper import ISAPScraper

# Utwórz klienta
scraper = ISAPScraper('config.yaml')

# Sprawdź nowe akty
new_acts = scraper.check_for_new_acts(days_back=7)
print(f"Znaleziono {len(new_acts)} nowych aktów!")

# Eksportuj
scraper.export_to_csv('akty.csv')
```

## Przykłady

Zobacz katalog `examples/`:

- `example_basic_usage.py` - Podstawowe użycie
- `example_monitoring.py` - Monitorowanie z powiadomieniami
- `example_analysis.py` - Analiza danych

## Struktura danych

Dane zapisywane są w `data/acts_database.json`:

```json
{
  "acts": {
    "WDU20240001984": {
      "address": "WDU20240001984",
      "publisher": "DU",
      "type": "Rozporządzenie",
      "year": 2024,
      "title": "Rozporządzenie Rady Ministrów ...",
      "displayAddress": "Dz.U. 2024 poz. 1984",
      "status": "obowiązujący",
      "inForce": "IN_FORCE",
      "url": "https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20240001984"
    }
  }
}
```

## Rozwiązywanie problemów

### Błędy sieciowe / API niedostępne

Zmniejsz tempo zapytań w `config.yaml`:

```yaml
rate_limiting:
  requests_per_second: 2
```

### Scraper nic nie znajduje

1. Sprawdź logi w `logs/`
2. Upewnij się, że API jest dostępne (`https://api.sejm.gov.pl/eli/acts`)
3. Sprawdź konfigurację `config.yaml` (wydawcy `DU`/`MP`, zakres lat)

### Brakuje katalogu

Katalogi tworzone automatycznie przy pierwszym uruchomieniu:
- `data/` - dane i cache
- `logs/` - logi

## Więcej informacji

📖 Pełna dokumentacja: [README.md](README.md)

📚 Specyfikacja API: https://api.sejm.gov.pl/eli.html

🐛 Problemy? Sprawdź logi w `logs/`
