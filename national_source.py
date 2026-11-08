"""Importiert passende Bekanntmachungen aus dem CSV-OpenData-Export."""
import csv
import io
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

API_URL = "https://oeffentlichevergabe.de/api/notice-exports"
STATE_PREFIXES = {
    "DE4": "Brandenburg",
    "DE8": "Mecklenburg-Vorpommern",
    "DED": "Sachsen",
    "DEE": "Sachsen-Anhalt",
    "DEG": "Thüringen",
}
SEARCH_PATTERN = re.compile(
    r"holz[\s-]*pellet(?:s)?|pelletlieferung|pellets?\b|"
    r"holzhack(?:schnitzel)?|hackschnitzel|holzbrennstoff|"
    r"brennstoffe auf holzbasis|\bbks\b|braunkohlestaub|"
    r"braunkohle|steinkohle|\bkohle\b|briketts?\b",
    re.IGNORECASE,
)


def _read_table(archive, filename):
    try:
        raw = archive.read(filename)
    except KeyError:
        return []
    text = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig", newline="")
    return list(csv.DictReader(text))


def _join_key(row):
    return (str(row.get("noticeIdentifier", "")).strip(),
            str(row.get("noticeVersion", "")).strip())


def _text(value):
    return str(value or "").strip()


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


def fetch_national_notices(publication_day=None):
    """Lädt CSV-Export eines Veröffentlichungstags (Standard: Vortag)."""
    day = (
        datetime.now(ZoneInfo("Europe/Berlin")).date() - timedelta(days=1)
        if publication_day is None
        else datetime.fromisoformat(str(publication_day)).date()
    )
    response = requests.get(
        API_URL,
        params={"pubDay": day.isoformat(), "format": "csv.zip"},
        timeout=(20, 180),
    )
    response.raise_for_status()
    if not response.content.startswith(b"PK"):
        raise ValueError("Bekanntmachungsservice lieferte keine gültige ZIP-Datei.")

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        notices = _read_table(archive, "notice.csv")
        purposes = _read_table(archive, "purpose.csv")
        organisations = _read_table(archive, "organisation.csv")
        places = _read_table(archive, "placeOfPerformance.csv")
        classifications = _read_table(archive, "classification.csv")
        submissions = _read_table(archive, "submissionTerms.csv")

    def group(rows):
        result = defaultdict(list)
        for row in rows:
            result[_join_key(row)].append(row)
        return result

    purpose_by = group(purposes)
    org_by = group(organisations)
    place_by = group(places)
    class_by = group(classifications)
    submission_by = group(submissions)

    found = {}
    stats = {"publication_day": day.isoformat(), "notices_in_export": len(notices),
             "matched_keyword": 0, "matched_state": 0, "results": 0}
    for notice in notices:
        key = _join_key(notice)
        p_rows = purpose_by.get(key, [])
        o_rows = org_by.get(key, [])
        pl_rows = place_by.get(key, [])
        c_rows = class_by.get(key, [])
        s_rows = submission_by.get(key, [])

        title = " | ".join(dict.fromkeys(_text(r.get("title")) for r in p_rows if _text(r.get("title"))))
        description = " | ".join(dict.fromkeys(_text(r.get("description")) for r in p_rows if _text(r.get("description"))))
        buyer_rows = [r for r in o_rows if _text(r.get("organisationRole")).lower() == "buyer"]
        buyer = buyer_rows[0] if buyer_rows else {}
        cpv_codes = []
        for row in c_rows:
            if _text(row.get("classificationType")).lower() == "cpv":
                cpv_codes.extend(x.strip() for x in (
                    _text(row.get("mainClassificationCode")) + "," +
                    _text(row.get("additionalClassificationCodes"))
                ).split(",") if x.strip())

        search_text = " ".join((title, description, _text(notice.get("noticeType"))))
        if not SEARCH_PATTERN.search(search_text):
            continue
        stats["matched_keyword"] += 1

        state = None
        place = ""
        for row in pl_rows:
            code = _text(row.get("placePerformanceCountrySubdivision")).upper()
            state = next((name for prefix, name in STATE_PREFIXES.items()
                          if code.startswith(prefix)), None)
            if state:
                place = " ".join(filter(None, (
                    _text(row.get("placePerformancePostCode")),
                    _text(row.get("placePerformanceCity")),
                )))
                break
        if not state:
            for row in o_rows:
                code = _text(row.get("organisationCountrySubdivision")).upper()
                state = next((name for prefix, name in STATE_PREFIXES.items()
                              if code.startswith(prefix)), None)
                if state:
                    place = _text(row.get("organisationCity"))
                    break
        if not state:
            continue
        stats["matched_state"] += 1

        category = _category(search_text, cpv_codes)
        if not category:
            continue

        notice_id = _text(notice.get("noticeIdentifier"))
        version = _text(notice.get("noticeVersion"))
        url = "https://oeffentlichevergabe.de/ui/de/search/details?noticeId=" + notice_id
        estimate = next((_text(r.get("estimatedValue")) for r in p_rows if _text(r.get("estimatedValue"))), "")
        deadline = next((_text(r.get("tenderValidityDeadline")) for r in s_rows if _text(r.get("tenderValidityDeadline"))), "")
        record = {
            "id": notice_id,
            "state": state,
            "title": title or "Ausschreibung ohne Titel",
            "original_title": title,
            "buyer": _text(buyer.get("organisationName")),
            "place": place or state,
            "deadline": deadline,
            "published": _text(notice.get("publicationDate")) or day.isoformat(),
            "url": url,
            "documents_url": "",
            "notice_url": url,
            "description": description,
            "cpv": ", ".join(sorted(set(cpv_codes))),
            "gewerk": "",
            "estimated_value": estimate,
            "search_term": "Bekanntmachungsservice OpenData",
            "woodpellet_check": category,
            "source": "Bekanntmachungsservice",
            "notice_version": version,
            "notice_tag": _text(notice.get("noticeType")),
        }
        previous = found.get(notice_id)
        if previous is None or version >= previous.get("notice_version", ""):
            found[notice_id] = record

    stats["results"] = len(found)
    return list(found.values()), stats
