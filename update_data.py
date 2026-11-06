
import json
import time
import os
from datetime import datetime
from pathlib import Path
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

def search_state(state, slug):
    params = {
        "was": "Holzpellets",
        "land": slug,
        "status": "offen",
        "sort": "neu",
        "seite": 1
    }

   headers = {
    "User-Agent": "Holzpellets-Radar/2.0",
    "Authorization": f"Bearer {os.environ['VERGABEWEISER_API_KEY']}"
}

    for attempt in range(3):
        try:
            response = requests.get(
                API,
                params=params,
                headers=headers,
                timeout=45
            )

            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After", "30"))

                if attempt == 2 or wait > 120:
                    return [], [
                        f"Rate-Limit erreicht. Bitte später erneut versuchen. "
                        f"Wartezeit laut Server: {wait} Sekunden."
                    ]

                time.sleep(max(wait, 5))
                continue

            response.raise_for_status()
            data = response.json()

            results = []

            for item in data.get("results", []):
                title = (
                    item.get("title")
                    or item.get("original_title")
                    or ""
                )

                # Nur echte Holzpellet-Treffer übernehmen
                search_text = (
                    title + " " +
                    str(item.get("original_title") or "") + " " +
                    str(item.get("gewerk") or "")
                ).lower()

                if "pellet" not in search_text:
                    continue

                buyer = item.get("buyer") or {}
                place = item.get("place") or {}
                deadline = item.get("deadline") or {}

                results.append({
                    "id": item.get("id", ""),
                    "state": state,
                    "title": title,
                    "buyer": (
                        buyer.get("name", "")
                        if isinstance(buyer, dict)
                        else str(buyer)
                    ),
                    "place": (
                        place.get("text")
                        or place.get("city")
                        or place.get("land")
                        or state
                    ),
                    "deadline": (
                        deadline.get("label", "")
                        if isinstance(deadline, dict)
                        else str(deadline)
                    ),
                    "published": item.get("published_on") or "",
                    "url": item.get("url") or "",
                    "source": "Vergabeweiser"
                })

            return results, []

        except Exception as error:
            if attempt == 2:
                return [], [str(error)]

            time.sleep(5 * (attempt + 1))

    return [], ["Suche konnte nicht abgeschlossen werden."]


all_results = []
all_errors = []

for state, slug in STATES.items():
    print("Suche:", state)

    results, errors = search_state(state, slug)

    all_results.extend(results)
    all_errors.extend([
        state + ": " + error for error in errors
    ])

    # Anfragen zeitlich entzerren
    time.sleep(5)

# Doppelte Ergebnisse entfernen
unique = {}

for item in all_results:
    key = item.get("id") or item.get("url") or item.get("title")
    unique[str(key)] = item

results = list(unique.values())

results.sort(
    key=lambda x: x.get("published") or "",
    reverse=True
)

Path("data").mkdir(exist_ok=True)

snapshot = {
    "updated_at": datetime.now(
        ZoneInfo("Europe/Berlin")
    ).isoformat(timespec="seconds"),
    "results": results,
    "errors": all_errors
}

Path("data/latest.json").write_text(
    json.dumps(snapshot, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("Suchlauf beendet.")
print("Gefundene Ausschreibungen:", len(results))
print("Fehler:", len(all_errors))
