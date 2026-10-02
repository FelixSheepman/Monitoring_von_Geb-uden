"""Streamlit-Ansichten fuer die Bausteine aus Kap. 4 bis 10 (Vorgehen, Bewertung, Kap. 8, Forschung)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .assessment import assessment_texts, sensor_overview, theory_vs_practice
from .buildings import GEBAEUDE, HEIZKREISE, N_HEIZKREISE, find_gebaeude
from .building_diagram import svg_netzplan
from .circuit_analysis import circuit_figures, circuit_quality, circuit_stats
from .comparison import agreement_summary, compare_table1
from .figures import carpet_period_label
from .process import (OUTLOOK, STATUS_FAIL, STATUS_INFO, STATUS_NA, STATUS_OK, agent_profile,
                      agent_variants, chapter_map, chart_types, load_research_questions, overall_summary,
                      research_answers, step_report, step_summary, tool_comparison)
from .structure import AMBER, GREEN, INFO_BLUE, RED, SEVERITY_COLORS, STEPS

STATUS_COLORS = {STATUS_OK: GREEN, STATUS_FAIL: RED, STATUS_NA: AMBER, STATUS_INFO: INFO_BLUE}


def _colored(df: pd.DataFrame, column: str, colors: dict[str, str]):
    return df.style.map(lambda v: f"background-color: {colors.get(str(v), '')}", subset=[column])


def _result_color(value: str) -> str:
    if value.startswith("bestätigt"):
        return GREEN
    if value.startswith(("teilweise", "nicht durchgängig")):
        return AMBER
    return RED


# ----------------------------------------------------------------------------- Datenpruefung (Ergaenzungen)

def render_data_extras(report) -> None:
    if report.head_table is not None:
        with st.expander("Abbildung 1: Messdatenkopf", expanded=False):
            st.dataframe(report.head_table.round(2), width="stretch", hide_index=True)
            st.caption("Die ersten Zeitschritte der Messdaten mit allen Messspalten.")
    if report.coverage is not None and len(report.coverage):
        with st.expander("Datenabdeckung der Heiz- und Sommerperioden (Anforderung Kap. 4)", expanded=True):
            st.dataframe(_colored(report.coverage, "Erfüllt", {"ja": GREEN, "nein": RED}),
                         width="stretch", hide_index=True)
            st.caption("Heizperiode: 1.10. bis 30.4., Sommerperiode: 1.6. bis 31.8. Erfüllt heißt: mindestens 80 % der Tage "
                       "haben Messdaten.")


# ----------------------------------------------------------------------------- Gebaeude und Heizkreise

def render_heizkreise(report, carpet_granularity: str, carpet_anchor, th=None) -> None:
    st.subheader("Heizungskonzept und Heizkreise")
    st.write(
        f"Die Anlage besteht aus **{N_HEIZKREISE} eigenständigen Heizkreisen** (jeweils mit eigenem Vor- und "
        "Rücklauf) in 4 Gebäuden; ein Gebäude kann mehrere Heizkreise besitzen. Der Netzplan unten zeigt, wie "
        "die Kreise an die Wärmeversorgung angeschlossen sind: rot ist der Vorlauf (warmes Wasser zum Verbraucher), "
        "blau der Rücklauf, die grau-kursive Schrift unter jedem Messpunkt nennt die zugehörige Spalte aus der "
        "Messdaten-Tabelle (Tab „Datenprüfung“) – so lässt sich jeder Wert einem Punkt im Netz zuordnen, auch ohne "
        "Vorwissen in Heizungstechnik."
    )
    st.markdown(svg_netzplan(st.session_state.get("selected_kreis")), unsafe_allow_html=True)
    st.caption(
        "Der feste Bericht in den übrigen Tabs (Datenprüfung, Abbildungen, Auswertung) zeigt immer den gesamten "
        "Datensatz mit allen 23 Spalten auf einmal – das bleibt für die vollständige Prüfung und den Abgleich mit "
        "Kapitel 6 der Arbeit nötig. Hier lässt sich zusätzlich ein einzelner Heizkreis auswählen: Karte unten "
        "anklicken (sie entspricht dem gleichnamigen Kästchen im Netzplan oben, das sich bei Auswahl farbig "
        "hervorhebt) für Datenprüfung, Kennzahlen und Diagramme nur für diesen Kreis."
    )

    cols = st.columns(len(GEBAEUDE))
    for col, geb in zip(cols, GEBAEUDE):
        with col:
            with st.container(border=True):
                # Eigene weisse Box statt reiner Textfarbe (wie bei der Carpetplot-Legende, siehe
                # figures.py): bleibt unabhaengig vom Streamlit-Theme (hell/dunkel) gut lesbar, eine
                # reine Farb-Textfarbe haette auf dunklem Grund zu wenig Kontrast haben koennen.
                st.markdown(
                    f"##### <span style='display:inline-block;background:#ffffff;border:1.5px solid {geb.farbe};"
                    f"border-radius:4px;padding:1px 9px;color:#1c2733'>{geb.name}</span>",
                    unsafe_allow_html=True,
                )
                st.caption(f"{len(geb.kreise)} Heizkreis" + ("" if len(geb.kreise) == 1 else "e"))
                for k in geb.kreise:
                    active = st.session_state.get("selected_kreis") == k.zone
                    if st.button(f"{'✅ ' if active else ''}{k.nr}. {k.short}", key=f"pick_{k.zone}",
                                width="stretch", type="primary" if active else "secondary"):
                        st.session_state["selected_kreis"] = None if active else k.zone
                        st.rerun()

    sel = st.session_state.get("selected_kreis")
    if sel is None:
        st.info("Kein Heizkreis ausgewählt. Die übrigen Tabs zeigen weiterhin den Gesamtbericht (Kap. 6) mit allen "
                "Abbildungen.")
        return

    if st.button("⤫ Auswahl aufheben (zum Gesamtbericht)"):
        st.session_state["selected_kreis"] = None
        st.rerun()

    kreis = HEIZKREISE[sel]
    geb = find_gebaeude(sel)
    st.divider()
    st.markdown(f"### {geb.name} – Heizkreis {kreis.nr}: {kreis.art}")

    stats = circuit_stats(report.df, kreis)
    if stats:
        cols = st.columns(len(stats))
        for c, (label, value) in zip(cols, stats.items()):
            c.metric(label, value)

    qdf = circuit_quality(report.quality_df, kreis)
    if len(qdf):
        st.markdown("**Datenprüfung dieses Heizkreises**")
        st.dataframe(_colored(qdf, "Plausibilität", {"Plausibel": GREEN, "Auffällig!": RED}),
                     width="stretch", hide_index=True)

    _label = carpet_period_label(carpet_granularity, pd.Timestamp(carpet_anchor))
    st.caption(f"📅 Carpetplot-Zeitfenster: **{carpet_granularity} – {_label}** (Seitenleiste ändern).")
    figs = circuit_figures(report.df, kreis, carpet_granularity, carpet_anchor, th)
    if not figs:
        st.warning("Für diesen Heizkreis liegen keine darstellbaren Messreihen vor.")
    for fig in figs:
        st.plotly_chart(fig.figure, width="stretch", key=f"kreis_{kreis.zone}_{fig.title}")
        st.caption(fig.caption)
        st.divider()
    st.caption("Diese Ansicht ergänzt den festen Bericht aus den übrigen Tabs und verändert ihn nicht. Ausgeschlossene "
               "Werte (Tab Datenprüfung) sind auch hier bereits nicht berücksichtigt.")


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
