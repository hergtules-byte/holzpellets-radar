
import json
from pathlib import Path
from datetime import datetime

import streamlit as st

# =====================================
# SEITENKONFIGURATION
# =====================================

st.set_page_config(
    page_title="Pellet und Kohle-Ausschreibungsradar",
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

DATA_FILE = Path("data/latest.json")

CATEGORIES = [
    "Holzpellet-Ausschreibungen",
    "Pellet-Projekte",
    "Holzhackschnitzel",
    "Weitere Holzbrennstoffe",
    "BKS / Kohle / Briketts",
    "Weitere Prüftreffer"
]

# =====================================
# DATEN LADEN
# =====================================

def load_data():
    if not DATA_FILE.exists():
        return {
            "updated_at": None,
            "results": [],
            "errors": [],
            "statistics": {}
        }

    try:
        return json.loads(
            DATA_FILE.read_text(encoding="utf-8")
        )
    except Exception as error:
        st.error(f"Fehler beim Lesen der Daten: {error}")
        return {
            "updated_at": None,
            "results": [],
            "errors": [],
            "statistics": {}
        }


# =====================================
# TREFFER EINORDNEN
# =====================================

def classify_result(item):
    label = str(
        item.get("woodpellet_check", "")
    ).lower()

    title = str(item.get("title", ""))
    description = str(item.get("description", ""))
    text = (title + " " + description).lower()

    # Hackschnitzel separat behandeln
    if "hackschnitzel" in label:
        return "Holzhackschnitzel"

    # BKS, Kohle und mineralische Briketts separat führen.
    # Holzbriketts bleiben in der Holzbrennstoff-Kategorie.
    if "bks / kohle / briketts" in label:
        return "BKS / Kohle / Briketts"

    # Projekte anhand des Ausschreibungsinhalts erkennen
    project_terms = [
        "umstellung",
        "pelletfeuerung",
        "pelletheizung",
        "biomassekessel",
        "kesselanlage",
        "heizungsanlage",
        "wärmeerzeugung",
        "errichtung",
        "installation",
        "montage",
        "neubau",
        "sanierung"
    ]

    is_project = any(
        term in text for term in project_terms
    )

    if is_project and (
        "pellet" in text or "biomasse" in text
    ):
        return "Pellet-Projekte"

    if "holzpellets eindeutig" in label:
        return "Holzpellet-Ausschreibungen"

    if "pellets" in label:
        return "Pellet-Projekte"

    if (
        "holzbrennstoff" in label
        or "cpv" in label
        or "sonstiger" in label
    ):
        return "Weitere Holzbrennstoffe"

    return "Weitere Prüftreffer"


# =====================================
# DATEN VORBEREITEN
# =====================================

data = load_data()

results = data.get("results", [])
errors = data.get("errors", [])
statistics = data.get("statistics", {})

for item in results:
    item["display_category"] = classify_result(item)

# =====================================
# KOPFBEREICH
# =====================================

st.title("🌲 Pellet und Kohle-Ausschreibungsradar")

st.caption(
    "Tägliche Suche nach Ausschreibungen "
    "in den fünf neuen Bundesländern"
)

if data.get("updated_at"):
    st.caption(
        "Letzte Aktualisierung: "
        + str(data["updated_at"])
    )

st.divider()

# =====================================
# GESAMTÜBERSICHT
# =====================================

st.header("Gesamtübersicht")

pellet_count = sum(
    1 for x in results
    if x["display_category"]
    == "Holzpellet-Ausschreibungen"
)

project_count = sum(
    1 for x in results
    if x["display_category"] == "Pellet-Projekte"
)

chip_count = sum(
    1 for x in results
    if x["display_category"] == "Holzhackschnitzel"
)

other_count = sum(
    1 for x in results
    if x["display_category"] == "Weitere Holzbrennstoffe"
)

other_fuel_count = sum(
    1 for x in results
    if x["display_category"] == "BKS / Kohle / Briketts"
)

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Alle Treffer", len(results))
col2.metric("Holzpellet-Ausschreibungen", pellet_count)
col3.metric("Pellet-Projekte", project_count)
col4.metric("Weitere Holzbrennstoffe", chip_count + other_count)
col5.metric("BKS / Kohle / Briketts", other_fuel_count)

st.divider()

# =====================================
# FILTER
# =====================================

st.header("Ausschreibungen und Projekte")

filter_col1, filter_col2 = st.columns(2)

with filter_col1:
    selected_state = st.selectbox(
        "Bundesland",
        ["Alle Bundesländer"] + STATES
    )

with filter_col2:
    selected_category = st.selectbox(
        "Kategorie",
        ["Alle Kategorien"] + CATEGORIES
    )

filtered = results

if selected_state != "Alle Bundesländer":
    filtered = [
        x for x in filtered
        if x.get("state") == selected_state
    ]

if selected_category != "Alle Kategorien":
    filtered = [
        x for x in filtered
        if x["display_category"] == selected_category
    ]

st.write(
    f"**{len(filtered)} Treffer gefunden**"
)

# =====================================
# ERGEBNISSE ANZEIGEN
# =====================================

for state in STATES:

    if (
        selected_state != "Alle Bundesländer"
        and selected_state != state
    ):
        continue

    state_results = [
        x for x in filtered
        if x.get("state") == state
    ]

    with st.container(border=True):

        st.subheader(state)

        st.caption(
            f"Gefundene Treffer: {len(state_results)}"
        )

        if not state_results:
            st.info(
                "Keine passenden Treffer in dieser Auswahl."
            )
            continue

        for category in CATEGORIES:

            category_results = [
                x for x in state_results
                if x["display_category"] == category
            ]

            if not category_results:
                continue

            with st.expander(
                f"{category} ({len(category_results)})",
                expanded=True
            ):

                for item in category_results:

                    st.markdown(
                        "### " + str(
                            item.get("title")
                            or "Ausschreibung ohne Titel"
                        )
                    )

                    st.caption(
                        "Einordnung: " + category
                    )

                    if item.get("buyer"):
                        st.write(
                            "**Auftraggeber:**",
                            item["buyer"]
                        )

                    if item.get("place"):
                        st.write(
                            "**Standort:**",
                            item["place"]
                        )

                    if item.get("published"):
                        st.write(
                            "**Veröffentlicht:**",
                            item["published"]
                        )

                    if item.get("deadline"):
                        st.write(
                            "**Angebotsfrist:**",
                            item["deadline"]
                        )

                    if item.get("estimated_value"):
                        st.write(
                            "**Geschätzter Auftragswert:**",
                            item["estimated_value"]
                        )

                    if item.get("description"):
                        st.write(
                            "**Beschreibung:**",
                            item["description"]
                        )

                    if item.get("cpv"):
                        st.caption(
                            "CPV: " + str(item["cpv"])
                        )

                    if item.get("url"):
                        st.markdown(
                            f"[Originalausschreibung öffnen ↗]"
                            f"({item['url']})"
                        )

                    if item.get("documents_url"):
                        st.markdown(
                            f"[Vergabeunterlagen öffnen ↗]"
                            f"({item['documents_url']})"
                        )

                    if item.get("notice_url"):
                        st.markdown(
                            f"[Originalbekanntmachung öffnen ↗]"
                            f"({item['notice_url']})"
                        )

                    st.divider()

# =====================================
# SUCHSTATISTIK
# =====================================

with st.expander("Suchstatistik und technische Details"):

    if statistics:
        st.json(statistics)

    if data.get("search_stats"):
        st.write("Einzelne Suchabfragen")
        st.dataframe(
            data["search_stats"],
            use_container_width=True
        )

    if errors:
        st.error("Fehler bei der Suche")

        for error in errors:
            st.write("• " + str(error))

    else:
        st.success(
            "Keine Suchfehler im letzten gespeicherten Lauf."
        )

# =====================================
# ABSCHLUSS
# =====================================

st.divider()

st.caption(
    "Pellet und Kohle-Ausschreibungsradar | "
    "Datenquellen: Vergabeweiser und Bekanntmachungsservice"
)

st.caption(
    "Bitte Angebotsfristen und Vergabeunterlagen "
    "immer in der Originalbekanntmachung prüfen."
)
