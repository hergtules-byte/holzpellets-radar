
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

SEARCH_TERMS = [
    "Holzpellets",
    "Pelletlieferung",
    "Pellets"
]

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


def get_value(value, *keys):
    if isinstance(value, dict):
        for key in keys:
            if value.get(key):
                return value[key]
    elif value:
        return str(value)
    return ""


for state, slug in STATES.items():

    for term in SEARCH_TERMS:

        print(f"Suche: {state} – {term}")

        try:
            response = requests.get(
                API,
                params={
                    "was": term,
                    "land": slug,
                    "status": "offen",
                    "sort": "neu",
                    "seite": 1
                },
                headers=headers,
                timeout=45
            )

            if response.status_code == 429:
                all_errors.append(
                    f"{state} / {term}: API-Limit erreicht."
                )
                continue

            response.raise_for_status()
            data = response.json()

            print("Suchverständnis:", data.get("understood"))
            print("Gesamtzahl laut API:", data.get("total"))

            for item in data.get("results", []):

                title = (
                    item.get("title")
                    or item.get("original_title")
                    or "Pellet-Ausschreibung"
                )

                original = item.get("original_title") or ""
                description = item.get("description") or ""

                search_text = (
                    title + " " + original + " " + description
                ).lower()

                if "pellet" not in search_text:
                    continue

                woodpellet_terms = [
                    "holzpellet",
                    "holz pellet",
                    "holzpellets"
                ]

                clearly_wood = any(
                    word in search_text
                    for word in woodpellet_terms
                )

                all_results.append({
                    "id": item.get("id", ""),
                    "state": state,
                    "title": title,
                    "buyer": get_value(
                        item.get("buyer"), "name"
                    ),
                    "place": get_value(
                        item.get("place"), "text", "city"
                    ) or state,
                    "deadline": get_value(
                        item.get("deadline"), "label"
                    ),
                    "published": item.get("published_on") or "",
                    "url": item.get("url") or "",
                    "search_term": term,
                    "woodpellet_check": (
                        "Holzpellet-Bezug erkannt"
                        if clearly_wood
                        else "Holzpellet-Bezug bitte prüfen"
                    ),
                    "source": "Vergabeweiser"
                })

        except Exception as error:
            all_errors.append(
                f"{state} / {term}: {str(error)}"
            )

            print("Fehler:", state, term, error)

        # Anfragen zeitlich entzerren
        time.sleep(2)


# Doppelte Ausschreibungen entfernen
unique = {}

for item in all_results:

    key = (
        str(item.get("id"))
        if item.get("id")
        else item.get("url") or (
            item.get("state", "") + item.get("title", "")
        )
    )

    if key not in unique:
        unique[key] = item

    elif (
        item["woodpellet_check"] == "Holzpellet-Bezug erkannt"
    ):
        unique[key]["woodpellet_check"] = (
            "Holzpellet-Bezug erkannt"
        )

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
print("HOLZPELLETS-RADAR ABGESCHLOSSEN")
print("Suchbegriffe:", len(SEARCH_TERMS))
print("Bundesländer:", len(STATES))
print("Suchanfragen:", len(STATES) * len(SEARCH_TERMS))
print("Gefundene Treffer:", len(results))
print("Davon mit erkanntem Holzpellet-Bezug:",
      sum(
          1 for x in results
          if x["woodpellet_check"] == "Holzpellet-Bezug erkannt"
      ))
print("Fehler:", len(all_errors))
print("--------------------------------")
