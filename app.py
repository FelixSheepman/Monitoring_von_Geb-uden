"""
KI-Agent fuer die Monitoring-Auswertung - interaktive Web-App (Streamlit).

Start:
    .venv/Scripts/streamlit run app.py
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from monitoring_agent.data_loader import load_measurements
from monitoring_agent.excel_export import export_workbook
from monitoring_agent.report import build_report

st.set_page_config(page_title="Monitoring KI-Agent", layout="wide", page_icon="📊")

SAMPLE_PATH = Path("source_docs/Messdaten 2024-2026.xlsx")

st.title("📊 KI-Agent: Technisches Monitoring")
st.caption(
    "Automatisierte Datenprüfung und grafische Aufbereitung von Monitoring-Messdaten "
    "– Ersatz für die manuelle Excel-Auswertung aus Kapitel 6 der Hausarbeit."
)

with st.sidebar:
    st.header("Eingabedaten")
    uploaded = st.file_uploader("Messdaten-Datei (.xlsx)", type=["xlsx"])
    use_sample = False
    if uploaded is None and SAMPLE_PATH.exists():
        use_sample = st.checkbox("Beispieldatensatz verwenden (Messdaten 2024–2026)", value=True)

    st.divider()
    st.header("Carpetplot-Zeitraum")
    carpet_year = st.number_input("Jahr", min_value=2020, max_value=2035, value=2025, step=1)
    carpet_month = st.number_input("Monat", min_value=1, max_value=12, value=2, step=1)

    st.divider()
    st.header("Darstellung Zeitreihen")
    resample_label = st.selectbox(
        "Auflösung Liniendiagramme",
        ["Rohdaten (15 Min.)", "Stundenmittel", "Tagesmittel"],
        index=1,
        help="Volle Auflösung ist exakt, aber unruhig zu lesen. Stunden-/Tagesmittel "
             "glätten die Darstellung für die Berichtsqualität, ohne die Aussage zu verändern.",
    )
    RESAMPLE_MAP = {"Rohdaten (15 Min.)": None, "Stundenmittel": "h", "Tagesmittel": "D"}


@st.cache_data(show_spinner="Lese Messdaten ein...")
def _load(file_bytes: bytes) -> pd.DataFrame:
    return load_measurements(io.BytesIO(file_bytes))


@st.cache_data(show_spinner="Führe Datenprüfung durch und erstelle Abbildungen...")
def _build(file_bytes: bytes, year: int, month: int, resample_rule: str | None):
    df = _load(file_bytes)
    report = build_report(df, carpet_year=year, carpet_month=month, display_resample=resample_rule)
    return report, df


input_bytes = None
if uploaded is not None:
    input_bytes = uploaded.getvalue()
elif use_sample:
    input_bytes = SAMPLE_PATH.read_bytes()

if input_bytes is None:
    st.info("Bitte eine Messdaten-.xlsx hochladen oder den Beispieldatensatz aktivieren.")
    st.stop()

try:
    report, df_full = _build(input_bytes, int(carpet_year), int(carpet_month),
                              RESAMPLE_MAP[resample_label])
except ValueError as e:
    st.error(str(e))
    st.stop()

n_auffaellig = int((report.quality_df["Plausibilität"] == "Auffällig!").sum())
n_ok = len(report.quality_df) - n_auffaellig

c1, c2, c3, c4 = st.columns(4)
c1.metric("Zeitraum", f"{df_full.index.min():%d.%m.%Y} – {df_full.index.max():%d.%m.%Y}")
c2.metric("Messpunkte", f"{len(df_full):,}".replace(",", "."))
c3.metric("Spalten plausibel", n_ok)
c4.metric("Spalten auffällig", n_auffaellig, delta_color="inverse")

tab_quality, tab_figures, tab_auswertung, tab_export = st.tabs(
    ["🔍 Datenprüfung", "📈 Abbildungen", "🧠 Auswertung", "⬇️ Export"])

with tab_quality:
    st.subheader("Tabelle 1 – Datenprüfung")
    filter_choice = st.radio("Filter", ["Alle", "Nur Auffällige", "Nur Plausible"],
                              horizontal=True, label_visibility="collapsed")
    qdf = report.quality_df
    if filter_choice == "Nur Auffällige":
        qdf = qdf[qdf["Plausibilität"] == "Auffällig!"]
    elif filter_choice == "Nur Plausible":
        qdf = qdf[qdf["Plausibilität"] == "Plausibel"]

    def _style_status(val):
        color = "#C6EFCE" if val == "Plausibel" else "#FFC7CE"
        return f"background-color: {color}"

    st.dataframe(
        qdf.style.map(_style_status, subset=["Plausibilität"]),
        use_container_width=True, hide_index=True, height=560,
    )

narrative_by_key: dict[str, list] = {}
for block in report.narrative:
    for key in block.figure_keys:
        narrative_by_key.setdefault(key, []).append(block)

with tab_figures:
    for entry in report.figures:
        st.plotly_chart(entry.figure, use_container_width=True, key=entry.key)
        st.caption(entry.caption)
        for block in narrative_by_key.get(entry.key, []):
            st.info(f"**{block.heading}**\n\n{block.text}")
        st.divider()

with tab_auswertung:
    st.subheader("Automatisierte Auswertung – Ersatz für Kapitel 6.4")
    st.caption(
        "Alle Werte werden live aus dem aktuellen Datensatz berechnet (keine festen Textbausteine)."
    )
    for block in report.narrative:
        with st.expander(block.heading, expanded=True):
            st.write(block.text)
            related = ", ".join(
                next(e.title for e in report.figures if e.key == k)
                for k in block.figure_keys if any(e.key == k for e in report.figures)
            )
            if related:
                st.caption(f"Bezug: {related}")

with tab_export:
    st.subheader("Report als Excel-Arbeitsmappe exportieren")
    st.write(
        "Erzeugt eine eigenständige .xlsx-Datei mit der Datenprüfung (farbcodiert) "
        "und allen Abbildungen als native, in Excel weiter editierbare Diagramme – "
        "analog zur bisherigen manuellen Auswertung."
    )
    if st.button("Excel-Report erzeugen", type="primary"):
        with st.spinner("Erzeuge Arbeitsmappe..."):
            full_report = build_report(df_full, int(carpet_year), int(carpet_month))
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir) / "monitoring_report.xlsx"
                export_workbook(full_report, str(tmp_path))
                data = tmp_path.read_bytes()
        st.download_button(
            "📥 monitoring_report.xlsx herunterladen",
            data=data,
            file_name="monitoring_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
