
import os
import re
import json
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


# ---------------------------------------
# KONFIGURATION
# ---------------------------------------

API = "https://vergabeweiser.de/api/v1"
DATA_FILE = Path("data/latest.json")

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

MAX_PAGES = 2
MAX_DETAIL_REQUESTS = 500
PAUSE = 0.25

api_key = os.environ.get("VERGABEWEISER_API_KEY")

if not api_key:
    raise RuntimeError(
        "GitHub Secret VERGABEWEISER_API_KEY fehlt."
    )

session = requests.Session()

session.headers.update({
    "Authorization": f"Bearer {api_key}",
    "User-Agent": "Holzpellets-Radar/3.0",
    "Accept": "application/json"
})

errors = []
candidates = {}
search_stats = []


# ---------------------------------------
# HILFSFUNKTIONEN
# ---------------------------------------

def get_value(value, *keys):
    if isinstance(value, dict):
        for key in keys:
            if value.get(key):
                return value[key]
    elif value:
        return str(value)

    return ""


def flatten_text(value):
    """Sammelt Text aus verschachtelten API-Daten."""

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        return " ".join(
            flatten_text(v)
            for v in value.values()
        )

    if isinstance(value, list):
        return " ".join(
            flatten_text(v)
            for v in value
        )

    return ""


def get_json(url, params=None):
    response = session.get(
        url,
        params=params,
        timeout=45
    )

    response.raise_for_status()

    return response.json()


def identify_pellets(text):
    text = text.lower()

    # Holzpellets eindeutig erwähnt
    wood_patterns = [
        r"holz[\s-]*pellet",
        r"pellet[\s-]*holz",
        r"pellets?\s+aus\s+holz",
        r"wood[\s-]*pellet"
    ]

    if any(
        re.search(pattern, text)
        for pattern in wood_patterns
    ):
        return "Holzpellets eindeutig erkannt"

    # Allgemeine Pellet-Bezüge zur manuellen Prüfung
    if "pellet" in text:
        return "Pellet-Bezug – Holzart prüfen"

    return None


def extract_result(item, detail, state, term):

    # Detaildaten haben Vorrang
    merged = dict(item)
    merged.update(detail)

    title = (
        merged.get("title")
        or merged.get("original_title")
        or "Pellet-Ausschreibung"
    )

    original = merged.get("original_title") or ""

    # Alle verfügbaren Textfelder einschließlich
    # Beschreibung und Losinformationen untersuchen
    complete_text = flatten_text(merged)

    classification = identify_pellets(complete_text)

    if not classification:
        return None

    buyer = merged.get("buyer") or {}
    place = merged.get("place") or {}
    deadline = merged.get("deadline") or {}

    return {
        "id": merged.get("id", ""),
        "state": state,
        "title": title,
        "original_title": original,
        "buyer": get_value(buyer, "name"),
        "place": (
            get_value(place, "text", "city")
            or state
        ),
        "deadline": get_value(deadline, "label"),
        "published": merged.get("published_on") or "",
        "url": merged.get("url") or "",
        "documents_url": merged.get("documents_url") or "",
        "notice_url": merged.get("notice_url") or "",
        "description": merged.get("description") or "",
        "cpv": merged.get("cpv") or "",
        "gewerk": merged.get("gewerk") or "",
        "estimated_value": merged.get("estimated_value"),
        "search_term": term,
        "woodpellet_check": classification,
        "source": "Vergabeweiser"
    }


# ---------------------------------------
# 1. SUCHEN
# ---------------------------------------

print("HOLZPELLETS-RADAR 3.0")
print("Starte die Suche in fünf Bundesländern.")
print("--------------------------------")

for state, slug in STATES.items():

    for term in SEARCH_TERMS:

        print(f"Suche: {state} – {term}")

        for page in range(1, MAX_PAGES + 1):

            try:
                data = get_json(
                    f"{API}/tenders",
                    params={
                        "was": term,
                        "land": slug,
                        "status": "offen",
                        "sort": "neu",
                        "seite": page
                    }
                )

                total = data.get("total", 0)
                results = data.get("results", [])

                print(
                    f"{state} / {term} / Seite {page}: "
                    f"{len(results)} Ergebnisse, "
                    f"gesamt laut API: {total}"
                )

                search_stats.append({
                    "state": state,
                    "term": term,
                    "page": page,
                    "total": total,
                    "received": len(results)
                })

                for item in results:

                    tender_id = item.get("id")

                    if tender_id:
                        candidates[str(tender_id)] = {
                            "item": item,
                            "state": state,
                            "term": term
                        }

                    else:
                        print(
                            "Hinweis: Ausschreibung ohne ID:",
                            item.get("title")
                        )

                # Keine weiteren Seiten erforderlich
                if page >= min(
                    data.get("pages", 1),
                    MAX_PAGES
                ):
                    break

                time.sleep(PAUSE)

            except Exception as error:
                errors.append(
                    f"Suche {state} / {term} / Seite "
                    f"{page}: {str(error)}"
                )

                print("Suchfehler:", error)
                break


