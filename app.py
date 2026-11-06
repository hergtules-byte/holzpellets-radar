
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


def search_state(state, slug, api_key):
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

    try:
        response = requests.get(
            API,
            params=params,
            headers=headers,
            timeout=45
        )

        if response.status_code == 429:
            return [], [
                "API-Limit erreicht. Bitte später erneut versuchen."
            ]

        response.raise_for_status()
        data = response.json()

        results = []

        for item in data.get("results", []):
            buyer = item.get("buyer") or {}
            place = item.get("place") or {}
            deadline = item.get("deadline") or {}

            results.append({
                "id": item.get("id", ""),
                "state": state,
                "title": (
                    item.get("title")
                    or item.get("original_title")
                    or "Holzpellet-Ausschreibung"
                ),
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

    except requests.exceptions.RequestException as error:
        return [], [str(error)]

    except Exception as error:
        return [], [str(error)]


def run_search(api_key):
    all_results = []
    all_errors = []

    progress = st.progress(0)

    for i, (state, slug) in enumerate(
        STATES.items(), start=1
    ):
        st.write("Durchsuche:", state)

        found, errors = search_state(
            state, slug, api_key
        )

        all_results.extend(found)

        for error in errors:
            all_errors.append(state + ": " + error)

        progress.progress(i / len(STATES))

        # Kurze Pause zwischen den Anfragen
        time.sleep(3)

    unique = {}

    for item in all_results:
        key = (
            item.get("id")
            or item.get("url")
            or item.get("title")
        )
        unique[str(key)] = item

    results = list(unique.values())

    results.sort(
        key=lambda x: x.get("published") or "",
        reverse=True
    )

    snapshot = {
        "updated_at": datetime.now(
            ZoneInfo("Europe/Berlin")
        ).isoformat(timespec="seconds"),
        "results": results,
        "errors": all_errors
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

    progress.empty()

    return snapshot


# Hauptseite

st.title("🌲 Holzpellets-Ausschreibungsradar")

st.caption(
    "Tägliche Suche in den fünf neuen Bundesländern"
)

data = load_data()

api_key = st.secrets.get(
    "VERGABEWEISER_API_KEY", ""
)

if not api_key:
    st.error(
        "API-Schlüssel fehlt. Bitte Streamlit-Secrets prüfen."
    )
    st.stop()


if st.sidebar.button(
    "🔄 Jetzt suchen",
    type="primary"
):
    with st.spinner(
        "Suche läuft. Bitte etwas Geduld ..."
    ):
        data = run_search(api_key)

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
        "Die Suche war nicht vollständig erfolgreich."
    )

    with st.expander(
        "Suchfehler anzeigen",
        expanded=True
    ):
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
                "### " + item["title"]
            )

            if item["buyer"]:
                st.write(
                    "Auftraggeber:",
                    item["buyer"]
                )

            if item["place"]:
                st.write(
                    "Ort:",
                    item["place"]
                )

            if item["deadline"]:
                st.write(
                    "Angebotsfrist:",
                    item["deadline"]
                )

            if item["published"]:
                st.write(
                    "Veröffentlicht:",
                    item["published"]
                )

            if item["url"]:
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
    "[Vergabeweiser – API und Datenquelle](https://vergabeweiser.de/api)"
)
