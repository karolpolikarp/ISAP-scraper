# isap-api - Klient API Aktów Prawnych Sejmu RP

Narzędzie do pobierania i monitorowania metadanych aktów prawnych z
**oficjalnego API ELI Sejmu RP** (`https://api.sejm.gov.pl/eli`) — Internetowego
Systemu Aktów Prawnych (ISAP).

> **Uwaga o architekturze:** narzędzie korzysta z oficjalnego, publicznego API
> JSON, a **nie** ze scrapowania strony `isap.sejm.gov.pl` (która jest chroniona
> przez WAF i nie nadaje się do automatycznego parsowania HTML). Dzięki temu jest
> szybkie i stabilne — pobranie metadanych całego rocznika to jedno zapytanie.

## Funkcjonalności

✅ **Pobieranie aktów prawnych**
- Pobieranie metadanych aktów z Dziennika Ustaw (DU) i Monitora Polskiego (MP)
- Konfigurowalny zakres lat
- Bogate metadane: tytuł, status, daty, typ aktu, ELI, adres publikacyjny

✅ **Monitorowanie zmian**
- Wykrywanie nowych aktów (po dacie ogłoszenia)
- Wykrywanie aktów, które utraciły moc obowiązującą (pole `inForce` z API)
- Automatyczne powiadomienia (do konfiguracji)

✅ **Eksport danych**
- Eksport do CSV
- Lokalna baza JSON
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

Edytuj plik `config.yaml`, aby dostosować narzędzie do swoich potrzeb:

```yaml
# Źródło danych
api_url: "https://api.sejm.gov.pl/eli"

# Wydawcy do pobierania (DU = Dziennik Ustaw, MP = Monitor Polski)
publishers:
  - DU
  - MP

# Zakres lat
year_range:
  start: 2020
  end: null  # null = do bieżącego roku

# Monitorowanie
monitoring:
  enabled: true
  interval_hours: 24

# Opcje pobierania
download:
  fetch_details: false  # true = dociągaj pełne szczegóły każdego aktu (wolniej)
```

## Użycie

### 1. Pobranie wszystkich aktów prawnych

```bash
python isap_api.py --mode scrape-all
```

To polecenie:
- Pobierze metadane wszystkich aktów zgodnie z konfiguracją
- Zapisze je w bazie `data/acts_database.json`
- Trwa kilkanaście sekund (jedno zapytanie API na rocznik)

### 2. Sprawdzenie nowych aktów prawnych

```bash
python isap_api.py --mode check-new --days 7
```

Sprawdzi akty ogłoszone w ostatnich 7 dniach i znajdzie te, których nie ma jeszcze
w bazie.

### 3. Znalezienie aktów, które utraciły moc

```bash
python isap_api.py --mode find-replaced
```

Sprawdzi (na podstawie pola `inForce` i statusu z API), które akty zostały
uchylone lub wygasły, i zaktualizuje ich status w bazie.

### 4. Eksport do CSV

```bash
python isap_api.py --mode export --output akty.csv
```

### 5. Statystyki

```bash
python isap_api.py --mode stats
```

Wyświetli statystyki bazy: podział według wydawcy, statusu i lat.

### 6. Pobranie pełnych tekstów aktów

```bash
# PDF (domyślnie z konfiguracji), tylko pierwsze 50 aktów z bazy
python isap_api.py --mode fetch-texts --format pdf --limit 50

# PDF i HTML
python isap_api.py --mode fetch-texts --format both
```

