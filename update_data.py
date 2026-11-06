
import os
import json
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

STATES = {
    "Brandenburg": "brandenburg",
    "Mecklenburg-Vorpommern": "mecklenburg-vorpommern",
    "Sachsen": "sachsen",
    "Sachsen-Anhalt": "sachsen-anhalt",
    "Thüringen": "thueringen"
}

API = "https://vergabeweiser.de/api/v1/tenders"
DATA_FILE = Path("data/latest.json")

api_key = os.environ.get("VERGABEWEISER_API_KEY")

if not api_key:
    raise RuntimeError(
        "GitHub Secret VERGABEWEISER_API_KEY fehlt."
    )

headers = {
    "Authorization": f"Bearer {api_key}",
    "User-Agent": "Holzpellets-Radar/2.0"
}

all_results = []
all_errors = []

for state, slug in STATES.items():
    print("Durchsuche:", state)

    try:
        response = requests.get(
            API,
            params={
                "was": "Holzpellets",
                "land": slug,
                "status": "offen",
                "sort": "neu",
                "seite": 1
            },
            headers=headers,
            timeout=45
        )

        if response.status_code == 429:
            wait = response.headers.get(
                "Retry-After", "unbekannt"
            )
            all_errors.append(
                f"{state}: API-Limit erreicht. "
                f"Retry-After: {wait}"
            )
            print("API-Limit erreicht:", state)
            continue

        response.raise_for_status()
        data = response.json()
print("Suchverständnis:", data.get("understood"))
print("Gesamtzahl laut API:", data.get("total"))
print("Such-URL:", data.get("search_url"))
        for item in data.get("results", []):
            title = (
                item.get("title")
                or item.get("original_title")
                or "Holzpellet-Ausschreibung"
            )

            all_results.append({
                "id": item.get("id", ""),
                "state": state,
                "title": title,
                "buyer": (
                    (item.get("buyer") or {}).get("name", "")
                ),
                "place": (
                    (item.get("place") or {}).get("text")
                    or (item.get("place") or {}).get("city")
                    or state
                ),
                "deadline": (
                    (item.get("deadline") or {}).get("label", "")
                ),
                "published": item.get("published_on") or "",
                "url": item.get("url") or "",
                "source": "Vergabeweiser"
            })

        print(
            state,
            "- Treffer:",
            len(data.get("results", []))
        )

    except Exception as error:
        all_errors.append(
            f"{state}: {str(error)}"
        )
        print("Fehler:", state, error)

    time.sleep(3)

# Doppelte Ausschreibungen entfernen
unique = {}

for item in all_results:
    key = (
        item.get("id")
        or item.get("url")
        or item.get("title")
    )
    unique[str(key)] = item

results = list(unique.values())

results.sort(
    key=lambda x: x.get("published") or "",
    reverse=True
)

# Ergebnisse speichern
DATA_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

snapshot = {
    "updated_at": datetime.now(
        ZoneInfo("Europe/Berlin")
    ).isoformat(timespec="seconds"),
    "results": results,
    "errors": all_errors
}

DATA_FILE.write_text(
    json.dumps(
        snapshot,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

print("--------------------------------")
print("Holzpellets-Radar abgeschlossen")
print("Treffer:", len(results))
print("Fehler:", len(all_errors))
print("--------------------------------")

if all_errors:
    print("WARNUNG: Suche teilweise unvollständig.")
