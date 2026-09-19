"""
Bewertung der Befunde (Kap. 6.5 der Hausarbeit), Datenabdeckung, Messdatenkopf (Abbildung 1),
Sensorik-Uebersicht (Kap. 4.1) und Theorie-Praxis-Abgleich ("Ueberpruefung theoretischer Aussagen
auch in der Praxis", Kap. 4).

Alle Einstufungen folgen offen gelegten Regeln; jede Zeile nennt Regel und Kennzahl.
"""

from __future__ import annotations

import pandas as pd

from . import anomalies as an
from .config import COLUMNS
from .extras import availability_daily, pump_runtime_monthly
from .metrics import daily_consumption
from .settings import Thresholds

LEVELS = ["gering", "mittel", "hoch"]
FREQ_LIMITS = (10.0, 50.0)     # % der Zeit: mittel ab 10, hoch ab 50
ENERGY_LIMITS = (1.0, 5.0)     # % des Gesamtverbrauchs: mittel ab 1, hoch ab 5

ZONE_LABELS = {
    "wmz_019": ("Wärmemengenzähler 019", "Gesamtanlage"),
    "rlt_primaer": ("RLT primär (Heizregister)", "RLT02/03"),
    "heizung_lager_geb2": ("Statische Heizung Lager", "Gebäude 2"),
    "heizung_geb1_geb3": ("Statische Heizung", "Gebäude 1 (Geb. 3)"),
    "rlt_kl01": ("RLT-Anlage KL01 (RLT02/03.01)", "Luftseite"),
    "strom_abluft": ("Stromzähler Abluftventilator", "RLT02/03"),
    "strom_zuluft": ("Stromzähler Zuluftventilator", "RLT02/03"),
    "stat_heizung_geb06": ("Statische Heizflächen", "Gebäude 06"),
    "fbh_geb06": ("Fußbodenheizung", "Gebäude 06"),
    "fbh_geb08_ki": ("Fußbodenheizung KI-Räume", "Gebäude 08"),
    "fbh_geb08_intensiv": ("Fußbodenheizung Intensivpflege", "Gebäude 08"),
}
ROLE_LABELS = {
    "meter_energy": "Wärmemenge (kumuliert)", "meter_electric": "Elektrische Arbeit (kumuliert)",
    "vl": "Vorlauftemperatur (Ist)", "rl": "Rücklauftemperatur", "soll_vl": "Vorlauf-Sollwert",
    "pump": "Pumpenstatus (0/1)", "aul": "Außenlufttemperatur", "zul": "Zulufttemperatur",
}

RECOMMENDATIONS = {
    "heizkurve": "Heizgrenze in der Regelung einführen (Abschalten der Heizkreise ab Tagesmittel der Außentemperatur oberhalb der Grenze) und Heizkurve nachjustieren.",
    "rlt_dauerbetrieb": "Zeitprogramm bzw. bedarfsgeführte Regelung für die RLT-Anlage einrichten; sensible Bereiche (OP, Intensivpflege) ausnehmen und Absenkung mit dem Betreiber abstimmen.",
    "hydraulik_fbh": "Mischerkreis und Übersteuerung in der Unterstation prüfen, Vorlauftemperatur der FBH-Zone begrenzen und hydraulischen Abgleich kontrollieren.",
    "delta_t": "Differenzdruckgeregelte Pumpen einsetzen bzw. Pumpenkennlinie und Ventile prüfen, um die Spreizung zu erhöhen.",
    "sommer_restwaerme": "Restverbrauch außerhalb der Heizperiode untersuchen (Zirkulations- und Leitungsverluste), Verteilnetz in der Übergangszeit abschalten.",
    "pumpen_sommer": "Sommerabschaltung der Heizkreispumpen konsequent umsetzen und Ursache für unterschiedliches Verhalten in vergleichbaren Monaten klären.",
    "datenqualitaet": "Datenpunkte mit Nullwert-Aussetzern und den gemeinsamen Ausfall mit dem Betreiber klären (z. B. Zeitumstellung, Gateway) und Plausibilitätsüberwachung einrichten.",
    "zaehler": "Zählerrücksprünge klären (Reset, Übertragungsfehler) und bei der Verbrauchsbilanz herausrechnen, damit Tageswerte nicht verfälscht werden.",
}


# ----------------------------------------------------------------------------- Abbildung 1 / Kap. 4.1

