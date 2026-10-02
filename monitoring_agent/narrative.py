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


def _monatsliste(months: list[pd.Timestamp]) -> str:
    """Aufeinanderfolgende Monate als Bereich, z.B. 'Juni bis August 2025, Dezember 2025'."""
    groups: list[list[pd.Timestamp]] = []
    for m in sorted(months):
        if groups and (m.year * 12 + m.month) - (groups[-1][-1].year * 12 + groups[-1][-1].month) == 1:
            groups[-1].append(m)
        else:
            groups.append([m])
    return ", ".join(_monat(g[0]) if len(g) == 1 else f"{_MONATE[g[0].month - 1]} bis {_monat(g[-1])}" for g in groups)


def _delta_t_details(df: pd.DataFrame, pairs: list[tuple[str, str, str, str]], th: Thresholds) -> str:
    """Ergaenzung zur Spreizung: Spreizung im Heizbetrieb, Monate mit Spreizung nahe null (samt Pumpenlaufzeit)
    und negative Spreizungen (Ruecklauf waermer als Vorlauf) mit Abgleich gegen den Pumpenstatus."""
    ranges, zero_txt, neg_txt = [], [], []
    for label, vl_col, rl_col, pump_col in pairs:
        vl, rl, pump = df[vl_col].replace(0, np.nan), df[rl_col].replace(0, np.nan), df[pump_col]
        dt = (vl - rl).dropna()
        heiz = dt[(vl.reindex(dt.index) > th.aktiv_schwelle_vl) & dt.index.month.isin(HEIZPERIODE_MONATE)]
        if len(heiz) > 96:
            q05, q95 = heiz.quantile([0.05, 0.95])
            ranges.append(f"{label} im Median {heiz.median():.1f} K ({q05:.1f} K bis {q95:.1f} K im 5.–95. Perzentil)")

        monthly = dt.resample("MS").agg(["median", "size"])
        near0 = monthly[(monthly["size"] >= 96 * 10) & (monthly["median"] < 1.0)]
        if len(near0):
            on = float(pump[dt.index[dt.index.to_period("M").to_timestamp().isin(near0.index)]].mean() * 100)
            if on >= 50:
                deut = ("das Heizungswasser zirkuliert dabei ohne nennenswerten Temperaturabfall; laufen die Pumpen ungeregelt "
                        "weiter, wird elektrische Energie für eine nutzlose Wasserzirkulation aufgewendet")
            else:
                deut = ("die Pumpe steht in dieser Zeit überwiegend still, die geringe Spreizung spiegelt also kaum Durchfluss "
                        "wider und ist für sich kein Hinweis auf vermeidbaren Pumpenstrom")
            zero_txt.append(f"Bei {label} liegt die Spreizung im Monatsmedian in {_monatsliste(list(near0.index))} unter 1 K "
                            f"(Pumpe in diesen Monaten zu {on:.0f} % der Zeit in Betrieb); {deut}.")

        neg = dt[dt < 0]
        if len(neg) >= 50:
            status = pump.reindex(neg.index).dropna()
            off = float((status == 0).mean() * 100) if len(status) else float("nan")
            if off >= 80:
                deut = "überwiegend bei stehender Pumpe, was sich durch Auskühlen bzw. Nachwärme der Leitung erklären lässt"
            elif off <= 20:
                deut = ("überwiegend bei laufender Pumpe; ein wärmerer Rücklauf als Vorlauf ist im durchströmten Betrieb "
                        "physikalisch nicht möglich und deutet auf eine Abweichung zwischen den beiden Temperatursensoren "
                        "hin, deren Kalibrierung zu prüfen ist")
            else:
                deut = "sowohl bei stehender als auch bei laufender Pumpe; die Zeitpunkte sind mit dem Pumpenstatus abzugleichen"
            neg_txt.append(f"{label}: {len(neg)} Zeitschritte ({len(neg) / len(dt) * 100:.1f} %) mit negativer Spreizung bis "
                           f"{neg.min():.1f} K, davon {100 - off:.0f} % bei laufender Pumpe – {deut}")

    out = []
    if ranges:
        out.append("Im regulären Heizbetrieb (Oktober–April, aktiver Betrieb) liegt die Spreizung bei " + "; ".join(ranges) + ".")
    out += zero_txt
    if neg_txt:
        out.append("Auffällig sind zudem negative Spreizungen: " + "; ".join(neg_txt) + ".")
    return " ".join(out)


