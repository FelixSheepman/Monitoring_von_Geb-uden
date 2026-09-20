"""
KI-Agent fuer die Monitoring-Auswertung - interaktive Web-App (Streamlit).

Start:
    .venv/Scripts/streamlit run app.py
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import os
import re
import tempfile
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from monitoring_agent.comparison import agreement_summary, compare_findings, compare_table1
from monitoring_agent.data_loader import load_measurements, read_manual_minmax
from monitoring_agent.exclusion import CLEAR_RULES, clear_only, find_invalid
from monitoring_agent.excel_export import export_workbook
from monitoring_agent.extras import savings_explanations
from monitoring_agent.llm_agent import MODELS, build_facts, generate_narrative, make_client
from monitoring_agent import figures as fx
from monitoring_agent.config import COLUMNS
from monitoring_agent.quality import quality_to_dataframe, run_data_quality
from monitoring_agent.report import build_report
from monitoring_agent.settings import FEATURE_LABELS, Settings, Thresholds
from monitoring_agent.process import Ctx, evaluate_criteria, optimization_hints
from monitoring_agent.structure import STEPS
from monitoring_agent.ui import (render_assessment, render_chapter8, render_data_extras, render_process,
                                 render_research)
from monitoring_agent.word_export import export_chapter8_docx, export_docx

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
    "– Ersatz für die manuelle Excel-Auswertung aus Kapitel 6 der Hausarbeit. "
    "Neu hier? Öffne den Tab „📖 Anleitung“."
)

GUIDE_PATH = Path("docs/anleitung.md")


def render_guide() -> None:
    """Zeigt docs/anleitung.md; Bilder (Markdown-Syntax ![..](img/x.png)) werden aus docs/ geladen."""
    if not GUIDE_PATH.exists():
        st.warning("Anleitung nicht gefunden (docs/anleitung.md).")
        return
    chunk: list[str] = []
    for line in GUIDE_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"!\[(.*?)\]\((.*?)\)\s*$", line)
        if m and (GUIDE_PATH.parent / m.group(2)).exists():
            if chunk:
                st.markdown("\n".join(chunk))
                chunk = []
            st.image(str(GUIDE_PATH.parent / m.group(2)), caption=m.group(1))
        else:
            chunk.append(line)
    if chunk:
        st.markdown("\n".join(chunk))

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


@st.cache_data(show_spinner=False)
def _manual_minmax(file_bytes: bytes):
    try:
        return read_manual_minmax(io.BytesIO(file_bytes))
    except Exception:
        return None


@st.cache_data(show_spinner="Führe Datenprüfung durch und erstelle Abbildungen...")
def _build(file_bytes: bytes, year: int, month: int, resample_rule: str | None, anomalies: bool,
           th: Thresholds, strict: bool, excluded: frozenset):
    df, load_seconds = _load(file_bytes)
    report = build_report(df, carpet_year=year, carpet_month=month,
                          display_resample=resample_rule, show_anomalies=anomalies,
                          thresholds=th, strict_rules=strict, excluded=excluded)
    report.timings = {"Einlesen": load_seconds, **report.timings}
    return report


input_bytes = None
if uploaded is not None:
    input_bytes = uploaded.getvalue()
elif use_sample:
    input_bytes = SAMPLE_PATH.read_bytes()

if input_bytes is None:
    st.info("Bitte eine Messdaten-.xlsx hochladen oder den Beispieldatensatz aktivieren.")
    with st.expander("📖 Anleitung", expanded=True):
        render_guide()
    st.stop()

@st.cache_data(show_spinner=False)
def _candidates(file_bytes: bytes) -> pd.DataFrame:
    return find_invalid(_load(file_bytes)[0])


MODE_KEEP = "Alle Werte behalten (wie bisher)"
MODE_SELECT = "Nur ausgewählte Werte ausschließen"
MODE_ALL = "Alle eindeutig fehlerhaften Werte ausschließen"


def _current_exclusions(cands: pd.DataFrame, file_hash: str) -> frozenset:
    """Liest die Auswahl aus dem Zustand der Widgets im Tab Datenprüfung (steht beim Rerun vor dem Zeichnen bereit)."""
    mode = st.session_state.get("excl_mode", MODE_KEEP)
    if mode == MODE_ALL:
        return clear_only(cands)
    if mode == MODE_SELECT:
        edited = (st.session_state.get(f"excl_editor_{file_hash}") or {}).get("edited_rows", {})
        rows = [cands.iloc[int(i)] for i, change in edited.items() if change.get("Ausschließen") and int(i) < len(cands)]
        return frozenset((r["Spalte"], r["rule_key"]) for r in rows)
    return frozenset()


file_hash = hashlib.md5(input_bytes).hexdigest()[:10]
try:
    candidates = _candidates(input_bytes)
    excluded = _current_exclusions(candidates, file_hash)
    report = _build(input_bytes, int(carpet_year), int(carpet_month),
                    RESAMPLE_MAP[resample_label], settings.show_anomalies, thresholds, settings.strict_rules, excluded)
except ValueError as e:
    st.error(str(e))
    st.stop()

# Bereits erzeugte Exporte passen nach einer geänderten Auswahl nicht mehr zu den Daten.
if st.session_state.get("_export_signature") != (file_hash, excluded):
    for stale in ("xlsx_bytes", "docx_bytes", "docx_warnings"):
        st.session_state.pop(stale, None)
    st.session_state["_export_signature"] = (file_hash, excluded)

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

ctx = Ctx(report=report, manual_minmax=_manual_minmax(input_bytes), assessment=report.assessment,
          coverage=report.coverage, llm_result=llm_result, manual_hours=st.session_state.get("manual_hours", 0.0))
crit = evaluate_criteria(ctx)
hints = optimization_hints(crit, ctx, thresholds.fbh_limit)

tab_names = ["🔍 Datenprüfung", "📈 Abbildungen", "🧠 Auswertung"]
if settings.show_assessment:
    tab_names.append("🏁 Bewertung")
if settings.show_comparison:
    tab_names.append("⚖️ Vergleich")
if settings.show_process:
    tab_names.append("🧭 Vorgehen")
if settings.show_research:
    tab_names.append("🎓 Forschung")
if settings.show_explorer:
    tab_names.append("🔎 Explorer")
tab_names.append("⬇️ Export")
tab_names.append("🗺️ Funktionsweise")
tab_names.append("📖 Anleitung")
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
        width="stretch", hide_index=True, height=560,
    )
    render_data_extras(report)

    st.divider()
    st.subheader("Fehlerhafte Werte behandeln")
    if candidates.empty:
        st.success("Es wurden keine einzelnen fehlerhaften Werte erkannt, die sich ausschließen ließen.")
    else:
        clear = candidates[candidates["rule_key"].isin(CLEAR_RULES)]
        pairs = candidates[~candidates["rule_key"].isin(CLEAR_RULES)]
        n_clear = f"{int(clear['Anzahl'].sum()):,}".replace(",", ".")
        st.markdown(
            f"Die Prüfung hat **{n_clear}** eindeutig fehlerhafte Werte gefunden (Nullwert-Aussetzer, Werte außerhalb "
            "des plausiblen Bereichs, Zähler-Rücksprünge). Ihr entscheidet, ob sie in die weitere Auswertung einfließen."
        )
        if len(pairs):
            n_pairs = f"{int(pairs['Anzahl'].sum()):,}".replace(",", ".")
            st.markdown(
                f"Zusätzlich gibt es **{n_pairs}** Werte in Vor-/Rücklaufpaaren, bei denen der Rücklauf über dem Vorlauf "
                "liegt. Das kann ein echter Messwert sein (z. B. Auskühlen bei stehender Pumpe). Sie werden deshalb nie "
                "automatisch ausgeschlossen, sondern nur, wenn ihr sie unter „Nur ausgewählte Werte ausschließen“ "
                "ausdrücklich abhakt."
            )
        mode = st.radio("Behandlung", [MODE_KEEP, MODE_SELECT, MODE_ALL], key="excl_mode",
                        help="Standard ist „wie bisher“: Alle Werte fließen ein, nichts ändert sich.")
        if mode == MODE_SELECT:
            editor_df = candidates.copy()
            editor_df.insert(0, "Ausschließen", False)
            st.data_editor(
                editor_df, key=f"excl_editor_{file_hash}", hide_index=True, width="stretch",
                disabled=[c for c in editor_df.columns if c != "Ausschließen"],
                column_config={
                    "Ausschließen": st.column_config.CheckboxColumn("Ausschließen", help="Haken setzen: Werte werden nicht berücksichtigt."),
                    "rule_key": None,
                    "Begründung": st.column_config.TextColumn(width="large"),
                })
        else:
            st.dataframe(candidates.drop(columns="rule_key"), width="stretch", hide_index=True)
        log = report.exclusion_log
        if len(log.summary):
            n_ex = f"{log.n_values:,}".replace(",", ".")
            st.info(f"Aktuell nicht berücksichtigt: **{n_ex}** Werte in **{log.n_columns}** "
                    f"{'Spalte' if log.n_columns == 1 else 'Spalten'}. "
                    "Sie fehlen in den Abbildungen und fließen nicht in Kennwerte, Auswertungstext, Bewertung und "
                    "Einsparpotenzial ein. Das Protokoll steht im Tab „Auswertung“.")
        st.caption("Ausgeschlossene Werte werden wie Fehlwerte behandelt. Die Tabelle oben zeigt weiterhin die "
                   "unveränderten Rohdaten; die Rohdatei wird nie verändert.")

narrative_by_key: dict[str, list] = {}
for block in active_narrative:
    for key in block.figure_keys:
        narrative_by_key.setdefault(key, []).append(block)

with tabs["📈 Abbildungen"]:
    if settings.show_anomalies and report.anomaly_counts:
        st.caption("Rote Rauten markieren erkannte Anomalien: " + " · ".join(
            f"{k}: {v}" for k, v in report.anomaly_counts.items()))
    st.caption("Die Nummerierung folgt der Hausarbeit: Abbildung 1 ist der Messdatenkopf (Tab Datenprüfung), die Diagramme beginnen bei Abbildung 2.")
    for number, entry in enumerate(report.figures, start=2):
        st.plotly_chart(entry.figure, width="stretch", key=entry.key)
        st.caption(f"**Abbildung {number}: {entry.title}.** {entry.caption}")
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

    st.divider()
    st.subheader("🚫 Nicht berücksichtigte Werte")
    log = report.exclusion_log
    if not len(log.summary):
        st.caption("Es wurden keine Werte ausgeschlossen, alle Messwerte fließen in die Auswertung ein. "
                   "Fehlerhafte Werte lassen sich im Tab „Datenprüfung“ ausschließen.")
    else:
        e1, e2, e3 = st.columns(3)
        e1.metric("Werte ausgeschlossen", f"{log.n_values:,}".replace(",", "."))
        e2.metric("Spalten betroffen", log.n_columns)
        share = 100 * log.n_values / (len(report.raw_df) * report.raw_df.shape[1])
        e3.metric("Anteil aller Messwerte", f"{share:.3f} %".replace(".", ","))
        st.dataframe(log.summary, width="stretch", hide_index=True,
                     column_config={"Begründung": st.column_config.TextColumn(width="large")})
        st.caption("Diese Werte sind in Abbildungen, Kennwerten, Auswertungstext, Bewertung und Einsparpotenzial "
                   "nicht berücksichtigt. Die Datenprüfung zeigt weiterhin die Rohdaten.")
        with st.expander(f"Einzelwerte anzeigen ({len(log.details):,})".replace(",", ".")):
            st.dataframe(log.details, width="stretch", hide_index=True,
                         column_config={"Zeitpunkt": st.column_config.DatetimeColumn(format="DD.MM.YYYY HH:mm")})
            st.download_button("📥 Einzelwerte als CSV", log.details.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                               file_name="nicht_beruecksichtigte_werte.csv", mime="text/csv")

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
        st.dataframe(sv, width="stretch", hide_index=True)
        st.caption("Bezug: gemessene Wärme (Zähler 019) und Ventilatorstrom (Zähler 021/022). Weitere Potenziale "
                   "(Pumpenabschaltung, Spreizung, Geb.08) sind mit den vorhandenen Daten nicht beziffert. "
                   "Annahmen im Einstellungsmenü unter „Schwellenwerte & Annahmen“ anpassbar.")
        for blk in savings_explanations(df_full, thresholds):
            with st.expander(blk.heading, expanded=blk.heading.startswith(("Maßnahme", "Gesamt"))):
                st.write(blk.text)

if settings.show_assessment:
    with tabs["🏁 Bewertung"]:
        render_assessment(report, settings.show_savings)

if settings.show_process:
    with tabs["🧭 Vorgehen"]:
        render_process(report, crit, llm_result)

if settings.show_research:
    with tabs["🎓 Forschung"]:
        render_research(ctx, crit, report, thresholds, settings.show_savings)

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
                run_data_quality(report.raw_df, strict=strict, fbh_limit=thresholds.fbh_limit))))
            rows.append({"Regelsatz": name, "Übereinstimmung %": sm["Übereinstimmung %"],
                         "Trefferquote %": sm["Trefferquote % (manuelle Auffälligkeiten vom Agent gefunden)"],
                         "Genauigkeit %": sm["Genauigkeit % (Agent-Auffälligkeiten auch manuell auffällig)"],
                         "nur Agent": sm["nur Agent auffällig"], "nur manuell": sm["nur manuell auffällig"]})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption("Trefferquote: Anteil der manuell gefundenen Auffälligkeiten, die der Agent auch findet. "
                   "Genauigkeit: Anteil der Agent-Auffälligkeiten, die auch manuell auffällig waren. "
                   "v2 aktivieren: Einstellungsmenü → „Erweiterte Prüfregeln (v2)“.")

        st.markdown("**Datenprüfung Spalte für Spalte**")
        only_diff = st.checkbox("Nur Abweichungen zeigen", value=True)
        view = cmp1[cmp1["Ergebnis"] != "übereinstimmend"] if only_diff else cmp1
        st.dataframe(
            view.style.map(lambda v: f"background-color: {'#C6EFCE' if v == 'übereinstimmend' else '#FFE699'}",
                           subset=["Ergebnis"]),
            width="stretch", hide_index=True,
        )

        st.markdown("**Fachliche Kontrollkriterien (Kap. 6.4)**")
        st.dataframe(compare_findings([b.heading for b in report.narrative]),
                     width="stretch", hide_index=True)

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

        render_chapter8(crit, hints, report)

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
                                                       unit=", ".join(sorted(units))), width="stretch")
            else:
                st.info("Bitte mindestens eine Spalte wählen.")
        elif kind == "Streudiagramm (x/y)":
            cx, cy = st.columns(2)
            x_col = cx.selectbox("x-Achse", names, index=names.index("RLT KL01 Außenluft"))
            y_col = cy.selectbox("y-Achse", names, index=names.index("Stat. Heizung Geb.06 VL (Ist)"))
            st.plotly_chart(fx.fig_heating_curve(sub, x_col, y_col, f"{y_col} vs. {x_col}", x_label=x_col, y_label=y_col),
                            width="stretch")
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
                                          zmin=zr[0], zmax=zr[1], unit=unit), width="stretch")

with tabs["🗺️ Funktionsweise"]:
    plan_path = Path("docs/ablaufplan.html")
    if plan_path.exists():
        components.html(plan_path.read_text(encoding="utf-8"), height=3300, scrolling=True)
    else:
        st.warning("Ablaufplan nicht gefunden (docs/ablaufplan.html).")

with tabs["📖 Anleitung"]:
    render_guide()

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
                        include_savings=settings.show_savings, include_assessment=settings.show_assessment)
                    st.session_state["docx_bytes"] = buf.getvalue()
            for w in st.session_state.get("docx_warnings", []):
                st.warning(w)
            if "docx_bytes" in st.session_state:
                st.download_button("📥 monitoring_bericht.docx", st.session_state["docx_bytes"],
                                   file_name="monitoring_bericht.docx",
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        else:
            st.info("Word-Export ist im Einstellungsmenü ausgeschaltet.")

    if settings.enable_word_export:
        st.divider()
        st.markdown("**Kapitel 8 als Word-Entwurf** – Gegenüberstellung, Vergleich, Optimierung, Diskussion und Zusammenfassung je Zwischenschritt")
        if st.button("Kapitel-8-Entwurf erzeugen"):
            buf8 = io.BytesIO()
            notes = {s: st.session_state.get(f"disc_{s}", "") for s in STEPS}
            export_chapter8_docx(buf8, crit, hints, notes, report.timings)
            st.session_state["docx8_bytes"] = buf8.getvalue()
        if "docx8_bytes" in st.session_state:
            st.download_button("📥 kapitel8_vergleich.docx", st.session_state["docx8_bytes"],
                               file_name="kapitel8_vergleich.docx",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        st.caption("Die Diskussion schreibt ihr im Tab „Vergleich“ (Bereich Kapitel 8); dort eingegebener Text wird übernommen.")