def measurement_head(df: pd.DataFrame, n: int = 8) -> pd.DataFrame:
    """Messdatenkopf (Abbildung 1 der Hausarbeit): die ersten n Zeitschritte."""
    head = df.head(n).copy()
    head.insert(0, "Datum", head.index.strftime("%d.%m.%Y %H:%M"))
    return head.reset_index(drop=True)


def sensor_overview() -> pd.DataFrame:
    """Sensorik-Uebersicht aus der Spaltenkonfiguration (Kap. 4.1: Messstellen, Anlage, Messgroesse)."""
    rows = []
    for i, c in enumerate(COLUMNS, start=1):
        anlage, bereich = ZONE_LABELS.get(c.zone, (c.zone, ""))
        rows.append({"Nr.": i, "Messpunkt": c.short, "Anlage": anlage, "Gebäude/Bereich": bereich,
                     "Messgröße": ROLE_LABELS.get(c.role, c.role), "Einheit": c.unit})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- Datenabdeckung

def data_coverage(df: pd.DataFrame, min_share: float = 0.8) -> pd.DataFrame:
    """Abdeckung der Heizperioden (1.10.-30.4.) und Sommerperioden (1.6.-31.8.) mit Messdaten."""
    days_with_data = set(df.dropna(how="all").index.normalize())
    first, last = df.index.min().normalize(), df.index.max().normalize()
    rows = []
    for year in range(first.year - 1, last.year + 1):
        for kind, start, end in (
            ("Heizperiode", pd.Timestamp(year, 10, 1), pd.Timestamp(year + 1, 4, 30)),
            ("Sommerperiode", pd.Timestamp(year + 1, 6, 1), pd.Timestamp(year + 1, 8, 31)),
        ):
            if end < first or start > last:
                continue
            all_days = pd.date_range(start, end, freq="D")
            have = sum(1 for d in all_days if d in days_with_data)
            share = have / len(all_days)
            label = f"{start:%d.%m.%Y} – {end:%d.%m.%Y}"
            rows.append({"Zeitraum": kind, "Bezeichnung": label, "Tage im Zeitraum": len(all_days),
                         "Tage mit Daten": have, "Abdeckung %": round(share * 100, 1),
                         "Erfüllt": "ja" if share >= min_share else "nein"})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- Bewertung

def _level(value: float | None, limits: tuple[float, float]) -> int | None:
    if value is None or pd.isna(value):
        return None
    return 2 if value >= limits[1] else 1 if value >= limits[0] else 0


def _severity(freq: float | None, energy: float | None, floor: int = 0) -> tuple[str, str]:
    lf, le = _level(freq, FREQ_LIMITS), _level(energy, ENERGY_LIMITS)
    parts = []
    if lf is not None:
        parts.append(f"Häufigkeit {freq:.0f} % der Zeit → {LEVELS[lf]} (mittel ab {FREQ_LIMITS[0]:.0f} %, hoch ab {FREQ_LIMITS[1]:.0f} %)")
    if le is not None:
        parts.append(f"Energie {energy:.1f} % des Verbrauchs → {LEVELS[le]} (mittel ab {ENERGY_LIMITS[0]:.0f} %, hoch ab {ENERGY_LIMITS[1]:.0f} %)")
    if floor:
        parts.append(f"Mindeststufe {LEVELS[floor]} wegen Sicherheits-/Bilanzrelevanz")
    level = max([x for x in (lf, le, floor) if x is not None] or [0])
    return LEVELS[level], "Maximum-Prinzip: " + "; ".join(parts) if parts else "keine Kennzahl verfügbar"


