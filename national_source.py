"""Abruf und Auswertung des offiziellen Bekanntmachungsservice OpenData-Exports."""
import io
import json
import re
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

API_URL = "https://oeffentlichevergabe.de/api/notice-exports"
STATE_PREFIXES = {
    "Brandenburg": ("DE4",),
    "Mecklenburg-Vorpommern": ("DE8",),
    "Sachsen": ("DED",),
    "Sachsen-Anhalt": ("DEE",),
    "Thüringen": ("DEG",),
}
STATE_NAMES = {
    "brandenburg": "Brandenburg",
    "mecklenburg-vorpommern": "Mecklenburg-Vorpommern",
    "mecklenburg vorpommern": "Mecklenburg-Vorpommern",
    "sachsen": "Sachsen",
    "sachsen-anhalt": "Sachsen-Anhalt",
    "sachsen anhalt": "Sachsen-Anhalt",
    "thüringen": "Thüringen",
    "thueringen": "Thüringen",
}
SEARCH_TERMS = (
    "holzpellet", "pelletlieferung", "pellets", "holzhackschnitzel",
    "holzbrennstoff", "brennstoffe auf holzbasis", "bks",
    "braunkohlestaub", "braunkohle", "steinkohle", "kohle", "brikett",
)


def _flatten(value):
    if isinstance(value, dict):
        return " ".join(_flatten(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_flatten(v) for v in value)
    if isinstance(value, (str, int, float)):
        return str(value)
    return ""


def _find_state(release, combined_text):
    # Erst explizite Bundeslandangaben aus Orts-/Adressdaten auswerten.
    lowered = combined_text.lower()
    for needle, state in STATE_NAMES.items():
        if re.search(r"(?<![a-zäöü])" + re.escape(needle) + r"(?![a-zäöü])", lowered):
            return state

    # NUTS-1-Codes der fünf Länder.
    upper = combined_text.upper()
    for state, prefixes in STATE_PREFIXES.items():
        if any(re.search(r"(?<![A-Z0-9])" + p + r"[A-Z0-9]{0,2}", upper) for p in prefixes):
            return state
    return None


def _category(text, cpv_codes):
    t = text.lower()
    if re.search(r"holz[\s-]*pellet|pellet[\s-]*holz|wood[\s-]*pellet", t):
        return "Holzpellets eindeutig"
    if any(str(code).startswith("09111400") for code in cpv_codes):
        return "Holzbrennstoff – CPV 09111400"
    if re.search(r"holz[\s-]*hack[\s-]*schnitzel|hackschnitzel", t):
        return "Holzhackschnitzel – prüfen"
    if re.search(r"holzbrennstoff|brennstoffe auf holzbasis|holzbriketts?", t):
        return "Sonstiger Holzbrennstoff"
    if re.search(r"\bbks\b|braunkohlestaub|braunkohle|steinkohle|\bkohle\b|briketts?", t):
        return "BKS / Kohle / Briketts"
    if "pellet" in t:
        return "Pellets – Holzart prüfen"
    return None


def fetch_national_notices():
    """Lädt den vollständigen Vortagesexport und gibt passende Treffer zurück."""
    yesterday = (datetime.now(ZoneInfo("Europe/Berlin")).date() - timedelta(days=1))
    params = {"pubDay": yesterday.isoformat(), "format": "ocds.zip"}
    response = requests.get(API_URL, params=params, timeout=(20, 180))
    response.raise_for_status()

    if not response.content.startswith(b"PK"):
        raise ValueError("Der Bekanntmachungsservice hat keine gültige ZIP-Datei geliefert.")

    found = {}
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        for filename in archive.namelist():
            if filename.endswith("/") or not filename.lower().endswith(".json"):
                continue
            try:
                payload = json.loads(archive.read(filename))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            releases = payload.get("releases", []) if isinstance(payload, dict) else []
            for release in releases:
                if not isinstance(release, dict):
                    continue
                tags = release.get("tag") or []
                # Zuschlags-/Ergebnisbekanntmachungen sind keine offenen Verkaufschancen.
                if tags and "tender" not in tags and "planning" not in tags:
                    continue

                tender = release.get("tender") or {}
                parties = release.get("parties") or []
                buyer = next(
                    (p for p in parties if "buyer" in (p.get("roles") or [])),
                    {},
                )
                title = tender.get("title") or ""
                description = tender.get("description") or ""
                item_text = _flatten(tender.get("items") or [])
                cpv_codes = []
                for item in tender.get("items") or []:
                    classification = item.get("classification") or {}
                    code = classification.get("id")
                    if code:
                        cpv_codes.append(str(code))

                full_text = " ".join((title, description, item_text, _flatten(tender), _flatten(buyer)))
                if not any(term in full_text.lower() for term in SEARCH_TERMS):
                    continue

                state = _find_state(release, " ".join((_flatten(tender), _flatten(buyer))))
                if not state:
                    continue

                category = _category(full_text, cpv_codes)
                if not category:
                    continue

                notice_id = str(release.get("id") or payload.get("id") or filename)
                version = str(release.get("version") or "")
                dedupe_key = notice_id
                url = (
                    "https://oeffentlichevergabe.de/ui/de/search/details?noticeId="
                    + notice_id
                )
                buyer_address = buyer.get("address") or {}
                place = tender.get("items") or []
                location_text = _flatten(place) or _flatten(buyer_address)

                record = {
                    "id": notice_id,
                    "state": state,
                    "title": title or "Ausschreibung ohne Titel",
                    "original_title": title,
                    "buyer": buyer.get("name") or "",
                    "place": location_text[:300] or state,
                    "deadline": "",
                    "published": release.get("date") or yesterday.isoformat(),
                    "url": url,
                    "documents_url": "",
                    "notice_url": url,
                    "description": description,
                    "cpv": ", ".join(sorted(set(cpv_codes))),
                    "gewerk": "",
                    "estimated_value": (tender.get("value") or {}).get("amount"),
                    "search_term": "Bekanntmachungsservice OpenData",
                    "woodpellet_check": category,
                    "source": "Bekanntmachungsservice",
                    "notice_version": version,
                    "notice_tag": ", ".join(tags),
                }
                # Bei mehreren Versionen derselben Bekanntmachung die letzte behalten.
                previous = found.get(dedupe_key)
                if previous is None or version >= previous.get("notice_version", ""):
                    found[dedupe_key] = record

    return list(found.values()), yesterday.isoformat()
