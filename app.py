"""
KI-Agent fuer die Monitoring-Auswertung - interaktive Web-App (Streamlit).

Start:
    .venv/Scripts/streamlit run app.py
"""

from __future__ import annotations

import dataclasses
import io
import os
import tempfile
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from monitoring_agent.comparison import agreement_summary, compare_findings, compare_table1
from monitoring_agent.data_loader import load_measurements
from monitoring_agent.excel_export import export_workbook
from monitoring_agent.extras import savings_explanations
from monitoring_agent.llm_agent import MODELS, build_facts, generate_narrative, make_client
from monitoring_agent import figures as fx
from monitoring_agent.config import COLUMNS
from monitoring_agent.quality import quality_to_dataframe, run_data_quality
from monitoring_agent.report import build_report
from monitoring_agent.settings import FEATURE_LABELS, Settings, Thresholds
from monitoring_agent.word_export import export_docx

st.set_page_config(page_title="Monitoring KI-Agent", layout="wide", page_icon="📊")

SAMPLE_PATH = Path("source_docs/Messdaten 2024-2026.xlsx")
RESAMPLE_MAP = {"Rohdaten (15 Min.)": None, "Stundenmittel": "h", "Tagesmittel": "D"}
DEFAULTS = Settings()


def _api_key_from_environment() -> str:
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", "")


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
        "Auflösung Liniendiagramme", list(RESAMPLE_MAP), index=1,
        help="Glättet nur die Anzeige der Liniendiagramme. Datenprüfung, Carpetplots und "
             "Tagesverbräuche rechnen immer mit den Rohdaten.",
    )

    st.divider()
    with st.expander("⚙️ Einstellungen – Funktionen an/aus", expanded=False):
        flags = {}
        for key, (label, help_text) in FEATURE_LABELS.items():
            flags[key] = st.toggle(label, value=getattr(DEFAULTS, key), help=help_text, key=f"flag_{key}")
        llm_model = DEFAULTS.llm_model
        api_key = ""
        if flags["use_llm"]:
            llm_model = st.selectbox("Claude-Modell", list(MODELS), format_func=MODELS.get, key="llm_model")
            api_key = _api_key_from_environment()
            if api_key:
                st.success("API-Key gefunden (Secrets/Umgebung).")
            else:
                api_key = st.text_input("Anthropic-API-Key", type="password",
                                         help="Wird nur für diese Sitzung im Arbeitsspeicher gehalten.")
    settings = Settings(**flags, llm_model=llm_model)

    with st.expander("🎚️ Schwellenwerte & Annahmen", expanded=False):
        th_defaults = Thresholds()
        thresholds = Thresholds(
            heizgrenze_aul=st.slider("Heizgrenze Außentemperatur (°C)", 5.0, 20.0, th_defaults.heizgrenze_aul, 0.5),
            aktiv_schwelle_vl=st.slider("Aktiver Heizbetrieb ab Vorlauf (°C)", 15.0, 40.0, th_defaults.aktiv_schwelle_vl, 1.0),
            delta_t_min=st.slider("Mindest-Spreizung Delta T (K)", 1.0, 10.0, th_defaults.delta_t_min, 0.5),
            fbh_limit=st.slider("FBH-Auslegungsgrenze Vorlauf (°C)", 30.0, 50.0, th_defaults.fbh_limit, 1.0),
            heat_avoid_share=st.slider("Vermeidbarer Wärmeanteil oberhalb Heizgrenze", 0.0, 1.0, th_defaults.heat_avoid_share, 0.05),
            rlt_night_hours=st.slider("RLT-Nachtabsenkung (Stunden/Nacht)", 0.0, 12.0, th_defaults.rlt_night_hours, 1.0),
            rlt_night_reduction=st.slider("Ventilatorstrom-Reduktion in der Nacht", 0.0, 1.0, th_defaults.rlt_night_reduction, 0.05),
            heat_price=st.number_input("Wärmepreis (€/kWh)", 0.0, 1.0, th_defaults.heat_price, 0.01),
            power_price=st.number_input("Strompreis (€/kWh)", 0.0, 2.0, th_defaults.power_price, 0.01),
        )


@st.cache_data(show_spinner="Lese Messdaten ein...")
def _load(file_bytes: bytes):
    t0 = time.perf_counter()
    df = load_measurements(io.BytesIO(file_bytes))
    return df, time.perf_counter() - t0


