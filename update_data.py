
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
PAUSE = 1.0

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


def request_json(url, params=None, max_retries=4):
    """Request JSON with bounded backoff for rate limits and transient server errors."""
    for attempt in range(max_retries + 1):
        response = session.get(
            url,
            params=params,
            timeout=45
        )
        if response.status_code == 429 or response.status_code in (500, 502, 503, 504):
            if attempt >= max_retries:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After", "")
            try:
                wait_seconds = float(retry_after)
            except (TypeError, ValueError):
                wait_seconds = min(2 ** attempt, 30)
            time.sleep(max(1, min(wait_seconds, 60)))
            continue
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

                # Pace every search request, including the last page of each term.
                time.sleep(PAUSE)

                if page >= data.get("pages", 1):
                    break

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
# 3. OFFIZIELLER BEKANNTMACHUNGSSERVICE
# =====================================

national_stats = {"results": 0, "publication_day": None, "errors": []}

try:
    from national_source import fetch_national_notices

    national_results, source_stats = fetch_national_notices()
    national_stats.update(source_stats)
    national_stats["results"] = len(national_results)

    # Bestehende Treffer nicht überschreiben; dubbele Notice-IDs vermeiden.
    existing_ids = {str(item.get("id")) for item in results.values()}
    for item in national_results:
        item_id = str(item.get("id"))
        if item_id not in existing_ids:
            results["national-" + item_id] = item
            existing_ids.add(item_id)

    for source_error in national_stats.get("errors", []):
        errors.append(f"Bekanntmachungsservice: {source_error}")

    print(
        "Bekanntmachungsservice:",
        len(national_results),
        "passende Treffer für",
        national_stats["publication_day"]
    )
except Exception as error:
    message = f"Bekanntmachungsservice: {error}"
    national_stats["errors"].append(message)
    errors.append(message)
    print("Fehler beim Bekanntmachungsservice:", error)


# =====================================
# 4. TED ALS ZUSÄTZLICHE DATENQUELLE
# =====================================

ted_stats = {"results": 0, "errors": []}

try:
    from ted_source import fetch_ted_notices

    ted_results, source_stats = fetch_ted_notices(days_back=60)
    ted_stats.update(source_stats)
    ted_stats["results"] = len(ted_results)

    for source_error in ted_stats.get("errors", []):
        errors.append(f"TED: {source_error}")

    existing_ids = {str(item.get("id")) for item in results.values()}
    for item in ted_results:
        item_id = str(item.get("id"))
        if item_id not in existing_ids:
            results["ted-" + item_id] = item
            existing_ids.add(item_id)

    print("TED:", len(ted_results), "passende Treffer")
except Exception as error:
    message = f"TED: {error}"
    ted_stats["errors"].append(message)
    errors.append(message)
    print("Fehler bei TED:", error)


# =====================================
# 5. QUELLENÜBERGREIFENDE DUBLETTEN PRÜFEN
# =====================================

import unicodedata

def duplicate_key(item):
    """Conservative fingerprint: same state, normalized title and buyer."""
    def normalize(value):
        value = unicodedata.normalize("NFKD", str(value or "").casefold())
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        value = re.sub(r"[^a-z0-9]+", " ", value)
        return " ".join(value.split())

    title = normalize(item.get("title") or item.get("original_title"))
    buyer = normalize(item.get("buyer"))
    state = normalize(item.get("state"))
    # Without both a meaningful title and buyer, do not risk false merges.
    if len(title) < 18 or not buyer or not state:
        return None
    return state, title, buyer

deduplicated = {}
fingerprints = {}
duplicate_count = 0

for item in results.values():
    key = duplicate_key(item)
    if key is None or key not in fingerprints:
        deduplicated_key = str(item.get("source", "")) + "-" + str(item.get("id", ""))
        deduplicated[deduplicated_key] = item
        if key is not None:
            fingerprints[key] = deduplicated_key
        continue

    duplicate_count += 1
    primary = deduplicated[fingerprints[key]]
    sources = set(primary.get("also_found_in", []))
    sources.add(str(item.get("source", "")))
    primary["also_found_in"] = sorted(x for x in sources if x)
    ids = set(primary.get("source_ids", []))
    ids.add(f"{item.get('source')}:{item.get('id')}")
    ids.add(f"{primary.get('source')}:{primary.get('id')}")
    primary["source_ids"] = sorted(x for x in ids if x)

results = deduplicated

# =====================================
# 6. SORTIEREN
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
        "cross_source_duplicates_merged": duplicate_count,
        "confirmed_woodpellets": confirmed,
        "cpv_wood_fuels": cpv_results,
        "manual_review": review,
        "other_fuels_bks_coal_briquettes": other_fuels,
        "errors": len(errors),
        "national_source_results": national_stats["results"],
        "national_source_publication_day": national_stats["publication_day"],
        "ted_source_results": ted_stats["results"],
        "ted_source_since": ted_stats.get("since"),
        "ted_source_queries": ted_stats.get("queries", 0),
        "ted_source_raw_notices": ted_stats.get("raw_notices", 0),
        "ted_source_errors": len(ted_stats.get("errors", []))
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
