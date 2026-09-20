"""
Prozessmodell der Studienarbeit (Kap. 5 bis 9): Zwischenschritte, Kontrollkriterien, Vergleich je
Zwischenschritt (Kap. 8.2 bis 8.6), Forschungsfragen (Kap. 9) sowie Uebersichtstabellen zu Agent,
Werkzeugen und Kapiteln.

Die Kontrollkriterien (reference/kontrollkriterien.csv) werden automatisch gegen das Ergebnis des
Agenten bzw. gegen die manuelle Referenz (reference/*.csv) geprueft. Grenzwerte lassen sich in der
CSV anpassen; sie sind Vorschlaege und mit dem Betreuer abzustimmen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from .assessment import data_coverage
from .comparison import REFERENCE_DIR, agreement_summary, compare_findings, compare_table1
from .config import COLUMNS
from .quality import quality_to_dataframe, run_data_quality
from .structure import REPORT_SECTIONS, REQUIRED_SECTION_KEYWORDS, STEP_CHAPTERS, STEPS

STATUS_OK, STATUS_FAIL, STATUS_INFO, STATUS_NA = "erfüllt", "nicht erfüllt", "Info", "nicht bewertbar"

# Kriterien, die direkt gegen ein manuelles Ergebnis vergleichen. Alle anderen sind Eigenpruefungen
# (Vollstaendigkeit, Konfiguration, Anforderung) und sagen nichts ueber die inhaltliche Uebereinstimmung.
REFERENCE_IDS = {"DP2", "DP3", "DP4", "GR1", "GR2", "AW1", "BW4"}
ART_REFERENCE, ART_SELF = "Referenzvergleich", "Eigenprüfung"


@dataclass
class Ctx:
    report: object
    manual_minmax: pd.DataFrame | None = None
    assessment: pd.DataFrame | None = None
    coverage: pd.DataFrame | None = None
    llm_result: object | None = None
    manual_hours: float = 0.0


# ----------------------------------------------------------------------------- Hilfen

def _read_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(REFERENCE_DIR / name, sep=";", encoding="utf-8").fillna("")


def load_criteria() -> pd.DataFrame:
    crit = _read_csv("kontrollkriterien.csv")
    crit["Grenzwert"] = pd.to_numeric(crit["Grenzwert"], errors="coerce")
    return crit


def figure_kind(fig) -> str:
    """Diagrammtyp anhand des Haupt-Traces (erster Trace). Anomalie-Marker werden erst danach angehaengt
    und duerfen den Typ nicht veraendern."""
    main = fig.data[0]
    if main.type == "heatmap":
        return "Carpetplot"
    if main.type == "bar":
        return "Säule"
    if main.type in ("scatter", "scattergl") and main.mode == "markers":
        return "Streu"
    return "Linie"


def _has_numbers(text: str, minimum: int = 2) -> bool:
    return len(re.findall(r"\d+[.,]?\d*", text)) >= minimum


def _de(x: float) -> str:
    """Ganzzahl mit Punkt als Tausendertrennzeichen (deutsche Schreibweise)."""
    return f"{x:,.0f}".replace(",", ".")


def _pct(part: float, whole: float) -> float:
    return part / whole * 100 if whole else float("nan")


# ----------------------------------------------------------------------------- Kontrollkriterien

def _measure(ctx: Ctx) -> dict[str, tuple[float | None, str, str]]:
    """Liefert je Kriterium (Ist-Wert, Detail, manuelle Referenz)."""
    rep = ctx.report
    out: dict[str, tuple[float | None, str, str]] = {}

    cmp1 = compare_table1(rep.quality_df)
    summ = agreement_summary(cmp1)
    exp = len(COLUMNS)
    out["DP1"] = (_pct(len(rep.quality_df), exp), f"{len(rep.quality_df)} von {exp} Spalten geprüft", f"{len(cmp1)} Spalten (Tabelle 1)")

    if ctx.manual_minmax is None:
        out["DP2"] = (None, "Min-/Max-Zeilen in der Excel-Kopfzeile nicht vorhanden", "")
    else:
        ok = total = 0
        for c in COLUMNS:
            m = ctx.manual_minmax.loc[c.short]
            for key, val in (("Min", rep.raw_df[c.short].min()), ("Max", rep.raw_df[c.short].max())):
                total += 1
                ok += int(pd.notna(m[key]) and abs(val - m[key]) <= 0.01)
        out["DP2"] = (_pct(ok, total), f"{ok} von {total} Kennwerten identisch", f"{total} Kennwerte in der Kopfzeile")

    rec = summ["Trefferquote % (manuelle Auffälligkeiten vom Agent gefunden)"]
    prec = summ["Genauigkeit % (Agent-Auffälligkeiten auch manuell auffällig)"]
    man_flag = int((cmp1["Manuell"] == "Auffällig").sum())
    both = int(((cmp1["Manuell"] == "Auffällig") & (cmp1["Agent"] == "Auffällig")).sum())
    agent_flag = int((cmp1["Agent"] == "Auffällig").sum())
    out["DP3"] = (rec, f"{both} von {man_flag} manuell auffälligen Spalten auch vom Agent markiert", f"{man_flag} auffällige Spalten")
    out["DP4"] = (prec, f"{both} von {agent_flag} Agent-Auffälligkeiten auch manuell auffällig", f"{man_flag} auffällige Spalten")

    cov = ctx.coverage if ctx.coverage is not None else data_coverage(rep.df)
    heiz = cov[(cov["Zeitraum"] == "Heizperiode")]
    somm = cov[(cov["Zeitraum"] == "Sommerperiode")]
    out["DP5"] = (float((heiz["Erfüllt"] == "ja").sum()),
                  "; ".join(f"{r['Bezeichnung']}: {r['Abdeckung %']:.0f} %" for _, r in heiz.iterrows()), "mindestens 2 (Kap. 4)")
    out["DP6"] = (float((somm["Erfüllt"] == "ja").sum()),
                  "; ".join(f"{r['Bezeichnung']}: {r['Abdeckung %']:.0f} %" for _, r in somm.iterrows()), "mindestens 1 (Kap. 4)")

    manual_abb = _read_csv("manual_abbildungen.csv")
    figs = {f.key: f.figure for f in rep.figures}
    have_head = getattr(rep, "head_table", None) is not None
    available = set(figs) | ({"messdatenkopf"} if have_head else set())
    missing = manual_abb[~manual_abb["Agent_Key"].isin(available)]
    out["GR1"] = (_pct(len(manual_abb) - len(missing), len(manual_abb)),
                  f"{len(manual_abb) - len(missing)} von {len(manual_abb)} manuellen Abbildungen reproduziert"
                  + (f"; fehlt: {', '.join(missing['Titel_manuell'])}" if len(missing) else ""),
                  f"{len(manual_abb)} Abbildungen (Excel)")

    mismatched = []
    for _, r in manual_abb.iterrows():
        kind = "Tabelle" if r["Agent_Key"] == "messdatenkopf" and have_head else (figure_kind(figs[r["Agent_Key"]]) if r["Agent_Key"] in figs else None)
        if kind != r["Diagrammtyp"]:
            mismatched.append(f"Abb. {r['Nr']} ({r['Diagrammtyp']} ↔ {kind})")
    out["GR2"] = (_pct(len(manual_abb) - len(mismatched), len(manual_abb)),
                  "alle Typen identisch" if not mismatched else "Abweichungen: " + "; ".join(mismatched), "Excel-Diagrammtypen")

    checks: list[tuple[str, bool]] = []
    checks.append(("keine Sekundärachse", all("yaxis2" not in f.layout.to_plotly_json() for f in figs.values())))
    carpets = [figs[k] for k in ("carpet_rlt_vl", "carpet_rlt_rl") if k in figs]
    checks.append(("Carpetplots mit fester Farbskala", bool(carpets) and all(
        f.data[0].zmin is not None and f.data[0].zmax is not None for f in carpets)))
    hk = figs.get("heizkurve")
    checks.append(("Heizkurve als Punktwolke mit Trendlinie", hk is not None and any(t.mode == "markers" for t in hk.data)
                   and any(t.name == "Regressionslinie" for t in hk.data)))
    soll_ist = [figs[k] for k in ("regelguete_stat_heizung", "regelguete_fbh") if k in figs]
    checks.append(("Soll und Ist gemeinsam auf einer Achse", bool(soll_ist) and all(
        {"Soll-Vorlauf", "Ist-Vorlauf"} <= {t.name for t in f.data} for f in soll_ist)))
    passed = sum(ok for _, ok in checks)
    out["GR3"] = (_pct(passed, len(checks)), "; ".join(f"{n}: {'ja' if ok else 'nein'}" for n, ok in checks), "Regeln aus Kap. 5.2")

    labelled = sum(1 for f in rep.figures if f.figure.layout.title.text and f.figure.layout.xaxis.title.text and f.caption)
    out["GR4"] = (_pct(labelled, len(rep.figures)), f"{labelled} von {len(rep.figures)} Abbildungen mit Titel, Achsenbeschriftung und Bildunterschrift", "")

    heads = [b.heading for b in rep.narrative]
    fc = compare_findings(heads)
    n_found = int((fc["Vom Agent gefunden"] == "ja").sum())
    out["AW1"] = (_pct(n_found, len(fc)), f"{n_found} von {len(fc)} manuellen Befunden gefunden", f"{len(fc)} Befunde (Kap. 6.4)")
    quant = sum(_has_numbers(b.text) for b in rep.narrative)
    out["AW2"] = (_pct(quant, len(rep.narrative)), f"{quant} von {len(rep.narrative)} Texten mit ≥ 2 Zahlenwerten", "")
    ref = sum(bool(b.figure_keys) for b in rep.narrative)
    out["AW3"] = (_pct(ref, len(rep.narrative)), f"{ref} von {len(rep.narrative)} Texten mit Abbildungsbezug", "")
    extra = [h for h in heads if h not in set(fc["Agent_Block"])]
    out["AW4"] = (float(len(extra)), ("Zusätzlich: " + "; ".join(extra)) if extra else "keine zusätzlichen Befunde", "")

    a = ctx.assessment
    if a is None or a.empty:
        for k in ("BW1", "BW2", "BW3", "BW4"):
            out[k] = (None, "Bewertung nicht erzeugt", "")
    else:
        done = int(((a["Schweregrad"] != "") & (a["Empfehlung"] != "")).sum())
        out["BW1"] = (_pct(done, len(a)), f"{done} von {len(a)} Befunden mit Schweregrad und Empfehlung", "")
        rule = int(((a["Einstufungsregel"] != "") & (a["Kennzahl"] != "")).sum())
        out["BW2"] = (_pct(rule, len(a)), f"{rule} von {len(a)} Einstufungen mit Regel und Kennzahl", "")
        sv = rep.savings
        if sv is not None and (sv["Maßnahme"] == "Summe").any():
            share = float(sv[sv["Maßnahme"] == "Summe"].iloc[0]["Anteil %"])
            out["BW3"] = (1.0, f"{share:.1f} % beziffert gegenüber 10 % Ziel", "Ziel 10 % (Kap. 4)")
        else:
            out["BW3"] = (0.0, "Einsparpotenzial nicht berechnet (Funktion ausgeschaltet)", "Ziel 10 % (Kap. 4)")
        mb = _read_csv("manual_bewertung.csv")
        if mb.empty:
            out["BW4"] = (None, "Referenz fehlt: reference/manual_bewertung.csv ist leer (Kap. 6.5 der Hausarbeit)", "nicht hinterlegt")
        else:
            merged = a.merge(mb, left_on="Schlüssel", right_on="Befund_Key")
            same = int((merged["Schweregrad"] == merged["Manuell_Schweregrad"]).sum())
            out["BW4"] = (_pct(same, len(mb)), f"{same} von {len(mb)} manuellen Einstufungen identisch", f"{len(mb)} Einstufungen")

    present = sum(any(k in s for s in REPORT_SECTIONS) for k in REQUIRED_SECTION_KEYWORDS)
    out["BE1"] = (_pct(present, len(REQUIRED_SECTION_KEYWORDS)), f"{present} von {len(REQUIRED_SECTION_KEYWORDS)} Pflichtabschnitten in der Berichtsgliederung", "Gliederung Kap. 6.1–6.6")
    cap = sum(bool(f.caption) and bool(f.title) for f in rep.figures)
    out["BE2"] = (_pct(cap, len(rep.figures)), f"{cap} von {len(rep.figures)} Abbildungen mit Nummer und Bildunterschrift", "")
    return out


def evaluate_criteria(ctx: Ctx, criteria: pd.DataFrame | None = None) -> pd.DataFrame:
    crit = criteria if criteria is not None else load_criteria()
    measured = _measure(ctx)
    rows = []
    for _, c in crit.iterrows():
        value, detail, manual = measured.get(c["ID"], (None, "Kriterium nicht implementiert", ""))
        limit, op = c["Grenzwert"], c["Vergleich"]
        if op == "info":
            status, soll = STATUS_INFO, "informativ"
        elif value is None or pd.isna(value):
            status, soll = STATUS_NA, f"{op} {limit:g} {c['Einheit']}"
        else:
            ok = value >= limit if op == ">=" else value <= limit
            status, soll = (STATUS_OK if ok else STATUS_FAIL), f"{op} {limit:g} {c['Einheit']}"
        rows.append({"ID": c["ID"], "Schritt": c["Schritt"], "Kapitel": STEP_CHAPTERS.get(c["Schritt"], ""),
                     "Art": ART_REFERENCE if c["ID"] in REFERENCE_IDS else ART_SELF,
                     "Kriterium": c["Kriterium"], "Ist": value, "Einheit": c["Einheit"], "Soll": soll,
                     "Manuell (Referenz)": manual, "Status": status, "Detail": detail})
    return pd.DataFrame(rows)


def step_summary(crit: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for step in STEPS:
        sub = crit[crit["Schritt"] == step]
        rated = sub[sub["Status"].isin([STATUS_OK, STATUS_FAIL])]
        ok = int((rated["Status"] == STATUS_OK).sum())
        rows.append({"Zwischenschritt": step, "Kapitel": STEP_CHAPTERS[step], "Kriterien": len(sub),
                     "davon Referenzvergleich": int((rated["Art"] == ART_REFERENCE).sum()), "erfüllt": ok,
                     "nicht erfüllt": int((rated["Status"] == STATUS_FAIL).sum()),
                     "nicht bewertbar/Info": int((~sub["Status"].isin([STATUS_OK, STATUS_FAIL])).sum()),
                     "Erfüllungsgrad %": round(_pct(ok, len(rated)), 0) if len(rated) else float("nan")})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- Kap. 8: Vergleich je Zwischenschritt

def optimization_hints(crit: pd.DataFrame, ctx: Ctx, fbh_limit: float = 40.0) -> dict[str, str]:
    """Optimierungsvorschlaege fuer nicht erfuellte oder nicht bewertbare Kriterien (Kap. 8.x.3)."""
    hints: dict[str, str] = {}
    failing = set(crit[crit["Status"].isin([STATUS_FAIL, STATUS_NA])]["ID"])
    if failing & {"DP3", "DP4"}:
        v2 = agreement_summary(compare_table1(quality_to_dataframe(run_data_quality(ctx.report.raw_df, strict=True, fbh_limit=fbh_limit))))
        rec = v2["Trefferquote % (manuelle Auffälligkeiten vom Agent gefunden)"]
        prec = v2["Genauigkeit % (Agent-Auffälligkeiten auch manuell auffällig)"]
        hints["DP3"] = (f"Erweiterte Prüfregeln (v2) aktivieren: Die Trefferquote steigt dann auf {rec:.0f} %. "
                        f"Die Genauigkeit liegt bei {prec:.0f} %.")
        hints["DP4"] = ("Zusätzliche Agent-Auffälligkeiten (z. B. Rücklauf über Vorlauf, Zählerrücksprünge, Nullwerte in Sollwerten) "
                        "fachlich prüfen: Sind sie berechtigt, liegt die Lücke in der manuellen Prüfung. Andernfalls Schwellen "
                        "anheben, z. B. Rücklauf über Vorlauf erst ab 5 % der Zeitschritte melden.")
    generic = {
        "DP1": "Fehlende Spalten in der Spaltenzuordnung (config.py) ergänzen.",
        "DP2": "Abweichende Kennwerte klären: andere Datenbasis oder Rundung in der manuellen Auswertung.",
        "DP5": "Fehlende Monate der Heizperiode beim Betreiber nachfordern und den Datensatz erweitern.",
        "DP6": "Fehlende Sommermonate nachfordern oder die Anforderung in der Arbeit begründet anpassen.",
        "GR1": "Fehlende Abbildungen im Agenten ergänzen (figures.py, report.py).",
        "GR2": "Diagrammtyp der abweichenden Abbildung angleichen oder die Abweichung fachlich begründen.",
        "GR3": "Konfigurationsregel in figures.py nachziehen (Achsen, Farbskala, Trendlinie).",
        "GR4": "Titel, Achsenbeschriftung und Bildunterschrift für die betroffenen Abbildungen ergänzen.",
        "AW1": "Für den fehlenden Befund eine Auswertungsregel in narrative.py ergänzen.",
        "AW2": "Auswertungstexte um berechnete Kennzahlen erweitern.",
        "AW3": "Texte einer Abbildung zuordnen (figure_keys).",
        "BW1": "Fehlende Empfehlungen im Maßnahmenkatalog (assessment.py) ergänzen.",
        "BW2": "Einstufungsregel und Kennzahl für jeden Befund ausgeben.",
        "BW3": "Funktion „Energieeinsparpotenzial“ im Einstellungsmenü einschalten.",
        "BW4": "Manuelle Bewertung aus Kap. 6.5 in reference/manual_bewertung.csv eintragen (Spalten Befund_Key;Manuell_Schweregrad;Manuelle_Empfehlung), damit der Vergleich möglich wird.",
        "BE1": "Fehlende Abschnitte in die Berichtsgliederung (structure.py, word_export.py) aufnehmen.",
        "BE2": "Bildunterschriften für alle Abbildungen ergänzen.",
    }
    for id_ in failing:
        hints.setdefault(id_, generic.get(id_, "Kriterium prüfen und Ursache klären."))
    return hints


def tool_comparison(timings: dict[str, float] | None) -> pd.DataFrame:
    """Werkzeugvergleich Excel (konventionell) und Python/Plotly (Agent) fuer den Zwischenschritt Grafikerstellung."""
    gr = f"{timings['Grafiken']:.1f} s für alle Abbildungen" if timings and "Grafiken" in timings else "Sekunden (siehe Laufzeitmessung)"
    return pd.DataFrame([
        {"Aspekt": "Erstellung", "Excel (konventionell)": "Manuell je Diagramm (Pivot-Tabelle, Formatierung, Achsen)", "Python/Plotly (Agent)": f"Skript erzeugt alle Abbildungen automatisch: {gr}"},
        {"Aspekt": "Carpetplot", "Excel (konventionell)": "Pivot-Tabelle mit bedingter Formatierung, Farbskala manuell fixiert (Kap. 5.2)", "Python/Plotly (Agent)": "Heatmap mit fest hinterlegter Farbskala als Parameter"},
        {"Aspekt": "Reproduzierbarkeit", "Excel (konventionell)": "Abhängig von manuellen Einstellungen", "Python/Plotly (Agent)": "Gleiche Daten ergeben gleiche Abbildungen; durch Tests abgesichert"},
        {"Aspekt": "Neue Daten", "Excel (konventionell)": "Diagramme und Pivots müssen manuell angepasst werden", "Python/Plotly (Agent)": "Neue Datei hochladen, Abbildungen entstehen neu"},
        {"Aspekt": "Interaktivität", "Excel (konventionell)": "Statische Diagramme im Dokument", "Python/Plotly (Agent)": "Zoom, Hover, Filter in der Web-App; statische Bilder im Word-Bericht"},
        {"Aspekt": "Nachbearbeitung", "Excel (konventionell)": "Direkt im Diagramm möglich", "Python/Plotly (Agent)": "Excel-Export mit nativen, editierbaren Diagrammen vorhanden"},
    ])


def step_report(step: str, crit: pd.DataFrame, hints: dict[str, str], timings: dict[str, float] | None = None) -> dict:
    """Bausteine fuer Kap. 8.x: Gegenueberstellung, Vergleich, Optimierung, Zusammenfassung (Diskussion schreibt ihr selbst)."""
    sub = crit[crit["Schritt"] == step]
    rated = sub[sub["Status"].isin([STATUS_OK, STATUS_FAIL])]
    ok = int((rated["Status"] == STATUS_OK).sum())
    fail = rated[rated["Status"] == STATUS_FAIL]
    na = sub[sub["Status"] == STATUS_NA]
    parts = [f"Für den Zwischenschritt {step} wurden {len(sub)} Kontrollkriterien geprüft. {ok} von {len(rated)} bewertbaren Kriterien sind erfüllt."]
    n_ref = int((rated["Art"] == ART_REFERENCE).sum())
    if len(rated) and n_ref == 0:
        parts.append("Für diesen Schritt liegt keine manuelle Referenz vor: Die Kriterien prüfen Vollständigkeit und Nachvollziehbarkeit, "
                     "nicht die inhaltliche Übereinstimmung mit einer manuellen Lösung.")
    elif len(rated):
        parts.append(f"{n_ref} von {len(rated)} bewertbaren Kriterien vergleichen direkt mit der manuellen Referenz, die übrigen sind Eigenprüfungen.")
    if len(fail):
        parts.append("Abweichungen: " + "; ".join(
            f"{r['Kriterium']} (Ist {r['Ist']:.0f} {r['Einheit']}, Soll {r['Soll']})" for _, r in fail.iterrows()) + ".")
    if len(na):
        parts.append("Nicht bewertbar wegen fehlender Referenz: " + "; ".join(na["Kriterium"]) + ".")
    vergleich = " ".join(parts)

    optim = [f"{r['ID']}: {hints[r['ID']]}" for _, r in sub.iterrows() if r["ID"] in hints]
    if not len(fail) and not len(na):
        zusammenfassung = f"Der Agent erreicht im Zwischenschritt {step} alle Kontrollkriterien und liegt damit mindestens auf dem Niveau der konventionellen Bearbeitung."
    else:
        zusammenfassung = (f"Der Agent erfüllt im Zwischenschritt {step} {ok} von {len(rated)} bewertbaren Kriterien. "
                           "Die Abweichungen sind oben genannt; die Optimierungsvorschläge zeigen, wie sie sich beheben lassen.")
    if step == "Grafikerstellung":
        zusammenfassung += (" Bei der Bewertung ist zu berücksichtigen, dass die konventionelle Bearbeitung mit Excel und die "
                            "KI-gestützte mit Python-Skripten erfolgt (siehe Werkzeugvergleich).")
    return {"gegenueberstellung": sub.drop(columns=["Kapitel"]), "vergleich": vergleich, "optimierung": optim, "zusammenfassung": zusammenfassung}


def overall_summary(crit: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    summ = step_summary(crit)
    rated = crit[crit["Status"].isin([STATUS_OK, STATUS_FAIL])]
    ok = int((rated["Status"] == STATUS_OK).sum())
    weakest = summ.dropna(subset=["Erfüllungsgrad %"]).sort_values("Erfüllungsgrad %").head(1)
    ref = rated[rated["Art"] == ART_REFERENCE]
    ref_ok = int((ref["Status"] == STATUS_OK).sum())
    txt = (f"Über alle {len(STEPS)} Zwischenschritte sind {ok} von {len(rated)} bewertbaren Kontrollkriterien erfüllt "
           f"({_pct(ok, len(rated)):.0f} %). Davon vergleichen {len(ref)} direkt mit der manuellen Referenz ({ref_ok} erfüllt); "
           f"die übrigen {len(rated) - len(ref)} sind Eigenprüfungen und belegen Vollständigkeit, nicht inhaltliche Übereinstimmung.")
    if len(weakest) and weakest.iloc[0]["Erfüllungsgrad %"] < 100:
        w = weakest.iloc[0]
        txt += f" Den größten Optimierungsbedarf hat der Zwischenschritt {w['Zwischenschritt']} ({w['Erfüllungsgrad %']:.0f} % erfüllt)."
    return summ, txt


# ----------------------------------------------------------------------------- Kap. 9 / 10

def load_research_questions() -> pd.DataFrame:
    return _read_csv("forschungsfragen.csv")


def research_answers(ctx: Ctx, crit: pd.DataFrame, cmp_summary: dict, timings: dict[str, float]) -> dict[str, str]:
    """Antwortentwuerfe mit Belegen aus den Ergebnissen. Sie muessen von euch fachlich eingeordnet werden."""
    rated = crit[crit["Status"].isin([STATUS_OK, STATUS_FAIL])]
    ok = int((rated["Status"] == STATUS_OK).sum())
    rec = cmp_summary["Trefferquote % (manuelle Auffälligkeiten vom Agent gefunden)"]
    prec = cmp_summary["Genauigkeit % (Agent-Auffälligkeiten auch manuell auffällig)"]
    fc = compare_findings([b.heading for b in ctx.report.narrative])
    total = sum(timings.values())
    sv = ctx.report.savings
    tot = sv[sv["Maßnahme"] == "Summe"].iloc[0] if sv is not None else None
    answers = {}
    answers["FF1"] = (f"Der Agent erfüllt {ok} von {len(rated)} bewertbaren Kontrollkriterien ({_pct(ok, len(rated)):.0f} %). "
                      f"Er findet {int((fc['Vom Agent gefunden'] == 'ja').sum())} von {len(fc)} manuell festgestellten fachlichen Befunden, "
                      f"in der Datenprüfung liegen Trefferquote bei {rec:.0f} % und Genauigkeit bei {prec:.0f} %. "
                      "Die Reproduktion ist damit weitgehend gelungen; Abweichungen betreffen vor allem zusätzliche, vom Agenten strenger bewertete Spalten.")
    if ctx.manual_hours > 0:
        answers["FF2"] = (f"Die Bearbeitung durch den Agenten dauert {total:.1f} s (davon {timings.get('Einlesen', 0):.1f} s Einlesen der Excel-Datei) "
                          f"gegenüber {ctx.manual_hours:.1f} h manuell. Das entspricht einem Faktor von rund {ctx.manual_hours * 3600 / max(total, 0.001):,.0f}."
                          .replace(",", "."))
    else:
        answers["FF2"] = (f"Die Bearbeitung durch den Agenten dauert {total:.1f} s. Für den Vergleich fehlt der manuelle Zeitaufwand; "
                          "bitte im Bereich „Laufzeit des Agenten“ (Kennzahlen oben) in Stunden eintragen.")
    if tot is not None:
        gap = 10 - tot["Anteil %"]
        head = (f"Beziffert werden {_de(tot['Einsparung kWh/a'])} kWh pro Jahr ({_de(tot['Kosten €/a'])} € pro Jahr), "
                f"das sind {tot['Anteil %']:.1f} % des Gesamtverbrauchs. ")
        tail = ("Das Ziel von 10 % wird erreicht." if gap <= 0 else
                f"Das Ziel von 10 % wird um {gap:.1f} Prozentpunkte verfehlt; weiteres Potenzial ist erkennbar, aber nicht beziffert.")
        answers["FF3"] = head + tail
    else:
        answers["FF3"] = "Das Einsparpotenzial ist ausgeschaltet; bitte im Einstellungsmenü aktivieren."
    fails = crit[crit["Status"] == STATUS_FAIL]["Kriterium"].tolist()
    llm = ""
    if ctx.llm_result is not None:
        llm = (f" Die LLM-Auswertung ({ctx.llm_result.model}) benötigte {ctx.llm_result.seconds:.1f} s und "
               f"{ctx.llm_result.output_tokens} Ausgabe-Tokens.")
    answers["FF4"] = ("Grenzen des Agenten: Er kennt weder Nutzung noch Anlagenkonzept und stuft rein nach Regeln und Kennzahlen ein; "
                      "Annahmen zum Einsparpotenzial sind Schätzungen; die Spaltenzuordnung ist an das Datenlayout gebunden."
                      + (" Nicht erfüllte Kriterien: " + "; ".join(fails) + "." if fails else " Alle bewertbaren Kriterien sind erfüllt.") + llm)
    return answers


OUTLOOK = [
    "Echter LLM-Agent mit Werkzeugaufrufen: Ein Sprachmodell wählt die Zwischenschritte selbst und ruft die vorhandenen Prüf-, Grafik- und Bewertungsfunktionen auf.",
    "Anbindung an die Gebäudeleittechnik: Laufende Auswertung statt einmaliger Berichte, mit automatischer Meldung neuer Auffälligkeiten.",
    "Weitere Messgrößen: Pumpenstrom, Volumenströme und Raumtemperaturen würden die bisher nicht bezifferten Potenziale messbar machen.",
    "Lernende Verfahren zur Anomalieerkennung als Ergänzung der regelbasierten Prüfung, validiert gegen die hier erarbeiteten Kontrollkriterien.",
    "Übertragung auf weitere Objekte durch Anpassung der Spaltenzuordnung und Schwellenwerte.",
]


# ----------------------------------------------------------------------------- Uebersichten (Kap. 4/5)

def agent_profile() -> pd.DataFrame:
    return pd.DataFrame([
        {"Bestandteil": "Wahrnehmung", "Umsetzung in der App": "Einlesen der Excel-Messdaten und Zuordnung der Spalten zu Messpunkten (data_loader, config)"},
        {"Bestandteil": "Planung", "Umsetzung in der App": "Feste Abfolge der Zwischenschritte: Datenprüfung → Grafikerstellung → Auswertung → Bewertung → Berichtserstellung"},
        {"Bestandteil": "Werkzeuge", "Umsetzung in der App": "Prüfregeln (quality), Diagramme (figures), Kennzahlen (metrics, extras), Bewertung (assessment), Export (Word, Excel)"},
        {"Bestandteil": "Kontext/Gedächtnis", "Umsetzung in der App": "Schwellenwerte und Annahmen, Referenzdaten der manuellen Auswertung (reference/*.csv)"},
        {"Bestandteil": "Handeln/Ausgabe", "Umsetzung in der App": "Tabellen, Abbildungen, Auswertungstexte, Bewertung, Berichte"},
        {"Bestandteil": "Kontrolle", "Umsetzung in der App": "Kontrollkriterien je Zwischenschritt (diese Ansicht) und automatische Tests (pytest)"},
        {"Bestandteil": "Optionales Sprachmodell", "Umsetzung in der App": "Claude formuliert Auswertungstexte aus den berechneten Kennzahlen (llm_agent); rechnet selbst nichts"},
    ])


def agent_variants(timings: dict[str, float] | None, llm_result=None) -> pd.DataFrame:
    rule_t = f"{timings.get('Auswertungstext', 0):.2f} s" if timings else "unter 1 s"
    llm_t = f"{llm_result.seconds:.1f} s, {llm_result.output_tokens} Ausgabe-Tokens" if llm_result is not None else "noch nicht ausgeführt"
    return pd.DataFrame([
        {"Merkmal": "Zahlen", "Regelbasierter Agent": "Deterministisch berechnet", "LLM-Agent (Claude)": "Gleiche berechnete Kennzahlen; das Modell darf keine erfinden"},
        {"Merkmal": "Reproduzierbarkeit", "Regelbasierter Agent": "Identisches Ergebnis bei gleichen Daten", "LLM-Agent (Claude)": "Formulierung kann bei jedem Lauf variieren"},
        {"Merkmal": "Nachvollziehbarkeit", "Regelbasierter Agent": "Jede Aussage folgt einer Regel im Code", "LLM-Agent (Claude)": "Einordnung durch das Modell, Belege bleiben die Kennzahlen"},
        {"Merkmal": "Formulierung", "Regelbasierter Agent": "Vorgegebene Textbausteine mit berechneten Werten", "LLM-Agent (Claude)": "Frei formulierter Fließtext, verknüpft Befunde"},
        {"Merkmal": "Laufzeit Auswertungstext", "Regelbasierter Agent": rule_t, "LLM-Agent (Claude)": llm_t},
        {"Merkmal": "Abhängigkeiten", "Regelbasierter Agent": "Keine", "LLM-Agent (Claude)": "API-Key und Internetverbindung, Kosten je Aufruf"},
    ])


def chapter_map() -> pd.DataFrame:
    return pd.DataFrame([
        {"Kapitel": "4 Theoretische Grundlagen", "Inhalt": "Monitoring, grafische Darstellungsformen, Anlagentechnik, Sensorik, KI-Agenten",
         "Unterstützung in der App": "Sensorik-Übersicht, Diagrammtypen und Konfigurationsregeln (Tab Vorgehen), Agent-Steckbrief, Glossar der Anleitung"},
        {"Kapitel": "5 Vorbereitung", "Inhalt": "Zwischenschritte, Kontrollkriterien, Vorauswahl KI-Agent",
         "Unterstützung in der App": "Tab Vorgehen: Zwischenschritte, Kontrollkriterien, Agent-Steckbrief und Varianten"},
        {"Kapitel": "6 Konventioneller Bericht", "Inhalt": "Datenprüfung, Grafiken, Auswertung, Bewertung, Bericht in Excel",
         "Unterstützung in der App": "Manuelle Referenz in reference/*.csv, Tab Vergleich"},
        {"Kapitel": "7 Nachweisführung mit KI-Agent", "Inhalt": "Agent auf jeden Zwischenschritt anwenden",
         "Unterstützung in der App": "Tabs Datenprüfung, Abbildungen, Auswertung, Bewertung, Export"},
        {"Kapitel": "8 Vergleich", "Inhalt": "Gegenüberstellung, Vergleich, Optimierung, Diskussion, Zusammenfassung je Zwischenschritt",
         "Unterstützung in der App": "Tab Vergleich (8.2–8.6) und Word-Export „Kapitel 8“"},
        {"Kapitel": "9 Forschungsfragen", "Inhalt": "Beantwortung der Forschungsfragen", "Unterstützung in der App": "Tab Forschung: Antwortentwürfe mit Belegen"},
        {"Kapitel": "10 Zusammenfassung", "Inhalt": "Ergebnisse, Empfehlungen, Ausblick", "Unterstützung in der App": "Tab Forschung: Theorie-Praxis-Abgleich, Empfehlungen, Ausblick; Word-Bericht"},
    ])


def chart_types() -> pd.DataFrame:
    """Diagrammtypen und ihre Konfiguration (Kap. 4.2 und 5.2 der Hausarbeit)."""
    return pd.DataFrame([
        {"Diagrammtyp": "Liniendiagramm", "Einsatz": "Regelgüte (Soll/Ist), Tag-Nacht-Zyklen, Zonenvergleich, Spreizung",
         "Konfiguration in der App": "Datum auf der x-Achse; keine Sekundärachse bei gleicher Einheit (z. B. °C)"},
        {"Diagrammtyp": "Streudiagramm", "Einsatz": "Abhängigkeit zweier Größen, z. B. Heizkurve (Außentemperatur/Vorlauf)",
         "Konfiguration in der App": "Unverbundene Punktwolke mit linearer Trendlinie zur Bestimmung der Steilheit"},
        {"Diagrammtyp": "Säulen-/Flächendiagramm", "Einsatz": "Kumulierte Messdaten und Energiebilanzen, Tages- und Monatswerte",
         "Konfiguration in der App": "Tageswerte aus der Differenz der Zählerstände"},
        {"Diagrammtyp": "Carpetplot", "Einsatz": "Betriebszustände über Tag und Monat auf einen Blick",
         "Konfiguration in der App": "Datum in den Spalten, Uhrzeit in den Zeilen, Farbskala fest auf 20–65 °C (blau niedrig, rot hoch)"},
    ])