def _pumpen_schluss(df: pd.DataFrame, pairs: list[tuple[str, str, str, str]], th: Thresholds) -> str:
    """Deutung der Zeitschritte mit geringer Spreizung anhand des Pumpenstatus: laeuft die Pumpe in mehr als der
    Haelfte davon, sprechen sie fuer ungeregelt weiterlaufende Pumpen; sonst eher fuer auskuehlende Leitungen."""
    laufen, stehen = [], []
    for label, vl_col, rl_col, pump_col in pairs:
        vl = df[vl_col].replace(0, np.nan)
        low = (vl > th.aktiv_schwelle_vl) & ((vl - df[rl_col].replace(0, np.nan)) < th.delta_t_min)
        status = df.loc[low, pump_col].dropna()
        if not len(status):
            continue
        on = float(status.mean() * 100)
        (laufen if on >= 50 else stehen).append((label, on))
    out = []
    if laufen:
        out.append("Bei " + " und ".join(f"{l} läuft die Pumpe in {o:.0f} %" for l, o in laufen) + " dieser Zeitschritte weiter. "
                   "Wiederkehrende Phasen mit sehr geringer Spreizung bei laufender Pumpe sprechen für ungeregelt weiterlaufende "
                   "Umwälzpumpen ohne Differenzdruckregelung und damit für vermeidbaren Pumpenstromverbrauch bei gleichzeitig "
                   "ineffizienter Wärmeübergabe.")
    if stehen:
        out.append("Bei " + " und ".join(f"{l} steht die Pumpe dagegen in {100 - o:.0f} %" for l, o in stehen) + " dieser "
                   "Zeitschritte still; dort spiegelt die geringe Spreizung eher abkühlende Leitungen als einen Pumpenbetrieb "
                   "ohne Wärmeabnahme wider.")
    return " ".join(out) or ("Wiederkehrende Phasen mit sehr geringer Spreizung sprechen für ungeregelt weiterlaufende "
                             "Umwälzpumpen ohne Differenzdruckregelung und damit für vermeidbaren Pumpenstromverbrauch bei "
                             "gleichzeitig ineffizienter Wärmeübergabe.")


def _delta_t_text(df: pd.DataFrame, pairs: list[tuple[str, str, str, str]], th: Thresholds) -> NarrativeBlock:
    parts = []
    for label, vl_col, rl_col, _pump in pairs:
        dt = df[vl_col] - df[rl_col]
        active = df[vl_col] > th.aktiv_schwelle_vl
        frac_low = (dt[active] < th.delta_t_min).mean() if active.any() else float("nan")
        parts.append(f"{label} in {frac_low*100:.0f} % der aktiven Betriebszeit")

    text = (
        "Bei effizientem Betrieb sollte die Temperaturspreizung zwischen Vor- und Rücklauf während "
        f"aktiver Heizphasen deutlich über {th.delta_t_min:.0f} Kelvin liegen. In den vorliegenden Daten liegt sie bei "
        f"{' bzw. '.join(parts)} unterhalb dieses Werts. " + _pumpen_schluss(df, pairs, th)
    )
    details = _delta_t_details(df, pairs, th)
    if details:
        text += " " + details
    return NarrativeBlock(["delta_t"], "Geringe Temperaturspreizung deutet auf ungeregelte Pumpen hin", text)


_MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
           "November", "Dezember"]
HEIZPERIODE_MONATE = (10, 11, 12, 1, 2, 3, 4)   # 1.10. bis 30.4., wie bei der Datenabdeckung (assessment.py)
SOMMER_MONATE = (6, 7, 8)


def _datum(t: pd.Timestamp) -> str:
    return f"{t:%d.%m.%Y}"


def _aussetzer_zeitpunkte(df: pd.DataFrame, cols: list[str]) -> list[pd.Timestamp]:
    """Beginn jedes Ereignisses mit Messwert exakt 0 (Zeitschritte im Abstand bis 1 h = ein Ereignis)."""
    events: list[pd.Timestamp] = []
    last = None
    for t in df.index[(df[cols] == 0).any(axis=1)]:
        if last is None or (t - last) > pd.Timedelta(hours=1):
            events.append(t)
        last = t
    return events


def _monat(t: pd.Timestamp) -> str:
    return f"{_MONATE[t.month - 1]} {t.year}"


def _sollwert_verlauf(soll: pd.Series) -> tuple[str, bool]:
    """Beschreibt den Verlauf des Sollwerts als Abschnitte gleichen (gerundeten) Monatsmedians, z.B.
    '20 °C (November 2024 bis September 2025), 22 °C (Oktober 2025)'. Zweiter Wert: Sollwert nahezu konstant
    (Monatsmediane umfassen hoechstens 3 K), also keine witterungsgefuehrte Nachfuehrung."""
    monthly = soll.resample("MS").median().dropna()
    if monthly.empty:
        return "", False
    level = monthly.round(0).astype(int)
    segments: list[list] = []
    for ts, val in level.items():
        if segments and segments[-1][0] == val:
            segments[-1][2] = ts
        else:
            segments.append([val, ts, ts])
    parts = [f"{val} °C ({_monat(a)}" + (f" bis {_monat(b)})" if b != a else ")") for val, a, b in segments]
    return ", ".join(parts), float(monthly.max() - monthly.min()) <= 3


