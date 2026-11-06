
import json
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st

st.set_page_config(
    page_title="Holzpellets-Radar",
    page_icon="🌲",
    layout="wide"
)

STATES = {
    "Brandenburg": "brandenburg",
    "Mecklenburg-Vorpommern": "mecklenburg-vorpommern",
    "Sachsen": "sachsen",
    "Sachsen-Anhalt": "sachsen-anhalt",
    "Thüringen": "thueringen"
}

API = "https://vergabeweiser.de/api/v1/tenders"
DATA_FILE = Path("data/latest.json")


def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(
                DATA_FILE.read_text(encoding="utf-8")
            )
        except Exception:
            pass

    return {
        "updated_at": None,
        "results": [],
        "errors": []
    }



def search_state(state, slug):
    api_key = st.secrets.get("VERGABEWEISER_API_KEY", "")

    if not api_key:
        return [], ["API-Schlüssel fehlt in den Streamlit-Secrets."]

    params = {
        "was": "Holzpellets",
        "land": slug,
        "status": "offen",
        "sort": "neu",
        "seite": 1
    }

    headers = {
        "User-Agent": "Holzpellets-Radar/2.0",
        "Authorization": f"Bearer {api_key}"
    }

    for attempt in range(3):
        try:
            response = requests.get(
                API,
                params=params,
                headers=headers,
                timeout=45
            )

            if response.status_code == 429:
                wait = int(
                    response.headers.get("Retry-After", "60")
                )

                if attempt == 2 or wait > 120:
                    return [], [
                        "Rate-Limit erreicht. Bitte später erneut versuchen."
                    ]

                time.sleep(max(wait, 5))
                continue

            response.raise_for_status()
            data = response.json()

            results = []

            for item in data.get("results", []):
                title = (
                    item.get("title")
                    or item.get("original_title")
                    or ""
                )

                search_text = (
                    title + " " +
                    str(item.get("original_title") or "") + " " +
                    str(item.get("gewerk") or "")
                ).lower()

                if "pellet" not in search_text:
                    continue

                buyer = item.get("buyer") or {}
                place = item.get("place") or {}
                deadline = item.get("deadline") or {}

                results.append({
                    "id": item.get("id", ""),
                    "state": state,
                    "title": title,
                    "buyer": (
                        buyer.get("name", "")
                        if isinstance(buyer, dict)
                        else str(buyer)
                    ),
                    "place": (
                        place.get("text")
                        or place.get("city")
                        or state
                    ),
                    "deadline": (
                        deadline.get("label", "")
                        if isinstance(deadline, dict)
                        else str(deadline)
                    ),
                    "published": item.get("published_on") or "",
                    "url": item.get("url") or "",
                    "source": "Vergabeweiser"
                })

            return results, []

        except Exception as error:
            if attempt == 2:
                return [], [str(error)]

            time.sleep(5 * (attempt + 1))

    return [], ["Suche nicht abgeschlossen."]

    }

    for attempt in range(3):
        try:
            api_key = st.secrets.get("VERGABEWEISER_API_KEY", "")

if not api_key:
    return [], ["API-Schlüssel fehlt in den Streamlit-Secrets."]


api_key = st.secrets.get("VERGABEWEISER_API_KEY", "")

if not api_key:
    return [], ["API-Schlüssel fehlt in den Streamlit-Secrets."]

response = requests.get(
    API,
    params=params,
    headers={
        "User-Agent": "Holzpellets-Radar/2.0",
        "Authorization": f"Bearer {api_key}"
    },
    timeout=45
)
,
    timeout=45
)
            )

            if response.status_code == 429:
                wait = int(
                    response.headers.get("Retry-After", "30")
                )

                if attempt == 2 or wait > 120:
                    return [], [
                        f"Rate-Limit: Bitte später erneut versuchen. "
                        f"Wartezeit: {wait} Sekunden."
                    ]

                time.sleep(max(wait, 5))
                continue

            response.raise_for_status()
            data = response.json()

            results = []

            for item in data.get("results", []):
                title = (
                    item.get("title")
                    or item.get("original_title")
                    or ""
                )

                search_text = (
                    title + " " +
                    str(item.get("original_title") or "") + " " +
                    str(item.get("gewerk") or "")
                ).lower()

                if "pellet" not in search_text:
                    continue

                buyer = item.get("buyer") or {}
                place = item.get("place") or {}
                deadline = item.get("deadline") or {}

                results.append({
                    "id": item.get("id", ""),
                    "state": state,
                    "title": title,
                    "buyer": (
                        buyer.get("name", "")
                        if isinstance(buyer, dict)
                        else str(buyer)
                    ),
                    "place": (
                        place.get("text")
                        or place.get("city")
                        or place.get("land")
                        or state
                    ),
                    "deadline": (
                        deadline.get("label", "")
                        if isinstance(deadline, dict)
                        else str(deadline)
                    ),
                    "published": item.get("published_on") or "",
                    "url": item.get("url") or "",
                    "source": "Vergabeweiser"
                })

            return results, []

        except Exception as error:
            if attempt == 2:
                return [], [str(error)]

            time.sleep(5 * (attempt + 1))

    return [], ["Suche nicht abgeschlossen."]


