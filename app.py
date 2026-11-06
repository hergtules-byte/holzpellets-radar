
import json
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

STATES = [
    "Brandenburg",
    "Mecklenburg-Vorpommern",
    "Sachsen",
    "Sachsen-Anhalt",
    "Thüringen"
]

TERMS = [
    "Holzpellets",
    "Holzpellet",
    "Pelletlieferung",
    "Lieferung von Holzpellets"
]

DATA_FILE = Path("data/latest.json")
API = "https://vergabeweiser.de/api/v1/tenders"

st.title("🌲 Holzpellets-Ausschreibungsradar")
st.caption("Tägliche Suche in den fünf neuen Bundesländern")

def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "updated_at": None,
        "results": [],
        "errors": []
    }

def search_state(state):
    results = {}
    errors = []

    for term in TERMS:
        try:
            response = requests.get(
                API,
                params={
                    "was": term,
                    "wo": state,
                    "status": "offen",
                    "seite": 1,
                    "sort": "neu"
                },
                timeout=35
            )
            response.raise_for_status()
            data = response.json()

            for item in data.get("results", []):
                title = str(
                    item.get("title")
                    or item.get("original_title")
                    or item.get("description")
                    or ""
                )

                if "pellet" not in (
                    title + " " +
                    str(item.get("description") or "")
                ).lower():
                    continue

                url = (
                    item.get("url")
                    or item.get("notice_url")
                    or item.get("link")
                    or ""
                )

                ident = str(item.get("id") or url or title)

                results[ident] = {
                    "state": state,
                    "title": title,
                    "buyer": item.get("buyer") or "",
                    "place": item.get("place") or state,
                    "deadline": item.get("deadline") or "",
                    "published": item.get("published_at") or "",
                    "url": url
                }

        except Exception as error:
            errors.append(f"{term}: {error}")

    return list(results.values()), errors


def run_search():
    all_results = []
    all_errors = []

    progress = st.progress(0)

    for i, state in enumerate(STATES):
        results, errors = search_state(state)
        all_results.extend(results)
        all_errors.extend(
            [state + ": " + e for e in errors]
        )
        progress.progress((i + 1) / len(STATES))

    unique = {
        str(x.get("url") or x.get("title")): x
        for x in all_results
    }

    snapshot = {
        "updated_at": datetime.now(
            ZoneInfo("Europe/Berlin")
        ).isoformat(timespec="seconds"),
        "results": list(unique.values()),
        "errors": all_errors
    }

    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return snapshot


data = load_data()

if st.sidebar.button("🔄 Jetzt suchen", type="primary"):
    with st.spinner("Suche läuft ..."):
        data = run_search()
    st.rerun()

if data["updated_at"]:
    st.caption("Letzte Aktualisierung: " + data["updated_at"])
else:
    st.warning("Noch keine Suche durchgeführt.")

if data["errors"]:
    st.warning(
        "Einige Suchabfragen sind fehlgeschlagen. "
        "Die Ergebnisse können unvollständig sein."
    )
    with st.expander("Fehler anzeigen"):
        for error in data["errors"]:
            st.write(error)

st.metric("Gefundene Ausschreibungen", len(data["results"]))

for state in STATES:
    results = [
        x for x in data["results"]
        if x["state"] == state
    ]

    with st.container(border=True):
        st.subheader(state)
        st.write(f"Gefundene Ausschreibungen: {len(results)}")

        if not results:
            if data["errors"]:
                st.info(
                    "Keine bestätigten Treffer. "
                    "Die Suche war möglicherweise unvollständig."
                )
            elif data["updated_at"]:
                st.success(
                    "Keine passenden Ausschreibungen gefunden."
                )
            else:
                st.info("Noch keine Suche durchgeführt.")

        for item in results:
            st.markdown("### " + (item["title"] or "Holzpellet-Ausschreibung"))

            if item["buyer"]:
                st.write("Auftraggeber:", item["buyer"])

            if item["place"]:
                st.write("Ort:", item["place"])

            if item["deadline"]:
                st.write("Angebotsfrist:", item["deadline"])

            if item["published"]:
                st.write("Veröffentlicht:", item["published"])

            if item["url"]:
                st.markdown(
                    f"[Zur Ausschreibung öffnen]({item['url']})"
                )

            st.divider()

st.caption(
    "Hinweis: Bitte Fristen und Vergabeunterlagen immer "
    "in der Originalbekanntmachung prüfen. "
    "Eine vollständige Erfassung aller regionalen "
    "Ausschreibungen kann nicht garantiert werden."
)
