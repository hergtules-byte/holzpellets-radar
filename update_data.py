
import os
import re
import json
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

# =====================================
# KONFIGURATION
# =====================================

API = "https://vergabeweiser.de/api/v1"
DATA_FILE = Path("data/latest.json")

STATES = {
    "Brandenburg": "brandenburg",
    "Mecklenburg-Vorpommern": "mecklenburg-vorpommern",
    "Sachsen": "sachsen",
    "Sachsen-Anhalt": "sachsen-anhalt",
    "Thüringen": "thueringen"
}

# Breite Suche, damit keine relevanten Begriffe
# von vornherein ausgeschlossen werden.
SEARCH_TERMS = [
    "Holzpellets",
    "Holzpelletlieferung",
    "Pelletlieferung",
    "Pellets",
    "Holzhackschnitzel",
    "Holzbrennstoffe",
    "Brennstoffe auf Holzbasis",
    "Holz",
    # Zusätzliche Brennstoff-Suchbegriffe (getrennt von Holzpellets ausgewertet)
    "BKS",
    "Braunkohlestaub",
    "Kohle",
    "Briketts"
]

MAX_PAGES = 2
MAX_DETAIL_REQUESTS = 500
PAUSE = 0.25

CPV_WOOD_FUEL = "09111400"

api_key = os.environ.get("VERGABEWEISER_API_KEY")

if not api_key:
    raise RuntimeError(
        "GitHub Secret VERGABEWEISER_API_KEY fehlt."
    )

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {api_key}",
    "User-Agent": "Holzpellets-Radar/4.0",
    "Accept": "application/json"
})

candidates = {}
results = {}
errors = []
search_stats = []


# =====================================
# HILFSFUNKTIONEN
# =====================================

def flatten(value):
    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        return " ".join(
            flatten(v) for v in value.values()
        )

    if isinstance(value, list):
        return " ".join(
            flatten(v) for v in value
        )

    return ""


def get_value(value, *keys):
    if isinstance(value, dict):
        for key in keys:
            if value.get(key):
                return value[key]

    if value:
        return str(value)

    return ""


def request_json(url, params=None):
    response = session.get(
        url,
        params=params,
        timeout=45
    )
    response.raise_for_status()
    return response.json()


def classify(item, detail):

    combined = {}
    combined.update(item)
    combined.update(detail)

    title = (
        combined.get("title")
        or combined.get("original_title")
        or ""
    )

    original = combined.get("original_title") or ""
    description = combined.get("description") or ""

    # Alle Detailangaben untersuchen
    full_text = flatten(combined).lower()

    cpv_text = flatten(
        combined.get("cpv", "")
    )

    cpv_digits = re.sub(
        r"\D", "", cpv_text
    )

    # 1. Holzpellets eindeutig
    if re.search(
        r"holz[\s-]*pellet|pellet[\s-]*holz|wood[\s-]*pellet",
        full_text
    ):
        return "Holzpellets eindeutig", combined

    # 2. CPV-Code für Holzbrennstoffe
    if cpv_digits.startswith(CPV_WOOD_FUEL):
        return "Holzbrennstoff – CPV 09111400", combined

    # 3. Hackschnitzel
    if re.search(
        r"holz[\s-]*hack[\s-]*schnitzel|hackschnitzel",
        full_text
    ):
        return "Holzhackschnitzel – prüfen", combined

    # 4. Sonstige Holzbrennstoffe
    if re.search(
        r"holzbrennstoff|brennstoff.*holzbasis|"
        r"brennstoffe auf holzbasis|"
        r"holzbrikett|holzbriketts",
        full_text
    ):
        return "Sonstiger Holzbrennstoff", combined

    # 5. Fossile bzw. sonstige Brennstoffe separat erfassen.
    # Holzbriketts wurden oben bereits als Holzbrennstoff eingeordnet.
    if re.search(
        r"\bbks\b|braunkohlestaub|braunkohle|steinkohle|"
        r"\bkohle\b|briketts?",
        full_text
    ):
        return "BKS / Kohle / Briketts", combined

    # 6. Allgemeine Pellets
    if "pellet" in full_text:
        return "Pellets – Holzart prüfen", combined

    return None, combined


# =====================================
# 1. AUSSCHREIBUNGEN SUCHEN
# =====================================

print("HOLZPELLETS-RADAR 4.0")
print("Suche in fünf Bundesländern")
print("--------------------------------")

for state, slug in STATES.items():

    for term in SEARCH_TERMS:

        print(f"Suche: {state} – {term}")

        for page in range(1, MAX_PAGES + 1):

            try:
                data = request_json(
                    f"{API}/tenders",
                    params={
                        "was": term,
                        "land": slug,
                        "status": "offen",
                        "sort": "neu",
                        "seite": page
                    }
                )

                entries = data.get("results", [])

                search_stats.append({
                    "state": state,
                    "term": term,
                    "page": page,
                    "total": data.get("total", 0),
                    "received": len(entries)
                })

                print(
                    f"  Seite {page}: "
                    f"{len(entries)} Ergebnisse"
                )

                for entry in entries:

                    tender_id = entry.get("id")

                    if tender_id:
                        key = str(tender_id)

                        if key not in candidates:
                            candidates[key] = {
                                "item": entry,
                                "state": state,
                                "term": term
                            }

                if page >= data.get("pages", 1):
                    break

                time.sleep(PAUSE)

            except Exception as error:
                errors.append(
                    f"{state} / {term}: {error}"
                )
                print("Suchfehler:", error)
                break


