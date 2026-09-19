"""Zusaetzliche Auswertungen: Pumpenlaufzeiten, Datenverfuegbarkeit, Energieeinsparpotenzial."""

from __future__ import annotations

import pandas as pd

from .config import COLUMNS
from .metrics import daily_consumption
from .narrative import NarrativeBlock
from .settings import Thresholds

PUMP_COLS = {"Stat. Heizung Geb.06": "Stat. Heizung Geb.06 Pumpe", "FBH Geb.06": "FBH Geb.06 Pumpe"}
STEP_HOURS = 0.25


def pump_runtime_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Laufzeit der Heizkreispumpen in Stunden je Monat (15-Min-Raster)."""
    out = {label: df[col].resample("MS").sum() * STEP_HOURS for label, col in PUMP_COLS.items()}
    return pd.DataFrame(out)


def availability_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Anzahl fehlerhafter Zeitschritte (fehlend oder exakt 0 bei Temperaturkanaelen) je Spalte und Tag."""
    bad = pd.DataFrame(index=df.index)
    for c in COLUMNS:
        s = df[c.short]
        is_bad = s.isna()
        if c.role in ("vl", "rl", "soll_vl"):
            is_bad |= s == 0
        bad[c.short] = is_bad
    return bad.resample("D").sum()


def savings_potential(df: pd.DataFrame, th: Thresholds) -> pd.DataFrame:
    """Grobe Abschaetzung des Einsparpotenzials mit ausdruecklich genannten Annahmen."""
    days = max((df.index.max() - df.index.min()).days + 1, 1)
    to_year = 365 / days

    heat_daily = daily_consumption(df, "Zähler 019 – WMZ")
    aul_daily = df["RLT KL01 Außenluft"].resample("D").mean()
    warm_days = aul_daily[aul_daily > th.heizgrenze_aul].index
    heat_warm = heat_daily.reindex(warm_days).sum()
    heat_total = heat_daily.sum()

    fans = sum(daily_consumption(df, c).sum() for c in ("Zähler 021 – Strom Abluft", "Zähler 022 – Strom Zuluft"))

    heat_save = heat_warm * th.heat_avoid_share * to_year
    fan_save = fans * (th.rlt_night_hours / 24) * th.rlt_night_reduction * to_year
    total_energy_year = (heat_total + fans) * to_year

    rows = [
        {"Maßnahme": f"Heizgrenze bei {th.heizgrenze_aul:.0f} °C Außentemperatur",
         "Annahme": f"{th.heat_avoid_share*100:.0f} % des Wärmeverbrauchs an Tagen mit Tagesmittel > {th.heizgrenze_aul:.0f} °C sind vermeidbar",
         "Einsparung kWh/a": heat_save, "Kosten €/a": heat_save * th.heat_price},
        {"Maßnahme": "RLT-Ventilatoren: Nachtabsenkung",
         "Annahme": f"{th.rlt_night_hours:.0f} h/Nacht mit {th.rlt_night_reduction*100:.0f} % weniger Ventilatorstrom",
         "Einsparung kWh/a": fan_save, "Kosten €/a": fan_save * th.power_price},
    ]
    out = pd.DataFrame(rows)
    total = {"Maßnahme": "Summe", "Annahme": f"Bezug: gemessener Gesamtverbrauch {total_energy_year:,.0f} kWh/a (Wärme + Ventilatorstrom)".replace(",", "."),
             "Einsparung kWh/a": out["Einsparung kWh/a"].sum(), "Kosten €/a": out["Kosten €/a"].sum()}
    out = pd.concat([out, pd.DataFrame([total])], ignore_index=True)
    out["Anteil %"] = out["Einsparung kWh/a"] / total_energy_year * 100
    return out.round({"Einsparung kWh/a": 0, "Kosten €/a": 0, "Anteil %": 1})