def build_assessment(df: pd.DataFrame, quality_df: pd.DataFrame, savings: pd.DataFrame | None,
                     th: Thresholds) -> pd.DataFrame:
    rows = []

    def add(key, bereich, befund, kennzahl, freq, energy, floor=0, hinweis=""):
        level, rule = _severity(freq, energy, floor)
        rows.append({"Schlüssel": key, "Bereich": bereich, "Befund": befund, "Kennzahl": kennzahl,
                     "Schweregrad": level, "Einstufungsregel": rule, "Empfehlung": RECOMMENDATIONS[key],
                     "Hinweis": hinweis})

    sv = savings.set_index("Maßnahme") if savings is not None else None
    heat_share = sv.iloc[0]["Anteil %"] if sv is not None else None
    fan_share = sv.iloc[1]["Anteil %"] if sv is not None else None

    aul, vl = df["RLT KL01 Außenluft"], df["Stat. Heizung Geb.06 VL (Ist)"]
    above = pd.DataFrame({"a": aul, "v": vl}).dropna()
    above = above[above["a"] > th.heizgrenze_aul]
    frac = float((above["v"] > th.aktiv_schwelle_vl).mean() * 100) if len(above) else float("nan")
    add("heizkurve", "Regelung Heizung", "Heizkurve ohne erkennbare Heizgrenze",
        f"{frac:.0f} % der Zeitschritte über {th.heizgrenze_aul:.0f} °C Außentemperatur mit Vorlauf > {th.aktiv_schwelle_vl:.0f} °C",
        frac, heat_share)

    ab = daily_consumption(df, "Zähler 021 – Strom Abluft")
    we = ab[ab.index.dayofweek >= 5].mean(); wt = ab[ab.index.dayofweek < 5].mean()
    add("rlt_dauerbetrieb", "Lüftung (RLT)", "RLT-Anlage im Dauerbetrieb ohne erkennbare Nachtabsenkung",
        f"Wochenende {we:.1f} kWh/Tag gegenüber {wt:.1f} kWh/Tag Werktag ({(we / wt - 1) * 100:+.1f} %)",
        None, fan_share, hinweis="Klinikbetrieb: ein Teil der Bereiche benötigt Dauerbetrieb, Absenkung nur nach Abstimmung.")

    zones = [("FBH Geb.08 KI-Räume", "FBH Geb.08 KI-Räume VL"), ("FBH Geb.08 Intensivpflege", "FBH Geb.08 Intensivpflege VL"),
             ("FBH Geb.06", "FBH Geb.06 VL (Ist)")]
    shares = {lbl: float((df[col].dropna() > th.fbh_limit).mean() * 100) for lbl, col in zones}
    worst = max(shares, key=shares.get)
    add("hydraulik_fbh", "Hydraulik Fußbodenheizung", "Hydraulischer Abgleich: Auffällig hohe FBH-Vorlauftemperatur",
        "; ".join(f"{k}: {v:.0f} % der Zeit über {th.fbh_limit:.0f} °C" for k, v in shares.items()),
        shares[worst], None, floor=1 if any("Intensiv" in k and v >= 1 for k, v in shares.items()) else 0,
        hinweis="Zone Intensivpflege ist sicherheitsrelevant (Überhitzung); Maßnahmen nur mit dem Betreiber abstimmen.")

    pairs = [("Stat. Heizung Geb.06", "Stat. Heizung Geb.06 VL (Ist)", "Stat. Heizung Geb.06 RL"),
             ("FBH Geb.06", "FBH Geb.06 VL (Ist)", "FBH Geb.06 RL")]
    lows = {}
    for lbl, v, r in pairs:
        active = df[v] > th.aktiv_schwelle_vl
        lows[lbl] = float(((df[v] - df[r])[active] < th.delta_t_min).mean() * 100) if active.any() else float("nan")
    add("delta_t", "Hydraulik/Pumpen", "Geringe Temperaturspreizung deutet auf ungeregelte Pumpen hin",
        "; ".join(f"{k}: {v:.0f} % der aktiven Zeit unter {th.delta_t_min:g} K" for k, v in lows.items()),
        max(lows.values()), None)

    heat = daily_consumption(df, "Zähler 019 – WMZ")
    summer_share = float(heat[heat.index.month.isin([6, 7, 8])].sum() / heat.sum() * 100)
    add("sommer_restwaerme", "Wärmeverbrauch", "Restwärmeverbrauch außerhalb der Heizperiode",
        f"Sommermonate (Jun–Aug) = {summer_share:.1f} % des gemessenen Wärmeverbrauchs", None, summer_share)

    monthly = pump_runtime_monthly(df)
    share = monthly.div(monthly.index.days_in_month * 24, axis=0)
    summer_pump = float(share[share.index.month.isin([6, 7, 8])].mean().mean() * 100)
    add("pumpen_sommer", "Pumpen", "Heizkreispumpen mit Sommerabschaltung, aber Restlaufzeiten",
        f"Pumpenlaufzeit im Sommer im Mittel {summer_pump:.0f} % der Zeit", summer_pump, None)

    bad = availability_daily(df)
    bad_share = float(bad.values.sum() / (len(df) * df.shape[1]) * 100)
    common = int(((bad > 0).sum(axis=1) >= 10).sum())
    add("datenqualitaet", "Datenqualität", "Nullwert-Aussetzer und gemeinsamer Datenausfall",
        f"{int(bad.values.sum())} fehlerhafte Zeitschritte ({bad_share:.3f} % aller Werte), {common} Tag(e) mit Ausfall von ≥ 10 Sensoren",
        bad_share, None)

    resets = sum(len(an.meter_resets(df, c)) for c in ("Zähler 019 – WMZ", "Zähler 021 – Strom Abluft", "Zähler 022 – Strom Zuluft"))
    add("zaehler", "Datenqualität", "Rückläufige Zählerstände", f"{resets} Zählerrücksprünge in den drei Zählern",
        None, None, floor=1 if resets else 0, hinweis="Verfälscht Tagesverbräuche, deshalb mindestens mittlere Stufe.")

    out = pd.DataFrame(rows)
    order = {"hoch": 0, "mittel": 1, "gering": 2}
    out = out.sort_values(by="Schweregrad", key=lambda s: s.map(order), kind="stable").reset_index(drop=True)
    out.insert(0, "Nr.", range(1, len(out) + 1))
    return out