@st.cache_data(show_spinner="Führe Datenprüfung durch und erstelle Abbildungen...")
def _build(file_bytes: bytes, year: int, month: int, resample_rule: str | None, anomalies: bool,
           th: Thresholds, strict: bool):
    df, load_seconds = _load(file_bytes)
    report = build_report(df, carpet_year=year, carpet_month=month,
                          display_resample=resample_rule, show_anomalies=anomalies,
                          thresholds=th, strict_rules=strict)
    report.timings = {"Einlesen": load_seconds, **report.timings}
    return report


input_bytes = None
if uploaded is not None:
    input_bytes = uploaded.getvalue()
elif use_sample:
    input_bytes = SAMPLE_PATH.read_bytes()

if input_bytes is None:
    st.info("Bitte eine Messdaten-.xlsx hochladen oder den Beispieldatensatz aktivieren.")
    st.stop()

try:
    report = _build(input_bytes, int(carpet_year), int(carpet_month),
                    RESAMPLE_MAP[resample_label], settings.show_anomalies, thresholds, settings.strict_rules)
except ValueError as e:
    st.error(str(e))
    st.stop()

df_full = report.df
n_auffaellig = int((report.quality_df["Plausibilität"] == "Auffällig!").sum())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Zeitraum", f"{df_full.index.min():%d.%m.%Y} – {df_full.index.max():%d.%m.%Y}")
c2.metric("Messpunkte", f"{len(df_full):,}".replace(",", "."))
c3.metric("Spalten plausibel", len(report.quality_df) - n_auffaellig)
c4.metric("Spalten auffällig", n_auffaellig, delta_color="inverse")

# --- Laufzeitmessung -------------------------------------------------------
if settings.show_timings:
    with st.expander("⏱️ Laufzeit des Agenten", expanded=False):
        total = sum(report.timings.values())
        cols = st.columns(len(report.timings) + 1)
        for col, (name, sec) in zip(cols, report.timings.items()):
            col.metric(name, f"{sec:.2f} s")
        cols[-1].metric("Gesamt", f"{total:.1f} s")
        manual_h = st.number_input(
            "Manueller Zeitaufwand für dieselben Schritte (Stunden) – bitte selbst eintragen",
            min_value=0.0, value=0.0, step=0.5, key="manual_hours",
            help="Schätzt oder messt, wie lange ihr für Datenprüfung, Grafiken und Auswertung in Excel gebraucht habt.",
        )
        if manual_h > 0:
            st.success(f"Der Agent ist rund **{manual_h * 3600 / max(total, 0.001):,.0f}-mal** schneller "
                       f"({manual_h:.1f} h manuell vs. {total:.1f} s Agent).".replace(",", "."))
        st.caption("Hinweis: Werte stammen aus der Berechnung; bei gecachten Ergebnissen sind es die Zeiten des ersten Laufs.")

# --- Auswertungstext (regelbasiert / Claude) ---------------------------------
llm_result = st.session_state.get("llm_result") if settings.use_llm else None
narrative_source = "Regelbasiert"
if llm_result is not None:
    narrative_source = st.sidebar.radio("Auswertungstext anzeigen/exportieren",
                                        ["Regelbasiert", "Claude (LLM)"], key="narrative_source")
active_narrative = llm_result.blocks if (llm_result is not None and narrative_source == "Claude (LLM)") \
    else report.narrative

tab_names = ["🔍 Datenprüfung", "📈 Abbildungen", "🧠 Auswertung"]
if settings.show_comparison:
    tab_names.append("⚖️ Vergleich")
if settings.show_explorer:
    tab_names.append("🔎 Explorer")
tab_names.append("⬇️ Export")
tabs = dict(zip(tab_names, st.tabs(tab_names)))

with tabs["🔍 Datenprüfung"]:
    st.subheader("Tabelle 1 – Datenprüfung")
    filter_choice = st.radio("Filter", ["Alle", "Nur Auffällige", "Nur Plausible"],
                             horizontal=True, label_visibility="collapsed")
    qdf = report.quality_df
    if filter_choice == "Nur Auffällige":
        qdf = qdf[qdf["Plausibilität"] == "Auffällig!"]
    elif filter_choice == "Nur Plausible":
        qdf = qdf[qdf["Plausibilität"] == "Plausibel"]
    st.dataframe(
        qdf.style.map(lambda v: f"background-color: {'#C6EFCE' if v == 'Plausibel' else '#FFC7CE'}",
                      subset=["Plausibilität"]),
        use_container_width=True, hide_index=True, height=560,
    )

