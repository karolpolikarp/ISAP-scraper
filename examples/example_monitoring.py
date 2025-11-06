#!/usr/bin/env python3
"""
Przykład monitorowania aktów prawnych z powiadomieniami
"""

from isap_scraper import ISAPScraper
import json
from datetime import datetime


def send_slack_notification(webhook_url: str, message: str):
    """
    Przykład wysłania powiadomienia na Slack
    (wymaga konfiguracji webhook URL)
    """
    import requests

    payload = {
        'text': message
    }

    try:
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        print("Powiadomienie wysłane na Slack")
    except Exception as e:
        print(f"Błąd wysyłania powiadomienia: {e}")


def send_email_notification(recipients: list, subject: str, body: str):
    """
    Przykład wysłania powiadomienia e-mail
    (wymaga konfiguracji SMTP)
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    # Konfiguracja SMTP (przykład dla Gmail)
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = "twoj_email@gmail.com"
    sender_password = "twoje_haslo_aplikacji"

    try:
        # Utwórz wiadomość
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject

        message.attach(MIMEText(body, "plain"))

        # Wyślij e-mail
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(message)

        print("Powiadomienie e-mail wysłane")
    except Exception as e:
        print(f"Błąd wysyłania e-maila: {e}")


def monitor_with_keywords(scraper: ISAPScraper, keywords: list):
    """
    Monitoruj akty zawierające określone słowa kluczowe
    """
    print(f"\n=== Monitorowanie aktów z słowami kluczowymi: {', '.join(keywords)} ===\n")

    # Sprawdź nowe akty
    new_acts = scraper.check_for_new_acts(days_back=7)

    if not new_acts:
        print("Brak nowych aktów")
        return

    # Filtruj według słów kluczowych
    relevant_acts = []
    for act in new_acts:
        title = act.get('title', '').lower()
        if any(keyword.lower() in title for keyword in keywords):
            relevant_acts.append(act)

    print(f"Znaleziono {len(relevant_acts)} aktów pasujących do kryteriów:\n")

    for act in relevant_acts:
        print(f"📋 {act.get('type')}/{act.get('year')}")
        print(f"   Tytuł: {act.get('title', 'Brak tytułu')}")
        print(f"   URL: {act.get('url', 'Brak URL')}")
        print(f"   Data: {act.get('publication_date', 'Nieznana')}")
        print()

    return relevant_acts


def monitor_replaced_acts(scraper: ISAPScraper):
    """
    Monitoruj akty, które zostały zastąpione
    """
    print("\n=== Sprawdzanie zastąpionych aktów ===\n")

    replaced_acts = scraper.find_replaced_acts()

    if not replaced_acts:
        print("Brak nowo zastąpionych aktów")
        return

    print(f"Znaleziono {len(replaced_acts)} zastąpionych aktów:\n")

    for act in replaced_acts:
        print(f"⚠️  {act.get('type')}/{act.get('year')}")
        print(f"   Tytuł: {act.get('title', 'Brak tytułu')}")
        print(f"   Status: {act.get('status_details', 'Zastąpiony')}")
        if act.get('replaced_by'):
            print(f"   Zastąpiony przez: {act.get('replaced_by')}")
        print()

    return replaced_acts


def create_html_report(new_acts: list, replaced_acts: list, output_file: str):
    """
    Utwórz raport HTML z nowych i zastąpionych aktów
    """
    html = f"""
    <!DOCTYPE html>
    <html lang="pl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Raport ISAP - {datetime.now().strftime('%Y-%m-%d')}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }}
            h1 {{
                color: #2c3e50;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
            }}
            h2 {{
                color: #34495e;
                margin-top: 30px;
            }}
            .act {{
                background: white;
                padding: 15px;
                margin: 10px 0;
                border-left: 4px solid #3498db;
                border-radius: 4px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .act.replaced {{
                border-left-color: #e74c3c;
            }}
            .act-title {{
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 5px;
            }}
            .act-meta {{
                color: #7f8c8d;
                font-size: 0.9em;
            }}
            .timestamp {{
                text-align: right;
                color: #95a5a6;
                font-style: italic;
            }}
        </style>
    </head>
    <body>
        <h1>📊 Raport ISAP</h1>
        <p class="timestamp">Wygenerowano: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

        <h2>✨ Nowe akty prawne ({len(new_acts)})</h2>
    """

    if new_acts:
        for act in new_acts:
            html += f"""
            <div class="act">
                <div class="act-title">{act.get('title', 'Brak tytułu')}</div>
                <div class="act-meta">
                    {act.get('type')}/{act.get('year')} |
                    Data: {act.get('publication_date', 'Nieznana')}
                </div>
                <div class="act-meta">
                    <a href="{act.get('url', '#')}">Więcej informacji</a>
                </div>
            </div>
            """
    else:
        html += "<p>Brak nowych aktów</p>"

    html += f"""
        <h2>⚠️ Zastąpione akty prawne ({len(replaced_acts)})</h2>
    """

    if replaced_acts:
        for act in replaced_acts:
            html += f"""
            <div class="act replaced">
                <div class="act-title">{act.get('title', 'Brak tytułu')}</div>
                <div class="act-meta">
                    {act.get('type')}/{act.get('year')} |
                    Status: {act.get('status_details', 'Zastąpiony')}
                </div>
            </div>
            """
    else:
        html += "<p>Brak zastąpionych aktów</p>"

    html += """
    </body>
    </html>
    """

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n📄 Raport HTML zapisany: {output_file}")


def main():
    print("=== ISAP Scraper - Przykład zaawansowanego monitorowania ===\n")

    # Utwórz scraper
    scraper = ISAPScraper('../config.yaml')

    # Monitoruj akty z konkretnymi słowami kluczowymi
    keywords = ['podatkowy', 'VAT', 'podatek', 'akcyza']
    relevant_acts = monitor_with_keywords(scraper, keywords)

    # Monitoruj zastąpione akty
    replaced_acts = monitor_replaced_acts(scraper)

    # Sprawdź wszystkie nowe akty
    all_new_acts = scraper.check_for_new_acts(days_back=7)

    # Utwórz raport HTML
    create_html_report(all_new_acts, replaced_acts or [], '../data/raport.html')

    # Przykład wysyłania powiadomień (wymaga konfiguracji)
    if relevant_acts:
        message = f"🔔 ISAP Alert: Znaleziono {len(relevant_acts)} nowych aktów związanych z podatkami!"

        # Slack (odkomentuj i skonfiguruj)
        # slack_webhook = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
        # send_slack_notification(slack_webhook, message)

        # E-mail (odkomentuj i skonfiguruj)
        # recipients = ["prawnik@firma.pl", "ceo@firma.pl"]
        # send_email_notification(recipients, "ISAP Alert", message)

        print(f"\n{message}")

    print("\n=== Zakończono ===")


if __name__ == '__main__':
    main()