def assessment_texts(assess: pd.DataFrame, savings: pd.DataFrame | None) -> dict[str, str]:
    """Ausformulierte Texte fuer Kap. 6.5 (Bewertung) und Kap. 6.6 (Zusammenfassung und Empfehlungen)."""
    counts = assess["Schweregrad"].value_counts()
    n_hoch, n_mittel, n_gering = (int(counts.get(k, 0)) for k in ("hoch", "mittel", "gering"))
    bewertung = (
        f"Die {len(assess)} Befunde wurden nach einheitlichen Regeln bewertet. Maßgeblich ist das Maximum aus der "
        f"Häufigkeit (Anteil der Zeit, in der der Befund auftritt) und der energetischen Relevanz (Anteil am gemessenen "
        f"Gesamtverbrauch); für sicherheits- oder bilanzrelevante Befunde gilt eine Mindeststufe. Daraus ergeben sich "
        f"{n_hoch} Befund(e) mit hohem, {n_mittel} mit mittlerem und {n_gering} mit geringem Schweregrad."
    )
    top = assess[assess["Schweregrad"] == "hoch"]
    top_txt = "; ".join(f"{r['Befund']} ({r['Kennzahl']})" for _, r in top.iterrows()) or "keine Befunde mit hohem Schweregrad"
    sv_txt = ""
    if savings is not None:
        tot = savings[savings["Maßnahme"] == "Summe"].iloc[0]
        gap = 10 - tot["Anteil %"]
        de = lambda x: f"{x:,.0f}".replace(",", ".")  # noqa: E731
        sv_txt = (f" Das bezifferbare Einsparpotenzial beträgt {de(tot['Einsparung kWh/a'])} kWh pro Jahr "
                  f"({de(tot['Kosten €/a'])} € pro Jahr) und damit {tot['Anteil %']:.1f} % des Gesamtverbrauchs. ")
        sv_txt += ("Das Ziel von 10 % wird erreicht." if gap <= 0 else
                   f"Das Ziel von 10 % wird rechnerisch um {gap:.1f} Prozentpunkte verfehlt; weiteres Potenzial ist "
                   "vorhanden, mit den vorliegenden Messgrößen aber nicht beziffert.")
    zusammenfassung = (f"Die Auswertung der Messdaten zeigt vor allem folgende Schwerpunkte: {top_txt}.{sv_txt} "
                       "Empfohlen wird, die Maßnahmen in der Reihenfolge des Schweregrads mit dem Betreiber abzustimmen "
                       "und die Wirkung anschließend durch erneutes Monitoring zu belegen.")
    return {"bewertung": bewertung, "zusammenfassung": zusammenfassung}


# ----------------------------------------------------------------------------- Theorie-Praxis

