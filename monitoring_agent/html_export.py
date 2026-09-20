"""
Eigenstaendiger HTML-Bericht: eine einzige Datei, die sich per Doppelklick in jedem Browser oeffnen laesst,
ohne Python und ohne Internetverbindung (plotly.js ist eingebettet). Die Diagramme bleiben interaktiv
(Zoom, Hover, Ein-/Ausblenden von Reihen). Inhalt und Reihenfolge entsprechen dem Word-Bericht.
"""

from __future__ import annotations

import html
from datetime import date

import pandas as pd

from .structure import REPORT_SECTIONS

SEVERITY = {"hoch": "#FFC7CE", "mittel": "#FFE699", "gering": "#C6EFCE"}
STATUS = {"Auffällig!": "#FFC7CE", "Plausibel": "#C6EFCE", "ja": "#C6EFCE", "nein": "#FFC7CE"}

CSS = """
:root{--bg:#ffffff;--fg:#1c2733;--muted:#5b6b7b;--line:#d5dce4;--navy:#1F3864;--soft:#f3f6fa}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 "Segoe UI",Arial,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 20px 60px}
h1{color:var(--navy);font-size:2rem;margin:.2em 0 .1em}
h2{color:var(--navy);font-size:1.4rem;margin:2.2em 0 .6em;padding-bottom:.25em;border-bottom:2px solid var(--navy)}
h3{color:var(--navy);font-size:1.1rem;margin:1.6em 0 .4em}
.sub{color:var(--muted);margin:0 0 1.2em}
.kpis{display:flex;flex-wrap:wrap;gap:12px;margin:1em 0}
.kpi{flex:1 1 170px;background:var(--soft);border:1px solid var(--line);border-radius:6px;padding:10px 14px}
.kpi b{display:block;font-size:1.4rem;color:var(--navy)}
.kpi span{color:var(--muted);font-size:.85rem}
.scroll{overflow-x:auto;margin:.6em 0 1em}
table{border-collapse:collapse;width:100%;font-size:.85rem}
th{background:var(--navy);color:#fff;text-align:left;padding:6px 8px;position:sticky;top:0}
td{border:1px solid var(--line);padding:5px 8px;vertical-align:top}
figure{margin:1.6em 0 .4em}
figcaption{font-size:.9rem;color:var(--muted);margin-top:.2em}
.text{background:var(--soft);border-left:4px solid var(--navy);padding:.5em 1em;margin:.8em 0 1.6em;border-radius:0 6px 6px 0}
.text h3{margin-top:.6em}
.note{color:var(--muted);font-size:.85rem}
nav{display:flex;flex-wrap:wrap;gap:4px 18px;background:var(--soft);border:1px solid var(--line);border-radius:6px;padding:8px 16px;margin:1em 0}
nav a{color:var(--navy)}
@media print{nav{display:none}h2{break-after:avoid}figure{break-inside:avoid}}
"""


def _fmt(value) -> str:
    if isinstance(value, float):
        if pd.isna(value):
            return ""
        return f"{value:.2f}".replace(".", ",")
    return html.escape(str(value))