narrative_by_key: dict[str, list] = {}
for block in active_narrative:
    for key in block.figure_keys:
        narrative_by_key.setdefault(key, []).append(block)

with tabs["📈 Abbildungen"]:
    if settings.show_anomalies and report.anomaly_counts:
        st.caption("Rote Rauten markieren erkannte Anomalien: " + " · ".join(
            f"{k}: {v}" for k, v in report.anomaly_counts.items()))
    for entry in report.figures:
        st.plotly_chart(entry.figure, use_container_width=True, key=entry.key)
        st.caption(entry.caption)
        for block in narrative_by_key.get(entry.key, []):
            st.info(f"**{block.heading}**\n\n{block.text}")
        st.divider()

with tabs["🧠 Auswertung"]:
    st.subheader("Automatisierte Auswertung – Ersatz für Kapitel 6.4")
    if settings.use_llm:
        st.markdown("**Claude-Auswertung**")
        st.caption("Die Zahlen kommen aus den Berechnungen, Claude formuliert nur die fachliche Einordnung.")
        if not api_key:
            st.warning("Kein API-Key vorhanden. Trage ihn im Einstellungsmenü (Sidebar) ein.")
        elif st.button("Auswertung mit Claude erzeugen", type="primary"):
            with st.spinner(f"{llm_model} schreibt die Auswertung..."):
                try:
                    st.session_state["llm_result"] = generate_narrative(
                        build_facts(report), make_client(api_key), llm_model)
                    st.rerun()
                except Exception as e:  # Fehler dem Nutzer zeigen, App nicht abbrechen
                    st.error(f"Claude-Aufruf fehlgeschlagen: {type(e).__name__}: {e}")
        if llm_result is not None:
            st.success(f"Erzeugt mit {llm_result.model} in {llm_result.seconds:.1f} s "
                       f"({llm_result.input_tokens} Eingabe-/{llm_result.output_tokens} Ausgabe-Tokens)"
                       + (" – Fallback-Modell wurde verwendet." if llm_result.fallback_used else "."))
        st.divider()
    st.markdown(f"**Angezeigte Quelle: {narrative_source}**")
    for block in active_narrative:
        with st.expander(block.heading, expanded=True):
            st.write(block.text)
            titles = [e.title for e in report.figures if e.key in block.figure_keys]
            if titles:
                st.caption("Bezug: " + ", ".join(titles))

    if settings.show_savings and report.savings is not None:
        st.divider()
        st.subheader("💡 Energieeinsparpotenzial")
        sv = report.savings
        total_row = sv[sv["Maßnahme"] == "Summe"].iloc[0]
        s1, s2, s3 = st.columns(3)
        s1.metric("Einsparung gesamt", f"{total_row['Einsparung kWh/a']:,.0f} kWh/a".replace(",", "."))
        s2.metric("Kosten", f"{total_row['Kosten €/a']:,.0f} €/a".replace(",", "."))
        s3.metric("Anteil am Gesamtverbrauch", f"{total_row['Anteil %']:.1f} %",
                  f"{total_row['Anteil %'] - 10:+.1f} %-Punkte zum 10-%-Ziel", delta_color="off")
        st.dataframe(sv, use_container_width=True, hide_index=True)
        st.caption("Bezug: gemessene Wärme (Zähler 019) und Ventilatorstrom (Zähler 021/022). Weitere Potenziale "
                   "(Pumpenabschaltung, Spreizung, Geb.08) sind mit den vorhandenen Daten nicht beziffert. "
                   "Annahmen im Einstellungsmenü unter „Schwellenwerte & Annahmen“ anpassbar.")
        for blk in savings_explanations(df_full, thresholds):
            with st.expander(blk.heading, expanded=blk.heading.startswith(("Maßnahme", "Gesamt"))):
                st.write(blk.text)

