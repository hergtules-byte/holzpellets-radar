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


def _category(title, description, cpv):
    """Nur belastbare Beschaffungssignale; Projekt- und Zufallsnennungen ausschließen."""
    title_text = str(title or "").lower()
    description_text = str(description or "").lower()
    cpv = [str(code) for code in (cpv or [])]
    if any(code.startswith("09111400") for code in cpv):
        return "Holzbrennstoff – CPV 09111400"
    if any(code.startswith("03413000") for code in cpv):
        return "Holzhackschnitzel – prüfen"
    project_terms = ("kesselanlage", "biomassekessel", "heizungsanlage",
        "pelletheizung", "pelletfeuerung", "wärmeerzeugung", "umstellung",
        "neubau", "sanierung", "installation", "montage", "errichtung")
    if any(term in title_text for term in project_terms):
        return None
    procurement = ("liefer", "beschaffung", "bedarf", "rahmenvereinbarung",
        "brennstoff", "versorgung", "abnahme")
    if re.search(r"holz[\s-]*pellet|pellet[\s-]*holz|wood[\s-]*pellet", title_text):
        if any(term in title_text for term in procurement) or any(
            term in description_text for term in ("liefer", "beschaffung", "bedarf", "brennstoff", "versorgung")
        ):
            return "Holzpellets eindeutig"
        return None
    if re.search(r"holz[\s-]*hack[\s-]*schnitzel|hackschnitzel|wood[\s-]*chips", title_text):
        if any(term in title_text + " " + description_text for term in procurement):
            return "Holzhackschnitzel – prüfen"
        return None
    if re.search(r"holzbrikett|wood[\s-]*briquette|holzbrennstoff|wood[\s-]*fuel", title_text):
        return "Sonstiger Holzbrennstoff"
    if re.search(r"\bbks\b|braunkohle|steinkohle|\bkohle\b", title_text):
        return "BKS / Kohle / Briketts"
    if "pellet" in title_text and any(term in title_text + " " + description_text for term in procurement):
        return "Pellets – Holzart prüfen"
    return None

def _search(session, query, limit=100, max_pages=50):
    """Fetch every TED page; never silently accept a truncated result set."""
    notices = []
    total = None
    for page in range(1, max_pages + 1):
        body = {"query": query, "fields": FIELDS, "page": page, "limit": limit,
                "paginationMode": "PAGE_NUMBER", "scope": "ALL"}
        for attempt in range(4):
            response = session.post(API_URL, json=body, timeout=90)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 3:
                    response.raise_for_status()
                try:
                    delay = float(response.headers.get("Retry-After", ""))
                except (TypeError, ValueError):
                    delay = 1.5 * (2 ** attempt)
                time.sleep(min(max(delay, 0.5), 20))
                continue
            response.raise_for_status()
            break
        payload = response.json()
        if payload.get("timedOut"):
            raise RuntimeError(f"TED search timed out for query: {query}")
        batch = payload.get("notices", [])
        notices.extend(batch)
        if total is None and payload.get("totalNoticeCount") is not None:
            total = int(payload["totalNoticeCount"])
        if not batch or len(batch) < limit or (total is not None and len(notices) >= total):
            return notices
        time.sleep(0.2)
    if total is None or len(notices) < total:
        raise RuntimeError(f"TED pagination limit reached: retrieved {len(notices)} of {total} notices")
    return notices


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
        category = _category(title, description, cpv)
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
