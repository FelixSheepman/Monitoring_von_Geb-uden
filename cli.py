#!/usr/bin/env python
"""
KI-Agent fuer die Monitoring-Auswertung - Kommandozeilen-Variante.

Liest einen Messdatensatz im Format von "Messdaten 2024-2026.xlsx" ein und
erzeugt automatisiert:
  1. Eine Datenpruefung (Tabelle 1 aus Kap. 6.2 der Hausarbeit)
  2. Die 11 Abbildungen aus Kap. 6.3
als eigenstaendige Excel-Arbeitsmappe.

Beispiel:
    python cli.py --input "source_docs/Messdaten 2024-2026.xlsx" --output report.xlsx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from monitoring_agent.data_loader import load_measurements
from monitoring_agent.excel_export import export_workbook
from monitoring_agent.report import build_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Automatisierte Monitoring-Auswertung")
    parser.add_argument("--input", "-i", required=True, help="Pfad zur Messdaten-.xlsx")
    parser.add_argument("--output", "-o", default="monitoring_report.xlsx",
                         help="Pfad der erzeugten Report-.xlsx (Default: monitoring_report.xlsx)")
    parser.add_argument("--carpet-year", type=int, default=2025)
    parser.add_argument("--carpet-month", type=int, default=2)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Eingabedatei nicht gefunden: {input_path}", file=sys.stderr)
        return 1

    print(f"Lese Messdaten: {input_path}")
    df = load_measurements(input_path)
    print(f"  {len(df):,} Zeitschritte, {df.index.min()} bis {df.index.max()}")

    print("Führe Datenprüfung durch und erstelle Abbildungen...")
    report = build_report(df, carpet_year=args.carpet_year, carpet_month=args.carpet_month)

    n_auffaellig = (report.quality_df["Plausibilität"] == "Auffällig!").sum()
    print(f"  {len(report.quality_df)} Spalten geprüft, davon {n_auffaellig} auffällig")

    print(f"Schreibe Report: {args.output}")
    export_workbook(report, args.output)
    print("Fertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
