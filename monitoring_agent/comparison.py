"""
Vergleich konventionelle (manuelle) Auswertung vs. Agent - Grundlage fuer Kapitel 8
("Gegenueberstellung der Ergebnisse fuer die Kontrollkriterien").

Die manuellen Referenzwerte liegen in reference/*.csv und koennen dort korrigiert werden.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"


def compare_table1(quality_df: pd.DataFrame, manual_path: Path | None = None) -> pd.DataFrame:
    manual = pd.read_csv(manual_path or REFERENCE_DIR / "manual_tabelle1.csv", sep=";", encoding="utf-8").fillna("")
    agent = quality_df[["Spalte", "Bezeichnung", "Plausibilität", "Bewertung"]].rename(
        columns={"Plausibilität": "Agent", "Bewertung": "Agent_Befund"})
    agent["Agent"] = agent["Agent"].str.replace("!", "", regex=False)

    merged = agent.merge(manual, on="Spalte")
    merged["Ergebnis"] = merged.apply(_classify, axis=1)
    return merged[["Spalte", "Bezeichnung", "Manuell", "Agent", "Ergebnis", "Manueller_Befund", "Agent_Befund"]]


def _classify(row) -> str:
    if row["Manuell"] == row["Agent"]:
        return "übereinstimmend"
    if row["Agent"] == "Auffällig":
        return "nur Agent auffällig"
    return "nur manuell auffällig"


def compare_findings(narrative_headings: list[str], manual_path: Path | None = None) -> pd.DataFrame:
    manual = pd.read_csv(manual_path or REFERENCE_DIR / "manual_findings.csv", sep=";", encoding="utf-8")
    manual["Vom Agent gefunden"] = manual["Agent_Block"].isin(narrative_headings).map({True: "ja", False: "nein"})
    return manual


def agreement_summary(table1_cmp: pd.DataFrame) -> dict[str, float]:
    n = len(table1_cmp)
    counts = table1_cmp["Ergebnis"].value_counts()
    agree = int(counts.get("übereinstimmend", 0))
    manual_flag = int((table1_cmp["Manuell"] == "Auffällig").sum())
    agent_flag = int((table1_cmp["Agent"] == "Auffällig").sum())
    both = int(((table1_cmp["Manuell"] == "Auffällig") & (table1_cmp["Agent"] == "Auffällig")).sum())
    return {
        "Trefferquote % (manuelle Auffälligkeiten vom Agent gefunden)": round(both / manual_flag * 100, 1) if manual_flag else float("nan"),
        "Genauigkeit % (Agent-Auffälligkeiten auch manuell auffällig)": round(both / agent_flag * 100, 1) if agent_flag else float("nan"),
        "Spalten gesamt": n,
        "übereinstimmend": agree,
        "Übereinstimmung %": round(agree / n * 100, 1) if n else float("nan"),
        "nur Agent auffällig": int(counts.get("nur Agent auffällig", 0)),
        "nur manuell auffällig": int(counts.get("nur manuell auffällig", 0)),
    }