def _de(x: float, digits: int = 0) -> str:
    return f"{x:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def savings_explanations(df: pd.DataFrame, th: Thresholds) -> list[NarrativeBlock]:
    """Ausformulierte Erlaeuterung der Einsparmassnahmen; alle Zahlen werden aus den Daten berechnet."""
    days = max((df.index.max() - df.index.min()).days + 1, 1)
    to_year = 365 / days

    heat_daily = daily_consumption(df, "Zähler 019 – WMZ")
    aul_daily = df["RLT KL01 Außenluft"].resample("D").mean()
    warm_days = aul_daily[aul_daily > th.heizgrenze_aul].index
    warm_share = len(warm_days) / max(aul_daily.notna().sum(), 1) * 100
    heat_warm = heat_daily.reindex(warm_days).sum()
    heat_total = heat_daily.sum()
    fans = sum(daily_consumption(df, c).sum() for c in ("Zähler 021 – Strom Abluft", "Zähler 022 – Strom Zuluft"))

    heat_save = heat_warm * th.heat_avoid_share * to_year
    fan_save = fans * (th.rlt_night_hours / 24) * th.rlt_night_reduction * to_year
    total_energy_year = (heat_total + fans) * to_year
    sum_save = heat_save + fan_save
    share = sum_save / total_energy_year * 100
    gap = 10 - share

    intro = NarrativeBlock([], "Vorgehen und Bezugsgröße", (
        f"Das Einsparpotenzial wird aus den gemessenen Verbräuchen abgeschätzt. Bezugsgröße ist der gemessene "
        f"Gesamtverbrauch aus Wärme (Zähler 019) und Ventilatorstrom (Zähler 021 und 022) von hochgerechnet "
        f"{_de(total_energy_year)} kWh pro Jahr. Der Messzeitraum von {days} Tagen wird dazu auf ein Jahr "
        f"umgerechnet. Nicht gemessene Verbraucher, etwa Pumpenstrom oder Beleuchtung, sind nicht enthalten. "
        f"Die Maßnahmen beruhen auf den im Bericht genannten Annahmen und liefern Größenordnungen, keine Garantien."
    ))
    m1 = NarrativeBlock([], f"Maßnahme 1: Heizgrenze bei {th.heizgrenze_aul:.0f} °C Außentemperatur", (
        f"Bei einer Heizgrenze schaltet die Regelung den Heizbetrieb ab, sobald die Außentemperatur im Tagesmittel "
        f"über einem festgelegten Wert liegt. Die Auswertung der Heizkurve hat gezeigt, dass die Vorlauftemperatur "
        f"auch bei warmer Witterung deutlich über der Raumtemperatur bleibt. In {len(warm_days)} von "
        f"{int(aul_daily.notna().sum())} Tagen ({_de(warm_share, 0)} %) lag das Tagesmittel der Außentemperatur über "
        f"{th.heizgrenze_aul:.0f} °C. An diesen Tagen wurden {_de(heat_warm)} kWh Wärme verbraucht "
        f"({_de(heat_warm / heat_total * 100, 1)} % des gemessenen Wärmeverbrauchs). Unter der Annahme, dass "
        f"{th.heat_avoid_share*100:.0f} % davon durch konsequentes Abschalten vermeidbar sind, ergibt sich eine "
        f"Einsparung von {_de(heat_save)} kWh pro Jahr, das entspricht rund {_de(heat_save * th.heat_price)} € bei "
        f"{_de(th.heat_price, 2)} €/kWh. Das Potenzial ist klein, weil der Wärmeverbrauch im Sommer bereits niedrig ist. "
        f"Der Hauptvorteil der Maßnahme liegt darin, Zirkulations- und Leitungsverluste in der Übergangszeit zu vermeiden, "
        f"die hier nicht separat gemessen werden."
    ))
    m2 = NarrativeBlock([], "Maßnahme 2: Nachtabsenkung der RLT-Ventilatoren", (
        f"Die RLT-Anlage läuft nach den Auswertungen im Dauerbetrieb, ohne erkennbaren Unterschied zwischen Tag, Nacht "
        f"und Wochenende. Die beiden Ventilatoren verbrauchen zusammen {_de(fans * to_year)} kWh Strom pro Jahr. "
        f"Wird der Volumenstrom in Bereichen ohne Hygieneanforderung nachts für {th.rlt_night_hours:.0f} Stunden um "
        f"{th.rlt_night_reduction*100:.0f} % reduziert, spart das {_de(fan_save)} kWh pro Jahr "
        f"({_de(fan_save * th.power_price)} € bei {_de(th.power_price, 2)} €/kWh). Die Annahme bezieht sich direkt auf den "
        f"Stromverbrauch. Da die Leistungsaufnahme eines Ventilators etwa mit der dritten Potenz der Drehzahl sinkt, "
        f"genügt dafür bereits eine moderate Drehzahlabsenkung um rund 20 %. Voraussetzung ist, dass sensible Bereiche wie Operationssäle und "
        f"Intensivpflege ausgenommen werden. Die geringere Luftmenge senkt zusätzlich den Wärmebedarf der Lüftung, "
        f"was hier nicht beziffert ist."
    ))
    ziel = "erreicht" if share >= 10 else "nicht erreicht"
    conclusion = NarrativeBlock([], "Gesamteinordnung", (
        f"Beide Maßnahmen zusammen sparen {_de(sum_save)} kWh pro Jahr und {_de(heat_save * th.heat_price + fan_save * th.power_price)} € "
        f"Energiekosten. Das sind {_de(share, 1)} % des gemessenen Gesamtverbrauchs. Das Einsparziel von 10 % wird damit "
        f"{ziel}" + (f"; es fehlen rechnerisch {_de(gap, 1)} Prozentpunkte. " if share < 10 else ". ") +
        "Weiteres Potenzial ist in den Daten erkennbar, aber nicht bezifferbar: die vollständige Sommerabschaltung der "
        "Heizkreispumpen, die Verbesserung der geringen Temperaturspreizung durch eine Differenzdruckregelung sowie "
        "die Absenkung der zu hohen Vorlauftemperatur in den FBH-Zonen von Gebäude 08. Für diese Punkte fehlen "
        "Pumpenstrom- und Volumenstrommessungen."
    ))
    return [intro, m1, m2, conclusion]
