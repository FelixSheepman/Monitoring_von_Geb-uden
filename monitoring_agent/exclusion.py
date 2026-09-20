"""
Ausschluss fehlerhafter Einzelwerte.

Die Datenpruefung (quality.py) bewertet immer die Rohdaten. Hier kann der Nutzer
entscheiden, welche erkannten Fehlwerte in Grafiken, Kennwerten, Bewertung und
Einsparabschaetzung NICHT mehr einfliessen: Ausgeschlossene Werte werden wie
Fehlwerte (NaN) behandelt, die Rohdaten bleiben unveraendert. Jeder Ausschluss
wird mit Begruendung protokolliert (ExclusionLog).

Ein Ausschluss ist eine Auswahl aus Paaren (Spalte, Regel-Schluessel); ohne Auswahl
bleibt alles wie in den Rohdaten.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import COLUMNS, PLAUSIBLE_RANGE

# Reihenfolge = Prioritaet: ein Wert wird nur unter der ersten zutreffenden Regel protokolliert.
RULES: dict[str, str] = {
    "nullwert": "Nullwert-Aussetzer",
    "grenzwert": "Außerhalb des plausiblen Wertebereichs",
    "zaehler_rueckgang": "Zählerstand fällt (Rücksprung)",
    "rl_ueber_vl": "Rücklauf über Vorlauf",
}

_REASONS = {
    "nullwert": "Vor-/Rücklauf- und Sollwert-Temperaturen sind im Betrieb praktisch nie exakt 0 °C. "
                "Der Wert deutet auf einen Aussetzer der Datenaufzeichnung oder Übertragung hin.",
    "zaehler_rueckgang": "Ein kumulierender Zähler darf nicht sinken. Der Rücksprung deutet auf einen Reset oder "
                         "Übertragungsfehler hin. Entfernt wird nur der Wert des Rücksprungs selbst; ein dauerhafter "
                         "Versatz im weiteren Verlauf bleibt bestehen.",
    "rl_ueber_vl": "Der Rücklauf liegt über dem Vorlauf, was im Heizbetrieb physikalisch widersprüchlich ist. "
                   "Welcher der beiden Werte falsch ist, lässt sich nicht feststellen; entfernt wird der Wert dieser Spalte. "
                   "Hinweis: Bei stehender Pumpe kann das durch Auskühlen der Leitung auch ein echter Messwert sein.",
}

# Eindeutige Fehler. "rl_ueber_vl" ist mehrdeutig (kann bei stehender Pumpe ein echter Messwert sein)
# und wird deshalb nie automatisch, sondern nur auf ausdrueckliche Auswahl ausgeschlossen.
CLEAR_RULES = ("nullwert", "grenzwert", "zaehler_rueckgang")

Selection = frozenset  # frozenset[tuple[str, str]] aus (Spaltenname, Regel-Schluessel)


def _reason(rule: str, col) -> str:
    if rule == "grenzwert":
        bounds = PLAUSIBLE_RANGE[col.role]
        if col.role == "pump":
            return "Die Pumpenspalte darf nur die Werte 0 (aus) oder 1 (ein) enthalten."
        return (f"Der Wert liegt außerhalb der Plausibilitätsgrenzen für diese Messgröße "
                f"({bounds[0]} bis {bounds[1]} {col.unit}) und ist physikalisch unwahrscheinlich.")
    return _REASONS[rule]


def invalid_masks(df: pd.DataFrame) -> dict[tuple[str, str], pd.Series]:
    """Bool-Masken (True = fehlerhafter Wert) je (Spalte, Regel); nur Masken mit mindestens einem Treffer."""
    masks: dict[tuple[str, str], pd.Series] = {}
    zone_roles: dict[str, dict] = {}
    for c in COLUMNS:
        zone_roles.setdefault(c.zone, {})[c.role] = c

    def add(col_short: str, rule: str, mask: pd.Series) -> None:
        if mask.any():
            masks[(col_short, rule)] = mask

    for c in COLUMNS:
        s = df[c.short]
        if c.role in ("vl", "rl", "soll_vl"):
            add(c.short, "nullwert", s == 0)
        bounds = PLAUSIBLE_RANGE.get(c.role)
        if bounds is not None:
            lo, hi = bounds
            bad = ~s.isin([0, 1]) if c.role == "pump" else (s < lo) | (s > hi)
            add(c.short, "grenzwert", bad & s.notna())
        if c.role in ("meter_energy", "meter_electric"):
            diffs = s.dropna().diff()
            mask = pd.Series(False, index=df.index)
            mask.loc[diffs.index[diffs < 0]] = True
            add(c.short, "zaehler_rueckgang", mask)

    for roles in zone_roles.values():
        vl, rl = roles.get("vl"), roles.get("rl")
        if vl is not None and rl is not None:
            both = df[vl.short].notna() & df[rl.short].notna()
            mask = both & (df[rl.short] > df[vl.short])
            add(vl.short, "rl_ueber_vl", mask)
            add(rl.short, "rl_ueber_vl", mask)

    rule_order = list(RULES)
    col_order = [c.short for c in COLUMNS]
    return dict(sorted(masks.items(), key=lambda kv: (rule_order.index(kv[0][1]), col_order.index(kv[0][0]))))


def find_invalid(df: pd.DataFrame) -> pd.DataFrame:
    """Kandidatentabelle: welche fehlerhaften Werte gibt es, wie viele und warum sind sie fehlerhaft."""
    by_short = {c.short: c for c in COLUMNS}
    rows = []
    for (short, rule), mask in invalid_masks(df).items():
        idx = df.index[mask]
        rows.append({
            "Spalte": short,
            "Regel": RULES[rule],
            "Anzahl": int(mask.sum()),
            "Anteil %": round(100 * mask.sum() / len(df), 2),
            "Erster": f"{idx.min():%d.%m.%Y %H:%M}",
            "Letzter": f"{idx.max():%d.%m.%Y %H:%M}",
            "Begründung": _reason(rule, by_short[short]),
            "rule_key": rule,
        })
    return pd.DataFrame(rows, columns=["Spalte", "Regel", "Anzahl", "Anteil %", "Erster", "Letzter", "Begründung", "rule_key"])


def all_of(candidates: pd.DataFrame) -> frozenset:
    return frozenset(zip(candidates["Spalte"], candidates["rule_key"]))


def clear_only(candidates: pd.DataFrame) -> frozenset:
    """Auswahl aller eindeutig fehlerhaften Werte (ohne die mehrdeutigen Vor-/Ruecklauf-Widersprueche)."""
    return all_of(candidates[candidates["rule_key"].isin(CLEAR_RULES)])


@dataclass
class ExclusionLog:
    summary: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=SUMMARY_COLUMNS))
    details: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=DETAIL_COLUMNS))

    @property
    def n_values(self) -> int:
        return int(self.summary["Anzahl"].sum()) if len(self.summary) else 0

    @property
    def n_columns(self) -> int:
        return int(self.summary["Spalte"].nunique()) if len(self.summary) else 0


SUMMARY_COLUMNS = ["Spalte", "Regel", "Anzahl", "Anteil %", "Erster", "Letzter", "Begründung"]
DETAIL_COLUMNS = ["Zeitpunkt", "Spalte", "Messwert", "Einheit", "Regel", "Begründung"]


def apply_exclusions(df: pd.DataFrame, selection: frozenset | set | None) -> tuple[pd.DataFrame, ExclusionLog]:
    """Setzt die ausgewaehlten fehlerhaften Werte auf NaN. Gibt (bereinigtes df, Protokoll) zurueck.
    Ohne Auswahl wird `df` unveraendert (ohne Kopie) zurueckgegeben."""
    if not selection:
        return df, ExclusionLog()
    by_short = {c.short: c for c in COLUMNS}
    masks = invalid_masks(df)
    clean = df.copy()
    details, summary = [], []
    for rule in RULES:
        for (short, r), mask in masks.items():
            if r != rule or (short, r) not in selection:
                continue
            mask = mask & clean[short].notna()  # schon durch eine frühere Regel entfernte Werte nicht doppelt zählen
            if not mask.any():
                continue
            col = by_short[short]
            vals = clean.loc[mask, short]
            reason = _reason(rule, col)
            details.append(pd.DataFrame({
                "Zeitpunkt": vals.index, "Spalte": short, "Messwert": vals.to_numpy(), "Einheit": col.unit,
                "Regel": RULES[rule], "Begründung": reason,
            }))
            summary.append({
                "Spalte": short, "Regel": RULES[rule], "Anzahl": int(mask.sum()),
                "Anteil %": round(100 * mask.sum() / len(df), 2),
                "Erster": f"{vals.index.min():%d.%m.%Y %H:%M}", "Letzter": f"{vals.index.max():%d.%m.%Y %H:%M}",
                "Begründung": reason,
            })
            clean.loc[mask, short] = np.nan
    if not details:
        return df, ExclusionLog()
    log = ExclusionLog(
        summary=pd.DataFrame(summary, columns=SUMMARY_COLUMNS),
        details=pd.concat(details).sort_values(["Zeitpunkt", "Spalte"]).reset_index(drop=True),
    )
    return clean, log
