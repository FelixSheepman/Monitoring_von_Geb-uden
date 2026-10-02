"""
Exportiert den Report als eigenstaendige .xlsx-Arbeitsmappe - das direkte
Gegenstueck zur bisherigen manuellen Excel-Auswertung (Kapitel 6 der
Hausarbeit), aber automatisch erzeugt:

- Blatt "Datenpruefung": Tabelle 1 mit Ampel-Farbcodierung (Plausibel/Auffaellig)
- Ein Blatt je Liniendiagramm/Streudiagramm/Saeulendiagramm mit nativem
  Excel-Chart-Objekt (weiterhin in Excel bearbeitbar)
- Carpetplot-Blaetter ueber Pivot + bedingte Formatierung (3-Farben-Skala,
  fixe Grenzwerte) - exakt die in Kap. 5.2 beschriebene Technik
- Blaetter "Einsparpotenzial" (Kap. 4), "Bewertung" (Kap. 5, mit Schweregrad-Ampel),
  "Theorie-Praxis-Vergleich" (Kap. 6) und "Vergleich Agent-Manuell" (Kap. 8) - dieselben
  Tabellen wie in Word-/HTML-Export, damit alle drei Formate denselben Bericht zeigen

Zeitreihen mit 15-Min-Raster werden fuer die Excel-Charts auf Stundenwerte
verdichtet (Performance/Lesbarkeit); die interaktive Web-App zeigt die volle
Aufloesung.
"""

from __future__ import annotations

import pandas as pd
import xlsxwriter

from .metrics import daily_consumption
from .narrative import place_by_figure

HEADER_FMT = dict(bold=True, bg_color="#1F3864", font_color="white", border=1)
PLAUSIBEL_FMT = dict(bg_color="#C6EFCE", font_color="#006100")
AUFFAELLIG_FMT = dict(bg_color="#FFC7CE", font_color="#9C0006")
AMBER_FMT = dict(bg_color="#FFE699", font_color="#9C6500")
# Gleiche Einstufung wie in word_export.py/html_export.py (SEVERITY_COLORS/STATUS_COLORS), damit alle
# drei Exportformate dieselben Befunde farblich gleich darstellen.
SEVERITY_FMT = {"hoch": AUFFAELLIG_FMT, "mittel": AMBER_FMT, "gering": PLAUSIBEL_FMT}
STATUS_FMT = {"erfüllt": PLAUSIBEL_FMT, "nicht erfüllt": AUFFAELLIG_FMT, "nicht bewertbar": AMBER_FMT,
              "übereinstimmend": PLAUSIBEL_FMT, "nur Agent auffällig": AUFFAELLIG_FMT,
              "nur manuell auffällig": AUFFAELLIG_FMT}


def _write_quality_sheet(wb: xlsxwriter.Workbook, quality_df: pd.DataFrame) -> None:
    ws = wb.add_worksheet("Datenprüfung")
    header_fmt = wb.add_format(HEADER_FMT)
    plausibel_fmt = wb.add_format(PLAUSIBEL_FMT)
    auffaellig_fmt = wb.add_format(AUFFAELLIG_FMT)
    wrap_fmt = wb.add_format({"text_wrap": True, "valign": "top"})

    for j, col in enumerate(quality_df.columns):
        ws.write(0, j, col, header_fmt)

    for i, row in quality_df.iterrows():
        for j, col in enumerate(quality_df.columns):
            fmt = wrap_fmt
            if col == "Plausibilität":
                fmt = plausibel_fmt if row[col] == "Plausibel" else auffaellig_fmt
            ws.write(i + 1, j, row[col], fmt)

    ws.set_column("A:A", 8)
    ws.set_column("B:B", 45)
    ws.set_column("C:C", 8)
    ws.set_column("D:E", 10)
    ws.set_column("F:F", 10)
    ws.set_column("G:G", 14)
    ws.set_column("H:H", 60)
    ws.freeze_panes(1, 0)


