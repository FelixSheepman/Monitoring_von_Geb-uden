"""Zeichnet die Gebäude-/Heizkreis-Übersicht und den Netzplan der Heizungsanlage als eigenständiges SVG
(siehe buildings.py für die zugrunde liegenden Daten)."""

from __future__ import annotations

import html

from .buildings import GEBAEUDE

BOX_W, BOX_H, GAP, PAD = 148, 64, 12, 16
HEADER_H = 36
TOP = 54
BG = "#f4f6f8"
INK = "#1c2733"
MUTED = "#5b6b7b"


def _wrap(text: str, max_chars: int = 15) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if len(trial) > max_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines[:2] if len(lines) <= 2 else [lines[0], lines[1][:max_chars - 1] + "…"]


def svg_overview(selected_zone: str | None = None) -> str:
    """SVG-Übersicht aller Gebäude und ihrer Heizkreise; der ausgewählte Kreis wird hervorgehoben."""
    widths = [len(g.kreise) * BOX_W + (len(g.kreise) - 1) * GAP + 2 * PAD for g in GEBAEUDE]
    # Kopfzeile (Gebäudename) kann breiter sein als die Kreis-Boxen darunter -> pro Gebäude umbrechen und die
    # größte benötigte Zeilenzahl fürs ganze Diagramm übernehmen, damit alle Boxen auf gleicher Höhe beginnen.
    name_lines = [_wrap(g.name, max(10, round(w / 7.4))) for g, w in zip(GEBAEUDE, widths)]
    header_h = HEADER_H + max(len(lines) for lines in name_lines) * 15

    building_gap = 28
    total_w = sum(widths) + building_gap * (len(GEBAEUDE) - 1) + 40
    total_h = TOP + header_h + BOX_H + PAD + 30

    parts = [f'<svg viewBox="0 0 {total_w} {total_h}" xmlns="http://www.w3.org/2000/svg" '
             f'role="img" aria-label="Übersicht der Gebäude und ihrer Heizkreise" style="width:100%;height:auto;font-family:Arial,sans-serif">',
             f'<rect x="0" y="0" width="{total_w}" height="{total_h}" fill="{BG}" rx="10"/>']

    x = 20
    for g, w, lines in zip(GEBAEUDE, widths, name_lines):
        parts.append(f'<rect x="{x}" y="{TOP}" width="{w}" height="{header_h + BOX_H + PAD}" rx="10" '
                     f'fill="none" stroke="{g.farbe}" stroke-width="2.5"/>')
        ty = TOP + 21 - (len(lines) - 1) * 7
        for line in lines:
            parts.append(f'<text x="{x + w / 2}" y="{ty}" text-anchor="middle" font-size="13.5" '
                         f'font-weight="700" fill="{g.farbe}">{html.escape(line)}</text>')
            ty += 16
        bx = x + PAD
        by = TOP + header_h
        for k in g.kreise:
            active = k.zone == selected_zone
            fill = g.farbe if active else "#ffffff"
            text_color = "#ffffff" if active else INK
            stroke = g.farbe
            parts.append(f'<rect x="{bx}" y="{by}" width="{BOX_W}" height="{BOX_H}" rx="7" '
                         f'fill="{fill}" stroke="{stroke}" stroke-width="{2.5 if active else 1.3}"/>')
            parts.append(f'<text x="{bx + 10}" y="{by + 17}" font-size="11" font-weight="700" fill="{text_color}">'
                         f'{k.nr}</text>')
            lines = _wrap(k.short)
            ly = by + BOX_H / 2 - (len(lines) - 1) * 7
            for line in lines:
                parts.append(f'<text x="{bx + BOX_W / 2 + 6}" y="{ly + 4}" text-anchor="middle" font-size="11.5" '
                             f'fill="{text_color}">{html.escape(line)}</text>')
                ly += 15
            bx += BOX_W + GAP
        x += w + building_gap

    parts.append(f'<text x="{total_w / 2}" y="{total_h - 8}" text-anchor="middle" font-size="11.5" fill="{MUTED}">'
                 f'7 eigenständige Heizkreise in 4 Gebäuden · Kreis anklicken für die eigene Auswertung</text>')
    parts.append("</svg>")
    return "".join(parts)


# ============================================================================= Netzplan (Heizungskonzept)

