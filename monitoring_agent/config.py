"""
Datenmodell des Monitoring-Datensatzes ("Messdaten 2024-2026.xlsx").

Diese Datei ist die einzige Stelle, an der bekannt sein muss, welche
Excel-Spalte zu welchem physikalischen Messpunkt gehoert. Auswertung,
Diagramme und Datenpruefung lesen diese Konfiguration und bleiben so
unabhaengig von den konkreten Spaltennamen im Rohdatensatz.

Rollen (role):
    meter_energy    kumulierter Waermemengenzaehler (kWh, monoton steigend)
    meter_electric  kumulierter Stromzaehler (kWh, monoton steigend)
    vl              Vorlauftemperatur (Ist)
    rl              Ruecklauftemperatur (Ist)
    soll_vl         Vorlauf-Sollwert
    pump            Pumpenstatus (0/1)
    aul             Aussenlufttemperatur
    zul             Zulufttemperatur
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Column:
    excel_name: str
    short: str
    unit: str
    zone: str
    role: str


COLUMNS: list[Column] = [
    Column("Zähler 019 - WMZ\\ (M-Bus DSN 2) (M-Bus DSN 2) - Energie (Momentanwert)",
           "Zähler 019 – WMZ", "kWh", "wmz_019", "meter_energy"),
    Column("RLT primär\\VL Temp.", "RLT primär VL", "°C", "rlt_primaer", "vl"),
    Column("RLT primär\\RL Temp.", "RLT primär RL", "°C", "rlt_primaer", "rl"),
    Column("statische Heizung -Lager (Geb.2)\\VL Temp.", "Heizung Lager Geb.2 VL", "°C", "heizung_lager_geb2", "vl"),
    Column("statische Heizung -Lager(Geb.2)\\RL Temp.", "Heizung Lager Geb.2 RL", "°C", "heizung_lager_geb2", "rl"),
    Column("statische Heizung -Gebäude 1 (Geb.3)\\VL Temp.", "Heizung Geb.1/3 VL", "°C", "heizung_geb1_geb3", "vl"),
    Column("statische Heizung -Gebäude 1 (Geb.3)\\RL Temp.", "Heizung Geb.1/3 RL", "°C", "heizung_geb1_geb3", "rl"),
    Column("Anlage KL01 - RLT02/03.01\\AUL Temp.", "RLT KL01 Außenluft", "°C", "rlt_kl01", "aul"),
    Column("Anlage KL01 - RLT02/03.01\\ZUL Temp.", "RLT KL01 Zuluft", "°C", "rlt_kl01", "zul"),
    Column("Zähler 021 - Strom RLT02/03 Abluftventilator\\Energie (M-Bus DSN 1)",
           "Zähler 021 – Strom Abluft", "kWh", "strom_abluft", "meter_electric"),
    Column("Zähler 022 - Strom RLT02/03 Zuluftventilator\\Energie (M-Bus DSN 1)",
           "Zähler 022 – Strom Zuluft", "kWh", "strom_zuluft", "meter_electric"),
    Column("statische Heizflächen Geb.06\\VL Temp.", "Stat. Heizung Geb.06 VL (Ist)", "°C", "stat_heizung_geb06", "vl"),
    Column("statische Heizflächen Geb.06\\RL Temp.", "Stat. Heizung Geb.06 RL", "°C", "stat_heizung_geb06", "rl"),
    Column("Fußbodenheizung Geb.06\\VL Temp.", "FBH Geb.06 VL (Ist)", "°C", "fbh_geb06", "vl"),
    Column("Fußbodenheizung Geb.06\\RL Temp.", "FBH Geb.06 RL", "°C", "fbh_geb06", "rl"),
    Column("statische Heizflächen Geb.06\\HK Pumpe Betrieb", "Stat. Heizung Geb.06 Pumpe", "-", "stat_heizung_geb06", "pump"),
    Column("Fußbodenheizung Geb.06\\HK Pumpe Betrieb", "FBH Geb.06 Pumpe", "-", "fbh_geb06", "pump"),
    Column("VL-Sollwert Fußbodenheizung", "FBH Geb.06 VL (Soll)", "°C", "fbh_geb06", "soll_vl"),
    Column("VL-Sollwert Stat Heizfläche", "Stat. Heizung Geb.06 VL (Soll)", "°C", "stat_heizung_geb06", "soll_vl"),
    Column("FBH Geb.08 KI-Räume\\VL Temp.", "FBH Geb.08 KI-Räume VL", "°C", "fbh_geb08_ki", "vl"),
    Column("FBH Geb.08 KI-Räume\\RL Temp.", "FBH Geb.08 KI-Räume RL", "°C", "fbh_geb08_ki", "rl"),
    Column("FBH Geb.08 Intensivpflege\\VL Temp.", "FBH Geb.08 Intensivpflege VL", "°C", "fbh_geb08_intensiv", "vl"),
    Column("FBH Geb.08 Intensivpflege\\RL Temp.", "FBH Geb.08 Intensivpflege RL", "°C", "fbh_geb08_intensiv", "rl"),
]

DATE_COLUMN = "Datum"

# Plausible physikalische Wertebereiche fuer die generische Datenpruefung.
PLAUSIBLE_RANGE = {
    "vl": (-5, 80),
    "rl": (-5, 80),
    "soll_vl": (0, 80),
    "aul": (-25, 45),
    "zul": (-5, 45),
    "pump": (0, 1),
}

# Farbskala-Grenzen fuer Carpetplots (an reale Betriebsgrenzen der Anlage angelehnt,
# siehe Kap. 5.2 der Hausarbeit: fixe Min/Max statt Auto-Skalierung).
CARPET_COLOR_RANGE = {
    "rlt_primaer": {"vl": (20, 65), "rl": (20, 65)},
}

BUILDING_HOSPITAL_ZONES = {
    "fbh_geb08_ki", "fbh_geb08_intensiv",
}


def by_zone_role(columns: list[Column] = COLUMNS) -> dict:
    """Gruppiert Spalten nach (zone, role) -> Column, fuer schnellen Zugriff."""
    out = {}
    for c in columns:
        out[(c.zone, c.role)] = c
    return out