if settings.show_comparison:
    with tabs["⚖️ Vergleich"]:
        st.subheader("Vergleich manuelle Auswertung ↔ Agent (Kap. 8)")
        st.caption("Referenzwerte der manuellen Auswertung stehen in reference/*.csv und können dort korrigiert werden.")
        cmp1 = compare_table1(report.quality_df)
        summary = agreement_summary(cmp1)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Übereinstimmung Tabelle 1", f"{summary['Übereinstimmung %']:.0f} %",
                  f"{summary['übereinstimmend']} von {summary['Spalten gesamt']} Spalten", delta_color="off")
        m2.metric("Nur Agent auffällig", summary["nur Agent auffällig"])
        m3.metric("Nur manuell auffällig", summary["nur manuell auffällig"])
        m4.metric("Manuelle Befunde vom Agent gefunden",
                  f"{(compare_findings([b.heading for b in report.narrative])['Vom Agent gefunden'] == 'ja').sum()} von 5")

        st.markdown("**Regelsatz v1 gegen v2 (Kap. 8.2.3 Optimierung)**")
        rows = []
        for name, strict in (("v1 (Standard)", False), ("v2 (erweitert)", True)):
            sm = agreement_summary(compare_table1(quality_to_dataframe(
                run_data_quality(df_full, strict=strict, fbh_limit=thresholds.fbh_limit))))
            rows.append({"Regelsatz": name, "Übereinstimmung %": sm["Übereinstimmung %"],
                         "Trefferquote %": sm["Trefferquote % (manuelle Auffälligkeiten vom Agent gefunden)"],
                         "Genauigkeit %": sm["Genauigkeit % (Agent-Auffälligkeiten auch manuell auffällig)"],
                         "nur Agent": sm["nur Agent auffällig"], "nur manuell": sm["nur manuell auffällig"]})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("Trefferquote: Anteil der manuell gefundenen Auffälligkeiten, die der Agent auch findet. "
                   "Genauigkeit: Anteil der Agent-Auffälligkeiten, die auch manuell auffällig waren. "
                   "v2 aktivieren: Einstellungsmenü → „Erweiterte Prüfregeln (v2)“.")

        st.markdown("**Datenprüfung Spalte für Spalte**")
        only_diff = st.checkbox("Nur Abweichungen zeigen", value=True)
        view = cmp1[cmp1["Ergebnis"] != "übereinstimmend"] if only_diff else cmp1
        st.dataframe(
            view.style.map(lambda v: f"background-color: {'#C6EFCE' if v == 'übereinstimmend' else '#FFE699'}",
                           subset=["Ergebnis"]),
            use_container_width=True, hide_index=True,
        )

        st.markdown("**Fachliche Kontrollkriterien (Kap. 6.4)**")
        st.dataframe(compare_findings([b.heading for b in report.narrative]),
                     use_container_width=True, hide_index=True)

        if settings.show_timings:
            total = sum(report.timings.values())
            manual_h = st.session_state.get("manual_hours", 0.0)
            st.markdown("**Zeitaufwand**")
            st.write(f"Agent: {total:.1f} s" + (f" · manuell: {manual_h:.1f} h" if manual_h else
                     " · manueller Aufwand noch nicht eingetragen (Laufzeit-Bereich oben)"))

        if llm_result is not None:
            st.markdown("**Regelbasierte Auswertung ↔ Claude-Auswertung**")
            left, right = st.columns(2)
            left.markdown("*Regelbasiert*")
            for b in report.narrative:
                left.markdown(f"**{b.heading}**\n\n{b.text}")
            right.markdown(f"*Claude ({llm_result.model})*")
            for b in llm_result.blocks:
                right.markdown(f"**{b.heading}**\n\n{b.text}")

