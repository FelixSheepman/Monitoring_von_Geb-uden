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


def fig_heating_curve(df: pd.DataFrame, aul_col: str, vl_col: str, title: str,
                       x_label: str = "Außentemperatur (°C)", y_label: str = "Vorlauftemperatur (°C)") -> go.Figure:
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
    fig.update_layout(**_base_layout(title, y_label, x_label))
    fig.update_layout(hovermode="closest")
    return fig


def fig_carpet(df: pd.DataFrame, value_col: str, year: int, month: int, title: str,
               zmin: float | None = None, zmax: float | None = None, unit: str = "°C") -> go.Figure:
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
        colorbar=dict(title=unit),
        hovertemplate="Tag %{x}<br>%{y} Uhr<br>%{z:.1f} " + unit + "<extra></extra>",
    ))
    fig.update_layout(**_base_layout(title, "Uhrzeit", "Tag im Monat"))
    fig.update_layout(hovermode="closest", legend=None)
    return fig


CARPET_GRANULARITIES = ("Jahr", "Monat", "Woche", "Tag")
# Nachtfenster fuer die Tag/Nacht-Markierung in Carpetplots - ueblicher Zeitraum einer Nachtabsenkung;
# Annahme, in der Anlagendokumentation ggf. anzupassen.
NIGHT_START, NIGHT_END = "22:00", "06:00"
# Betriebszustaende als Anteile der Farbskala [zmin, zmax] - nur Beispielhaft/Orientierung, keine
# Herstellerangabe. Reihenfolge = aufsteigend; jede Stufe deckt [vorherige Grenze, eigene Grenze).
OPERATING_BANDS = (
    (0.15, "Aus"),
    (0.40, "Nachtabsenkung"),
    (0.85, "Normalbetrieb"),
    (1.00, "Volllast"),
)
MONTH_NAMES = ["Januar", "Februar", "März", "April", "Mai", "Juni",
              "Juli", "August", "September", "Oktober", "November", "Dezember"]
_WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
# Schriftgroesse der Zell-Beschriftung je Granularitaet: wenige, breite Spalten (Woche) vertragen groessere
# Schrift als viele, schmale (Monat); bei Tag ist die Zelle nach der Drehung schmal, aber sehr hoch.
_ANNOTATION_FONT_SIZE = {"Woche": 11, "Monat": 9, "Tag": 9}


