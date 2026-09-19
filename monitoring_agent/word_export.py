"""
Word-Export.

- export_docx: Monitoringbericht nach der Gliederung aus Kap. 6 der Hausarbeit
  (Einleitung, Datenpruefung, Grafik mit Auswertung, Einsparpotenzial, Bewertung, Zusammenfassung).
  Abbildungsnummern folgen der Hausarbeit: Abbildung 1 ist der Messdatenkopf, die Diagramme beginnen bei 2.
- export_chapter8_docx: Entwurf fuer Kap. 8 (Vergleich je Zwischenschritt, 8.1 bis 8.7).
"""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .structure import REPORT_SECTIONS, STEPS

GREEN, RED, AMBER, HEADER = "C6EFCE", "FFC7CE", "FFE699", "1F3864"
SEVERITY_COLORS = {"hoch": RED, "mittel": AMBER, "gering": GREEN}
STATUS_COLORS = {"erfüllt": GREEN, "nicht erfüllt": RED, "nicht bewertbar": AMBER, "Info": "DDEBF7"}


def _shade(cell, hex_fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def _fmt(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _table(doc: Document, df: pd.DataFrame, col_widths_cm: list[float], status_col: str | None = None,
           font_pt: int = 8, colors: dict[str, str] | None = None) -> None:
    """Tabelle mit Kopfzeile. `colors` ordnet Zellwerten der Statusspalte eine Fuellfarbe zu;
    ohne `colors` gelten gruen fuer Plausibel/uebereinstimmend und sonst rot."""
    t = doc.add_table(rows=1, cols=len(df.columns))
    t.style = "Table Grid"
    for j, name in enumerate(df.columns):
        c = t.rows[0].cells[j]
        c.text = ""
        run = c.paragraphs[0].add_run(str(name))
        run.bold, run.font.size, run.font.color.rgb = True, Pt(font_pt), RGBColor(255, 255, 255)
        _shade(c, HEADER)
    for _, row in df.iterrows():
        cells = t.add_row().cells
        for j, name in enumerate(df.columns):
            cells[j].text = ""
            run = cells[j].paragraphs[0].add_run(_fmt(row[name]))
            run.font.size = Pt(font_pt)
            if status_col and name == status_col:
                if colors is not None:
                    fill = colors.get(str(row[name]))
                else:
                    fill = GREEN if str(row[name]).startswith(("Plausibel", "übereinstimmend")) else RED
                if fill:
                    _shade(cells[j], fill)
    for row in t.rows:
        for j, w in enumerate(col_widths_cm):
            row.cells[j].width = Cm(w)


def _figure_png(fig) -> bytes | None:
    try:
        return fig.to_image(format="png", width=1000, height=480, scale=2)
    except Exception:
        return None


def _new_document(title: str, subtitle: str) -> Document:
    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.2)
    doc.styles["Normal"].font.name = "Arial"
    doc.styles["Normal"].font.size = Pt(10.5)
    doc.add_heading(title, 0)
    doc.add_paragraph(subtitle)
    return doc


def _bold_caption(doc: Document, bold: str, rest: str = "") -> None:
    p = doc.add_paragraph()
    p.add_run(bold).bold = True
    if rest:
        p.add_run(rest)


# ============================================================================= Monitoringbericht

def export_docx(report, path_or_buffer, narrative=None, comparison=None, include_savings: bool = True,
                include_assessment: bool = True, title="Monitoringbericht",
                subtitle="Automatisierte Auswertung durch den KI-Agenten") -> list[str]:
    """Schreibt den Bericht. Die Auswertungstexte stehen direkt unter der zugehoerigen Abbildung.
    Gibt Warnungen zurueck (z.B. fehlende Bilder)."""
    from .assessment import assessment_texts, theory_vs_practice
    from .extras import savings_explanations
    from .settings import Thresholds

    warnings: list[str] = []
    narrative = narrative if narrative is not None else report.narrative
    df = report.df
    th = getattr(report, "thresholds", None) or Thresholds()
    keys_in_order = [e.key for e in report.figures]

    # Jeder Text steht unter der LETZTEN Abbildung, auf die er sich bezieht (dann sind alle Bezuege schon gezeigt).
    placed: dict[str, list] = {}
    unassigned = []
    for b in narrative:
        valid = [k for k in b.figure_keys if k in keys_in_order]
        if valid:
            placed.setdefault(max(valid, key=keys_in_order.index), []).append(b)
        else:
            unassigned.append(b)

    doc = _new_document(title, subtitle)
    n = 0

    def chapter(name: str) -> None:
        nonlocal n
        n += 1
        doc.add_heading(f"{n} {name}", 1)

    # ---- 1 Einleitung und Datengrundlage
    chapter(REPORT_SECTIONS[0])
    doc.add_paragraph(
        f"Messzeitraum: {df.index.min():%d.%m.%Y} bis {df.index.max():%d.%m.%Y} · {len(df):,} Zeitschritte (15 min) · "
        f"{df.shape[1]} Messspalten · erstellt am {date.today():%d.%m.%Y}".replace(",", ".")
    )
    doc.add_paragraph(
        "Der Bericht wird in fünf Zwischenschritten erarbeitet: Datenprüfung, Grafikerstellung, Auswertung, Bewertung und "
        "Berichtserstellung. Jeder Schritt wird automatisiert auf den Rohdaten durchgeführt; die Zahlen im Text werden aus den "
        "Daten berechnet. Die fachliche Einordnung bleibt Aufgabe der Bearbeiter."
    )
    if report.coverage is not None and len(report.coverage):
        doc.add_paragraph(
            "Für ein aussagekräftiges Monitoring sollten mindestens zwei Heizperioden und eine Sommerperiode erfasst sein. "
            "Die Tabelle zeigt die Abdeckung der Zeiträume mit Messdaten."
        )
        _bold_caption(doc, "Tabelle 1: Datenabdeckung der Heiz- und Sommerperioden")
        _table(doc, report.coverage, [2.6, 4.6, 2.2, 2.2, 2.2, 1.6], status_col="Erfüllt",
               colors={"ja": GREEN, "nein": RED})

    # ---- 2 Datenprüfung
    chapter(REPORT_SECTIONS[1])
    doc.add_paragraph(
        "Die Datenprüfung wurde automatisiert auf den Rohdaten (15-Minuten-Auflösung) durchgeführt. "
        "Grün markierte Spalten sind plausibel, rot markierte weisen Auffälligkeiten auf."
    )
    q = report.quality_df[["Spalte", "Bezeichnung", "Einheit", "Min", "Max", "Plausibilität", "Bewertung"]]
    _bold_caption(doc, "Tabelle 2: Datenprüfung")
    _table(doc, q, [1.0, 4.6, 1.2, 1.5, 1.5, 1.8, 5.0], status_col="Plausibilität", font_pt=7)
    if report.head_table is not None:
        doc.add_paragraph()
        head = report.head_table.copy()
        head.columns = [c if c == "Datum" else c[:14] for c in head.columns]
        head = head.iloc[:, :9].round(2)
        _table(doc, head, [2.8] + [1.6] * (head.shape[1] - 1), font_pt=6)
        _bold_caption(doc, "Abbildung 1: Messdatenkopf. ",
                      "Ausschnitt der ersten Zeitschritte und der ersten Messspalten (Spaltennamen gekürzt).")

    # ---- 3 Grafische Aufbereitung und Auswertung
    chapter(REPORT_SECTIONS[2])
    doc.add_paragraph(
        "Zu jeder Abbildung folgt direkt die zugehörige Auswertung. Betrifft eine Auswertung mehrere Abbildungen, "
        "steht sie unter der letzten davon; der Bezug ist jeweils angegeben."
    )
    fig_no = {e.key: i for i, e in enumerate(report.figures, start=2)}
    missing_images = 0
    for entry in report.figures:
        png = _figure_png(entry.figure)
        if png:
            doc.add_picture(io.BytesIO(png), width=Cm(16))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        else:
            missing_images += 1
            doc.add_paragraph("[Abbildung konnte nicht gerendert werden]")
        _bold_caption(doc, f"Abbildung {fig_no[entry.key]}: {entry.title}. ", entry.caption)
        for b in placed.get(entry.key, []):
            doc.add_heading(b.heading, 3)
            doc.add_paragraph(b.text)
            refs = [f"Abbildung {fig_no[k]}" for k in b.figure_keys if k in fig_no]
            if len(refs) > 1:
                p = doc.add_paragraph()
                r = p.add_run("Bezug: " + ", ".join(refs))
                r.italic, r.font.size = True, Pt(9)
    if missing_images:
        warnings.append(
            f"{missing_images} Abbildung(en) konnten nicht als Bild eingefügt werden "
            "(Diagramm-Rendering benötigt einen installierten Chrome/Chromium-Browser)."
        )
    for b in unassigned:
        doc.add_heading(b.heading, 3)
        doc.add_paragraph(b.text)

    # ---- 4 Energieeinsparpotenzial
    chapter(REPORT_SECTIONS[3])
    if getattr(report, "savings", None) is not None and include_savings:
        intro, m1, m2, concl = savings_explanations(df, th)
        doc.add_heading(intro.heading, 2)
        doc.add_paragraph(intro.text)
        _bold_caption(doc, "Tabelle 3: Einsparpotenzial der untersuchten Maßnahmen")
        _table(doc, report.savings[["Maßnahme", "Annahme", "Einsparung kWh/a", "Kosten €/a", "Anteil %"]],
               [3.6, 6.2, 2.4, 2.0, 1.6])
        for b in (m1, m2, concl):
            doc.add_heading(b.heading, 2)
            doc.add_paragraph(b.text)
    else:
        doc.add_paragraph("Das Einsparpotenzial wurde für diesen Bericht nicht berechnet.")

    # ---- 5 Bewertung der Ergebnisse
    chapter(REPORT_SECTIONS[4])
    texts = None
    if include_assessment and report.assessment is not None and len(report.assessment):
        texts = assessment_texts(report.assessment, report.savings if include_savings else None)
        doc.add_paragraph(texts["bewertung"])
        _bold_caption(doc, "Tabelle 4: Bewertung und Priorisierung der Befunde")
        a = report.assessment[["Nr.", "Befund", "Schweregrad", "Kennzahl", "Empfehlung"]]
        _table(doc, a, [0.9, 3.6, 1.6, 4.2, 5.9], status_col="Schweregrad", colors=SEVERITY_COLORS, font_pt=7)
        doc.add_heading("Einstufungsregeln", 3)
        for _, r in report.assessment.iterrows():
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(f"{r['Befund']}: ").bold = True
            p.add_run(r["Einstufungsregel"])
            if r["Hinweis"]:
                p.add_run(f" Hinweis: {r['Hinweis']}")
    else:
        doc.add_paragraph("Die Bewertung wurde für diesen Bericht nicht erzeugt.")

    # ---- 6 Zusammenfassung und Empfehlungen
    chapter(REPORT_SECTIONS[5])
    if texts:
        doc.add_paragraph(texts["zusammenfassung"])
        doc.add_heading("Überprüfung theoretischer Aussagen in der Praxis", 3)
        _bold_caption(doc, "Tabelle 5: Theoretische Aussagen und Praxiswerte")
        _table(doc, theory_vs_practice(df, th, report.savings if include_savings else None),
               [5.0, 1.9, 5.3, 4.0], font_pt=7)
    else:
        doc.add_paragraph("Ohne Bewertung entfällt die Zusammenfassung.")

    if comparison is not None and len(comparison):
        n += 1
        doc.add_heading(f"{n} Vergleich manuelle Auswertung / Agent", 1)
        _bold_caption(doc, "Tabelle 6: Gegenüberstellung der Datenprüfung")
        cmp_df = comparison[["Spalte", "Manuell", "Agent", "Ergebnis", "Manueller_Befund", "Agent_Befund"]]
        _table(doc, cmp_df, [1.0, 1.8, 1.8, 2.6, 4.2, 4.2], status_col="Ergebnis", font_pt=7)

    doc.save(path_or_buffer)
    return warnings


# ============================================================================= Kapitel 8

def export_chapter8_docx(path_or_buffer, crit: pd.DataFrame, hints: dict[str, str], notes: dict[str, str],
                         timings: dict[str, float] | None = None) -> None:
    """Entwurf fuer Kap. 8: je Zwischenschritt Gegenueberstellung, Vergleich, Optimierung, Diskussion, Zusammenfassung."""
    from .process import overall_summary, step_report, tool_comparison

    doc = _new_document("Kapitel 8: Vergleich der konventionellen Bearbeitung mit der durch KI-Agenten",
                        "Entwurf, automatisch aus den Kontrollkriterien erzeugt")
    doc.add_heading("8.1 Einleitung", 1)
    doc.add_paragraph(
        "Die Ergebnisse der Zwischenschritte aus Kapitel 6 (konventionell mit Excel) und Kapitel 7 (KI-Agent) werden anhand der "
        "in Kapitel 5 festgelegten Kontrollkriterien gegenübergestellt. Kriterien mit dem Vermerk „Referenzvergleich“ "
        "vergleichen direkt mit dem manuellen Ergebnis; „Eigenprüfung“ bedeutet, dass Vollständigkeit, Konfiguration oder "
        "Anforderungen geprüft werden. Die Grenzwerte sind Vorschläge und mit dem Betreuer abzustimmen. "
        "Die Abschnittsnummern (8.2 bis 8.7) sind bei Bedarf an die Gliederung der Arbeit anzupassen."
    )
    for i, step in enumerate(STEPS, start=2):
        rep = step_report(step, crit, hints, timings)
        doc.add_heading(f"8.{i} Zwischenschritt {i - 1}: {step}", 1)
        doc.add_heading(f"8.{i}.1 Gegenüberstellung der Ergebnisse für die Kontrollkriterien", 2)
        g = rep["gegenueberstellung"][["ID", "Art", "Kriterium", "Ist", "Einheit", "Soll", "Manuell (Referenz)", "Status", "Detail"]]
        _table(doc, g, [0.8, 1.8, 3.2, 0.9, 1.3, 1.6, 2.0, 1.6, 3.4], status_col="Status", colors=STATUS_COLORS, font_pt=7)
        if step == "Grafikerstellung":
            doc.add_paragraph()
            _bold_caption(doc, "Werkzeugvergleich: Excel und Python")
            _table(doc, tool_comparison(timings), [2.6, 6.0, 8.0], font_pt=7)
        doc.add_heading(f"8.{i}.2 Vergleich der Ergebnisse", 2)
        doc.add_paragraph(rep["vergleich"])
        doc.add_heading(f"8.{i}.3 Optimierung", 2)
        if rep["optimierung"]:
            for line in rep["optimierung"]:
                doc.add_paragraph(line, style="List Bullet")
        else:
            doc.add_paragraph("Für diesen Zwischenschritt ist keine Optimierung erforderlich.")
        doc.add_heading(f"8.{i}.4 Diskussion", 2)
        doc.add_paragraph(notes.get(step) or "[Diskussion von den Bearbeitern zu ergänzen]")
        doc.add_heading(f"8.{i}.5 Zusammenfassung der Ergebnisse", 2)
        doc.add_paragraph(rep["zusammenfassung"])

    summ, txt = overall_summary(crit)
    doc.add_heading(f"8.{len(STEPS) + 2} Zusammenfassung über alle Schritte und Kontrollkriterien", 1)
    _table(doc, summ, [3.0, 3.2, 1.4, 2.0, 1.4, 1.6, 1.9, 2.1], font_pt=7)
    doc.add_paragraph(txt)
    doc.save(path_or_buffer)