def theory_vs_practice(df: pd.DataFrame, th: Thresholds, savings: pd.DataFrame | None) -> pd.DataFrame:
    rows = []

    def add(aussage, quelle, praxis, ergebnis):
        rows.append({"Theoretische Aussage": aussage, "Quelle": quelle, "Praxis (Messdaten)": praxis, "Ergebnis": ergebnis})

    aul, vl = df["RLT KL01 Außenluft"], df["Stat. Heizung Geb.06 VL (Ist)"]
    above = pd.DataFrame({"a": aul, "v": vl}).dropna()
    above = above[above["a"] > th.heizgrenze_aul]
    frac = float((above["v"] > th.aktiv_schwelle_vl).mean() * 100)
    add(f"Oberhalb von etwa {th.heizgrenze_aul:.0f} °C Außentemperatur ist kein Heizbetrieb erforderlich (Heizgrenze)", "Kap. 6.4",
        f"{frac:.0f} % der Zeitschritte oberhalb der Grenze mit Vorlauf > {th.aktiv_schwelle_vl:.0f} °C",
        "nicht bestätigt (Regelung weicht ab)" if frac > 10 else "bestätigt")

    p95 = {lbl: float(df[col].quantile(0.95)) for lbl, col in (
        ("Geb.06", "FBH Geb.06 VL (Ist)"), ("Geb.08 KI-Räume", "FBH Geb.08 KI-Räume VL"),
        ("Geb.08 Intensivpflege", "FBH Geb.08 Intensivpflege VL"))}
    over = [k for k, v in p95.items() if v > th.fbh_limit]
    add(f"Fußbodenheizungen sind Niedertemperatursysteme (Vorlauf höchstens etwa {th.fbh_limit:.0f} °C)", "Kap. 6.4",
        "95. Perzentil: " + "; ".join(f"{k} {v:.1f} °C" for k, v in p95.items()),
        "bestätigt" if not over else f"teilweise bestätigt (Abweichung: {', '.join(over)})")

    viol = {}
    for lbl, v, r in (("Stat. Heizung Geb.06", "Stat. Heizung Geb.06 VL (Ist)", "Stat. Heizung Geb.06 RL"),
                      ("FBH Geb.06", "FBH Geb.06 VL (Ist)", "FBH Geb.06 RL"),
                      ("FBH Geb.08 KI", "FBH Geb.08 KI-Räume VL", "FBH Geb.08 KI-Räume RL"),
                      ("FBH Geb.08 Intensiv", "FBH Geb.08 Intensivpflege VL", "FBH Geb.08 Intensivpflege RL")):
        both = df[[v, r]].dropna()
        viol[lbl] = float((both[r] > both[v]).mean() * 100)
    add("Im Heizbetrieb liegt die Rücklauftemperatur unter der Vorlauftemperatur", "Kap. 6.2 (Tabelle 1)",
        "Rücklauf > Vorlauf: " + "; ".join(f"{k} {v:.1f} %" for k, v in viol.items()),
        "bestätigt" if max(viol.values()) < 1 else "teilweise bestätigt")

    dts = []
    for v, r in (("Stat. Heizung Geb.06 VL (Ist)", "Stat. Heizung Geb.06 RL"), ("FBH Geb.06 VL (Ist)", "FBH Geb.06 RL")):
        active = df[v] > th.aktiv_schwelle_vl
        dts.append(float(((df[v] - df[r])[active] < th.delta_t_min).mean() * 100))
    add(f"Bei effizientem Betrieb liegt die Spreizung deutlich über {th.delta_t_min:g} K", "Kap. 6.4",
        f"Spreizung unter {th.delta_t_min:g} K in {min(dts):.0f} bis {max(dts):.0f} % der aktiven Zeit",
        "bestätigt" if max(dts) < 5 else "nicht durchgängig bestätigt (wiederkehrende Phasen mit geringer Spreizung)")

    ab = daily_consumption(df, "Zähler 021 – Strom Abluft")
    diff = (ab[ab.index.dayofweek >= 5].mean() / ab[ab.index.dayofweek < 5].mean() - 1) * 100
    add("Klinikkomplexe haben keinen ausgeprägten Nacht- oder Wochenend-Absenkbetrieb", "Kap. 6.1",
        f"Ventilatorstrom am Wochenende {diff:+.1f} % gegenüber Werktagen",
        "bestätigt" if abs(diff) < 5 else "nicht bestätigt")

    cov = data_coverage(df)
    heiz = int(((cov["Zeitraum"] == "Heizperiode") & (cov["Erfüllt"] == "ja")).sum())
    somm = int(((cov["Zeitraum"] == "Sommerperiode") & (cov["Erfüllt"] == "ja")).sum())
    add("Ein Monitoring sollte mindestens zwei Heizperioden und eine Sommerperiode umfassen", "Kap. 4 / 6.2",
        f"{heiz} Heizperiode(n) und {somm} Sommerperiode(n) mit mindestens 80 % Tagesabdeckung",
        "bestätigt" if heiz >= 2 and somm >= 1 else "nicht erfüllt")

    if savings is not None:
        tot = savings[savings["Maßnahme"] == "Summe"].iloc[0]["Anteil %"]
        add("Systematische Datenanalyse ermöglicht Energieeinsparungen von bis zu 10 % ohne Komforteinbußen", "Kap. 6.1",
            f"{tot:.1f} % des Gesamtverbrauchs beziffert (Heizgrenze, RLT-Nachtabsenkung)",
            "bestätigt" if tot >= 10 else "teilweise bestätigt (weiteres Potenzial nicht beziffert)")
    return pd.DataFrame(rows)
