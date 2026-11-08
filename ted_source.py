"""TED Search API importer for German wood-fuel tenders in five eastern states.

TED publishes EU-threshold procurement notices. Search is anonymous and read-only.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
import time
import requests

API_URL = "https://api.ted.europa.eu/v3/notices/search"
STATE_PREFIXES = {
    "DE4": "Brandenburg",
    "DE8": "Mecklenburg-Vorpommern",
    "DED": "Sachsen",
    "DEE": "Sachsen-Anhalt",
    "DEG": "Thüringen",
}
SEARCH_PHRASES = (
    "wood pellets",
    "pellets",
    "wood chips",
    "wood briquettes",
    "wood fuel",
    "wood fuels",
    "Holzpellets",
    "Holzhackschnitzel",
    "Holzbriketts",
    "Holzbrennstoff",
)
CPV_CODES = ("09111400", "03413000")
FIELDS = [
    "publication-number",
    "publication-date",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "classification-cpv",
    "place-of-performance",
    "deadline-receipt-tender-date-lot",
    "description-glo",
]


def _lang(value):
    if isinstance(value, dict):
        value = value.get("deu") or value.get("eng") or next(iter(value.values()), "")
    if isinstance(value, list):
        return " ".join(str(x) for x in value if x)
    return str(value or "")


def _state_from_nuts(values):
    if isinstance(values, str):
        values = [values]
    for value in values or []:
        code = str(value).upper()
        for prefix, state in STATE_PREFIXES.items():
            if code.startswith(prefix):
                return state
    return None


def _category(text, cpv):
    t = text.lower()
    if re.search(r"holz[\s-]*pellet|pellet[\s-]*holz|wood[\s-]*pellet", t):
        return "Holzpellets eindeutig"
    if any(str(code).startswith("09111400") for code in cpv):
        return "Holzbrennstoff – CPV 09111400"
    if re.search(r"holz[\s-]*hack[\s-]*schnitzel|wood[\s-]*chips|hackschnitzel", t):
        return "Holzhackschnitzel – prüfen"
    if re.search(r"holzbrikett|wood[\s-]*briquette|holzbrennstoff|wood[\s-]*fuel", t):
        return "Sonstiger Holzbrennstoff"
    if re.search(r"\bbks\b|braunkohle|steinkohle|\bkohle\b", t):
        return "BKS / Kohle / Briketts"
    if "pellet" in t:
        return "Pellets – Holzart prüfen"
    return None


def _search(session, query, limit=100):
    body = {
        "query": query,
        "fields": FIELDS,
        "page": 1,
        "limit": limit,
        "paginationMode": "PAGE_NUMBER",
        "scope": "ALL",
    }
    response = session.post(API_URL, json=body, timeout=90)
    response.raise_for_status()
    payload = response.json()
    if payload.get("timedOut"):
        raise RuntimeError(f"TED search timed out for query: {query}")
    return payload.get("notices", [])


def fetch_ted_notices(days_back=60):
    """Fetch German TED notices and retain only the five target states."""
    since = (datetime.now(ZoneInfo("Europe/Berlin")).date()
             - timedelta(days=days_back)).strftime("%Y%m%d")
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Pellet-Kohle-Ausschreibungsradar/1.0",
    })

    candidates = {}
    stats = {
        "since": since,
        "queries": 0,
        "raw_notices": 0,
        "target_states": 0,
        "results": 0,
        "errors": [],
    }

    queries = [
        f'publication-date>={since} AND buyer-country=DEU AND FT~("{phrase}") SORT BY publication-number DESC'
        for phrase in SEARCH_PHRASES
    ]
    queries.extend(
        f"publication-date>={since} AND buyer-country=DEU AND classification-cpv={code} SORT BY publication-number DESC"
        for code in CPV_CODES
    )

    for query in queries:
        stats["queries"] += 1
        try:
            notices = _search(session, query)
            stats["raw_notices"] += len(notices)
            for notice in notices:
                number = str(notice.get("publication-number") or "").strip()
                if number:
                    candidates[number] = notice
        except Exception as exc:
            stats["errors"].append(f"{query}: {exc}")
        time.sleep(0.35)

    results = []
    for number, notice in candidates.items():
        place_codes = notice.get("place-of-performance") or []
        state = _state_from_nuts(place_codes)
        if not state:
            continue
        stats["target_states"] += 1

        title = _lang(notice.get("notice-title"))
        description = _lang(notice.get("description-glo"))
        buyer = _lang(notice.get("buyer-name"))
        cpv = notice.get("classification-cpv") or []
        if isinstance(cpv, str):
            cpv = [cpv]
        combined = " ".join((title, description))
        category = _category(combined, cpv)
        if not category:
            continue

        date = str(notice.get("publication-date") or "")[:10]
        deadline = notice.get("deadline-receipt-tender-date-lot") or []
        if isinstance(deadline, list):
            deadline = deadline[0] if deadline else ""
        results.append({
            "id": number,
            "state": state,
            "title": title or "TED-Ausschreibung ohne Titel",
            "original_title": title,
            "buyer": buyer,
            "place": ", ".join(str(x) for x in place_codes),
            "deadline": str(deadline or ""),
            "published": date,
            "url": f"https://ted.europa.eu/de/notice/-/detail/{number}",
            "documents_url": "",
            "notice_url": f"https://ted.europa.eu/de/notice/-/detail/{number}",
            "description": description,
            "cpv": ", ".join(sorted(set(str(x) for x in cpv))),
            "gewerk": "",
            "estimated_value": "",
            "search_term": "TED Search API",
            "woodpellet_check": category,
            "source": "TED",
        })

    stats["results"] = len(results)
    return results, stats
