"""Importer for the German Bekanntmachungsservice Open Data export.

The official export is a daily ZIP. This first integration consumes the OCDS JSON
variant and deliberately fails independently from the existing Vergabeweiser feed.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

EXPORT_URL = "https://oeffentlichevergabe.de/api/notice-exports"
STATE_CODES = {
    "Brandenburg": ("DE40", "DE4"),
    "Mecklenburg-Vorpommern": ("DE80", "DE8"),
    "Sachsen": ("DED",),
    "Sachsen-Anhalt": ("DEE",),
    "Thüringen": ("DEG",),
}
TERMS = re.compile(
    r"holz[\\s-]*pellet|pellet|holz[\\s-]*hack[\\s-]*schnitzel|"
    r"hackschnitzel|holzbrennstoff|brennstoff.*holzbasis|"
    r"bks|braunkohlestaub|braunkohle|steinkohle|\\bkohle\\b|briketts?",
    re.IGNORECASE,
)


def _flatten(value):
    if isinstance(value, dict):
        return " ".join(_flatten(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_flatten(v) for v in value)
    if isinstance(value, (str, int, float)):
        return str(value)
    return ""


def _first(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _state_for(release):
    text = _flatten(release).upper()
    for state, codes in STATE_CODES.items():
        if any(re.search(r"(?<![A-Z0-9])" + re.escape(code) + r"(?![A-Z0-9])", text) for code in codes):
            return state
    # Some notices expose the federal state as a plain-language region.
    plain = _flatten(release).casefold()
    for state in STATE_CODES:
        if state.casefold() in plain:
            return state
    return None


def _category(text, cpv_text):
    low = text.casefold()
    cpv = re.sub(r"\\D", "", cpv_text)
    if re.search(r"holz[\\s-]*pellet|pellet[\\s-]*holz|wood[\\s-]*pellet", low):
        return "Holzpellets eindeutig"
    if cpv.startswith("09111400"):
        return "Holzbrennstoff – CPV 09111400"
    if re.search(r"holz[\\s-]*hack[\\s-]*schnitzel|hackschnitzel", low):
        return "Holzhackschnitzel – prüfen"
    if re.search(r"holzbrennstoff|brennstoff.*holzbasis|holzbriketts?", low):
        return "Sonstiger Holzbrennstoff"
    if re.search(r"\\bbks\\b|braunkohlestaub|braunkohle|steinkohle|\\bkohle\\b|briketts?", low):
        return "BKS / Kohle / Briketts"
    if "pellet" in low:
        return "Pellets – Holzart prüfen"
    return None


def fetch_notices(timeout=90):
    """Return matching notice records and diagnostic metadata for yesterday."""
    yesterday = (datetime.now(ZoneInfo("Europe/Berlin")).date() - timedelta(days=1))
    day = yesterday.isoformat()
    response = requests.get(
        EXPORT_URL,
        params={"pubDay": day, "format": "ocds.zip"},
        headers={"Accept": "application/zip", "User-Agent": "Pellet-Kohle-Radar/1.0"},
        timeout=timeout,
    )
    response.raise_for_status()
    if not response.content.startswith(b"PK"):
        raise ValueError(
            "Bekanntmachungsservice lieferte keine ZIP-Datei "
            f"(Content-Type: {response.headers.get('Content-Type', 'unbekannt')})."
        )

    records = {}
    releases_seen = 0
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        for name in archive.namelist():
            if name.endswith("/") or not name.lower().endswith(".json"):
                continue
            payload = json.loads(archive.read(name).decode("utf-8-sig"))
            releases = payload.get("releases", []) if isinstance(payload, dict) else []
            for release in releases:
                releases_seen += 1
                # Avoid award/planning-only records; keep tender notices.
                tags = release.get("tag", [])
                if tags and not any("tender" in str(tag).casefold() for tag in tags):
                    continue
                state = _state_for(release)
                if not state:
                    continue
                tender = release.get("tender") or {}
                title = _first(tender.get("title"), release.get("title"), "Ausschreibung ohne Titel")
                description = _first(tender.get("description"), release.get("description"))
                items = tender.get("items") or []
                cpv_parts = []
                item_text = []
                for item in items:
                    item_text.append(_flatten(item))
                    classification = item.get("classification") or {}
                    if classification.get("id"):
                        cpv_parts.append(str(classification["id"]))
                    for additional in item.get("additionalClassifications") or []:
                        if additional.get("id"):
                            cpv_parts.append(str(additional["id"]))
                combined_text = " ".join([title, description, _flatten(tender.get("items")), _flatten(tender.get("lots"))])
                category = _category(combined_text, " ".join(cpv_parts))
                if not category or not TERMS.search(combined_text + " " + " ".join(cpv_parts)):
                    continue

                parties = release.get("parties") or []
                buyer = ""
                for party in parties:
                    if "buyer" in (party.get("roles") or []):
                        buyer = _first(party.get("name"))
                        break
                tender_period = tender.get("tenderPeriod") or {}
                notice_id = _first(release.get("id"), payload.get("id") if isinstance(payload, dict) else "")
                if not notice_id:
                    notice_id = name
                record_id = "bkms-" + str(notice_id)
                records[record_id] = {
                    "id": record_id,
                    "state": state,
                    "title": title,
                    "original_title": title,
                    "buyer": buyer,
                    "place": state,
                    "deadline": _first(tender_period.get("endDate")),
                    "published": _first(release.get("date"), day),
                    "url": "",
                    "documents_url": "",
                    "notice_url": "",
                    "description": description,
                    "cpv": ", ".join(sorted(set(cpv_parts))),
                    "gewerk": "",
                    "estimated_value": (tender.get("value") or {}).get("amount"),
                    "search_term": "Bekanntmachungsservice Open Data",
                    "woodpellet_check": category,
                    "source": "Bekanntmachungsservice",
                }

    return list(records.values()), {
        "publication_day": day,
        "releases_seen": releases_seen,
        "matching_notices": len(records),
    }