def _write_exclusion_sheet(wb: xlsxwriter.Workbook, log) -> None:
    """Blatt mit den nicht beruecksichtigten Werten: oben die Zusammenfassung, darunter jeder Einzelwert."""
    ws = wb.add_worksheet("Ausgeschlossene Werte")
    header_fmt = wb.add_format(HEADER_FMT)
    wrap_fmt = wb.add_format({"text_wrap": True, "valign": "top"})
    time_fmt = wb.add_format({"num_format": "dd.mm.yyyy hh:mm", "valign": "top"})
    row = 0
    for j, col in enumerate(log.summary.columns):
        ws.write(row, j, col, header_fmt)
    for _, r in log.summary.iterrows():
        row += 1
        for j, col in enumerate(log.summary.columns):
            ws.write(row, j, r[col], wrap_fmt)
    row += 2
    ws.write(row, 0, "Einzelwerte", wb.add_format({"bold": True, "font_size": 12, "font_color": "#1F3864"}))
    row += 1
    first_detail = row
    for j, col in enumerate(log.details.columns):
        ws.write(row, j, col, header_fmt)
    for _, r in log.details.iterrows():
        row += 1
        ws.write_datetime(row, 0, r["Zeitpunkt"].to_pydatetime(), time_fmt)
        for j, col in enumerate(log.details.columns[1:], start=1):
            ws.write(row, j, r[col], wrap_fmt)
    ws.autofilter(first_detail, 0, row, len(log.details.columns) - 1)
    ws.set_column(0, 0, 40)
    ws.set_column(1, 1, 36)
    ws.set_column(2, 3, 12)
    ws.set_column(4, 5, 22)
    ws.set_column(6, 6, 70)


def _write_timeseries_chart(wb: xlsxwriter.Workbook, sheet_name: str, title: str,
                             x: pd.Index, series: dict[str, pd.Series], y_title: str,
                             chart_type: str = "line", x_title: str = "Zeit") -> None:
    ws = wb.add_worksheet(sheet_name[:31])
    date_fmt = wb.add_format({"num_format": "yyyy-mm-dd hh:mm"})
    ws.write(0, 0, x_title)
    for c, name in enumerate(series, start=1):
        ws.write(0, c, name)
    for r, ts in enumerate(x, start=1):
        ws.write_datetime(r, 0, ts, date_fmt) if hasattr(ts, "hour") else ws.write(r, 0, str(ts))
    for c, (name, s) in enumerate(series.items(), start=1):
        for r, val in enumerate(s.values, start=1):
            if pd.notna(val):
                ws.write_number(r, c, float(val))

    n = len(x)
    chart = wb.add_chart({"type": chart_type, "subtype": "straight" if chart_type == "scatter" else None})
    for c, name in enumerate(series, start=1):
        chart.add_series({
            "name": name,
            "categories": [sheet_name[:31], 1, 0, n, 0],
            "values": [sheet_name[:31], 1, c, n, c],
            "line": {"width": 1.5},
        })
    chart.set_title({"name": title})
    chart.set_x_axis({"name": x_title})
    chart.set_y_axis({"name": y_title})
    chart.set_size({"width": 780, "height": 380})
    ws.insert_chart(0, len(series) + 2, chart)


def _write_scatter_with_trend(wb: xlsxwriter.Workbook, sheet_name: str, title: str,
                               x: pd.Series, y: pd.Series, x_title: str, y_title: str) -> None:
    ws = wb.add_worksheet(sheet_name[:31])
    ws.write(0, 0, x_title)
    ws.write(0, 1, y_title)
    sub = pd.DataFrame({x_title: x, y_title: y}).dropna()
    for r, (_, row) in enumerate(sub.iterrows(), start=1):
        ws.write_number(r, 0, float(row[x_title]))
        ws.write_number(r, 1, float(row[y_title]))

    n = len(sub)
    chart = wb.add_chart({"type": "scatter", "subtype": "marker_only"})
    chart.add_series({
        "name": "Messpunkte",
        "categories": [sheet_name[:31], 1, 0, n, 0],
        "values": [sheet_name[:31], 1, 1, n, 1],
        "marker": {"type": "circle", "size": 3, "fill": {"color": "#0072B2"}, "border": {"none": True}},
        "trendline": {"type": "linear", "line": {"color": "#D55E00", "width": 2.5}},
    })
    chart.set_title({"name": title})
    chart.set_x_axis({"name": x_title})
    chart.set_y_axis({"name": y_title})
    chart.set_size({"width": 780, "height": 380})
    ws.insert_chart(0, 3, chart)