Pobiera treść aktów z bazy i zapisuje do `data/texts/` (`{adres}.pdf` / `{adres}.html`).
Akty już pobrane są pomijane (chyba że dodasz `--overwrite`). Szczegóły poniżej —
patrz [Pełne teksty aktów](#pełne-teksty-aktów).

## Automatyczne monitorowanie

### Uruchomienie monitora jednorazowo

```bash
python monitor.py --mode once
```

### Uruchomienie ciągłego monitorowania

```bash
python monitor.py --mode continuous
```

Monitor sprawdza nowe akty zgodnie z harmonogramem w konfiguracji (domyślnie co 24h).

### Uruchomienie jako usługa systemowa (Linux)

Utwórz plik `/etc/systemd/system/isap-monitor.service`:

```ini
[Unit]
Description=ISAP Monitor
After=network.target

[Service]
Type=simple
User=twoj_user
WorkingDirectory=/sciezka/do/isap-api
ExecStart=/usr/bin/python3 /sciezka/do/isap-api/monitor.py --mode continuous
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

```cron
# Sprawdzaj nowe akty codziennie o 6:00
0 6 * * * cd /sciezka/do/isap-api && /usr/bin/python3 monitor.py --mode once
```

## Struktura projektu

```
isap-api/
├── config.yaml              # Konfiguracja
├── requirements.txt         # Zależności Python
├── isap_api.py          # Główny klient API
├── monitor.py               # Monitor automatyczny
├── README.md                # Ta dokumentacja
├── data/                    # Dane (tworzone automatycznie)
│   └── acts_database.json   # Baza aktów
├── logs/                    # Logi (tworzone automatycznie)
└── examples/                # Przykłady użycia
```

## API klienta

### Podstawowe użycie w kodzie Python

```python
from isap_api import ISAPClient

# Utwórz klienta
scraper = ISAPClient('config.yaml')

# Pobierz akty z konkretnego roku (publisher: DU lub MP)
acts_2025 = scraper.scrape_acts_by_year(2025, publisher='DU')

# Sprawdź nowe akty
new_acts = scraper.check_for_new_acts(days_back=7)

# Pobierz szczegóły aktu (po adresie publikacyjnym)
details = scraper.get_act_details('WDU20240001984')

# Znajdź akty, które utraciły moc
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
    "WDU20240001984": {
      "address": "WDU20240001984",
      "publisher": "DU",
      "type": "Rozporządzenie",
      "year": 2024,
      "pos": 1984,
      "title": "Rozporządzenie Rady Ministrów z dnia ...",
      "displayAddress": "Dz.U. 2024 poz. 1984",
      "ELI": "DU/2024/1984",
      "status": "obowiązujący",
      "inForce": "IN_FORCE",
      "announcementDate": "2024-12-30",
      "url": "https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20240001984",
      "scraped_at": "2026-01-20T10:30:00"
    }
  },
  "metadata": {
    "last_update": "2026-01-20T10:30:00",
    "total_acts": 23485
  }
}
```

## Wydawcy

- **DU** — Dziennik Ustaw (główne akty prawne)
- **MP** — Monitor Polski (akty niższego rzędu)

Pełną listę wydawców zwraca endpoint `GET /acts` (oraz metoda `get_publishers()`).

## Statusy aktów

Status pochodzi wprost z API (pole `status`), np.:

- `obowiązujący` — akt obowiązujący
- `uchylony`, `uznany za uchylony`, `wygaśnięcie aktu` — akt nieobowiązujący
- `akt posiada tekst jednolity`, `akt objęty tekstem jednolitym` — informacje o tekście jednolitym

Dodatkowo pole `inForce` przyjmuje wartości `IN_FORCE` / `NOT_IN_FORCE` / `UNKNOWN`
i jest najpewniejszym wskaźnikiem mocy obowiązującej.

## Pełne teksty aktów

ELI API udostępnia treść aktów, ale w trzech „smakach" o różnej jakości
strukturalnej. Warto rozumieć ich ograniczenia:

| Forma | Endpoint | Dostępność | Uwagi |
|-------|----------|------------|-------|
| **PDF** | `/acts/{pub}/{rok}/{poz}/text.pdf` | niemal zawsze (`textPDF=true`) | render dokumentu — **nie** tekst per-artykuł |
| **Pełny HTML** | `/acts/{pub}/{rok}/{poz}/text.html` | gdy `textHTML=true` | cały akt jako HTML |
| **Fragment** | `.../text.html/{tree}` np. `art=1` | gdy artykuły są adresowalne na poziomie głównym | czysty pojedynczy artykuł, bez parsowania PDF |

Czego ELI API **nie** ma: czystego, strukturalnego endpointu „daj artykuł N jako
JSON" dla dowolnego aktu. Dwa istotne przypadki brzegowe:

- **Najnowsze teksty jednolite kodeksów (KC, KP) bywają PDF-only** (`textHTML=false`)
  — wtedy `text.html` zwraca pusty body, zostaje PDF.
- **Teksty jednolite są publikowane jako Obwieszczenia** — ich drzewo na poziomie
  głównym to treść obwieszczenia, a właściwy kodeks jest zagnieżdżony, więc bare
  `art=N` nie trafia (trzeba pełnej ścieżki `tree` albo całego HTML).

Klient obsługuje to wprost:

```python
from isap_api import ISAPClient
c = ISAPClient()
act = c.db['acts']['WDU20240001976']

