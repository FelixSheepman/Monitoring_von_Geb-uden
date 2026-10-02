"""
Automatisierte Auswertungstexte - Ersatz fuer die manuelle Interpretation in
Kapitel 6.4 der Hausarbeit ("Auswertung der Ergebnisse").

Anders als die Datenpruefung (quality.py), die einzelne Spalten prueft,
verknuepfen diese Funktionen mehrere Groessen zu einer fachlichen Aussage -
z.B. "Heizkurve zu flach/ohne Heizgrenze" aus Aussentemperatur + Vorlauf.
Alle Zahlen im Text werden live aus den Daten berechnet (keine Textbausteine
mit festen Werten), damit der Text bei neuen Messdaten automatisch mitzieht.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import daily_consumption, duration_curve, duration_curve_percentiles
from .settings import Thresholds


@dataclass
class NarrativeBlock:
    figure_keys: list[str]
    heading: str
    text: str


def place_by_figure(narrative: list[NarrativeBlock], figure_keys_in_order: list[str]
                     ) -> tuple[dict[str, list[NarrativeBlock]], list[NarrativeBlock]]:
    """Ordnet jeden Textblock der LETZTEN Abbildung zu, auf die er sich bezieht (dann sind beim Lesen
    bereits alle Bezuege gezeigt worden); Bloecke ohne Bezug zu einer vorhandenen Abbildung landen in
    der zweiten Rueckgabe. Gemeinsam fuer Word-, HTML- und Excel-Export, damit alle drei Formate
    dieselbe Zuordnung von Auswertungstext zu Abbildung zeigen."""
    placed: dict[str, list[NarrativeBlock]] = {}
    unassigned: list[NarrativeBlock] = []
    for b in narrative:
        valid = [k for k in b.figure_keys if k in figure_keys_in_order]
        if valid:
            placed.setdefault(max(valid, key=figure_keys_in_order.index), []).append(b)
        else:
            unassigned.append(b)
    return placed, unassigned


def _heizkurve_text(df: pd.DataFrame, aul_col: str, vl_col: str, th: Thresholds) -> NarrativeBlock:
    sub = df[[aul_col, vl_col]].dropna()
    slope, intercept = np.polyfit(sub[aul_col], sub[vl_col], 1)

    above = sub[sub[aul_col] > th.heizgrenze_aul]
    frac_still_heating = (above[vl_col] > th.aktiv_schwelle_vl).mean() if len(above) else float("nan")
    mean_vl_above = above[vl_col].mean() if len(above) else float("nan")

    text = (
        f"Die Regressionsgerade der Heizkurve fällt mit einer Steigung von {slope:.2f} K "
        f"Vorlauftemperatur je K Außentemperatur ({intercept:.1f} °C bei 0 °C Außentemperatur). "
        f"Oberhalb von {th.heizgrenze_aul:.0f} °C Außentemperatur – ab der ein Heizbetrieb energetisch "
        f"i. d. R. nicht mehr erforderlich ist – liegt die Vorlauftemperatur in "
        f"{frac_still_heating*100:.0f} % der Zeitschritte weiterhin über {th.aktiv_schwelle_vl:.0f} °C "
        f"(Mittelwert {mean_vl_above:.1f} °C). Das deutet auf eine fehlende oder zu hoch angesetzte "
        f"Heizgrenztemperatur in der Regelung hin."
    )
    return NarrativeBlock(["heizkurve"], "Heizkurve ohne erkennbare Heizgrenze", text)


def _rlt_betrieb_text(df: pd.DataFrame, vl_col: str, meter_ab: str, meter_zu: str) -> NarrativeBlock:
    series = df[vl_col].dropna()
    hourly_profile = series.groupby(series.index.hour).mean()
    day_night_spread = hourly_profile.max() - hourly_profile.min()

    daily_ab = daily_consumption(df, meter_ab)
    is_weekend = daily_ab.index.dayofweek >= 5
    weekday_mean = daily_ab[~is_weekend].mean()
    weekend_mean = daily_ab[is_weekend].mean()
    weekend_diff_pct = (weekend_mean - weekday_mean) / weekday_mean * 100 if weekday_mean else float("nan")

    text = (
        f"Der mittlere Tagesgang der primären RLT-Vorlauftemperatur schwankt über 24 Stunden nur um "
        f"{day_night_spread:.1f} K (Minimum {hourly_profile.min():.1f} °C, Maximum {hourly_profile.max():.1f} °C) "
        f"– eine ausgeprägte Nachtabsenkung ist nicht erkennbar. Der tägliche Stromverbrauch des "
        f"Abluftventilators unterscheidet sich am Wochenende mit {weekend_mean:.1f} kWh/Tag nur um "
        f"{weekend_diff_pct:+.1f} % vom Werktagsmittel ({weekday_mean:.1f} kWh/Tag), was auf einen "
        f"durchgehenden Dauerbetrieb der RLT-Anlage auch außerhalb der Kernnutzungszeiten schließen lässt."
    )
    return NarrativeBlock(
        ["carpet_rlt_vl", "carpet_rlt_rl", "strom_rlt_taeglich"],
        "RLT-Anlage im Dauerbetrieb ohne erkennbare Nachtabsenkung", text,
    )


def _zonenvergleich_text(df: pd.DataFrame, fbh_cols: list[tuple[str, str]],
                          ref_col: str, ref_label: str, th: Thresholds) -> NarrativeBlock:
    lines = []
    worst_label, worst_p95 = None, -1
    for label, col in fbh_cols:
        p95 = df[col].quantile(0.95)
        if p95 > worst_p95:
            worst_p95, worst_label = p95, label
    ref_p95 = df[ref_col].quantile(0.95)

    text = (
        f"Für Niedertemperatursysteme wie Fußbodenheizungen gilt eine Auslegungsgrenze von rund "
        f"{th.fbh_limit:.0f} °C Vorlauftemperatur. Die Zone „{worst_label}“ überschreitet "
        f"dieses Niveau im 95. Perzentil mit {worst_p95:.1f} °C deutlich und nähert sich damit dem "
        f"Temperaturniveau der {ref_label} ({ref_p95:.1f} °C im 95. Perzentil). Dies deutet auf einen "
        f"fehlerhaften hydraulischen Abgleich oder eine übersteuerte Mischerregelung in dieser Zone hin."
    )
    return NarrativeBlock(["zonenvergleich"], "Hydraulischer Abgleich: Auffällig hohe FBH-Vorlauftemperatur", text)


def _delta_t_text(df: pd.DataFrame, pairs: list[tuple[str, str, str]], th: Thresholds) -> NarrativeBlock:
    parts = []
    for label, vl_col, rl_col in pairs:
        dt = df[vl_col] - df[rl_col]
        active = df[vl_col] > th.aktiv_schwelle_vl
        frac_low = (dt[active] < th.delta_t_min).mean() if active.any() else float("nan")
        parts.append(f"{label} in {frac_low*100:.0f} % der aktiven Betriebszeit")

    text = (
        "Bei effizientem Betrieb sollte die Temperaturspreizung zwischen Vor- und Rücklauf während "
        f"aktiver Heizphasen deutlich über {th.delta_t_min:.0f} Kelvin liegen. In den vorliegenden Daten liegt sie bei "
        f"{' bzw. '.join(parts)} unterhalb dieses Werts. Wiederkehrende Phasen mit sehr geringer "
        "Spreizung sprechen für ungeregelt weiterlaufende Umwälzpumpen ohne Differenzdruckregelung "
        "und damit für vermeidbaren Pumpenstromverbrauch bei gleichzeitig ineffizienter Wärmeübergabe."
    )
    return NarrativeBlock(["delta_t"], "Geringe Temperaturspreizung deutet auf ungeregelte Pumpen hin", text)


_MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
           "November", "Dezember"]
HEIZPERIODE_MONATE = (10, 11, 12, 1, 2, 3, 4)   # 1.10. bis 30.4., wie bei der Datenabdeckung (assessment.py)
SOMMER_MONATE = (6, 7, 8)


def _aussetzer_zeitpunkte(df: pd.DataFrame, cols: list[str]) -> tuple[int, list[str]]:
    """Ereignisse mit Messwert exakt 0 (Zeitschritte im Abstand bis 1 h = ein Ereignis): Anzahl der Ereignisse
    und deren Monate als 'Monat Jahr' (ohne Wiederholung, chronologisch)."""
    events: list[pd.Timestamp] = []
    last = None
    for t in df.index[(df[cols] == 0).any(axis=1)]:
        if last is None or (t - last) > pd.Timedelta(hours=1):
            events.append(t)
        last = t
    labels: list[str] = []
    for t in events:
        label = f"{_MONATE[t.month - 1]} {t.year}"
        if label not in labels:
            labels.append(label)
    return len(events), labels


def _regelguete_text(df: pd.DataFrame, label: str, ist_col: str, soll_col: str, limit: float, limit_label: str,
                     figure_key: str, heizkurve_bezug: bool = False) -> NarrativeBlock:
    """Regelguete (Soll- vs. Ist-Vorlauf) getrennt nach Heizperiode und Sommer: folgt der Ist dem Soll, wird die
    zulaessige Vorlauftemperatur eingehalten, liegt im Sommer eine dauerhafte Regelabweichung vor, und gibt es
    Aussetzer (Messwert 0)? Alle Zahlen und Zeitpunkte stammen live aus den Daten."""
    d = df[[ist_col, soll_col]].replace(0, np.nan)
    heiz = d[d.index.month.isin(HEIZPERIODE_MONATE)].dropna()
    sommer = d[d.index.month.isin(SOMMER_MONATE)].dropna()

    parts: list[str] = []
    h_lo, h_hi = heiz[ist_col].quantile([0.05, 0.95])
    corr = heiz[ist_col].corr(heiz[soll_col]) if len(heiz) > 2 else float("nan")
    abw = float((heiz[ist_col] - heiz[soll_col]).abs().median())
    folgt = corr >= 0.8 and abw <= 3
    if folgt:
        parts.append(
            f"Während der Heizperiode (Oktober–April) folgt die Ist-Vorlauftemperatur der Soll-Vorgabe weitgehend "
            f"(mittlere Abweichung {abw:.1f} K) und bewegt sich überwiegend zwischen {h_lo:.0f} °C und {h_hi:.0f} °C.")
    else:
        s_lo, s_hi = heiz[soll_col].quantile([0.05, 0.95])
        parts.append(
            f"Während der Heizperiode (Oktober–April) folgt die Ist-Vorlauftemperatur der Soll-Vorgabe nicht erkennbar: "
            f"Der Sollwert liegt überwiegend zwischen {s_lo:.0f} °C und {s_hi:.0f} °C, die gemessene Ist-Vorlauftemperatur "
            f"dagegen zwischen {h_lo:.0f} °C und {h_hi:.0f} °C (mittlere Abweichung {abw:.1f} K). Eine Regelgüte lässt sich "
            "damit nicht beurteilen; zu klären ist, ob der hinterlegte Sollwert für diesen Kreis überhaupt maßgeblich ist.")
    ist_max = float(d[ist_col].max())
    ueber = float((d[ist_col] > limit).mean() * 100)
    if ist_max <= limit:
        parts.append(f"Die zulässige Vorlauftemperatur ({limit_label}) von {limit:.0f} °C wird dabei zu keinem Zeitpunkt "
                     f"überschritten (Maximum {ist_max:.1f} °C), sodass aus thermischer Sicht kein unzulässiger "
                     "Betriebszustand vorliegt.")
    else:
        parts.append(f"Die zulässige Vorlauftemperatur ({limit_label}) von {limit:.0f} °C wird überschritten "
                     f"(Maximum {ist_max:.1f} °C, in {ueber:.1f} % der Zeitschritte). Dies ist ein Hinweis auf eine zu hoch "
                     "eingestellte Regelung oder eine falsch hinterlegte Grenze und mit dem Betreiber zu klären.")

    heading = f"Regelgüte {label}: Ist-Vorlauf folgt dem Sollwert" if folgt else f"Regelgüte {label}: Ist-Vorlauf folgt dem Sollwert nicht"
    if len(sommer) > 96:
        soll_s = float(sommer[soll_col].median())
        ist_lo, ist_hi = sommer[ist_col].quantile([0.05, 0.95])
        dev = float((sommer[ist_col] - sommer[soll_col]).median())
        if dev > 3:
            parts.append(
                f"Außerhalb der Heizperiode tritt eine dauerhafte Regelabweichung auf: Die Soll-Vorlauftemperatur liegt in den "
                f"Sommermonaten (Juni–August) bei rund {soll_s:.0f} °C, die gemessene Ist-Vorlauftemperatur verbleibt jedoch "
                f"auf einem Niveau von etwa {ist_lo:.0f} °C bis {ist_hi:.0f} °C (im Mittel {dev:.1f} K darüber). Die Anlage "
                "hält damit über die gesamte Sommerperiode eine Vorlauftemperatur aufrecht, die weder angefordert noch "
                "für die Wärmeversorgung erforderlich ist. "
                + ("Dieser Befund passt zur Heizkurve und zum täglichen Wärmeverbrauch und deutet auf das Fehlen "
                   "einer wirksamen Heizgrenztemperatur hin." if heizkurve_bezug else
                   "Das deutet auf das Fehlen einer wirksamen Heizgrenztemperatur bzw. Sommerabschaltung hin."))
            if folgt:
                heading = f"Regelgüte {label}: dauerhafte Regelabweichung im Sommer"
        else:
            parts.append(f"Auch in den Sommermonaten (Juni–August) bleibt die Ist-Vorlauftemperatur nahe am Sollwert "
                         f"(Soll rund {soll_s:.0f} °C, mittlere Abweichung {dev:+.1f} K).")

    n_events, months = _aussetzer_zeitpunkte(df, [ist_col, soll_col])
    if n_events:
        wann = f"an {n_events} Zeitpunkten" if n_events > 1 else "an einem Zeitpunkt"
        parts.append(
            f"Zusätzlich sind {wann} ({', '.join(months)}) Aussetzer mit einem Messwert von 0 °C zu erkennen. Ein Wert von 0 °C ist "
            "im laufenden Anlagenbetrieb nicht plausibel und deutet auf einen kurzzeitigen Ausfall der Messwerterfassung "
            "oder -übertragung hin. Die Aussagekraft des Datensatzes bleibt insgesamt erhalten; die betroffenen Werte "
            "lassen sich im Tab Datenprüfung gezielt von der weiteren Auswertung ausschließen.")
    return NarrativeBlock([figure_key], heading, " ".join(parts))


def _sommerbetrieb_text(df: pd.DataFrame, meter_col: str) -> NarrativeBlock:
    daily = daily_consumption(df, meter_col)
    summer = daily[daily.index.month.isin([6, 7, 8])]
    winter = daily[daily.index.month.isin([12, 1, 2])]
    ratio_pct = summer.mean() / winter.mean() * 100 if winter.mean() else float("nan")

    text = (
        f"Der mittlere tägliche Wärmeverbrauch sinkt in den Sommermonaten (Juni–August) auf "
        f"{summer.mean():.1f} kWh/Tag gegenüber {winter.mean():.1f} kWh/Tag im Winter "
        f"(Dezember–Februar), also auf rund {ratio_pct:.1f} % des winterlichen Niveaus. Der Verbrauch "
        "fällt jedoch nicht auf null, was auf fortlaufende Zirkulations- bzw. Leitungsverluste oder "
        "unnötigen Restbetrieb außerhalb der eigentlichen Heizperiode hindeutet."
    )
    return NarrativeBlock(["waerme_taeglich"], "Restwärmeverbrauch außerhalb der Heizperiode", text)


def _pumpen_text(df: pd.DataFrame, pump_cols: list[tuple[str, str]], meter_col: str) -> NarrativeBlock:
    parts, summer_shares, winter_shares = [], [], []
    for label, col in pump_cols:
        on = df[col].dropna()
        summer = on[on.index.month.isin([6, 7, 8])].mean()
        winter = on[on.index.month.isin([12, 1, 2])].mean()
        summer_shares.append(summer)
        winter_shares.append(winter)
        parts.append(f"{label} im Winter {winter*100:.0f} %, im Sommer {summer*100:.0f} %")
    summer_avg = sum(summer_shares) / len(summer_shares)
    daily = daily_consumption(df, meter_col)
    summer_heat = daily[daily.index.month.isin([6, 7, 8])].mean()

    if summer_avg > 0.8:
        heading = "Heizkreispumpen laufen ganzjährig durch"
        judgement = ("Eine witterungs- oder bedarfsabhängige Pumpenabschaltung (Sommerabschaltung) ist nicht "
                     "erkennbar; sie würde Pumpenstrom und Zirkulationsverluste vermeiden.")
    else:
        heading = "Heizkreispumpen mit Sommerabschaltung, aber Restlaufzeiten"
        judgement = (f"Eine Sommerabschaltung ist erkennbar; im Sommermittel laufen die Pumpen jedoch noch zu "
                     f"{summer_avg*100:.0f} % der Zeit. Jede weitere Verkürzung dieser Restlaufzeiten spart Pumpenstrom "
                     "und Zirkulationsverluste.")

    jun = {}
    for label, col in pump_cols:
        on = df[col].dropna()
        for year in sorted(set(on.index.year)):
            m = on[(on.index.year == year) & (on.index.month == 6)]
            if len(m) > 96 * 20:
                jun.setdefault(label, {})[year] = m.mean() * 100
    changes = [f"{lbl}: Juni {y0} {v[y0]:.0f} % gegenüber Juni {y1} {v[y1]:.0f} %"
               for lbl, v in jun.items() if len(v) >= 2 for y0, y1 in [(min(v), max(v))] if abs(v[y1] - v[y0]) > 15]
    change_text = (" Auffällig ist der Vergleich derselben Jahreszeit: " + "; ".join(changes) +
                   " – die Pumpenregelung verhält sich in den beiden Jahren unterschiedlich.") if changes else ""

    text = ("Anteil der Betriebszeit der Heizkreispumpen: " + "; ".join(parts) +
            f". Der mittlere Wärmeverbrauch im Sommer beträgt {summer_heat:.1f} kWh/Tag. " + judgement + change_text)
    return NarrativeBlock(["pumpenlaufzeit"], heading, text)


def _dauerlinie_text(df: pd.DataFrame, meter_col: str) -> NarrativeBlock:
    curve = duration_curve(df, meter_col)
    pct = duration_curve_percentiles(curve, (0.01, 0.05, 0.20))
    h1, p1 = pct[0.01]
    h5, p5 = pct[0.05]
    h20, p20 = pct[0.20]
    peak = curve["Leistung_kW"].max()
    text = (
        f"Die geordnete Dauerlinie zeigt die aus dem Wärmemengenzähler berechnete thermische Leistung, absteigend "
        f"sortiert über die Betriebsstunden. Die Spitzenleistung von {peak:.0f} kW wird nur kurzzeitig erreicht: "
        f"In {h1:.0f} Betriebsstunden (rund 1 % der erfassten Zeit) wird eine Leistung von {p1:.0f} kW oder mehr "
        f"abgerufen, in {h5:.0f} Stunden (5 %) noch {p5:.0f} kW, in {h20:.0f} Stunden (20 %) nur noch {p20:.0f} kW. "
        f"Ein Grundlastkessel, der auf einen Wert deutlich unter der Spitzenleistung ausgelegt ist, würde die "
        f"meiste Zeit genügen; nur für die seltenen Spitzen oberhalb seiner eigenen Leistung wäre ein "
        f"Zusatz- bzw. Spitzenlastgerät erforderlich. Die tatsächliche Leistung des vorhandenen Wärmeerzeugers "
        f"ist in den Messdaten nicht enthalten – die markierten Punkte sind Vorschläge für mögliche "
        f"Auslegungsgrenzen und durch die Anlagendokumentation bzw. den Betreiber zu bestätigen."
    )
    return NarrativeBlock(["dauerlinie_leistung"], "Geordnete Dauerlinie: Auslegung eines Zusatzheizgeräts", text)


def build_narrative(df: pd.DataFrame, th: Thresholds | None = None) -> list[NarrativeBlock]:
    """Erzeugt alle Auswertungstexte fuer den vorliegenden (vollaufgeloesten) Datensatz."""
    th = th or Thresholds()
    return [
        _regelguete_text(df, "Stat. Heizung Geb.06", "Stat. Heizung Geb.06 VL (Ist)", "Stat. Heizung Geb.06 VL (Soll)",
                         th.heizkoerper_limit, "Heizkörper", "regelguete_stat_heizung", heizkurve_bezug=True),
        _heizkurve_text(df, "RLT KL01 Außenluft", "Stat. Heizung Geb.06 VL (Ist)", th),
        _regelguete_text(df, "FBH Geb.06", "FBH Geb.06 VL (Ist)", "FBH Geb.06 VL (Soll)",
                         th.fbh_limit, "Fußbodenheizung", "regelguete_fbh"),
        _rlt_betrieb_text(df, "RLT primär VL", "Zähler 021 – Strom Abluft", "Zähler 022 – Strom Zuluft"),
        _zonenvergleich_text(df, [
            ("FBH Geb.08 KI-Räume", "FBH Geb.08 KI-Räume VL"),
            ("FBH Geb.08 Intensivpflege", "FBH Geb.08 Intensivpflege VL"),
            ("FBH Geb.06", "FBH Geb.06 VL (Ist)"),
        ], "Stat. Heizung Geb.06 VL (Ist)", "statischen Heizung Geb.06", th),
        _delta_t_text(df, [
            ("Stat. Heizung Geb.06", "Stat. Heizung Geb.06 VL (Ist)", "Stat. Heizung Geb.06 RL"),
            ("FBH Geb.06", "FBH Geb.06 VL (Ist)", "FBH Geb.06 RL"),
        ], th),
        _sommerbetrieb_text(df, "Zähler 019 – WMZ"),
        _pumpen_text(df, [("Stat. Heizung Geb.06", "Stat. Heizung Geb.06 Pumpe"), ("FBH Geb.06", "FBH Geb.06 Pumpe")],
                     "Zähler 019 – WMZ"),
        _dauerlinie_text(df, "Zähler 019 – WMZ"),
    ]