def _write_carpet_sheet(wb: xlsxwriter.Workbook, sheet_name: str, title: str,
                         df: pd.DataFrame, value_col: str, year: int, month: int,
                         zmin: float, zmax: float) -> None:
    ws = wb.add_worksheet(sheet_name[:31])
    sub = df.loc[(df.index.year == year) & (df.index.month == month), [value_col]].copy()
    sub["Tag"] = sub.index.day
    sub["Zeit"] = sub.index.strftime("%H:%M")
    pivot = sub.pivot_table(index="Zeit", columns="Tag", values=value_col, aggfunc="mean").sort_index()

    ws.write(0, 0, title)
    ws.write(1, 0, "Uhrzeit \\ Tag")
    for c, day in enumerate(pivot.columns, start=1):
        ws.write(1, c, int(day))
    for r, (time_label, row) in enumerate(pivot.iterrows(), start=2):
        ws.write(r, 0, time_label)
        for c, val in enumerate(row.values, start=1):
            if pd.notna(val):
                ws.write_number(r, c, float(val))

    last_row = 1 + len(pivot)
    last_col = len(pivot.columns)
    ws.conditional_format(2, 1, last_row, last_col, {
        "type": "3_color_scale",
        "min_type": "num", "min_value": zmin, "min_color": "#2C7BB6",
        "mid_type": "num", "mid_value": (zmin + zmax) / 2, "mid_color": "#FFFFBF",
        "max_type": "num", "max_value": zmax, "max_color": "#D7191C",
    })
    ws.set_column(0, 0, 10)
    ws.set_column(1, last_col, 6)


def _write_narrative_sheet(wb: xlsxwriter.Workbook, report) -> None:
    """Wie word_export.py/html_export.py: jeder Textblock steht unter der letzten Abbildung, auf die er
    sich bezieht (place_by_figure), statt in der urspruenglichen, unsortierten Reihenfolge - so zeigen
    alle drei Exportformate dieselbe Zuordnung von Auswertungstext zu Abbildung."""
    ws = wb.add_worksheet("Auswertung")
    heading_fmt = wb.add_format({"bold": True, "font_size": 12, "font_color": "#1F3864"})
    ref_fmt = wb.add_format({"italic": True, "font_color": "#5b6b7b"})
    text_fmt = wb.add_format({"text_wrap": True, "valign": "top"})

    keys_in_order = [e.key for e in report.figures]
    fig_no = {e.key: i for i, e in enumerate(report.figures, start=2)}
    placed, unassigned = place_by_figure(report.narrative, keys_in_order)

    row = 0

    def write_block(block) -> None:
        nonlocal row
        ws.write(row, 0, block.heading, heading_fmt)
        row += 1
        # Anders als in Word/HTML (dort nur bei mehreren Bezuegen, da der Text schon direkt unter der
        # Abbildung steht): hier bei jedem Bezug, weil Text und Abbildung in Excel auf getrennten
        # Blaettern liegen und der Bezug sonst nicht ablesbar waere.
        refs = [f"Abbildung {fig_no[k]}" for k in block.figure_keys if k in fig_no]
        if refs:
            ws.write(row, 0, "Bezug: " + ", ".join(refs), ref_fmt)
            row += 1
        ws.merge_range(row, 0, row, 4, block.text, text_fmt)
        ws.set_row(row, 60)
        row += 2

    for entry in report.figures:
        for block in placed.get(entry.key, []):
            write_block(block)
    for block in unassigned:
        write_block(block)
    ws.set_column(0, 4, 26)


def _write_df_sheet(wb: xlsxwriter.Workbook, sheet_name: str, df: pd.DataFrame, intro: str = "",
                     status_col: str | None = None, status_fmt: dict[str, dict] | None = None,
                     col_widths: list[int] | None = None) -> None:
    """Tabellenblatt mit Kopfzeile, optionalem Einleitungstext und optionaler Ampel-Farbcodierung
    einer Statusspalte - das Excel-Gegenstueck zu word_export._table()/html_export._table()."""
    ws = wb.add_worksheet(sheet_name[:31])
    header_fmt = wb.add_format(HEADER_FMT)
    wrap_fmt = wb.add_format({"text_wrap": True, "valign": "top"})
    status_fmts = {k: wb.add_format(v) for k, v in (status_fmt or {}).items()}
    row = 0
    if intro:
        ws.merge_range(row, 0, row, max(len(df.columns) - 1, 1),
                        intro, wb.add_format({"text_wrap": True, "valign": "top", "bold": True}))
        ws.set_row(row, 32)
        row += 2
    header_row = row
    for j, col in enumerate(df.columns):
        ws.write(row, j, col, header_fmt)
    for _, r in df.iterrows():
        row += 1
        for j, col in enumerate(df.columns):
            fmt = wrap_fmt
            if status_col and col == status_col:
                fmt = status_fmts.get(str(r[col]), wrap_fmt)
            val = r[col]
            if isinstance(val, float) and pd.notna(val):
                ws.write_number(row, j, val, fmt)
            else:
                ws.write(row, j, "" if pd.isna(val) else val, fmt)
    for j, w in enumerate(col_widths or [20] * len(df.columns)):
        ws.set_column(j, j, w)
    ws.freeze_panes(header_row + 1, 0)