def run_search():
    results = []
    errors = []

    progress = st.progress(0)

    for i, (state, slug) in enumerate(
        STATES.items(), start=1
    ):
        st.write("Durchsuche:", state)

        found, failed = search_state(state, slug)

        results.extend(found)
        errors.extend([
            state + ": " + error for error in failed
        ])

        progress.progress(i / len(STATES))
        time.sleep(5)

    unique = {}

    for item in results:
        key = item.get("id") or item.get("url") or item.get("title")
        unique[str(key)] = item

    snapshot = {
        "updated_at": datetime.now(
            ZoneInfo("Europe/Berlin")
        ).isoformat(timespec="seconds"),
        "results": list(unique.values()),
        "errors": errors
    }

    DATA_FILE.parent.mkdir(exist_ok=True)

    DATA_FILE.write_text(
        json.dumps(
            snapshot,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    return snapshot


data = load_data()

st.title("🌲 Holzpellets-Ausschreibungsradar")
st.caption(
    "Tägliche Suche in den fünf neuen Bundesländern"
)

if st.sidebar.button("🔄 Jetzt suchen", type="primary"):
    with st.spinner("Suche läuft. Bitte etwas Geduld ..."):
        data = run_search()

    st.rerun()


if data.get("updated_at"):
    st.caption(
        "Letzte Aktualisierung: "
        + data["updated_at"]
    )
else:
    st.info("Noch keine Suchdaten vorhanden.")


errors = data.get("errors", [])
results = data.get("results", [])

if errors:
    st.error(
        "Die Suche war teilweise oder vollständig "
        "nicht erfolgreich. Bitte die Hinweise prüfen."
    )

    with st.expander("Suchfehler anzeigen", expanded=True):
        for error in errors:
            st.write("• " + error)


st.metric(
    "Gefundene Ausschreibungen",
    len(results)
)


for state in STATES:
    state_results = [
        item for item in results
        if item.get("state") == state
    ]

    with st.container(border=True):
        st.subheader(state)

        st.write(
            "Gefundene Ausschreibungen:",
            len(state_results)
        )

        if not state_results:
            if errors:
                st.warning(
                    "Keine bestätigten Treffer. "
                    "Die Suche war möglicherweise unvollständig."
                )
            elif data.get("updated_at"):
                st.success(
                    "Keine passenden Ausschreibungen gefunden."
                )
            else:
                st.info("Noch keine Suche durchgeführt.")

        for item in state_results:
            st.markdown(
                "### " + (
                    item.get("title")
                    or "Holzpellet-Ausschreibung"
                )
            )

            if item.get("buyer"):
                st.write(
                    "Auftraggeber:",
                    item["buyer"]
                )

            if item.get("place"):
                st.write(
                    "Ort:",
                    item["place"]
                )

            if item.get("deadline"):
                st.write(
                    "Angebotsfrist:",
                    item["deadline"]
                )

            if item.get("published"):
                st.write(
                    "Veröffentlicht:",
                    item["published"]
                )

            if item.get("url"):
                st.markdown(
                    f"[Zur Originalausschreibung ↗]({item['url']})"
                )

            st.caption(
                "Quelle: Vergabeweiser"
            )

            st.divider()


st.caption(
    "Bitte Angebotsfristen und Vergabeunterlagen "
    "immer in der Originalbekanntmachung prüfen. "
    "Eine vollständige Erfassung aller Ausschreibungen "
    "kann nicht garantiert werden."
)

st.markdown(
    "[Datenquelle und API-Hinweise](https://vergabeweiser.de/api)"
)