def _table(df: pd.DataFrame, color_col: str | None = None, colors: dict[str, str] | None = None) -> str:
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in df.columns:
            style = ""
            if c == color_col and colors:
                bg = colors.get(str(r[c]))
                if bg:
                    style = f' style="background:{bg}"'
            cells.append(f"<td{style}>{_fmt(r[c])}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def _paragraphs(text: str) -> str:
    return "".join(f"<p>{html.escape(p)}</p>" for p in text.split("\n\n") if p.strip())


def _kpi(value: str, label: str) -> str:
    return f'<div class="kpi"><b>{html.escape(value)}</b><span>{html.escape(label)}</span></div>'


def export_html(report, path, narrative=None, comparison=None, include_savings: bool = True,
                include_assessment: bool = True, title: str = "Monitoringbericht") -> None:
    import plotly.graph_objects as go
    from plotly.offline import get_plotlyjs

    from .assessment import assessment_texts, theory_vs_practice
    from .extras import savings_explanations
    from .settings import Thresholds

    narrative = narrative if narrative is not None else report.narrative
    df = report.df
    th = getattr(report, "thresholds", None) or Thresholds()
    keys = [e.key for e in report.figures]
    placed: dict[str, list] = {}
    unassigned = []
    for b in narrative:
        valid = [k for k in b.figure_keys if k in keys]
        if valid:
            placed.setdefault(max(valid, key=keys.index), []).append(b)
        else:
            unassigned.append(b)

    n_bad = int((report.quality_df["Plausibilität"] == "Auffällig!").sum())
    out: list[str] = []
    out.append(f"<h1>{html.escape(title)}</h1>")
    out.append(f'<p class="sub">Automatisierte Auswertung durch den KI-Agenten · erstellt am {date.today():%d.%m.%Y}</p>')
    out.append('<div class="kpis">' + "".join([
        _kpi(f"{df.index.min():%d.%m.%Y} – {df.index.max():%d.%m.%Y}", "Messzeitraum"),
        _kpi(f"{len(df):,}".replace(",", "."), "Zeitschritte (15 min)"),
        _kpi(str(len(report.quality_df) - n_bad), "Spalten plausibel"),
        _kpi(str(n_bad), "Spalten auffällig"),
    ]) + "</div>")
    nav = [(f"s{i}", REPORT_SECTIONS[i]) for i in range(len(REPORT_SECTIONS))]
    out.append("<nav>" + "".join(f'<a href="#{a}">{i + 1} {html.escape(t)}</a>' for i, (a, t) in enumerate(nav)) + "</nav>")

    def section(i: int) -> None:
        out.append(f'<h2 id="s{i}">{i + 1} {html.escape(REPORT_SECTIONS[i])}</h2>')

    # 1 Einleitung und Datengrundlage
    section(0)
    out.append("<p>Der Bericht wird in fünf Zwischenschritten erarbeitet: Datenprüfung, Grafikerstellung, Auswertung, "
               "Bewertung und Berichtserstellung. Die Zahlen im Text werden aus den Messdaten berechnet. Die fachliche "
               "Einordnung bleibt Aufgabe der Bearbeiter.</p>")
    if report.coverage is not None and len(report.coverage):
        out.append("<h3>Datenabdeckung der Heiz- und Sommerperioden</h3>")
        out.append(_table(report.coverage, "Erfüllt", STATUS))

    # 2 Datenpruefung
    section(1)
    out.append("<p>Die Datenprüfung wurde automatisiert auf den Rohdaten (15-Minuten-Auflösung) durchgeführt. "
               "Grün markierte Spalten sind plausibel, rot markierte weisen Auffälligkeiten auf.</p>")
    out.append(_table(report.quality_df, "Plausibilität", STATUS))
    if report.head_table is not None:
        out.append("<h3>Messdatenkopf</h3>")
        out.append(_table(report.head_table.round(2).iloc[:, :10]))

    # 3 Grafische Aufbereitung und Auswertung
    section(2)
    out.append('<p class="note">Zu jeder Abbildung folgt direkt die zugehörige Auswertung. Die Diagramme sind '
               "interaktiv: Zoomen mit der Maus, Bereich per Doppelklick zurücksetzen, Reihen über die Legende ein- und ausblenden.</p>")
    fig_no = {e.key: i for i, e in enumerate(report.figures, start=2)}
    for entry in report.figures:
        fig = go.Figure(entry.figure)  # Kopie: das gecachte Original der App bleibt unverändert
        fig.update_layout(autosize=True, width=None)
        out.append("<figure>" + fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})
                   + f"<figcaption><b>Abbildung {fig_no[entry.key]}: {html.escape(entry.title)}.</b> "
                     f"{html.escape(entry.caption)}</figcaption></figure>")
        for b in placed.get(entry.key, []):
            refs = ", ".join(f"Abbildung {fig_no[k]}" for k in b.figure_keys if k in fig_no)
            out.append(f'<div class="text"><h3>{html.escape(b.heading)}</h3>{_paragraphs(b.text)}'
                       + (f'<p class="note">Bezug: {refs}</p>' if len(b.figure_keys) > 1 else "") + "</div>")
    for b in unassigned:
        out.append(f'<div class="text"><h3>{html.escape(b.heading)}</h3>{_paragraphs(b.text)}</div>')

    log = getattr(report, "exclusion_log", None)
    if log is not None and len(log.summary):
        n_values = f"{log.n_values:,}".replace(",", ".")
        out.append("<h3>Nicht berücksichtigte Messwerte</h3>")
        out.append(f"<p>Auf Entscheidung der Bearbeiter wurden {n_values} fehlerhafte Messwerte in {log.n_columns} "
                   "Spalte(n) von der Auswertung ausgeschlossen. Sie sind in Abbildungen, Kennwerten, Bewertung und "
                   "Einsparabschätzung nicht berücksichtigt. Die Datenprüfung bezieht sich auf die Rohdaten.</p>")
        out.append(_table(log.summary))

    # 4 Energieeinsparpotenzial
    section(3)
    if getattr(report, "savings", None) is not None and include_savings:
        intro, m1, m2, concl = savings_explanations(df, th)
        out.append(_paragraphs(intro.text))
        out.append(_table(report.savings[["Maßnahme", "Annahme", "Einsparung kWh/a", "Kosten €/a", "Anteil %"]]))
        for b in (m1, m2, concl):
            out.append(f"<h3>{html.escape(b.heading)}</h3>{_paragraphs(b.text)}")
    else:
        out.append("<p>Das Einsparpotenzial wurde für diesen Bericht nicht berechnet.</p>")

    # 5 Bewertung und 6 Zusammenfassung
    texts = None
    section(4)
    if include_assessment and report.assessment is not None and len(report.assessment):
        texts = assessment_texts(report.assessment, report.savings if include_savings else None)
        out.append(_paragraphs(texts["bewertung"]))
        out.append(_table(report.assessment[["Nr.", "Befund", "Schweregrad", "Kennzahl", "Empfehlung"]],
                          "Schweregrad", SEVERITY))
        out.append("<h3>Einstufungsregeln</h3><ul>" + "".join(
            f"<li><b>{html.escape(r['Befund'])}:</b> {html.escape(r['Einstufungsregel'])}"
            + (f" Hinweis: {html.escape(r['Hinweis'])}" if r["Hinweis"] else "") + "</li>"
            for _, r in report.assessment.iterrows()) + "</ul>")
    else:
        out.append("<p>Die Bewertung wurde für diesen Bericht nicht erzeugt.</p>")
    section(5)
    if texts:
        out.append(_paragraphs(texts["zusammenfassung"]))
        out.append("<h3>Überprüfung theoretischer Aussagen in der Praxis</h3>")
        out.append(_table(theory_vs_practice(df, th, report.savings if include_savings else None)))
    else:
        out.append("<p>Ohne Bewertung entfällt die Zusammenfassung.</p>")

    if comparison is not None and len(comparison):
        out.append(f'<h2 id="s6">{len(REPORT_SECTIONS) + 1} Vergleich manuelle Auswertung / Agent</h2>')
        out.append(_table(comparison[["Spalte", "Manuell", "Agent", "Ergebnis", "Manueller_Befund", "Agent_Befund"]]))

    page = (f'<!doctype html><html lang="de"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)}</title><style>{CSS}</style>"
            f"<script>{get_plotlyjs()}</script></head><body><main>{''.join(out)}</main></body></html>")
    if hasattr(path, "write"):
        path.write(page.encode("utf-8"))
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
