"""Einlesen des Rohdatensatzes ("Messdaten YYYY-YYYY.xlsx") in ein sauberes DataFrame."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import COLUMNS, DATE_COLUMN

HEADER_ROW_EXCEL = 7  # 1-indexierte Excel-Zeile mit den Klartext-Spaltennamen


def load_measurements(path: str | Path, sheet_name: str = "Tabelle1") -> pd.DataFrame:
    """Liest die Rohdaten ein und liefert ein DataFrame mit:
    - Index: Datum (datetime64)
    - Spalten: die in config.COLUMNS definierten `short`-Bezeichner
    """
    raw = pd.read_excel(
        path,
        sheet_name=sheet_name,
        header=HEADER_ROW_EXCEL - 1,
        engine="openpyxl",
    )
    raw = raw.rename(columns={DATE_COLUMN: "Datum"})
    raw["Datum"] = pd.to_datetime(raw["Datum"], format="%Y.%m.%d %H:%M:%S", errors="coerce")
    raw = raw.dropna(subset=["Datum"]).set_index("Datum").sort_index()

    rename_map = {c.excel_name: c.short for c in COLUMNS}
    missing = [name for name in rename_map if name not in raw.columns]
    if missing:
        raise ValueError(
            "Folgende erwartete Spalten fehlen im Datensatz (Excel-Layout hat sich "
            f"vermutlich geändert): {missing}"
        )

    df = raw[list(rename_map.keys())].rename(columns=rename_map)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def infer_interval_minutes(df: pd.DataFrame) -> float:
    deltas = df.index.to_series().diff().dropna()
    if deltas.empty:
        return float("nan")
    return deltas.dt.total_seconds().median() / 60


def read_manual_minmax(path_or_buffer, sheet_name: str = "Tabelle1") -> pd.DataFrame | None:
    """Liest die in der Excel-Kopfzeile hinterlegten Min-/Max-Werte (manuelle Kennwerte, Zeilen 4 und 5).
    Liefert None, wenn die Zeilen nicht mit 'Min'/'Max' beschriftet sind."""
    import openpyxl

    wb = openpyxl.load_workbook(path_or_buffer, read_only=True, data_only=True)
    try:
        rows = list(wb[sheet_name].iter_rows(min_row=4, max_row=5, values_only=True))
    finally:
        wb.close()
    if len(rows) < 2 or str(rows[0][0]).strip() != "Min" or str(rows[1][0]).strip() != "Max":
        return None
    shorts = [c.short for c in COLUMNS]
    return pd.DataFrame({"Min": rows[0][1:1 + len(shorts)], "Max": rows[1][1:1 + len(shorts)]}, index=shorts).apply(
        pd.to_numeric, errors="coerce")