VL_COLOR = "#C0392B"   # warm/rot - Vorlauf
RL_COLOR = "#2E6DA4"   # kalt/blau - Ruecklauf
SOLL_COLOR = "#B8860B"  # Sollwert-Sensor (gestrichelt, gelb-braun)
CARD_W, CARD_H = 258, 196
RLT_EXTRA_H = 92
CARD_GAP_X, CARD_GAP_Y = 22, 46
BUS_GAP = 30          # Abstand zwischen Gebaeude-Sammelschiene und oberer Kante der Karten


def _text(x, y, s, size=11, weight="400", color=INK, anchor="start", italic=False, family=None) -> str:
    style = f'font-style="italic" ' if italic else ""
    fam = f' font-family="{family}"' if family else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{color}" '
           f'text-anchor="{anchor}" {style}{fam}>{html.escape(s)}</text>')


def _pump_icon(cx, cy, color=INK) -> str:
    """Genormtes Pumpensymbol: Kreis mit Dreieck (zeigt die Förderrichtung)."""
    r = 9
    tri = f'{cx-4:.1f},{cy-5.5:.1f} {cx-4:.1f},{cy+5.5:.1f} {cx+5.5:.1f},{cy:.1f}'
    return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="#ffffff" stroke="{color}" stroke-width="1.6"/>'
           f'<polygon points="{tri}" fill="{color}"/>')


def _meter_icon(cx, cy, label, color=INK) -> str:
    """Zaehler-Symbol: Kreis mit Zeiger, Kurzlabel darunter."""
    import math
    r = 10
    ang = math.radians(235)
    x2, y2 = cx + r * 0.6 * math.cos(ang), cy + r * 0.6 * math.sin(ang)
    return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="#ffffff" stroke="{color}" stroke-width="1.6"/>'
           f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="1.6"/>'
           + _text(cx, cy + r + 13, label, size=8.5, weight="700", color=color, anchor="middle"))


def _device_icon(kind, x, y, color) -> str:
    """Endgeraet-Symbol am Ende eines Heizkreises: Heizkoerper (Balken), Fussbodenheizung (Maeander) oder
    Lueftungsanlage (Kanalbox mit Pfeilen)."""
    if kind == "fbh":
        p = f"M{x-26:.1f},{y-10:.1f} h18 v16 h-18 v-16 M{x-8:.1f},{y-2:.1f} h18"
        return (f'<path d="M{x-26:.1f} {y-16:.1f} h44 v10 q0 4 -4 4 h-8 q-4 0 -4 4 v6 q0 4 4 4 h8 q4 0 4 4 v10 '
               f'h-44 v-10 q0 -4 4 -4 h8 q4 0 4 -4 v-6 q0 -4 -4 -4 h-8 q-4 0 -4 -4 z" '
               f'fill="#FCEFC7" stroke="{color}" stroke-width="1.4"/>')
    if kind == "rlt":
        return (f'<rect x="{x-24:.1f}" y="{y-16:.1f}" width="48" height="32" rx="4" fill="#EAF2FB" '
               f'stroke="{color}" stroke-width="1.4"/>'
               f'<path d="M{x-16:.1f} {y-5:.1f} h14 l-4,-4 M{x-2:.1f} {y-5:.1f} l-4,4" fill="none" '
               f'stroke="{RL_COLOR}" stroke-width="1.6"/>'
               f'<path d="M{x+16:.1f} {y+6:.1f} h-14 l4,-4 M{x+2:.1f} {y+6:.1f} l4,4" fill="none" '
               f'stroke="{VL_COLOR}" stroke-width="1.6"/>')
    # Heizkoerper (Standard)
    bars = "".join(f'<line x1="{x-18+i*6.5:.1f}" y1="{y-14:.1f}" x2="{x-18+i*6.5:.1f}" y2="{y+14:.1f}" '
                   f'stroke="{color}" stroke-width="2.4"/>' for i in range(7))
    return (f'<rect x="{x-22:.1f}" y="{y-16:.1f}" width="44" height="32" rx="3" fill="#FBE4E1" '
           f'stroke="{color}" stroke-width="1.2"/>' + bars)