def _heizperiode_jahr(idx: pd.DatetimeIndex) -> np.ndarray:
    """Startjahr der Heizperiode (Oktober bis April) zu jedem Zeitpunkt, z.B. 2025 fuer Januar 2026."""
    return np.where(idx.month >= 10, idx.year, idx.year - 1)


def _heizperioden(ist: pd.Series) -> list[tuple[str, float, float, float, float]]:
    """Je Heizperiode (Oktober bis April, mit mindestens 60 Tagen Daten): Bezeichnung '2024/25', Median,
    5.- und 95.-Perzentil sowie Standardabweichung des Ist-Vorlaufs."""
    heiz = ist[ist.index.month.isin(HEIZPERIODE_MONATE)].dropna()
    season = _heizperiode_jahr(heiz.index)
    out = []
    for year in sorted(set(season)):
        s = heiz[season == year]
        if len(s) >= 96 * 60:
            out.append((f"{year}/{str(year + 1)[-2:]}", float(s.median()), float(s.quantile(0.05)),
                        float(s.quantile(0.95)), float(s.std())))
    return out


def _regelguete_text(df: pd.DataFrame, label: str, ist_col: str, soll_col: str, limit: float, limit_label: str,
                     figure_key: str, heizkurve_bezug: bool = False, niedertemperatur: bool = False) -> NarrativeBlock:
    """Regelguete (Soll- vs. Ist-Vorlauf): folgt der Ist dem Soll, wie verlaeuft der Sollwert, wird die zulaessige
    Vorlauftemperatur eingehalten (sonst wann und wie hoch), veraendert sich das Betriebsverhalten ueber die
    Heizperioden, liegt im Sommer eine dauerhafte Regelabweichung vor, und gibt es Aussetzer (Messwert 0)?
    Alle Zahlen und Zeitpunkte stammen live aus den Daten."""
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
        verlauf, konstant = _sollwert_verlauf(d[soll_col])
        if konstant:
            parts.append(
                f"Bereits der Verlauf der Soll-Vorgabe ist auffällig: Sie verharrt über den gesamten Erfassungszeitraum "
                f"nahezu unverändert und liegt bei {verlauf}. Eine witterungsgeführte Nachführung ist nicht erkennbar; der "
                "hinterlegte Wert wirkt damit nicht als gleitende Führungsgröße, sondern als fester Grundwert.")
        dev = (heiz[ist_col] - heiz[soll_col])
        d_lo, d_hi = dev.quantile([0.05, 0.95])
        parts.append(
            f"Die Ist-Vorlauftemperatur folgt dieser Vorgabe nicht erkennbar: Sie liegt in der Heizperiode im Mittel "
            f"{dev.median():.1f} K oberhalb des Sollwerts ({d_lo:.0f} K bis {d_hi:.0f} K im 5.–95. Perzentil) und bewegt "
            f"sich überwiegend zwischen {h_lo:.0f} °C und {h_hi:.0f} °C. Eine Regelabweichung dieser Größenordnung über "
            "einen so langen Zeitraum lässt sich nicht mit der Trägheit des Systems erklären. Sie deutet darauf hin, dass "
            "der Kreis dem vorgegebenen Sollwert nicht folgt, sondern von der übergeordneten Wärmeverteilung mitgeführt "
            "oder manuell übersteuert wird (zu klären mit dem Betreiber; im Zusammenhang mit dem Zonenvergleich zu lesen). "
            "Eine Regelgüte lässt sich damit nicht beurteilen.")

    seasons = _heizperioden(d[ist_col])
    if len(seasons) >= 2:
        first, last = seasons[0], seasons[-1]
        # Nur bei echter Veraenderung (Schwankungsbreite mindestens verdoppelt); ein anderes Temperaturniveau
        # allein kann bei witterungsgefuehrten Kreisen einfach am Wetter liegen.
        if last[4] >= 2 * first[4]:
            monthly_std = d[ist_col].resample("MS").std()
            cand = monthly_std[monthly_std.index.month.isin(HEIZPERIODE_MONATE)]
            cand = cand[_heizperiode_jahr(cand.index) > int(first[0][:4])]
            onset = next((ts for ts, s in cand.items() if s > 2 * first[4]), None)
            parts.append(
                f"Ab der Heizperiode {last[0]} ändert sich das Betriebsverhalten erkennbar: Der Ist-Vorlauf liegt in der "
                f"Heizperiode {first[0]} im Median bei {first[1]:.0f} °C ({first[2]:.0f} °C bis {first[3]:.0f} °C), in der "
                f"Heizperiode {last[0]} bei {last[1]:.0f} °C ({last[2]:.0f} °C bis {last[3]:.0f} °C). Die Schwankungsbreite steigt "
                f"deutlich (Standardabweichung {first[4]:.1f} K gegenüber {last[4]:.1f} K)"
                + (f", erkennbar ab {_monat(onset)}." if onset is not None else ".")
                + " Da die Änderung zeitlich klar abgrenzbar ist, liegt die Vermutung nahe, dass in diesem Zeitraum ein "
                  "Eingriff in die Regelung oder in die Hydraulik erfolgt ist (mit dem Betreiber zu klären).")

    ist_max = float(d[ist_col].max())
    over = d[d[ist_col] > limit][ist_col]
    if over.empty:
        parts.append(f"Die zulässige Vorlauftemperatur ({limit_label}) von {limit:.0f} °C wird dabei zu keinem Zeitpunkt "
                     f"überschritten (Maximum {ist_max:.1f} °C), sodass aus thermischer Sicht kein unzulässiger "
                     "Betriebszustand vorliegt.")
    else:
        hours = len(over) * 0.25
        peaks = over.resample("MS").max().dropna()
        peak_txt = "; ".join(f"{_monat(ts)}: bis {v:.1f} °C" for ts, v in peaks.items())
        text = (f"Die zulässige Vorlauftemperatur ({limit_label}) von {limit:.0f} °C wird zwischen dem {_datum(over.index.min())} "
                f"und dem {_datum(over.index.max())} in {len(over)} Zeitschritten (rund {hours:.0f} Stunden) überschritten "
                f"({peak_txt}; Maximum {ist_max:.1f} °C).")
        if niedertemperatur:
            text += (" Da es sich um ein Niedertemperatursystem handelt, ist dieser Zustand nicht nur energetisch nachteilig: "
                     "Zu hohe Vorlauftemperaturen können Estrich und Bodenbelag belasten und zu unzulässig hohen "
                     "Oberflächentemperaturen in den betroffenen Räumen führen. Ursache und Abhilfe sind mit dem Betreiber "
                     "zu klären.")
        else:
            text += " Dies ist ein Hinweis auf eine zu hoch eingestellte Regelung oder eine falsch hinterlegte Grenze und mit dem Betreiber zu klären."
        parts.append(text)

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

    events = _aussetzer_zeitpunkte(df, [ist_col, soll_col])
    if events:
        wann = f"an {len(events)} Zeitpunkten" if len(events) > 1 else "an einem Zeitpunkt"
        parts.append(
            f"Zusätzlich sind {wann} ({', '.join(_datum(t) for t in events)}) Aussetzer mit einem Messwert von 0 °C zu "
            "erkennen. Ein Wert von 0 °C ist im laufenden Anlagenbetrieb nicht plausibel und deutet auf einen "
            "kurzzeitigen Ausfall der Messwerterfassung oder -übertragung hin. Die Aussagekraft des Datensatzes bleibt "
            "insgesamt erhalten; die betroffenen Werte lassen sich im Tab Datenprüfung gezielt von der weiteren Auswertung "
            "ausschließen.")
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
                         th.fbh_limit, "Fußbodenheizung", "regelguete_fbh", niedertemperatur=True),
        _rlt_betrieb_text(df, "RLT primär VL", "Zähler 021 – Strom Abluft", "Zähler 022 – Strom Zuluft"),
        _zonenvergleich_text(df, [
            ("FBH Geb.08 KI-Räume", "FBH Geb.08 KI-Räume VL"),
            ("FBH Geb.08 Intensivpflege", "FBH Geb.08 Intensivpflege VL"),
            ("FBH Geb.06", "FBH Geb.06 VL (Ist)"),
        ], "Stat. Heizung Geb.06 VL (Ist)", "statischen Heizung Geb.06", th),
        _delta_t_text(df, [
            ("Stat. Heizung Geb.06", "Stat. Heizung Geb.06 VL (Ist)", "Stat. Heizung Geb.06 RL", "Stat. Heizung Geb.06 Pumpe"),
            ("FBH Geb.06", "FBH Geb.06 VL (Ist)", "FBH Geb.06 RL", "FBH Geb.06 Pumpe"),
        ], th),
        _sommerbetrieb_text(df, "Zähler 019 – WMZ"),
        _pumpen_text(df, [("Stat. Heizung Geb.06", "Stat. Heizung Geb.06 Pumpe"), ("FBH Geb.06", "FBH Geb.06 Pumpe")],
                     "Zähler 019 – WMZ"),
        _dauerlinie_text(df, "Zähler 019 – WMZ"),
    ]