def carpet_window(anchor: pd.Timestamp, granularity: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """[Start, Ende) des Zeitfensters fuer die gewaehlte Granularitaet; `anchor` legt fest, welches
    Jahr/Monat/Woche/welcher Tag gezeigt wird (bei Woche/Tag ist nur das Datum von anchor relevant)."""
    if granularity == "Jahr":
        start = pd.Timestamp(year=anchor.year, month=1, day=1)
        return start, pd.Timestamp(year=anchor.year + 1, month=1, day=1)
    if granularity == "Monat":
        start = pd.Timestamp(year=anchor.year, month=anchor.month, day=1)
        return start, start + pd.offsets.MonthBegin(1)
    if granularity == "Woche":
        start = anchor.normalize() - pd.Timedelta(days=anchor.weekday())
        return start, start + pd.Timedelta(days=7)
    start = anchor.normalize()
    return start, start + pd.Timedelta(days=1)


def carpet_period_label(granularity: str, anchor: pd.Timestamp) -> str:
    """Kurzbezeichnung des Zeitfensters fuer Titel/Beschriftung, z.B. '02/2025', 'KW 6 (03.02.2025)'."""
    if granularity == "Jahr":
        return f"{anchor.year}"
    if granularity == "Monat":
        return f"{anchor.month:02d}/{anchor.year}"
    if granularity == "Woche":
        start, _ = carpet_window(anchor, "Woche")
        return f"KW {start.isocalendar().week} ({start:%d.%m.%Y})"
    return f"{anchor:%d.%m.%Y}"


NIGHT_BOUNDARY_COLOR = "#FFD23F"  # kraeftiges Gelb - gegenueber jeder Heatmap-Farbe (auch Blau) klar erkennbar


def _night_shapes(granularity: str) -> list[dict]:
    """Markierung der Nachtzeit (siehe NIGHT_START/NIGHT_END): eine dunkle Abdunkelung der Flaeche (wirkt
    unabhaengig von der darunterliegenden Heatmap-Farbe, auch auf blauen/kalten Zellen) plus zwei kraeftige
    gestrichelte Grenzlinien an Nachtbeginn/-ende, statt einer kaum sichtbaren Farbtoenung. Bei normaler
    Ausrichtung (Uhrzeit auf der y-Achse) waagerecht (ueber Mitternacht hinweg), bei "Tag" (Uhrzeit auf der
    x-Achse) senkrecht."""
    fill = dict(fillcolor="rgba(0,0,0,0.30)", line_width=0, layer="above")
    boundary = dict(line=dict(color=NIGHT_BOUNDARY_COLOR, width=2.6, dash="dash"), layer="above")
    if granularity == "Tag":
        return [
            dict(type="rect", xref="x", yref="y domain", x0="00:00", x1=NIGHT_END, y0=0, y1=1, **fill),
            dict(type="rect", xref="x", yref="y domain", x0=NIGHT_START, x1="23:45", y0=0, y1=1, **fill),
            dict(type="line", xref="x", yref="y domain", x0=NIGHT_END, x1=NIGHT_END, y0=0, y1=1, **boundary),
            dict(type="line", xref="x", yref="y domain", x0=NIGHT_START, x1=NIGHT_START, y0=0, y1=1, **boundary),
        ]
    return [
        dict(type="rect", xref="x domain", yref="y", x0=0, x1=1, y0="00:00", y1=NIGHT_END, **fill),
        dict(type="rect", xref="x domain", yref="y", x0=0, x1=1, y0=NIGHT_START, y1="23:45", **fill),
        dict(type="line", xref="x domain", yref="y", x0=0, x1=1, y0=NIGHT_END, y1=NIGHT_END, **boundary),
        dict(type="line", xref="x domain", yref="y", x0=0, x1=1, y0=NIGHT_START, y1=NIGHT_START, **boundary),
    ]


def _operating_band_colors_and_bounds(zmin: float, zmax: float, unit: str) -> list[tuple[str, str, str]]:
    """Je Betriebszustand: (Farbe passend zur Heatmap-Skala, Name, Wertebereich als Text)."""
    import plotly.colors as pc
    lo_frac = 0.0
    out = []
    for hi_frac, label in OPERATING_BANDS:
        mid = (lo_frac + hi_frac) / 2
        color = pc.sample_colorscale("RdYlBu_r", [mid])[0]
        lo_val, hi_val = zmin + lo_frac * (zmax - zmin), zmin + hi_frac * (zmax - zmin)
        bounds = f"< {hi_val:.0f} {unit}" if lo_frac == 0 else (
            f"> {lo_val:.0f} {unit}" if hi_frac == 1 else f"{lo_val:.0f}–{hi_val:.0f} {unit}")
        out.append((color, label, bounds))
        lo_frac = hi_frac
    return out


def _add_operating_bands_legend(fig: go.Figure, zmin: float, zmax: float, unit: str, y0: float, y1: float) -> None:
    """Zeichnet die Betriebszustaende als Reihe ECHTER farbiger Kaestchen (eigene Shapes, nicht nur
    eingefaerbte Schriftzeichen) mit fetter Beschriftung daneben - das faellt auf den ersten Blick auf,
    auch neben einer bunten Heatmap. `y0`/`y1` (paper-Koordinaten) geben die Hoehe der Kaestchen vor."""
    bands = _operating_band_colors_and_bounds(zmin, zmax, unit)
    seg = 1.0 / len(bands)
    for i, (color, label, bounds) in enumerate(bands):
        x0 = i * seg + seg * 0.08
        x1 = x0 + 0.028
        fig.add_shape(type="rect", xref="paper", yref="paper", x0=x0, x1=x1, y0=y0, y1=y1,
                     fillcolor=color, line=dict(color="#2a2a2a", width=1.2), visible=True)
        fig.add_annotation(
            text=f"<b>{label}</b><br>{bounds}", xref="paper", yref="paper",
            x=x1 + 0.014, y=(y0 + y1) / 2, xanchor="left", yanchor="middle",
            showarrow=False, font=dict(size=12, color="#1a1a1a"), align="left", visible=True,
            bgcolor="rgba(255,255,255,0.9)", bordercolor="#2a2a2a", borderwidth=1, borderpad=3,
        )


def _add_carpet_overlays(fig: go.Figure, granularity: str, zmin: float | None, zmax: float | None, unit: str) -> None:
    """Fuegt die Tag/Nacht-Markierung und die Betriebszustaende-Legende hinzu, je mit eigenem Button
    ein-/ausblendbar (direkt im Diagramm, keine Streamlit-Interaktion noetig). Beide Legenden stehen in
    einer eigens reservierten Zeile INNERHALB des Diagramms (Achsen-Domain verkleinert), nicht per
    negativer paper-Koordinate unterhalb des Canvas - dort waeren sie je nach Diagrammgroesse
    abgeschnitten oder nur als duenner, leicht zu uebersehender Textstreifen sichtbar."""
    night_shapes = _night_shapes(granularity)
    for shape in night_shapes:
        fig.add_shape(**shape, visible=True)

    has_legend = zmin is not None and zmax is not None
    reserved = 0.24 if has_legend else 0.11  # Anteil der Plotflaeche fuer die Legenden-Zeile(n)
    fig.update_yaxes(domain=[reserved, 1])
    fig.update_layout(margin=dict(t=90, b=26))

    fig.add_annotation(
        text=f"🌓 Grau + gelb gestrichelt = Nachtzeit ({NIGHT_START}–{NIGHT_END} Uhr, Annahme)",
        xref="paper", yref="paper", x=0, y=reserved - 0.025, xanchor="left", yanchor="top",
        showarrow=False, font=dict(size=12, color="#1a1a1a"), visible=True,
        bgcolor="rgba(255,255,255,0.9)", bordercolor="#2a2a2a", borderwidth=1, borderpad=3,
    )
    if has_legend:
        _add_operating_bands_legend(fig, zmin, zmax, unit, y0=0.01, y1=reserved - 0.09)

    n_night = len(night_shapes)  # 2 Flaechen + 2 Grenzlinien
    night_on = {f"shapes[{i}].visible": True for i in range(n_night)} | {"annotations[0].visible": True}
    night_off = {f"shapes[{i}].visible": False for i in range(n_night)} | {"annotations[0].visible": False}
    buttons = [dict(
        type="buttons", direction="left", showactive=False, x=0, y=1.16, xanchor="left", yanchor="top",
        pad=dict(r=4, t=2),
        buttons=[
            dict(label="🌓 Tag/Nacht ein", method="relayout", args=[night_on]),
            dict(label="Tag/Nacht aus", method="relayout", args=[night_off]),
        ])]
    if has_legend:
        n_bands = len(OPERATING_BANDS)
        legend_shape_idx = range(n_night, n_night + n_bands)
        legend_ann_idx = range(1, 1 + n_bands)
        legend_on = ({f"shapes[{i}].visible": True for i in legend_shape_idx}
                    | {f"annotations[{i}].visible": True for i in legend_ann_idx})
        legend_off = ({f"shapes[{i}].visible": False for i in legend_shape_idx}
                     | {f"annotations[{i}].visible": False for i in legend_ann_idx})
        buttons.append(dict(
            type="buttons", direction="left", showactive=False, x=0.45, y=1.16, xanchor="left", yanchor="top",
            pad=dict(r=4, t=2),
            buttons=[
                dict(label="🎨 Betriebszustände ein", method="relayout", args=[legend_on]),
                dict(label="Betriebszustände aus", method="relayout", args=[legend_off]),
            ]))
    fig.update_layout(updatemenus=buttons)


def fig_carpet_window(df: pd.DataFrame, value_col: str, granularity: str, anchor: pd.Timestamp, title: str,
                       zmin: float | None = None, zmax: float | None = None, unit: str = "°C",
                       annotate_col: str | None = None, annotate_label: str = "Außentemp.",
                       annotate_unit: str = "°C") -> go.Figure:
    """Carpetplot ueber ein waehlbares Zeitfenster (Jahr/Monat/Woche/Tag) statt eines fest hinterlegten
    Monats; jede Zelle bleibt ein einzelner 15-Min-Messwert (kein Glaetten). Bei Woche/Monat/Tag laesst
    sich eine zweite Messgroesse (z.B. Aussentemperatur) als Zahl in die Zelle schreiben, um den
    Zusammenhang mit `value_col` sichtbar zu machen (bei Jahr waere das wegen der Zellenzahl unleserlich,
    daher dort automatisch ohne Beschriftung). Farbskala fix auf reale Betriebsgrenzen (kein Auto-Scaling)."""
    anchor = pd.Timestamp(anchor)
    start, end = carpet_window(anchor, granularity)
    use_annotate = annotate_col is not None and annotate_col != value_col and granularity != "Jahr"
    cols = [value_col] + ([annotate_col] if use_annotate else [])
    sub = df.loc[start:end - pd.Timedelta(minutes=1), cols].dropna(how="all").copy()

    if sub.empty:
        fig = go.Figure(go.Heatmap(z=[[None]], zmin=zmin, zmax=zmax, colorbar=dict(title=unit)))
        fig.update_layout(**_base_layout(f"{title} – keine Messwerte in diesem Zeitraum", "", ""))
        return fig

    day = sub.index.normalize()
    sub["Zeit"] = sub.index.strftime("%H:%M")
    if granularity == "Tag":
        sub["Spalte"] = "Verlauf"
        col_order = ["Verlauf"]
        x_title, y_title = "", "Uhrzeit"
    elif granularity == "Woche":
        sub["Spalte"] = [_WEEKDAYS[d] for d in sub.index.weekday]
        col_order = _WEEKDAYS
        x_title, y_title = "Wochentag", "Uhrzeit"
    elif granularity == "Monat":
        sub["Spalte"] = sub.index.day
        col_order = sorted(sub["Spalte"].unique())
        x_title, y_title = "Tag im Monat", "Uhrzeit"
    else:  # Jahr
        order_df = pd.DataFrame({"_tag": day, "Spalte": day.strftime("%d.%m.")}).drop_duplicates().sort_values("_tag")
        sub["Spalte"] = day.strftime("%d.%m.")
        col_order = order_df["Spalte"].tolist()
        x_title, y_title = "Tag im Jahr", "Uhrzeit"

    pivot = sub.pivot_table(index="Zeit", columns="Spalte", values=value_col, aggfunc="mean") \
        .sort_index().reindex(columns=col_order)

    heat = dict(z=pivot.values, x=pivot.columns.astype(str), y=pivot.index,
                colorscale="RdYlBu_r", zmin=zmin, zmax=zmax, colorbar=dict(title=unit))
    hover = "%{x}<br>%{y} Uhr<br>%{z:.1f} " + unit
    if use_annotate:
        apivot = sub.pivot_table(index="Zeit", columns="Spalte", values=annotate_col, aggfunc="mean") \
            .sort_index().reindex(columns=col_order)
        # Eine Nachkommastelle wie im Tooltip - der tatsaechliche Messwert, nicht auf ganze Grad gerundet.
        heat["text"] = apivot.values
        heat["texttemplate"] = "%{text:.1f}"
        heat["textfont"] = dict(size=_ANNOTATION_FONT_SIZE.get(granularity, 9), color="#111111")
        hover += f"<br>{annotate_label}: " + "%{text:.1f} " + annotate_unit
    heat["hovertemplate"] = hover + "<extra></extra>"

    if granularity == "Tag":  # als waagerechter Streifen (Uhrzeit von links nach rechts) statt 1-Spalten-Saeule
        heat["x"], heat["y"] = heat["y"], heat["x"]
        heat["z"] = np.transpose(heat["z"])
        if "text" in heat:
            heat["text"] = np.transpose(heat["text"])
        x_title, y_title = "Uhrzeit", ""

    fig = go.Figure(go.Heatmap(**heat))
    fig.update_layout(**_base_layout(title, y_title, x_title))
    fig.update_layout(hovermode="closest", legend=None)
    if granularity == "Tag":
        fig.update_yaxes(showticklabels=False)
        fig.update_layout(height=340)  # Platz fuer die Tag/Nacht- und Betriebszustaende-Legende unter dem Streifen
    elif use_annotate:
        # Genug Hoehe fuer die 96 Uhrzeit-Zeilen, sonst ist die Zahl in der Zelle nicht mehr lesbar.
        fig.update_layout(height=980)
    else:
        fig.update_layout(height=560)  # Jahr: keine Zellbeschriftung, aber Platz fuer die Legenden unter dem Plot
    _add_carpet_overlays(fig, granularity, zmin, zmax, unit)
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


def fig_duration_curve(curve: pd.DataFrame, markers: dict[float, tuple[float, float]], title: str) -> go.Figure:
    """Geordnete Dauerlinie der thermischen Leistung: absteigend sortierte Leistung ueber die
    Betriebsstunden, in denen sie erreicht oder ueberschritten wird. `markers` (siehe
    metrics.duration_curve_percentiles) blendet Referenzlinien bei ausgewaehlten Zeitanteilen ein, z.B.
    "5 % der Betriebsstunden: 20 kW" - mögliche Auslegungspunkte fuer ein Spitzenlast-/Zusatzheizgeraet."""
    fig = go.Figure(go.Scatter(
        x=curve["Stunden"], y=curve["Leistung_kW"], mode="lines", name="Leistung",
        line=dict(color=COLOR_IST, width=2), fill="tozeroy", fillcolor="rgba(0,114,178,0.12)",
    ))
    for frac, (hours, power) in sorted(markers.items()):
        fig.add_shape(type="line", x0=hours, x1=hours, y0=0, y1=power, line=dict(color=VERMILLION, width=1, dash="dot"))
        fig.add_shape(type="line", x0=0, x1=hours, y0=power, y1=power, line=dict(color=VERMILLION, width=1, dash="dot"))
        fig.add_annotation(x=hours, y=power, text=f"{frac*100:.0f} % · {power:.0f} kW", showarrow=True,
                            arrowhead=0, ax=28, ay=-18, font=dict(size=10, color=VERMILLION))
    fig.update_layout(**_base_layout(title, "Thermische Leistung (kW)", "Betriebsstunden (absteigend sortiert)"))
    fig.update_layout(showlegend=False)
    return fig


LIMIT_LINE_COLOR = "#9B1B30"  # dunkles Rot: deutlich von Soll/Ist/Zone-Farben unterscheidbar, "Warnung"


def add_component_limit(fig: go.Figure, limit: float, label: str, unit: str = "°C",
                        color: str = LIMIT_LINE_COLOR) -> go.Figure:
    """Zeichnet eine klar sichtbare, dick gestrichelte Grenzlinie bei `limit` (z.B. die zulaessige
    Vorlauftemperatur einer Heizungskomponente) auf ein bestehendes Zeitreihen- oder Streudiagramm, mit
    Beschriftung. So ist sofort erkennbar, wenn ein Messwert diese Grenze ueberschreitet."""
    fig.add_hline(
        y=limit, line_color=color, line_width=2.8, line_dash="dash",
        annotation_text=f"{label}: {limit:.0f} {unit}", annotation_position="top left",
        annotation_font=dict(size=10.5, color=color, family="Arial Black, Arial, sans-serif"),
        annotation_bgcolor="rgba(255,255,255,0.78)",
    )
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


def fig_pump_runtime(monthly: pd.DataFrame, title: str) -> go.Figure:
    """Abbildung 13: Monatliche Laufzeit der Heizkreispumpen in Stunden."""
    fig = go.Figure()
    for label, color in zip(monthly.columns, ZONE_PALETTE):
        fig.add_trace(go.Bar(x=monthly.index, y=monthly[label], name=label, marker_color=color))
    fig.update_layout(**_base_layout(title, "Laufzeit (h/Monat)", "Monat"))
    fig.update_layout(barmode="group")
    return fig


def fig_availability(avail: pd.DataFrame, title: str) -> go.Figure:
    """Abbildung 14: Datenverfuegbarkeit je Spalte und Tag (Anzahl fehlerhafter Zeitschritte)."""
    fig = go.Figure(go.Heatmap(
        z=avail.T.values, x=avail.index, y=avail.columns, colorscale="Reds", zmin=0,
        zmax=max(3, float(avail.values.max())),
        colorbar=dict(title="Fehler/Tag"),
        hovertemplate="%{y}<br>%{x|%d.%m.%Y}<br>%{z:.0f} fehlerhafte Zeitschritte<extra></extra>",
    ))
    fig.update_layout(**_base_layout(title, "", "Datum"))
    fig.update_layout(hovermode="closest", legend=None, height=560, margin=dict(l=230, r=30, t=70, b=50))
    return fig