def _circuit_card(kreis, building_color, selected: bool) -> tuple[str, int]:
    """Eine Karte (Mini-Schema) fuer genau einen Heizkreis. Gibt (SVG-Fragment, benoetigte Hoehe) zurueck,
    lokale Koordinaten beginnen bei (0, 0) oben links in der Karte."""
    is_rlt = kreis.extra_col("aul") is not None
    h = CARD_H + (RLT_EXTRA_H if is_rlt else 0)
    kind = "fbh" if "Fußbodenheizung" in kreis.art else ("rlt" if is_rlt else "heizkoerper")

    soll = kreis.col("soll_vl")
    node_x, node_y = 22, 72
    y_vl, y_rl = (84, 122) if soll is not None else (62, 100)  # mit Sollwert: mehr Platz fuer die 2 Zeilen darueber
    device_x = CARD_W - 54
    parts = [
        f'<g>',
        f'<rect x="0" y="0" width="{CARD_W}" height="{h}" rx="12" fill="#ffffff" '
        f'stroke="{building_color}" stroke-width="{3.4 if selected else 1.3}"/>',
        _text(16, 26, f"{kreis.nr}. {kreis.short}", size=12.5, weight="700", color=building_color),
    ]
    # Anschlussknoten (Verbindung zur Sammelschiene oben)
    parts.append(f'<line x1="{node_x}" y1="0" x2="{node_x}" y2="{node_y}" stroke="{building_color}" stroke-width="2"/>')
    parts.append(f'<circle cx="{node_x}" cy="{node_y}" r="4.5" fill="{building_color}"/>')
    # Vor- und Ruecklaufleitung
    parts.append(f'<line x1="{node_x}" y1="{y_vl}" x2="{device_x}" y2="{y_vl}" stroke="{VL_COLOR}" stroke-width="3.2"/>')
    parts.append(f'<line x1="{node_x}" y1="{y_rl}" x2="{device_x}" y2="{y_rl}" stroke="{RL_COLOR}" stroke-width="3.2"/>')
    parts.append(f'<line x1="{node_x}" y1="{node_y}" x2="{node_x}" y2="{y_vl}" stroke="{VL_COLOR}" stroke-width="3.2"/>')
    parts.append(f'<line x1="{node_x}" y1="{node_y}" x2="{node_x}" y2="{y_rl}" stroke="{RL_COLOR}" stroke-width="3.2"/>')

    # Pumpe auf dem Ruecklauf, falls vorhanden
    pump = kreis.col("pump")
    px = node_x + 28
    if pump is not None:
        parts.append(_pump_icon(px, y_rl, INK))
        parts.append(_text(px, y_rl + 22, "Pumpe", size=8.5, weight="700", color=INK, anchor="middle"))
        parts.append(_text(px, y_rl + 32, pump.short, size=7.5, color=MUTED, anchor="middle", italic=True))

    # Messpunkte (Sensordaten) auf Vor- und Ruecklauf; ein vorhandener Sollwert wird als eigene
    # Textzeile ueber dem Vorlauf-Messpunkt gestapelt (nicht als zweite Leitung - sonst ueberlappt der
    # Text mit dem Vorlauf-Messpunkt).
    sx = device_x - 54
    vl, rl = kreis.col("vl"), kreis.col("rl")
    if soll is not None:
        parts.append(_text(sx, y_vl - 42, soll.short, size=7.3, color=MUTED, anchor="middle", italic=True))
        parts.append(_text(sx, y_vl - 31, "Soll-Vorlauf", size=8.5, weight="700", color=SOLL_COLOR, anchor="middle"))
        parts.append(f'<circle cx="{sx}" cy="{y_vl-9}" r="8" fill="none" stroke="{SOLL_COLOR}" '
                     f'stroke-width="1.3" stroke-dasharray="2.5 2"/>')
    parts.append(f'<circle cx="{sx}" cy="{y_vl}" r="4.5" fill="{VL_COLOR}"/>')
    parts.append(_text(sx, y_vl - 9, "Vorlauf" + (" (Ist)" if soll is not None else ""), size=8.5, weight="700", color=VL_COLOR, anchor="middle"))
    parts.append(_text(sx, y_vl - 20, vl.short if vl else "", size=7.3, color=MUTED, anchor="middle", italic=True))
    parts.append(f'<circle cx="{sx}" cy="{y_rl}" r="4.5" fill="{RL_COLOR}"/>')
    parts.append(_text(sx, y_rl + 15, "Rücklauf", size=8.5, weight="700", color=RL_COLOR, anchor="middle"))
    parts.append(_text(sx, y_rl + 26, rl.short if rl else "", size=7.3, color=MUTED, anchor="middle", italic=True))

    parts.append(_device_icon(kind, device_x, (y_vl + y_rl) / 2, INK))
    device_label = {"fbh": "Fußbodenschleife", "rlt": "Luftbehandlung", "heizkoerper": "Heizkörper"}[kind]
    parts.append(_text(device_x, y_rl + 38, device_label, size=8, color=MUTED, anchor="middle"))

    if is_rlt:
        y0 = CARD_H + 10
        aul, zul = kreis.extra_col("aul"), kreis.extra_col("zul")
        meters = [c for c in kreis.extra_columns if c.role == "meter_electric"]
        parts.append(f'<line x1="14" y1="{y0-6}" x2="{CARD_W-14}" y2="{y0-6}" stroke="#E3E7EB" stroke-width="1"/>')
        parts.append(_text(16, y0 + 8, "Lüftungsseite (Zuluft/Abluft):", size=8.5, weight="700", color=MUTED))
        bx = 30
        for label, col, color in (("Außenluft", aul, RL_COLOR), ("Zuluft", zul, VL_COLOR)):
            parts.append(f'<circle cx="{bx}" cy="{y0+26}" r="4" fill="{color}"/>')
            parts.append(_text(bx + 9, y0 + 23, label, size=8, weight="700", color=INK))
            parts.append(_text(bx + 9, y0 + 33, col.short if col else "", size=7.2, color=MUTED, italic=True))
            bx += 118
        bx = 54
        for m in meters:
            parts.append(_meter_icon(bx, y0 + 58, m.short.replace("Zähler ", "Z. "), INK))
            bx += 110
    parts.append("</g>")
    return "".join(parts), h


