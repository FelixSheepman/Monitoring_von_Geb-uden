"""
Gliederung der Messstellen nach Gebaeude und Heizkreis.

Die feste Kap.-6-Auswertung (report.py) behandelt den gesamten Datensatz auf einmal.
Diese Datei ergaenzt eine zweite, davon unabhaengige Sicht: Welche der 23 Messspalten
gehoeren zu welchem der 7 eigenstaendigen Heizkreise (jeweils mit eigenem Vor- und
Ruecklauf), und zu welchem der 4 Gebaeude gehoert dieser Heizkreis. Grundlage ist die
Handskizze der Projektgruppe ("Situation des Monitorings").

Der Waermemengenzaehler (Zaehler 019, Zone "wmz_019") misst die gesamte Anlage und
zaehlt nicht zu einem einzelnen Heizkreis (SITE_COLUMNS). Die RLT-Anlage KL01
(Aussenluft-/Zulufttemperatur, Zone "rlt_kl01") und die beiden Stromzaehler der
Ventilatoren haben kein eigenes Vor-/Ruecklaufpaar; sie werden dem Heizkreis
"RLT-Anlage" von Gebaeude 3 als zusaetzliche Sensoren zugeordnet (siehe Skizze:
"Teilen eine Lüftungsanlage" mit Gebäude 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import COLUMNS, Column

# Reihenfolge = Nummerierung 1 bis 7 aus der Handskizze.
_ZONE_BUILDING: dict[str, str] = {
    "heizung_geb1_geb3": "geb3",
    "rlt_primaer": "geb3",
    "heizung_lager_geb2": "geb2",
    "fbh_geb06": "geb6",
    "stat_heizung_geb06": "geb6",
    "fbh_geb08_ki": "geb8",
    "fbh_geb08_intensiv": "geb8",
}

_ZONE_ART: dict[str, str] = {
    "heizung_geb1_geb3": "Heizkörper",
    "rlt_primaer": "RLT-Anlage",
    "heizung_lager_geb2": "Heizkörper",
    "fbh_geb06": "Fußbodenheizung",
    "stat_heizung_geb06": "Heizkörper (statische Heizflächen)",
    "fbh_geb08_ki": "Fußbodenheizung – Bereich I (KI-Räume)",
    "fbh_geb08_intensiv": "Fußbodenheizung – Bereich II (Intensivpflege)",
}

# Kurzbezeichnung fuer Buttons und das Uebersichtsdiagramm (dort ist wenig Platz).
_ZONE_SHORT: dict[str, str] = {
    "heizung_geb1_geb3": "Heizkörper",
    "rlt_primaer": "RLT-Anlage",
    "heizung_lager_geb2": "Heizkörper",
    "fbh_geb06": "Fußbodenheizung",
    "stat_heizung_geb06": "Heizkörper",
    "fbh_geb08_ki": "Fußboden Bereich I",
    "fbh_geb08_intensiv": "Fußboden Bereich II",
}

# Zonen ohne eigenes Vor-/Ruecklaufpaar, die inhaltlich zu einem Heizkreis gehoeren
# (andere Rollen: Aussenluft/Zuluft, Motorstrom) und dort als Zusatzsensoren erscheinen.
_ZONE_EXTRA: dict[str, tuple[str, ...]] = {
    "rlt_primaer": ("rlt_kl01", "strom_abluft", "strom_zuluft"),
}

_BUILDING_ORDER: list[str] = ["geb3", "geb2", "geb6", "geb8"]

# (Name, Farbe) je Gebaeude - Farben angelehnt an die Handskizze (grün/grau/orange/blau).
_BUILDING_META: dict[str, tuple[str, str]] = {
    "geb3": ("Gebäude 3", "#2E8B57"),
    "geb2": ("Gebäude 2 · Lager von Gebäude 3", "#7C93A3"),
    "geb6": ("Gebäude 6", "#D9822B"),
    "geb8": ("Gebäude 8", "#2F5FA8"),
}


@dataclass(frozen=True)
class Heizkreis:
    zone: str
    nr: int
    art: str
    short: str
    building: str
    columns: list[Column] = field(default_factory=list)
    extra_columns: list[Column] = field(default_factory=list)

    def col(self, role: str) -> Column | None:
        return next((c for c in self.columns if c.role == role), None)

    def extra_col(self, role: str) -> Column | None:
        return next((c for c in self.extra_columns if c.role == role), None)


@dataclass(frozen=True)
class Gebaeude:
    key: str
    name: str
    farbe: str
    kreise: list[Heizkreis]


def _build() -> list[Gebaeude]:
    by_zone: dict[str, list[Column]] = {}
    for c in COLUMNS:
        by_zone.setdefault(c.zone, []).append(c)

    kreise_by_building: dict[str, list[Heizkreis]] = {k: [] for k in _BUILDING_ORDER}
    for nr, (zone, building) in enumerate(_ZONE_BUILDING.items(), start=1):
        extra = [c for z in _ZONE_EXTRA.get(zone, ()) for c in by_zone.get(z, [])]
        kreise_by_building[building].append(
            Heizkreis(zone, nr, _ZONE_ART[zone], _ZONE_SHORT[zone], building, by_zone.get(zone, []), extra))

    return [Gebaeude(key, *(_BUILDING_META[key]), kreise_by_building[key]) for key in _BUILDING_ORDER]


GEBAEUDE: list[Gebaeude] = _build()
HEIZKREISE: dict[str, Heizkreis] = {k.zone: k for g in GEBAEUDE for k in g.kreise}
N_HEIZKREISE = len(HEIZKREISE)

# Spalten, die keinem Gebaeude/Heizkreis zugeordnet sind (misst die Gesamtanlage).
SITE_COLUMNS: list[Column] = [c for c in COLUMNS if c.zone not in _ZONE_BUILDING and c.zone not in
                              {z for extras in _ZONE_EXTRA.values() for z in extras}]


def find_gebaeude(zone: str) -> Gebaeude:
    return next(g for g in GEBAEUDE if any(k.zone == zone for k in g.kreise))
