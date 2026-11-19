"""Send one WEB.DE email when genuinely new tender IDs appear."""
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

DATA_FILE = Path("data/latest.json")
STATE_FILE = Path("data/notified_ids.json")
SMTP_HOST = "smtp.web.de"
SMTP_PORT = 587
RECIPIENT = os.environ.get("MAIL_TO", "andrei.hergt@web.de")


def identity(item):
    source = str(item.get("source") or "Unbekannte Quelle").strip()
    item_id = str(item.get("id") or "").strip()
    if not item_id:
        item_id = str(item.get("url") or item.get("notice_url") or "").strip()
    if not item_id:
        return None
    return f"{source}:{item_id}"


def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"{DATA_FILE} fehlt")
    if not STATE_FILE.exists():
        raise FileNotFoundError(
            f"{STATE_FILE} fehlt. Bitte den bekannten Datenbestand zuerst als Startbestand hinterlegen."
        )

    username = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    if not username or not password:
        raise RuntimeError(
            "GitHub Secrets SMTP_USER und SMTP_PASSWORD müssen eingerichtet sein."
        )

    snapshot = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    already_notified = set(state.get("notified_ids", []))

    new_items = []
    for item in snapshot.get("results", []):
        key = identity(item)
        if key and key not in already_notified:
            new_items.append((key, item))

    if not new_items:
        print("Keine neuen Ausschreibungen – keine E-Mail erforderlich.")
        return

    new_items.sort(key=lambda pair: (
        str(pair[1].get("state") or ""),
        str(pair[1].get("published") or ""),
        str(pair[1].get("title") or ""),
    ))

    lines = [
        f"Das Ausschreibungsradar hat {len(new_items)} neue passende Ausschreibung(en) gefunden.",
        "",
    ]
    for number, (key, item) in enumerate(new_items, start=1):
        lines.extend([
            f"{number}. {item.get('title') or 'Ausschreibung ohne Titel'}",
            f"Bundesland: {item.get('state') or 'Nicht angegeben'}",
            f"Auftraggeber: {item.get('buyer') or 'Nicht angegeben'}",
            f"Kategorie: {item.get('woodpellet_check') or 'Nicht angegeben'}",
            f"Quelle: {item.get('source') or 'Nicht angegeben'}",
            f"Veröffentlicht: {item.get('published') or 'Nicht angegeben'}",
            f"Angebotsfrist: {item.get('deadline') or 'Nicht angegeben'}",
            f"Link: {item.get('url') or item.get('notice_url') or 'Kein Link verfügbar'}",
            "",
        ])
    lines.extend([
        "Hinweis: Bitte Angebotsfrist und Vergabeunterlagen in der Originalbekanntmachung prüfen.",
        "Diese Nachricht wurde automatisch vom Pellet- und Kohle-Ausschreibungsradar versendet.",
    ])

    message = EmailMessage()
    message["Subject"] = (
        f"Neue Ausschreibung(en) im Pellet- und Kohle-Radar: {len(new_items)} Treffer"
    )
    message["From"] = username
    message["To"] = RECIPIENT
    message.set_content("\n".join(lines))

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(username, password)
        server.send_message(message)

    # Erst nach erfolgreichem Versand als gemeldet markieren.
    already_notified.update(key for key, _ in new_items)
    state["notified_ids"] = sorted(already_notified)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"E-Mail erfolgreich versendet: {len(new_items)} neue Ausschreibung(en) an {RECIPIENT}.")


if __name__ == "__main__":
    main()
