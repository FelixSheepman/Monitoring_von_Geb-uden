"""
Grafische Aufbereitung - automatisierter Ersatz fuer Kapitel 6.3 der Hausarbeit.

Jede Funktion liefert eine plotly.graph_objects.Figure fuer genau eine der in
Kapitel 6.3 beschriebenen Abbildungen (Abbildung 2-12). Die Konfigurationslogik
(keine Sekundaerachsen bei gleichen Einheiten, fixierte Farbskalen bei
Carpetplots, Scatter+Trendlinie bei Heizkurven, fixierte y-Achse bei
Binaerwerten) folgt Kapitel 5.2 der Hausarbeit.

Farben: feste, farbfehlsichtigkeitssichere Kategorialpalette (Okabe-Ito),
Zuordnung nach Bedeutung (Ist/Soll/Zone) statt Reihenfolge - siehe
dataviz-Skill: "Color follows the entity, never its rank."
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# Okabe-Ito: farbfehlsichtigkeitssichere Kategorialpalette
BLUE = "#0072B2"
ORANGE = "#E69F00"
GREEN = "#009E73"
VERMILLION = "#D55E00"
PINK = "#CC79A7"
SKY = "#56B4E9"
YELLOW = "#F0E442"
BLACK = "#000000"

COLOR_IST = BLUE
COLOR_SOLL = VERMILLION
ZONE_PALETTE = [BLUE, ORANGE, GREEN, VERMILLION, PINK, SKY]

TEMPLATE = "plotly_white"
FONT = dict(family="Arial, sans-serif", size=13, color="#1a1a1a")


def _base_layout(title: str, yaxis_title: str, xaxis_title: str = "Zeit") -> dict:
    return dict(
        title=dict(text=title, font=dict(size=15, family="Arial, sans-serif")),
        template=TEMPLATE,
        font=FONT,
        xaxis_title=xaxis_title,
        yaxis_title=yaxis_title,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=60, r=30, t=70, b=50),
    )


def fig_meter_cumulative(df: pd.DataFrame, col: str, title: str, unit: str = "kWh") -> go.Figure:
    """Abbildung 2: kumulierter Zaehlerstand ueber die Zeit."""
    fig = go.Figure(go.Scatter(
        x=df.index, y=df[col], mode="lines", name=title,
        line=dict(color=COLOR_IST, width=2),
    ))
    fig.update_layout(**_base_layout(title, f"{unit}"))
    fig.update_layout(showlegend=False)
    return fig


def fig_soll_ist(df: pd.DataFrame, soll_col: str, ist_col: str, title: str, unit: str = "°C") -> go.Figure:
    """Abbildung 3 / 7: Regelguete - Soll- vs. Ist-Vorlauftemperatur.
    Gleiche Einheit -> eine gemeinsame y-Achse (keine Sekundaerachse)."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index, y=df[soll_col], mode="lines", name="Soll-Vorlauf",
        line=dict(color=COLOR_SOLL, width=1.5, dash="dash"),
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df[ist_col], mode="lines", name="Ist-Vorlauf",
        line=dict(color=COLOR_IST, width=2),
    ))
    fig.update_layout(**_base_layout(title, f"Temperatur ({unit})"))
    return fig


def fig_heating_curve(df: pd.DataFrame, aul_col: str, vl_col: str, title: str) -> go.Figure:
    """Abbildung 4: Heizkurve - Streudiagramm mit Regressionslinie (unverbundene
    Punktwolke, Trendlinie ueber lineare Regression)."""
    sub = df[[aul_col, vl_col]].dropna()
    x, y = sub[aul_col].to_numpy(), sub[vl_col].to_numpy()

    fig = go.Figure(go.Scattergl(
        x=x, y=y, mode="markers", name="Messpunkte",
        marker=dict(color=COLOR_IST, size=4, opacity=0.35),
    ))
    if len(x) > 2:
        coeffs = np.polyfit(x, y, 1)
        x_line = np.linspace(x.min(), x.max(), 100)
        y_line = np.polyval(coeffs, x_line)
        fig.add_trace(go.Scatter(
            x=x_line, y=y_line, mode="lines", name="Regressionslinie",
            line=dict(color=COLOR_SOLL, width=2.5),
        ))
    fig.update_layout(**_base_layout(title, "Vorlauftemperatur (°C)", "Außentemperatur (°C)"))
    fig.update_layout(hovermode="closest")
    return fig