if settings.show_explorer:
    with tabs["🔎 Explorer"]:
        st.subheader("Freie Auswahl")
        names = [c.short for c in COLUMNS]
        kind = st.radio("Diagrammtyp", ["Liniendiagramm", "Streudiagramm (x/y)", "Carpetplot"], horizontal=True)
        d_min, d_max = df_full.index.min().date(), df_full.index.max().date()
        if kind != "Carpetplot":
            rng = st.date_input("Zeitraum", value=(d_min, d_max), min_value=d_min, max_value=d_max)
            start, end = (rng if isinstance(rng, tuple) and len(rng) == 2 else (d_min, d_max))
            sub = df_full.loc[str(start):str(end)]
        if kind == "Liniendiagramm":
            picked = st.multiselect("Spalten (gleiche Einheit wählen)", names, default=names[1:3])
            res = st.selectbox("Auflösung", list(RESAMPLE_MAP), index=1, key="exp_res")
            if picked:
                view = sub[picked].resample(RESAMPLE_MAP[res]).mean() if RESAMPLE_MAP[res] else sub[picked]
                units = {c.unit for c in COLUMNS if c.short in picked}
                if len(units) > 1:
                    st.warning("Verschiedene Einheiten gewählt: " + ", ".join(sorted(units)) +
                               ". Besser getrennt darstellen (keine Sekundärachsen).")
                st.plotly_chart(fx.fig_zone_comparison(view, [(n, n) for n in picked], "Freie Auswahl",
                                                       unit=", ".join(sorted(units))), use_container_width=True)
            else:
                st.info("Bitte mindestens eine Spalte wählen.")
        elif kind == "Streudiagramm (x/y)":
            cx, cy = st.columns(2)
            x_col = cx.selectbox("x-Achse", names, index=names.index("RLT KL01 Außenluft"))
            y_col = cy.selectbox("y-Achse", names, index=names.index("Stat. Heizung Geb.06 VL (Ist)"))
            st.plotly_chart(fx.fig_heating_curve(sub, x_col, y_col, f"{y_col} vs. {x_col}", x_label=x_col, y_label=y_col),
                            use_container_width=True)
        else:
            cc, cy_, cm = st.columns(3)
            col = cc.selectbox("Spalte", names, index=1)
            year = cy_.number_input("Jahr", 2020, 2035, int(df_full.index.min().year) + 1, key="exp_year")
            month = cm.number_input("Monat", 1, 12, 2, key="exp_month")
            series = df_full[col].dropna()
            lo, hi = float(series.quantile(0.01)), float(series.quantile(0.99))
            zr = st.slider("Farbskala fix (Kap. 5.2: feste Betriebsgrenzen)", float(series.min()), float(series.max()),
                           (lo, hi))
            unit = next(c.unit for c in COLUMNS if c.short == col)
            st.plotly_chart(fx.fig_carpet(df_full, col, int(year), int(month), f"{col} {int(month):02d}/{int(year)}",
                                          zmin=zr[0], zmax=zr[1], unit=unit), use_container_width=True)

with tabs["⬇️ Export"]:
    st.subheader("Bericht exportieren")
    export_report = dataclasses.replace(report, narrative=active_narrative)
    st.caption(f"Auswertungstext im Export: {narrative_source}")

    left, right = st.columns(2)
    with left:
        st.markdown("**Excel-Arbeitsmappe** – Datenprüfung + native, editierbare Diagramme")
        if st.button("Excel-Report erzeugen"):
            with st.spinner("Erzeuge Arbeitsmappe..."):
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir) / "monitoring_report.xlsx"
                    export_workbook(export_report, str(tmp_path))
                    st.session_state["xlsx_bytes"] = tmp_path.read_bytes()
        if "xlsx_bytes" in st.session_state:
            st.download_button("📥 monitoring_report.xlsx", st.session_state["xlsx_bytes"],
                               file_name="monitoring_report.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with right:
        if settings.enable_word_export:
            st.markdown("**Word-Bericht** – Gliederung, Abbildungen mit Beschriftung, Auswertung")
            if st.button("Word-Bericht erzeugen"):
                with st.spinner("Rendere Abbildungen und erzeuge Bericht (ca. 30 s)..."):
                    buf = io.BytesIO()
                    cmp_df = compare_table1(report.quality_df) if settings.show_comparison else None
                    st.session_state["docx_warnings"] = export_docx(
                        export_report, buf, narrative=active_narrative, comparison=cmp_df,
                        include_savings=settings.show_savings)
                    st.session_state["docx_bytes"] = buf.getvalue()
            for w in st.session_state.get("docx_warnings", []):
                st.warning(w)
            if "docx_bytes" in st.session_state:
                st.download_button("📥 monitoring_bericht.docx", st.session_state["docx_bytes"],
                                   file_name="monitoring_bericht.docx",
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        else:
            st.info("Word-Export ist im Einstellungsmenü ausgeschaltet.")
