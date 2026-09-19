"""
Automatisierte Datenpruefung - der KI-Agent-Ersatz fuer Kapitel 6.2 / Tabelle 1
der Hausarbeit.

Die Regeln sind bewusst generisch (nicht auf einzelne Spaltennamen hartkodiert),
damit die Pruefung auch auf zukuenftige/aktualisierte Messdatensaetze mit
gleichem Spaltenschema anwendbar bleibt. Jede Regel gibt eine Liste von
Befunden (Findings) zurueck, die pro Spalte zusammengefuehrt werden.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import COLUMNS, PLAUSIBLE_RANGE, by_zone_role


@dataclass
class Finding:
    severity: str  # "info" | "auffaellig"
    message: str


@dataclass
class ColumnQuality:
    column_id: int
    excel_name: str
    short: str
    unit: str
    zone: str
    role: str
    min_value: float
    max_value: float
    n_missing: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "Auffällig!" if any(f.severity == "auffaellig" for f in self.findings) else "Plausibel"

    @property
    def comment(self) -> str:
        msgs = [f.message for f in self.findings]
        return " / ".join(msgs) if msgs else "Keine Auffälligkeiten festgestellt."


def _check_range(series: pd.Series, role: str) -> list[Finding]:
    findings = []
    bounds = PLAUSIBLE_RANGE.get(role)
    if bounds is None:
        return findings
    lo, hi = bounds
    if role == "pump":
        bad = ~series.dropna().isin([0, 1])
        if bad.any():
            findings.append(Finding("auffaellig", f"{bad.sum()} Werte außerhalb {{0,1}}"))
        return findings
    below = series < lo
    above = series > hi
    if below.any():
        findings.append(Finding("auffaellig", f"Min={series.min():.2f} unterschreitet Plausibilitätsgrenze ({lo})"))
    if above.any():
        findings.append(Finding("auffaellig", f"Max={series.max():.2f} überschreitet Plausibilitätsgrenze ({hi}) – hoher Maximalwert"))
    return findings


def _check_zero_dropout(series: pd.Series, role: str) -> list[Finding]:
    """Bei Vor-/Ruecklauf- und Sollwert-Temperaturen eines aktiven Heizkreises ist
    ein Messwert von exakt 0.0 physikalisch praktisch ausgeschlossen - schon ein
    einzelnes Auftreten deutet auf einen Sensor-/Uebertragungsaussetzer hin
    (gleiche Heuristik wie in der manuellen Datenpruefung: "Min-Wert von 0")."""
    if role not in ("vl", "rl", "soll_vl"):
        return []
    valid = series.dropna()
    n_zero = int((valid == 0).sum())
    if n_zero > 0:
        return [Finding(
            "auffaellig",
            f"Min-Wert 0 in {n_zero} Zeitschritt(en) deutet auf Aussetzer der Datenaufzeichnung hin",
        )]
    return []


def _check_monotonic(series: pd.Series, role: str) -> list[Finding]:
    if role not in ("meter_energy", "meter_electric"):
        return []
    diffs = series.dropna().diff().dropna()
    regressions = diffs < 0
    if regressions.any():
        return [Finding(
            "auffaellig",
            f"{int(regressions.sum())} rückläufige Zählerstände (Reset/Übertragungsfehler)",
        )]
    return [Finding("info", "Zeigt stetigen Zuwachs (Monotonie) – kontinuierlicher Verbrauch")]


def _check_vl_rl_pair(df: pd.DataFrame, zone: str, roles: dict) -> list[Finding]:
    vl_col = roles.get("vl")
    rl_col = roles.get("rl")
    if vl_col is None or rl_col is None:
        return []
    vl, rl = df[vl_col.short], df[rl_col.short]
    valid = vl.notna() & rl.notna()
    if not valid.any():
        return []
    violation_frac = (rl[valid] > vl[valid]).mean()
    if violation_frac > 0.01:
        return [Finding(
            "auffaellig",
            f"Rücklauf liegt in {violation_frac*100:.1f}% der Zeitschritte über dem Vorlauf "
            "(untypisch für ein Heizsystem)",
        )]
    if rl.min() > vl.min():
        return [Finding(
            "auffaellig",
            "Das Minimum des Rücklaufs liegt über dem Minimum des Vorlaufs",
        )]
    return [Finding("info", "Liegt konsequent unter der Vorlauftemperatur")]


def _check_setpoint(df: pd.DataFrame, zone: str, roles: dict) -> list[Finding]:
    soll_col = roles.get("soll_vl")
    ist_col = roles.get("vl")
    if soll_col is None or ist_col is None:
        return []
    soll, ist = df[soll_col.short].dropna(), df[ist_col.short].dropna()
    if soll.empty or ist.empty:
        return []
    findings = []
    if soll.max() < ist.quantile(0.5):
        findings.append(Finding(
            "auffaellig",
            f"Max-Sollwert ({soll.max():.1f}°C) liegt unter dem Median-Istwert "
            f"({ist.quantile(0.5):.1f}°C) – Sollwert scheint zu gering angesetzt",
        ))
    return findings


def _strict_checks(df: pd.DataFrame, col, zone_roles: dict, fbh_limit: float) -> list[Finding]:
    """Regelsatz v2: zusaetzliche Regeln, abgeleitet aus dem Vergleich mit der manuellen Pruefung (Kap. 8.2.3)."""
    findings: list[Finding] = []
    series = df[col.short].dropna()
    if series.empty:
        return findings
    if col.role == "zul" and series.max() > 30:
        findings.append(Finding("auffaellig", f"Hohes Maximum der Zulufttemperatur ({series.max():.1f} °C)"))
    is_fbh = col.zone.startswith("fbh")
    if is_fbh and col.role == "vl" and series.max() > fbh_limit + 5:
        findings.append(Finding("auffaellig", f"Max-Vorlauf {series.max():.1f} °C für ein Niedertemperatursystem sehr hoch"))
    if is_fbh and col.role == "rl" and series.max() > fbh_limit:
        findings.append(Finding("auffaellig", f"Sehr hohe Rücklauftemperatur (Max {series.max():.1f} °C)"))
    if col.role == "rl":
        vl = zone_roles.get("vl")
        if vl is not None:
            both = df[[vl.short, col.short]].dropna()
            frac = (both[col.short] > both[vl.short]).mean() if len(both) else 0
            if frac > 0.01:
                findings.append(Finding("auffaellig", f"Rücklauf über dem Vorlauf in {frac*100:.1f}% der Zeitschritte (Widerspruch im Datenpaar)"))
    return findings


def run_data_quality(df: pd.DataFrame, strict: bool = False, fbh_limit: float = 40.0) -> list[ColumnQuality]:
    results: list[ColumnQuality] = []
    zone_roles = {}
    for c in COLUMNS:
        zone_roles.setdefault(c.zone, {})[c.role] = c

    for i, col in enumerate(COLUMNS, start=1):
        series = df[col.short]
        findings: list[Finding] = []
        findings += _check_range(series, col.role)
        findings += _check_zero_dropout(series, col.role)
        findings += _check_monotonic(series, col.role)
        if col.role == "vl":
            findings += _check_vl_rl_pair(df, col.zone, zone_roles[col.zone])
        if col.role == "soll_vl":
            findings += _check_setpoint(df, col.zone, zone_roles[col.zone])
        if strict:
            findings += _strict_checks(df, col, zone_roles[col.zone], fbh_limit)

        results.append(ColumnQuality(
            column_id=i,
            excel_name=col.excel_name,
            short=col.short,
            unit=col.unit,
            zone=col.zone,
            role=col.role,
            min_value=float(series.min()) if series.notna().any() else float("nan"),
            max_value=float(series.max()) if series.notna().any() else float("nan"),
            n_missing=int(series.isna().sum()),
            findings=findings,
        ))
    return results


def quality_to_dataframe(results: list[ColumnQuality]) -> pd.DataFrame:
    rows = []
    for r in results:
        rows.append({
            "Spalte": r.column_id,
            "Bezeichnung": r.excel_name,
            "Einheit": r.unit,
            "Min": round(r.min_value, 2),
            "Max": round(r.max_value, 2),
            "Fehlwerte": r.n_missing,
            "Plausibilität": r.status,
            "Bewertung": r.comment,
        })
    return pd.DataFrame(rows)