def _write_savings_sheet(wb: xlsxwriter.Workbook, savings: pd.DataFrame) -> None:
    _write_df_sheet(
        wb, "Einsparpotenzial", savings,
        intro="Abschätzung des Energieeinsparpotenzials auf Basis der gemessenen Verbräuche (Annahmen siehe Spalte "
              "„Annahme“; Details siehe Kapitel 4 des Berichts).",
        col_widths=[32, 55, 16, 14, 12])


def _write_assessment_sheet(wb: xlsxwriter.Workbook, assessment: pd.DataFrame) -> None:
    cols = [c for c in ["Nr.", "Befund", "Schweregrad", "Kennzahl", "Empfehlung", "Einstufungsregel", "Hinweis"]
            if c in assessment.columns]
    _write_df_sheet(
        wb, "Bewertung", assessment[cols],
        intro="Bewertung und Priorisierung der Befunde nach Schweregrad (hoch/mittel/gering).",
        status_col="Schweregrad", status_fmt=SEVERITY_FMT,
        col_widths=[5, 32, 12, 30, 45, 35, 30])


def _write_theory_sheet(wb: xlsxwriter.Workbook, theory: pd.DataFrame) -> None:
    _write_df_sheet(
        wb, "Theorie-Praxis-Vergleich", theory,
        intro="Überprüfung theoretischer Aussagen aus der Hausarbeit anhand der gemessenen Praxiswerte.",
        col_widths=[45, 10, 45, 35])


def _write_comparison_sheet(wb: xlsxwriter.Workbook, comparison: pd.DataFrame) -> None:
    cols = [c for c in ["Spalte", "Bezeichnung", "Manuell", "Agent", "Ergebnis", "Manueller_Befund", "Agent_Befund"]
            if c in comparison.columns]
    _write_df_sheet(
        wb, "Vergleich Agent-Manuell", comparison[cols],
        intro="Gegenüberstellung der Datenprüfung: manuelle Auswertung (Kap. 6) gegen den Agent (Kap. 7).",
        status_col="Ergebnis", status_fmt=STATUS_FMT,
        col_widths=[8, 32, 14, 14, 20, 35, 35])