def svg_netzplan(selected_zone: str | None = None) -> str:
    """Schematischer Netzplan der Heizungs-/Lüftungsanlage: zeigt, wie die 7 Heizkreise an die
    gemeinsame Wärmeversorgung angeschlossen sind, mit Vor-/Rücklaufleitungen, Pumpen, Sollwert-Fühlern
    und Zählern - jeweils beschriftet mit dem zugehörigen Spaltennamen aus den Messdaten, damit sich
    Diagramm und Datentabelle direkt zuordnen lassen."""
    rows: list[tuple] = []  # (Gebaeude, [(card_svg, h), ...], card_width_total)
    for g in GEBAEUDE:
        cards = [_circuit_card(k, g.farbe, k.zone == selected_zone) for k in g.kreise]
        row_w = len(cards) * CARD_W + (len(cards) - 1) * CARD_GAP_X
        rows.append((g, cards, row_w))

    building_gap = 70
    content_w = sum(r[2] for r in rows) + building_gap * (len(rows) - 1)
    total_w = max(content_w + 60, 760)

    # ---- Kopf: Waermeerzeugung + Hauptzaehler -------------------------------------------------
    cx = total_w / 2
    y = 18
    head = [
        f'<rect x="{cx-110:.1f}" y="{y:.1f}" width="220" height="46" rx="10" fill="#2b2b2b"/>',
        _text(cx, y + 20, "Wärmeerzeugung", size=13, weight="700", color="#ffffff", anchor="middle"),
        _text(cx, y + 36, "(Kessel/Übergabe – nicht in den Messdaten)", size=8, color="#cfd4da", anchor="middle"),
    ]
    y_meter = y + 46 + 34
    head.append(f'<line x1="{cx}" y1="{y+46}" x2="{cx}" y2="{y_meter-12}" stroke="{VL_COLOR}" stroke-width="3.2"/>')
    head.append(_meter_icon(cx, y_meter, "Zähler 019 – WMZ", INK))
    head.append(_text(cx + 16, y_meter - 4, "Wärmemengenzähler (kWh)", size=8.5, color=MUTED))
    y_bus0 = y_meter + 26

    # ---- Sammelschiene: verzweigt zu jedem Gebaeude -------------------------------------------
    svg = [f'<svg viewBox="0 0 {total_w} 0" xmlns="http://www.w3.org/2000/svg" role="img" '
          f'aria-label="Netzplan der Heizungsanlage: Wärmeerzeugung, Verteilung und alle 7 Heizkreise mit '
          f'Vorlauf, Rücklauf, Pumpen und Sollwertfühlern" style="width:100%;height:auto;font-family:Arial,sans-serif">']
    body: list[str] = []
    y_cursor = y_bus0

    body += head
    centers = []
    left_edge = (total_w - content_w) / 2
    xc = left_edge
    for g, cards, row_w in rows:
        centers.append(xc + row_w / 2)
        xc += row_w + building_gap
    bus_y = y_cursor
    body.append(f'<line x1="{min(centers):.1f}" y1="{bus_y}" x2="{max(centers):.1f}" y2="{bus_y}" '
               f'stroke="{VL_COLOR}" stroke-width="2.6"/>')
    body.append(f'<line x1="{cx}" y1="{bus_y}" x2="{cx}" y2="{bus_y}" stroke="{VL_COLOR}" stroke-width="2.6"/>')
    body.append(f'<line x1="{cx}" y1="{y_meter+10}" x2="{cx}" y2="{bus_y}" stroke="{VL_COLOR}" stroke-width="2.6"/>')

    y_cursor = bus_y + 18
    for (g, cards, row_w), center in zip(rows, centers):
        body.append(f'<line x1="{center:.1f}" y1="{bus_y}" x2="{center:.1f}" y2="{y_cursor}" '
                   f'stroke="{g.farbe}" stroke-width="2.4"/>')
        body.append(f'<circle cx="{center:.1f}" cy="{bus_y:.1f}" r="4" fill="{g.farbe}"/>')
        body.append(_text(center, y_cursor + 14, g.name, size=13.5, weight="700", color=g.farbe, anchor="middle"))
    y_cursor += 30

    max_row_h = 0
    for (g, cards, row_w), center in zip(rows, centers):
        row_x = center - row_w / 2
        xi = row_x
        for svg_frag, h in cards:
            body.append(f'<g transform="translate({xi:.1f},{y_cursor:.1f})">{svg_frag}</g>')
            max_row_h = max(max_row_h, h)
            xi += CARD_W + CARD_GAP_X
    y_cursor += max_row_h + 24

    # ---- Legende -------------------------------------------------------------------------------
    leg_y = y_cursor
    body.append(f'<rect x="20" y="{leg_y}" width="{total_w-40}" height="54" rx="10" fill="{BG}" stroke="#dde2e7"/>')
    lx = 36
    body.append(f'<line x1="{lx}" y1="{leg_y+18}" x2="{lx+26}" y2="{leg_y+18}" stroke="{VL_COLOR}" stroke-width="3.2"/>')
    body.append(_text(lx+34, leg_y+22, "Vorlauf (warm)", size=9.5))
    lx += 150
    body.append(f'<line x1="{lx}" y1="{leg_y+18}" x2="{lx+26}" y2="{leg_y+18}" stroke="{RL_COLOR}" stroke-width="3.2"/>')
    body.append(_text(lx+34, leg_y+22, "Rücklauf (kühler)", size=9.5))
    lx += 170
    body.append(f'<line x1="{lx}" y1="{leg_y+18}" x2="{lx+26}" y2="{leg_y+18}" stroke="{SOLL_COLOR}" stroke-width="1.6" stroke-dasharray="4 3"/>')
    body.append(_text(lx+34, leg_y+22, "Sollwert-Fühler", size=9.5))
    lx += 150
    body.append(_pump_icon(lx+10, leg_y+18, INK))
    body.append(_text(lx+26, leg_y+22, "Umwälzpumpe", size=9.5))
    lx += 150
    body.append(_meter_icon(lx+10, leg_y+18, "", INK))
    body.append(_text(lx+26, leg_y+22, "Zähler", size=9.5))
    body.append(_text(36, leg_y+42, "Farbiger Text unter jedem Messpunkt = Spaltenname in der Messdaten-Tabelle (Tab „Datenprüfung“).",
                      size=8.5, color=MUTED, italic=True))
    y_cursor = leg_y + 54 + 14

    total_h = y_cursor
    svg[0] = svg[0].replace('viewBox="0 0 {} 0"'.format(total_w), f'viewBox="0 0 {total_w:.0f} {total_h:.0f}"')
    svg.append(f'<rect x="0" y="0" width="{total_w:.0f}" height="{total_h:.0f}" fill="{BG}" rx="12"/>')
    svg += body
    svg.append("</svg>")
    return "".join(svg)
