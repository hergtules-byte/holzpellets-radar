
import json
from pathlib import Path
from datetime import datetime

import streamlit as st

# =====================================
# SEITENKONFIGURATION
# =====================================

st.set_page_config(
    page_title="Holzpellets-Ausschreibungsradar",
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
# VERTRIEBSPOTENZIAL BEWERTEN
# =====================================

def sales_profile(item):
    """Ordnet Treffer nach erkennbarem Vertriebsansatz ein."""
    buyer = str(item.get("buyer", ""))
    title = str(item.get("title", ""))
    description = str(item.get("description", ""))
    trade = str(item.get("gewerk", ""))
    text = " ".join([buyer, title, description, trade]).lower()

    public_terms = [
        "landratsamt", "gemeinde", "stadt ", "stadtverwaltung",
        "landkreis", "zweckverband", "kommun", "schule",
        "schullandheim", "krankenhaus", "klinikum", "universität",
        "universitaet", "wohnungsbau", "wohnungsgesellschaft",
        "wohnungsgenossenschaft", "pflegeheim", "seniorenheim"
    ]
    housing_terms = [
        "wohnungsbau", "wohnungsgesellschaft",
        "wohnungsgenossenschaft", "wohnungsunternehmen"
    ]
    education_health_terms = [
        "schule", "schullandheim", "krankenhaus", "klinikum",
        "universität", "universitaet", "pflegeheim", "seniorenheim"
    ]
    energy_terms = [
        "wärme", "waerme", "energieversorgung", "stadtwerke",
        "heizwerk", "biomassekessel", "wärmeversorgung",
        "waermeversorgung"
    ]

    if any(term in buyer.lower() for term in housing_terms):
        segment = "Wohnungswirtschaft"
    elif any(term in text for term in education_health_terms):
        segment = "Bildung & Soziales"
    elif any(term in text for term in energy_terms):
        segment = "Wärmeversorgung & Energie"
    elif any(term in text for term in public_terms):
        segment = "Öffentliche Hand"
    else:
        segment = "Sonstige Auftraggeber"

    supply_terms = [
        "lieferung von holzpellets", "lieferung von pellets",
        "holzpelletlieferung", "pelletlieferung",
        "bedarf an pellets", "jahresbedarf", "tonnen pellets",
        "pellets für", "brennstofflieferung"
    ]
    project_terms = [
        "umstellung", "pelletfeuerung", "pelletheizung",
        "biomassekessel", "kesselanlage", "wärmeerzeugung",
        "waermeerzeugung", "heizungsanlage", "errichtung",
        "installation", "montage", "neubau", "sanierung"
    ]

    direct_supply = any(term in text for term in supply_terms)
    pellet_context = "pellet" in text or "biomasse" in text
    project_context = pellet_context and any(
        term in text for term in project_terms
    )

    if direct_supply:
        grade = "A"
        reason = "Direkter Brennstoff- bzw. Pelletlieferbedarf erkennbar"
    elif project_context and segment != "Sonstige Auftraggeber":
        grade = "A"
        reason = "Konkretes Pellet-/Biomasseprojekt bei öffentlichem oder institutionellem Kunden"
    elif project_context or pellet_context:
        grade = "B"
        reason = "Projekt- oder Pelletbezug vorhanden; Lieferbedarf noch verifizieren"
    else:
        grade = "C"
        reason = "Holzbrennstoff-Bezug nur indirekt – manuelle Prüfung empfohlen"

    return grade, segment, reason


# =====================================
# DATEN VORBEREITEN
# =====================================

data = load_data()

results = data.get("results", [])
errors = data.get("errors", [])
statistics = data.get("statistics", {})

for item in results:
    item["display_category"] = classify_result(item)
    grade, segment, reason = sales_profile(item)
    item["sales_grade"] = grade
    item["customer_segment"] = segment
    item["sales_reason"] = reason

# =====================================
# KOPFBEREICH
# =====================================

st.title("🌲 Holzpellets-Ausschreibungsradar")

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

grade_a_count = sum(1 for x in results if x["sales_grade"] == "A")

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Alle Treffer", len(results))
col2.metric("Holzpellet-Ausschreibungen", pellet_count)
col3.metric("Pellet-Projekte", project_count)
col4.metric("Weitere Holzbrennstoffe", chip_count + other_count)
col5.metric("Vertriebspotenzial A", grade_a_count)

st.divider()

# =====================================
# FILTER
# =====================================

st.header("Ausschreibungen und Projekte")

filter_col1, filter_col2, filter_col3 = st.columns(3)

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

with filter_col3:
    selected_grade = st.selectbox(
        "Vertriebspotenzial",
        ["Alle Bewertungen", "A – hohe Priorität", "B – prüfen", "C – geringe Priorität"]
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

if selected_grade != "Alle Bewertungen":
    grade_filter = selected_grade[0]
    filtered = [
        x for x in filtered
        if x["sales_grade"] == grade_filter
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

                    grade = item.get("sales_grade", "C")
                    segment = item.get("customer_segment", "Sonstige Auftraggeber")
                    reason = item.get("sales_reason", "")

                    st.markdown(
                        f"**Vertriebspotenzial: {grade}** · Zielgruppe: **{segment}**"
                    )
                    st.caption(reason)

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
    "Holzpellets-Ausschreibungsradar | "
    "Datenquelle: Vergabeweiser"
)

st.caption(
    "Bitte Angebotsfristen und Vergabeunterlagen "
    "immer in der Originalbekanntmachung prüfen."
)