c.download_act_text(act, 'pdf')        # zapis data/texts/WDU20240001976.pdf
c.download_act_text(act, 'html')       # tylko gdy textHTML=true; inaczej None
html = c.get_act_article(act, 'art=1') # pojedynczy artykuł jako HTML (lub None)
```

`fetch_texts()` (tryb CLI `fetch-texts`) pomija akty bez tekstu w danym formacie
na podstawie flag `textPDF`/`textHTML` — bez marnowania zapytań i bez pustych plików.

## Rozwiązywanie problemów

### Brak połączenia / błędy sieciowe

API bywa chwilowo niedostępne. Klient ponawia próby (`rate_limiting.retry_attempts`).
W razie potrzeby zmniejsz tempo zapytań w `config.yaml`:

```yaml
rate_limiting:
  requests_per_second: 2
```

### Brak nowych aktów mimo że powinny być

1. Sprawdź, czy konfiguracja zawiera odpowiednich wydawców (`DU`, `MP`)
2. Sprawdź zakres lat (`year_range`)
3. Zwiększ okno wyszukiwania: `python isap_api.py --mode check-new --days 30`

### Logi

Wszystkie operacje są logowane do katalogu `logs/`.

## Przykłady zastosowań

### 1. Monitoring zmian w prawie dla kancelarii prawnej

```bash
python monitor.py --mode continuous
```

### 2. Budowa bazy wiedzy prawnej

```python
from isap_api import ISAPClient

scraper = ISAPClient()
scraper.scrape_all_acts()
scraper.export_to_csv('baza_prawa.csv')
```

### 3. Alerting o zmianach w konkretnych dziedzinach

```python
from isap_api import ISAPClient

scraper = ISAPClient()
new_acts = scraper.check_for_new_acts(days_back=1)

keywords = ['podatkowy', 'VAT', 'podatek']
relevant_acts = [
    act for act in new_acts
    if any(keyword in act.get('title', '').lower() for keyword in keywords)
]

if relevant_acts:
    print(f"Znaleziono {len(relevant_acts)} nowych aktów dotyczących podatków!")
```

## Wydajność

- **Pobranie metadanych całego rocznika**: jedno zapytanie API (ułamek sekundy)
- **Pełny zakres 2020–2026 (DU + MP)**: ~20 tys. aktów w kilkanaście sekund
- **Sprawdzenie nowych aktów**: kilka sekund
- **`find-replaced`**: zależnie od liczby aktów (jedno zapytanie szczegółów na akt)

## Limitacje

- Domyślnie pobierane są metadane aktów; pełne szczegóły (referencje, organ wydający)
  wymagają opcji `download.fetch_details: true` lub wywołania `get_act_details()`
- Pełne teksty: PDF to render dokumentu, a nie tekst strukturalny per-artykuł;
  HTML i fragmenty `art=N` są dostępne tylko dla części aktów — patrz
  [Pełne teksty aktów](#pełne-teksty-aktów)

## Planowane funkcjonalności

- [x] Pobieranie pełnych tekstów aktów (PDF/HTML) przez API
- [ ] Ekstrakcja tekstu z PDF (dla aktów PDF-only, np. teksty jednolite kodeksów)
- [ ] Budowa grafu zależności między aktami (referencje)
- [ ] Powiadomienia e-mail/Slack
- [ ] Web UI do przeglądania bazy
- [ ] Docker container

## Dokumentacja API

Pełna specyfikacja OpenAPI: https://api.sejm.gov.pl/eli.html

## Licencja

Kod źródłowy: **MIT License** — szczegóły w pliku [LICENSE](LICENSE).

Licencja MIT obejmuje wyłącznie kod tego projektu. **Nie** dotyczy samych aktów
prawnych ani ich metadanych — zgodnie z art. 4 ustawy o prawie autorskim i
prawach pokrewnych akty normatywne nie są przedmiotem prawa autorskiego i należą
do domeny publicznej.

## Disclaimer

Narzędzie korzysta z oficjalnego, publicznego API Sejmu RP i służy celom
edukacyjnym oraz badawczym. Przestrzegaj regulaminu korzystania z tego API.
