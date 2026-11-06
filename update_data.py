
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

STATES = [
    "Brandenburg",
    "Mecklenburg-Vorpommern",
    "Sachsen",
    "Sachsen-Anhalt",
    "Thüringen"
]

TERMS = [
    "Holzpellets",
    "Holzpellet",
    "Pelletlieferung",
    "Lieferung von Holzpellets"
]

API = "https://vergabeweiser.de/api/v1/tenders"


def search(state):
    items = {}
    errors = []

    for term in TERMS:
        try:
            response = requests.get(
                API,
                params={
                    "was": term,
                    "wo": state,
                    "status": "offen",
                    "seite": 1,
                    "sort": "neu"
                },
                timeout=35
            )
            response.raise_for_status()
            data = response.json()

            for item in data.get("results", []):
                title = str(
                    item.get("title")
                    or item.get("original_title")
                    or ""
                )

                description = str(item.get("description") or "")

                if "pellet" not in (
                    title + " " + description
                ).lower():
                    continue

                url = (
                    item.get("url")
                    or item.get("notice_url")
                    or item.get("link")
                    or ""
                )

                ident = str(item.get("id") or url or title)

                items[ident] = {
                    "id": ident,
                    "state": state,
                    "title": title or "Holzpellet-Ausschreibung",
                    "buyer": item.get("buyer") or "",
                    "place": item.get("place") or state,
                    "deadline": item.get("deadline") or "",
                    "published": item.get("published_at") or "",
                    "url": url
                }

        except Exception as error:
            errors.append(
                f"{state} / {term}: {error}"
            )

    return list(items.values()), errors


results = []
errors = []

for state in STATES:
    found, failed = search(state)
    results.extend(found)
    errors.extend(failed)

unique = {
    str(x.get("url") or x.get("title")): x
    for x in results
}

results = list(unique.values())

results.sort(
    key=lambda x: str(x.get("published") or ""),
    reverse=True
)

Path("data").mkdir(exist_ok=True)

snapshot = {
    "updated_at": datetime.now(
        ZoneInfo("Europe/Berlin")
    ).isoformat(timespec="seconds"),
    "results": results,
    "errors": errors
}

Path("data/latest.json").write_text(
    json.dumps(snapshot, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(
    f"{len(results)} Treffer gespeichert; "
    f"{len(errors)} Fehler."
)