# ---------------------------------------
# 2. DETAILDATEN ABRUFEN
# ---------------------------------------

print("--------------------------------")
print("Rufe ausführliche Ausschreibungen ab.")

all_results = []

detail_count = 0
detail_errors = 0

for tender_id, candidate in candidates.items():

    if detail_count >= MAX_DETAIL_REQUESTS:
        errors.append(
            "Maximale Zahl der Detailabrufe erreicht."
        )
        break

    item = candidate["item"]
    state = candidate["state"]
    term = candidate["term"]

    try:
        detail = get_json(
            f"{API}/tenders/{tender_id}"
        )

        # Falls die API die Daten verschachtelt liefert
        if isinstance(detail.get("tender"), dict):
            detail = detail["tender"]

        elif isinstance(detail.get("data"), dict):
            detail = detail["data"]

        detail_count += 1

        result = extract_result(
            item,
            detail,
            state,
            term
        )

        if result:
            all_results.append(result)

            print(
                "Treffer:",
                state,
                result["woodpellet_check"],
                result["title"]
            )

    except Exception as error:

        detail_errors += 1

        errors.append(
            f"Detail {tender_id}: {str(error)}"
        )

        print(
            "Detailfehler:",
            tender_id,
            error
        )

    time.sleep(PAUSE)


# ---------------------------------------
# 3. DOPPELTE ENTFERNEN
# ---------------------------------------

unique = {}

for item in all_results:

    key = (
        str(item.get("id"))
        or item.get("url")
        or (
            item.get("state", "")
            + item.get("title", "")
        )
    )

    if key not in unique:
        unique[key] = item

    elif (
        item["woodpellet_check"]
        == "Holzpellets eindeutig erkannt"
    ):
        unique[key]["woodpellet_check"] = (
            "Holzpellets eindeutig erkannt"
        )

results = list(unique.values())

results.sort(
    key=lambda x: x.get("published") or "",
    reverse=True
)


# ---------------------------------------
# 4. NACH BUNDESLAND SORTIEREN
# ---------------------------------------

for state in STATES:

    state_results = [
        item for item in results
        if item["state"] == state
    ]

    print("--------------------------------")
    print(state)
    print("Gefundene Treffer:", len(state_results))

    for item in state_results:
        print(
            item["woodpellet_check"],
            "-",
            item["title"]
        )


# ---------------------------------------
# 5. ERGEBNISSE SPEICHERN
# ---------------------------------------

DATA_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

confirmed = sum(
    1 for item in results
    if item["woodpellet_check"]
    == "Holzpellets eindeutig erkannt"
)

review = len(results) - confirmed

snapshot = {
    "updated_at": datetime.now(
        ZoneInfo("Europe/Berlin")
    ).isoformat(timespec="seconds"),

    "results": results,

    "errors": errors,

    "search_stats": search_stats,

    "statistics": {
        "states": len(STATES),
        "search_terms": len(SEARCH_TERMS),
        "search_requests": len(search_stats),
        "candidates": len(candidates),
        "detail_requests": detail_count,
        "detail_errors": detail_errors,
        "total_results": len(results),
        "confirmed_woodpellets": confirmed,
        "manual_review": review
    }
}

DATA_FILE.write_text(
    json.dumps(
        snapshot,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)


# ---------------------------------------
# 6. ABSCHLUSSMELDUNG
# ---------------------------------------

print("--------------------------------")
print("HOLZPELLETS-RADAR ABGESCHLOSSEN")
print("--------------------------------")

print("Suchanfragen:", len(search_stats))
print("Gefundene Kandidaten:", len(candidates))
print("Detailabrufe:", detail_count)

print("Holzpellets eindeutig:", confirmed)
print("Manuelle Prüfung:", review)

print("Fehler:", len(errors))

if errors:
    print("HINWEIS: Suche möglicherweise unvollständig.")
else:
    print("Alle ausgeführten Abfragen abgeschlossen.")

print("Ergebnisse gespeichert:", DATA_FILE)
print("--------------------------------")