def fig_carpet(df: pd.DataFrame, value_col: str, year: int, month: int, title: str,
               zmin: float | None = None, zmax: float | None = None) -> go.Figure:
    """Abbildung 5 / 6: Carpetplot als farbcodierte Heatmap.
    Spalten = Kalendertag, Zeilen = Uhrzeit (15-Min-Raster), siehe Kap. 5.2.
    Farbskala fix auf reale Betriebsgrenzen (kein Auto-Scaling)."""
    sub = df.loc[(df.index.year == year) & (df.index.month == month), [value_col]].copy()
    sub["Tag"] = sub.index.day
    sub["Zeit"] = sub.index.strftime("%H:%M")
    pivot = sub.pivot_table(index="Zeit", columns="Tag", values=value_col, aggfunc="mean")
    pivot = pivot.sort_index()

    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns, y=pivot.index,
        colorscale="RdYlBu_r", zmin=zmin, zmax=zmax,
        colorbar=dict(title="°C"),
        hovertemplate="Tag %{x}<br>%{y} Uhr<br>%{z:.1f} °C<extra></extra>",
    ))
    fig.update_layout(**_base_layout(title, "Uhrzeit", "Tag im Monat"))
    fig.update_layout(hovermode="closest", legend=None)
    return fig


def fig_zone_comparison(df: pd.DataFrame, series: list[tuple[str, str]], title: str,
                         unit: str = "°C") -> go.Figure:
    """Abbildung 8: Zonenvergleich mehrerer Vorlauftemperaturen (>=2 Serien ->
    Legende Pflicht, feste Kategorialfarben nach Zone statt Reihenfolge)."""
    fig = go.Figure()
    for (label, col), color in zip(series, ZONE_PALETTE):
        fig.add_trace(go.Scatter(
            x=df.index, y=df[col], mode="lines", name=label,
            line=dict(color=color, width=1.5),
        ))
    fig.update_layout(**_base_layout(title, f"Temperatur ({unit})"))
    return fig


def fig_delta_t(df: pd.DataFrame, series: list[tuple[str, str, str]], title: str) -> go.Figure:
    """Abbildung 9: Temperaturspreizung (Delta T = VL - RL) je System ueber die Zeit.
    `series`: Liste aus (Label, VL-Spalte, RL-Spalte)."""
    fig = go.Figure()
    for (label, vl_col, rl_col), color in zip(series, ZONE_PALETTE):
        dt = df[vl_col] - df[rl_col]
        fig.add_trace(go.Scatter(
            x=df.index, y=dt, mode="lines", name=label,
            line=dict(color=color, width=1.5),
        ))
    fig.update_layout(**_base_layout(title, "Delta T (K)"))
    fig.add_hline(y=0, line_color="#999", line_width=1, line_dash="dot")
    return fig


def fig_two_series(df: pd.DataFrame, col_a: str, label_a: str, col_b: str, label_b: str,
                    title: str, unit: str = "°C") -> go.Figure:
    """Abbildung 10: z.B. Außenluft- vs. Zulufttemperatur (gleiche Einheit -> eine y-Achse)."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df[col_a], mode="lines", name=label_a,
                              line=dict(color=BLUE, width=1.5)))
    fig.add_trace(go.Scatter(x=df.index, y=df[col_b], mode="lines", name=label_b,
                              line=dict(color=ORANGE, width=1.5)))
    fig.update_layout(**_base_layout(title, f"Temperatur ({unit})"))
    return fig


def fig_daily_lines(daily: dict[str, pd.Series], title: str, unit: str = "kWh") -> go.Figure:
    """Abbildung 11: taegliche Verbrauchswerte (z.B. Strom RLT-Ventilatoren) als Liniendiagramm."""
    fig = go.Figure()
    for (label, s), color in zip(daily.items(), ZONE_PALETTE):
        fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines+markers", name=label,
                                  line=dict(color=color, width=1.8), marker=dict(size=4)))
    fig.update_layout(**_base_layout(title, f"Energie ({unit})", "Datum"))
    return fig


def fig_daily_bar(daily: pd.Series, title: str, unit: str = "kWh") -> go.Figure:
    """Abbildung 12: taeglicher Waermeverbrauch als Saeulendiagramm."""
    fig = go.Figure(go.Bar(x=daily.index, y=daily.values, marker_color=COLOR_IST, name=title))
    fig.update_layout(**_base_layout(title, f"Verbrauch ({unit})", "Datum"))
    fig.update_layout(showlegend=False)
    return fig


def add_anomaly_markers(fig: go.Figure, x, y, name: str, color: str = "#C00000") -> go.Figure:
    """Legt rote Rautenmarker auf die Anomalie-Zeitpunkte (leere Eingabe -> keine Aenderung)."""
    if len(x) == 0:
        return fig
    fig.add_trace(go.Scattergl(
        x=x, y=y, mode="markers", name=name,
        marker=dict(color=color, size=7, symbol="diamond", line=dict(color="white", width=1)),
        hovertemplate=f"{name}<br>%{{x}}<br>%{{y:.1f}}<extra></extra>",
    ))
    return fig
