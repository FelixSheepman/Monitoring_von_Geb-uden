"""Streamlit-Ansichten fuer die Bausteine aus Kap. 4 bis 10 (Vorgehen, Bewertung, Kap. 8, Forschung)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .assessment import assessment_texts, sensor_overview, theory_vs_practice
from .comparison import agreement_summary, compare_table1
from .process import (OUTLOOK, STATUS_FAIL, STATUS_INFO, STATUS_NA, STATUS_OK, agent_profile,
                      agent_variants, chapter_map, chart_types, load_research_questions, overall_summary,
                      research_answers, step_report, step_summary, tool_comparison)
from .structure import STEPS

SEVERITY_COLORS = {"hoch": "#FFC7CE", "mittel": "#FFE699", "gering": "#C6EFCE"}
STATUS_COLORS = {STATUS_OK: "#C6EFCE", STATUS_FAIL: "#FFC7CE", STATUS_NA: "#FFE699", STATUS_INFO: "#DDEBF7"}


def _colored(df: pd.DataFrame, column: str, colors: dict[str, str]):
    return df.style.map(lambda v: f"background-color: {colors.get(str(v), '')}", subset=[column])


def _result_color(value: str) -> str:
    if value.startswith("bestätigt"):
        return "#C6EFCE"
    if value.startswith(("teilweise", "nicht durchgängig")):
        return "#FFE699"
    return "#FFC7CE"


# ----------------------------------------------------------------------------- Datenpruefung (Ergaenzungen)

def render_data_extras(report) -> None:
    if report.head_table is not None:
        with st.expander("Abbildung 1: Messdatenkopf", expanded=False):
            st.dataframe(report.head_table.round(2), width="stretch", hide_index=True)
            st.caption("Die ersten Zeitschritte der Messdaten mit allen Messspalten.")
    if report.coverage is not None and len(report.coverage):
        with st.expander("Datenabdeckung der Heiz- und Sommerperioden (Anforderung Kap. 4)", expanded=True):
            st.dataframe(_colored(report.coverage, "Erfüllt", {"ja": "#C6EFCE", "nein": "#FFC7CE"}),
                         width="stretch", hide_index=True)
            st.caption("Heizperiode: 1.10. bis 30.4., Sommerperiode: 1.6. bis 31.8. Erfüllt heißt: mindestens 80 % der Tage "
                       "haben Messdaten.")


# ----------------------------------------------------------------------------- Bewertung (Kap. 6.5)

def render_assessment(report, include_savings: bool) -> None:
    a = report.assessment
    st.subheader("Bewertung der Ergebnisse (Kap. 6.5)")
    if a is None or a.empty:
        st.info("Keine Bewertung verfügbar.")
        return
    texts = assessment_texts(a, report.savings if include_savings else None)
    counts = a["Schweregrad"].value_counts()
    c1, c2, c3 = st.columns(3)
    c1.metric("Hoher Schweregrad", int(counts.get("hoch", 0)))
    c2.metric("Mittlerer Schweregrad", int(counts.get("mittel", 0)))
    c3.metric("Geringer Schweregrad", int(counts.get("gering", 0)))
    st.write(texts["bewertung"])
    st.dataframe(_colored(a[["Nr.", "Bereich", "Befund", "Schweregrad", "Kennzahl", "Empfehlung"]], "Schweregrad", SEVERITY_COLORS),
                 width="stretch", hide_index=True)
    st.markdown("**Einstufung im Detail**")
    for _, r in a.iterrows():
        with st.expander(f"{r['Nr.']}. {r['Befund']} – {r['Schweregrad']}"):
            st.markdown(f"**Kennzahl:** {r['Kennzahl']}")
            st.markdown(f"**Einstufungsregel:** {r['Einstufungsregel']}")
            st.markdown(f"**Empfehlung:** {r['Empfehlung']}")
            if r["Hinweis"]:
                st.warning(r["Hinweis"])
    st.markdown("**Zusammenfassung und Empfehlungen (Kap. 6.6)**")
    st.write(texts["zusammenfassung"])
    st.caption("Die Einstufung folgt offen gelegten Regeln (Maximum aus Häufigkeit und energetischer Relevanz, Mindeststufe bei "
               "Sicherheits- oder Bilanzrelevanz). Sie ersetzt nicht die fachliche Bewertung durch den Betreiber.")


# ----------------------------------------------------------------------------- Vorgehen (Kap. 4/5)

def render_process(report, crit: pd.DataFrame, llm_result) -> None:
    st.subheader("Vorgehensweise der Projektarbeit")
    st.write(
        "Die Bearbeitung gliedert sich in drei aufeinander aufbauende Abschnitte: die Erarbeitung der fachlichen und "
        "methodischen Grundlagen, die Erstellung eines Monitoringberichts auf konventionelle Weise als Vergleichsgrundlage "
        "sowie die Bearbeitung derselben Aufgabe durch KI-Agenten mit anschließender Gegenüberstellung beider Wege. "
        "Diese Ansicht zeigt, was die App zu welchem Kapitel beiträgt und wie gut der Agent die Kontrollkriterien erfüllt."
    )
    with st.expander("Kapitel-Landkarte: Was unterstützt die App wo?", expanded=False):
        st.dataframe(chapter_map(), width="stretch", hide_index=True)

    st.markdown("### Zwischenschritte und Kontrollkriterien (Kap. 5.3, 7 und 8)")
    summ = step_summary(crit)
    cols = st.columns(len(summ))
    for col, (_, r) in zip(cols, summ.iterrows()):
        rated = r["erfüllt"] + r["nicht erfüllt"]
        col.metric(r["Zwischenschritt"], f"{r['erfüllt']} von {rated}", f"{r['davon Referenzvergleich']} Referenzvergleich(e)",
                   delta_color="off")
    _, overall_txt = overall_summary(crit)
    st.info(overall_txt)
    choice = st.radio("Anzeige", ["Alle"] + STEPS, horizontal=True, key="crit_step")
    view = crit if choice == "Alle" else crit[crit["Schritt"] == choice]
    st.dataframe(_colored(view[["ID", "Schritt", "Art", "Kriterium", "Ist", "Einheit", "Soll", "Manuell (Referenz)", "Status", "Detail"]],
                          "Status", STATUS_COLORS), width="stretch", hide_index=True)
    st.caption(
        "„Referenzvergleich“ prüft direkt gegen das manuelle Ergebnis. „Eigenprüfung“ prüft Vollständigkeit, Konfiguration oder "
        "Anforderungen und belegt keine inhaltliche Übereinstimmung. Kriterien und Grenzwerte stehen in "
        "reference/kontrollkriterien.csv und sind Vorschläge; bitte mit dem Betreuer abstimmen und dort anpassen."
    )

    st.markdown("### KI-Agent: Aufbau und Varianten (Kap. 4.4 und 5.4)")
    st.dataframe(agent_profile(), width="stretch", hide_index=True)
    st.markdown("**Regelbasierter Agent gegenüber LLM-Agent**")
    st.dataframe(agent_variants(report.timings, llm_result), width="stretch", hide_index=True)

    st.markdown("### Grundlagen für Kapitel 4")
    with st.expander("Sensorik-Übersicht (Kap. 4.1): Messpunkte, Anlage und Messgröße", expanded=False):
        st.dataframe(sensor_overview(), width="stretch", hide_index=True)
        st.caption("Aus der Spaltenkonfiguration abgeleitet. Die konkreten Einbauorte der Sensoren sind im Datensatz nicht "
                   "enthalten und müssen aus den Anlagenunterlagen ergänzt werden.")
    with st.expander("Arten der grafischen Aufbereitung und Konfiguration (Kap. 4.2 und 5.2)", expanded=False):
        st.dataframe(chart_types(), width="stretch", hide_index=True)
    with st.expander("Werkzeugvergleich Excel und Python (Zwischenschritt Grafikerstellung)", expanded=False):
        st.dataframe(tool_comparison(report.timings), width="stretch", hide_index=True)


# ----------------------------------------------------------------------------- Kapitel 8

def render_chapter8(crit: pd.DataFrame, hints: dict[str, str], report) -> None:
    st.divider()
    st.subheader("Kapitel 8: Vergleich je Zwischenschritt")
    st.caption("Aufbau wie in der Gliederung der Arbeit: Gegenüberstellung, Vergleich, Optimierung, Diskussion, Zusammenfassung. "
               "Die Diskussion schreibt ihr selbst; die Eingabe fließt in den Word-Entwurf (Tab Export) ein.")
    labels = [f"8.{i} {s}" for i, s in enumerate(STEPS, start=2)] + [f"8.{len(STEPS) + 2} Gesamt"]
    tabs = st.tabs(labels)
    for tab, step in zip(tabs, STEPS):
        with tab:
            rep = step_report(step, crit, hints, report.timings)
            st.markdown("**Gegenüberstellung der Ergebnisse für die Kontrollkriterien**")
            g = rep["gegenueberstellung"][["ID", "Art", "Kriterium", "Ist", "Einheit", "Soll", "Manuell (Referenz)", "Status", "Detail"]]
            st.dataframe(_colored(g, "Status", STATUS_COLORS), width="stretch", hide_index=True)
            if step == "Grafikerstellung":
                st.markdown("**Werkzeugvergleich**")
                st.dataframe(tool_comparison(report.timings), width="stretch", hide_index=True)
            st.markdown("**Vergleich der Ergebnisse**")
            st.write(rep["vergleich"])
            st.markdown("**Optimierung**")
            if rep["optimierung"]:
                for line in rep["optimierung"]:
                    st.markdown(f"- {line}")
            else:
                st.write("Keine Optimierung erforderlich.")
            st.markdown("**Diskussion** (von euch zu schreiben)")
            st.text_area("Diskussion", key=f"disc_{step}", height=120, label_visibility="collapsed",
                         placeholder="Eure Einordnung: Warum weicht der Agent ab? Was bedeutet das für die Praxis?")
            st.markdown("**Zusammenfassung der Ergebnisse**")
            st.write(rep["zusammenfassung"])
    with tabs[-1]:
        summ, txt = overall_summary(crit)
        st.dataframe(summ, width="stretch", hide_index=True)
        st.write(txt)


# ----------------------------------------------------------------------------- Forschung (Kap. 9/10)

def render_research(ctx, crit: pd.DataFrame, report, th, include_savings: bool) -> None:
    st.subheader("Beantwortung der Forschungsfragen (Kap. 9)")
    st.caption("Die Fragen stehen in reference/forschungsfragen.csv und sind ein Entwurf: bitte mit dem Betreuer abstimmen und dort "
               "anpassen. Die Antwortentwürfe fassen die Belege aus den Ergebnissen zusammen und ersetzen nicht eure fachliche Antwort.")
    answers = research_answers(ctx, crit, agreement_summary(compare_table1(report.quality_df)), report.timings)
    for _, q in load_research_questions().iterrows():
        with st.expander(f"{q['ID']}: {q['Forschungsfrage']}", expanded=True):
            st.markdown("**Antwortentwurf mit Belegen**")
            st.write(answers.get(q["ID"], "Für diese Frage ist kein automatischer Entwurf hinterlegt; bitte selbst beantworten."))
            st.text_area("Eure Antwort", key=f"ans_{q['ID']}", height=90,
                         placeholder="Eure Antwort (bitte zusätzlich in die Arbeit übernehmen; die Eingabe wird nur in dieser Sitzung gehalten)")

    st.markdown("### Überprüfung theoretischer Aussagen in der Praxis (Kap. 4)")
    tp = theory_vs_practice(report.df, th, report.savings if include_savings else None)
    st.dataframe(tp.style.map(lambda v: f"background-color: {_result_color(str(v))}", subset=["Ergebnis"]),
                 width="stretch", hide_index=True)
    st.caption("Die theoretischen Aussagen stammen aus euren Kapiteln 4, 6.1, 6.2 und 6.4. Der Abgleich nutzt die aktuellen Schwellenwerte.")

    st.markdown("### Zusammenfassung, Empfehlungen und Ausblick (Kap. 10)")
    if report.assessment is not None and len(report.assessment):
        st.write(assessment_texts(report.assessment, report.savings if include_savings else None)["zusammenfassung"])
    st.markdown("**Ausblick (Entwurf)**")
    for item in OUTLOOK:
        st.markdown(f"- {item}")
    _, txt = overall_summary(crit)
    st.caption(txt)