# =====================================
# 2. DETAILDATEN ABRUFEN
# =====================================

print("--------------------------------")
print("Prüfe vollständige Ausschreibungen")

detail_count = 0

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
        detail = request_json(
            f"{API}/tenders/{tender_id}"
        )

        if isinstance(detail.get("tender"), dict):
            detail = detail["tender"]

        elif isinstance(detail.get("data"), dict):
            detail = detail["data"]

        detail_count += 1

        category, combined = classify(item, detail)

        if not category:
            continue

        buyer = combined.get("buyer") or {}
        place = combined.get("place") or {}
        deadline = combined.get("deadline") or {}

        result = {
            "id": tender_id,
            "state": state,
            "title": (
                combined.get("title")
                or combined.get("original_title")
                or "Ausschreibung"
            ),
            "original_title": (
                combined.get("original_title") or ""
            ),
            "buyer": get_value(buyer, "name"),
            "place": (
                get_value(place, "text", "city")
                or state
            ),
            "deadline": get_value(deadline, "label"),
            "published": (
                combined.get("published_on") or ""
            ),
            "url": combined.get("url") or "",
            "documents_url": (
                combined.get("documents_url") or ""
            ),
            "notice_url": (
                combined.get("notice_url") or ""
            ),
            "description": (
                combined.get("description") or ""
            ),
            "cpv": flatten(
                combined.get("cpv", "")
            ),
            "gewerk": (
                combined.get("gewerk") or ""
            ),
            "estimated_value": (
                combined.get("estimated_value")
            ),
            "search_term": term,
            "woodpellet_check": category,
            "source": "Vergabeweiser"
        }

        results[tender_id] = result

        print(
            "TREFFER:",
            state,
            category,
            result["title"]
        )

    except Exception as error:
        errors.append(
            f"Detail {tender_id}: {error}"
        )
        print("Detailfehler:", tender_id, error)

    time.sleep(PAUSE)


# =====================================
# 3. SORTIEREN
# =====================================

all_results = list(results.values())

all_results.sort(
    key=lambda x: x.get("published") or "",
    reverse=True
)

# =====================================
# 4. BUNDESLÄNDER AUSWERTEN
# =====================================

for state in STATES:

    state_results = [
        r for r in all_results
        if r["state"] == state
    ]

    print("--------------------------------")
    print(state)
    print("Treffer:", len(state_results))

    for result in state_results:
        print(
            result["woodpellet_check"],
            result["title"]
        )


# =====================================
# 5. STATISTIK
# =====================================

confirmed = sum(
    1 for r in all_results
    if r["woodpellet_check"] == "Holzpellets eindeutig"
)

cpv_results = sum(
    1 for r in all_results
    if r["woodpellet_check"] == "Holzbrennstoff – CPV 09111400"
)

review = sum(
    1 for r in all_results
    if r["woodpellet_check"] not in [
        "Holzpellets eindeutig",
        "Holzbrennstoff – CPV 09111400"
    ]
)

other_fuels = sum(
    1 for r in all_results
    if r["woodpellet_check"] == "BKS / Kohle / Briketts"
)


# =====================================
# 6. SPEICHERN
# =====================================

DATA_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

snapshot = {
    "updated_at": datetime.now(
        ZoneInfo("Europe/Berlin")
    ).isoformat(timespec="seconds"),

    "results": all_results,

    "errors": errors,

    "search_stats": search_stats,

    "statistics": {
        "states": len(STATES),
        "search_terms": len(SEARCH_TERMS),
        "search_requests": len(search_stats),
        "candidates": len(candidates),
        "detail_requests": detail_count,
        "total_results": len(all_results),
        "confirmed_woodpellets": confirmed,
        "cpv_wood_fuels": cpv_results,
        "manual_review": review,
        "other_fuels_bks_coal_briquettes": other_fuels,
        "errors": len(errors)
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


# =====================================
# 7. ABSCHLUSS
# =====================================

print("--------------------------------")
print("HOLZPELLETS-RADAR ABGESCHLOSSEN")
print("--------------------------------")

print("Suchanfragen:", len(search_stats))
print("Kandidaten:", len(candidates))
print("Detailabrufe:", detail_count)
print("Holzpellets:", confirmed)
print("CPV-Holzbrennstoffe:", cpv_results)
print("Weitere Prüftreffer:", review)
print("Fehler:", len(errors))

if errors:
    print("WARNUNG: Suche möglicherweise unvollständig.")
else:
    print("Alle ausgeführten Abfragen abgeschlossen.")

print("Gespeichert:", DATA_FILE)
