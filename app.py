
import json
from pathlib import Path
import streamlit as st

# =====================================
# SEITENEINSTELLUNGEN
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


# =====================================
# DATEN LADEN
# =====================================

def load_data():
    if not DATA_FILE.exists():
        return {
            "updated_at": None,
            "results": [],
            "errors": []
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
            "errors": ["Datendatei konnte nicht gelesen werden."]
        }


# =====================================
# KATEGORIEN ZUORDNEN
# =====================================

def get_category(item):

    check = (
        item.get("woodpellet_check") or ""
    ).lower()

    title = (
        item.get("title") or ""
    ).lower()

    description = (
        item.get("description") or ""
    ).lower()

    text = title + " " + description

    if "holzpellets eindeutig" in check:
        return "Holzpellet-Ausschreibungen"

    if "pellets – holzart prüfen" in check:
        return "Pellet-Projekte"

    if "pellets - holzart prüfen" in check:
        return "Pellet-Projekte"

    if "pellet" in check:
        return "Pellet-Projekte"

    if (
        "hackschnitzel" in check
        or "holzbrennstoff" in check
        or "holzbrikett" in check
        or "cpv 09111400" in check
    ):
        return "Weitere Holzbrennstoffe"

    if "holzpellet" in text:
        return "Holzpellet-Ausschreibungen"

    if "pellet" in text:
        return "Pellet-Projekte"

    if (
        "hackschnitzel" in text
        or "holzbrikett" in text
        or "holzbrennstoff" in text
    ):
        return "Weitere Holzbrennstoffe"

    return "Weitere Holzbrennstoffe"


# =====================================
# EINZELNE AUSSCHREIBUNG ANZEIGEN
# =====================================

def show_tender(item):

    st.markdown(
        "#### " + (
            item.get("title")
            or "Ausschreibung ohne Titel"
        )
    )

    col1, col2 = st.columns(2)

    with col1:
        st.write(
            "**Auftraggeber:**",
            item.get("buyer") or "Nicht angegeben"
        )

        st.write(
            "**Ort:**",
            item.get("place") or "Nicht angegeben"
        )

    with col2:
        st.write(
            "**Angebotsfrist:**",
            item.get("deadline") or "Nicht angegeben"
        )

        st.write(
            "**Veröffentlicht:**",
            item.get("published") or "Nicht angegeben"
        )

    if item.get("description"):
        with st.expander("Beschreibung anzeigen"):
            st.write(item["description"])

    if item.get("cpv"):
        st.caption("CPV: " + str(item["cpv"]))

    if item.get("woodpellet_check"):
        st.caption(
            "Einstufung: "
            + item["woodpellet_check"]
        )

    links = []

    for key, label in [
        ("url", "Originalausschreibung"),
        ("notice_url", "Bekanntmachung"),
        ("documents_url", "Vergabeunterlagen")
    ]:
        url = item.get(key)

        if (
            isinstance(url, str)
            and url.startswith("https://")
            and url not in [x[1] for x in links]
        ):
            links.append((label, url))

    if links:
        for label, url in links:
            st.markdown(
                f"[{label} öffnen ↗]({url})"
            )

    st.caption("Quelle: Vergabeweiser")
    st.divider()


# =====================================
# HAUPTSEITE
# =====================================

st.title("🌲 Holzpellets-Ausschreibungsradar")

st.caption(
    "Tägliche Suche nach Ausschreibungen "
    "in den fünf neuen Bundesländern"
)

data = load_data()

results = data.get("results", [])
errors = data.get("errors", [])

if data.get("updated_at"):
    st.caption(
        "Letzte Aktualisierung: "
        + str(data["updated_at"])
    )
else:
    st.info(
        "Noch keine Suchdaten vorhanden."
    )

# =====================================
# FEHLERHINWEISE
# =====================================

if errors:
    st.warning(
        "Die Suche war teilweise oder vollständig "
        "nicht erfolgreich. Bitte Hinweise prüfen."
    )

    with st.expander("Suchfehler anzeigen"):
        for error in errors:
            st.write("• " + str(error))


# =====================================
# ERGEBNISSE EINORDNEN
# =====================================

categories = {
    "Holzpellet-Ausschreibungen": [],
    "Pellet-Projekte": [],
    "Weitere Holzbrennstoffe": []
}

for item in results:
    category = get_category(item)
    categories[category].append(item)


# =====================================
# ÜBERSICHT
# =====================================

st.subheader("Gesamtübersicht")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Alle Treffer",
        len(results)
    )

with col2:
    st.metric(
        "Holzpellet-Ausschreibungen",
        len(categories["Holzpellet-Ausschreibungen"])
    )

with col3:
    st.metric(
        "Pellet-Projekte",
        len(categories["Pellet-Projekte"])
    )

with col4:
    st.metric(
        "Weitere Holzbrennstoffe",
        len(categories["Weitere Holzbrennstoffe"])
    )


# =====================================
# BUNDESLÄNDER
# =====================================

st.subheader("Ausschreibungen nach Bundesland")

for state in STATES:

    state_results = [
        item for item in results
        if item.get("state") == state
    ]

    with st.container(border=True):

        st.header(state)

        st.write(
            f"Gefundene Treffer: {len(state_results)}"
        )

        for category_name in [
            "Holzpellet-Ausschreibungen",
            "Pellet-Projekte",
            "Weitere Holzbrennstoffe"
        ]:

            category_results = [
                item for item in state_results
                if get_category(item) == category_name
            ]

            with st.expander(
                f"{category_name} ({len(category_results)})",
                expanded=bool(category_results)
            ):

                if category_results:
                    for item in category_results:
                        show_tender(item)

                else:
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
                        st.info(
                            "Noch keine Suche durchgeführt."
                        )


# =====================================
# ABSCHLUSS
# =====================================

st.divider()

st.caption(
    "Bitte Angebotsfristen und Vergabeunterlagen "
    "immer in der Originalbekanntmachung prüfen. "
    "Die Suche kann keine vollständige Erfassung "
    "aller Ausschreibungen garantieren."
)

st.markdown(
    "[Vergabeweiser – API und Datenquelle]"
    "(https://vergabeweiser.de/api)"
)