def export_workbook(report, path: str, comparison: pd.DataFrame | None = None,
                     include_savings: bool = True, include_assessment: bool = True) -> None:
    df = report.df
    with xlsxwriter.Workbook(path) as wb:
        _write_quality_sheet(wb, report.quality_df)
        if report.narrative:
            _write_narrative_sheet(wb, report)
        if len(report.exclusion_log.summary):
            _write_exclusion_sheet(wb, report.exclusion_log)

        hourly = df.resample("h").mean()

        _write_timeseries_chart(wb, "Abb02_WMZ", "Zähler 019 – WMZ (kumuliert, Stundenmittel)",
                                 hourly.index, {"WMZ kumuliert": hourly["Zähler 019 – WMZ"]}, "kWh")

        _write_timeseries_chart(wb, "Abb03_Regelguete_Heizung",
                                 "Regelgüte Stat. Heizung Geb.06: Soll- vs. Ist-Vorlauf",
                                 hourly.index, {
                                     "Soll-Vorlauf": hourly["Stat. Heizung Geb.06 VL (Soll)"],
                                     "Ist-Vorlauf": hourly["Stat. Heizung Geb.06 VL (Ist)"],
                                 }, "Temperatur (°C)")

        _write_scatter_with_trend(wb, "Abb04_Heizkurve", "Heizkurve: Außentemp. vs. Vorlauftemp. Geb.06",
                                   df["RLT KL01 Außenluft"], df["Stat. Heizung Geb.06 VL (Ist)"],
                                   "Außentemperatur (°C)", "Vorlauftemperatur (°C)")

        _write_carpet_sheet(wb, "Abb05_Carpet_RLT_VL", f"RLT primär VL-Temp. {report.carpet_month:02d}/{report.carpet_year}",
                             df, "RLT primär VL", report.carpet_year, report.carpet_month, 20, 65)
        _write_carpet_sheet(wb, "Abb06_Carpet_RLT_RL", f"RLT primär RL-Temp. {report.carpet_month:02d}/{report.carpet_year}",
                             df, "RLT primär RL", report.carpet_year, report.carpet_month, 20, 65)

        _write_timeseries_chart(wb, "Abb07_Regelguete_FBH", "Regelgüte FBH Geb.06: Soll- vs. Ist-Vorlauf",
                                 hourly.index, {
                                     "Soll-Vorlauf": hourly["FBH Geb.06 VL (Soll)"],
                                     "Ist-Vorlauf": hourly["FBH Geb.06 VL (Ist)"],
                                 }, "Temperatur (°C)")

        _write_timeseries_chart(wb, "Abb08_Zonenvergleich", "Hydraulischer Abgleich: Zonenvergleich Vorlauftemperaturen",
                                 hourly.index, {
                                     "Stat. Heizung Geb.06": hourly["Stat. Heizung Geb.06 VL (Ist)"],
                                     "FBH Geb.06": hourly["FBH Geb.06 VL (Ist)"],
                                     "FBH Geb.08 KI-Räume": hourly["FBH Geb.08 KI-Räume VL"],
                                     "FBH Geb.08 Intensivpflege": hourly["FBH Geb.08 Intensivpflege VL"],
                                 }, "Temperatur (°C)")

        dt_stat = hourly["Stat. Heizung Geb.06 VL (Ist)"] - hourly["Stat. Heizung Geb.06 RL"]
        dt_fbh = hourly["FBH Geb.06 VL (Ist)"] - hourly["FBH Geb.06 RL"]
        _write_timeseries_chart(wb, "Abb09_DeltaT", "Effizienz: Temperaturspreizung (Delta T)",
                                 hourly.index, {"Stat. Heizung Geb.06": dt_stat, "FBH Geb.06": dt_fbh}, "Delta T (K)")

        _write_timeseries_chart(wb, "Abb10_RLT_AUL_ZUL", "RLT-Anlage: Außenluft vs. Zuluft",
                                 hourly.index, {
                                     "Außenluft": hourly["RLT KL01 Außenluft"],
                                     "Zuluft": hourly["RLT KL01 Zuluft"],
                                 }, "Temperatur (°C)")

        daily_ab = daily_consumption(df, "Zähler 021 – Strom Abluft")
        daily_zu = daily_consumption(df, "Zähler 022 – Strom Zuluft")
        _write_timeseries_chart(wb, "Abb11_Strom_RLT_taeglich", "Stromverbrauch RLT-Ventilatoren (Tageswerte)",
                                 daily_ab.index, {"Abluftventilator": daily_ab, "Zuluftventilator": daily_zu},
                                 "Energie (kWh)", x_title="Datum")

        daily_waerme = daily_consumption(df, "Zähler 019 – WMZ")
        _write_timeseries_chart(wb, "Abb12_Waerme_taeglich", "Täglicher Wärmeverbrauch",
                                 daily_waerme.index, {"Wärmeverbrauch": daily_waerme}, "kWh",
                                 chart_type="column", x_title="Datum")

        # Kapitel 4-6 der Hausarbeit (Einsparpotenzial, Bewertung, Theorie-Praxis-Vergleich) sowie der
        # Vergleich mit der manuellen Auswertung (Kap. 8) - bisher nur in Word-/HTML-Export enthalten.
        if include_savings and getattr(report, "savings", None) is not None:
            _write_savings_sheet(wb, report.savings)
        if include_assessment and getattr(report, "assessment", None) is not None and len(report.assessment):
            from .assessment import theory_vs_practice
            from .settings import Thresholds
            _write_assessment_sheet(wb, report.assessment)
            th = getattr(report, "thresholds", None) or Thresholds()
            _write_theory_sheet(wb, theory_vs_practice(df, th, report.savings if include_savings else None))
        if comparison is not None and len(comparison):
            _write_comparison_sheet(wb, comparison)
