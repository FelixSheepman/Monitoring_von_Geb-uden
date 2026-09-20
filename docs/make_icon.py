"""Erzeugt das Desktop-Icon (eigenes Design, kein Hochschul-Logo): docs/img/monitoring_icon.ico und .png."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent / "img"
NAVY, TEAL, WHITE, ORANGE = (18, 53, 91), (35, 110, 140), (255, 255, 255), (230, 159, 0)
S = 1024  # Zeichengroesse, wird herunterskaliert


def font(size):
    for name in ("arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_icon(with_text=True):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=190, fill=NAVY)
    top = 90 if with_text else 150
    # Gebaeude: zwei Bloecke mit Fensterraster
    base = 590 if with_text else 700
    for x0, x1, y0 in ((190, 470, top + 90), (500, 830, top + 200)):
        d.rectangle((x0, y0, x1, base), fill=TEAL, outline=WHITE, width=14)
        for wy in range(y0 + 45, base - 40, 80 if with_text else 95):
            for wx in range(x0 + 40, x1 - 50, 85):
                d.rectangle((wx, wy, wx + 45, wy + 40), fill=WHITE)
    # Messkurve ueber dem Gebaeude
    pts = [(120, base - 40), (300, base - 190), (450, base - 110), (620, base - 320), (760, base - 240), (910, base - 400)]
    d.line(pts, fill=ORANGE, width=34, joint="curve")
    for x, y in pts[-1:]:
        d.ellipse((x - 34, y - 34, x + 34, y + 34), fill=ORANGE)
    if with_text:
        d.rectangle((60, base + 30, S - 60, base + 36), fill=TEAL)
        for i, line in enumerate(("Monitoring", "von Gebäuden")):
            f = font(118 if i == 0 else 100)
            w = d.textlength(line, font=f)
            d.text(((S - w) / 2, base + 70 + i * 140), line, font=f, fill=WHITE)
    return img


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    big, small = draw_icon(True), draw_icon(False)
    big.resize((512, 512), Image.LANCZOS).save(OUT / "monitoring_icon.png")
    layers = [big.resize((s, s), Image.LANCZOS) for s in (256, 128)] + [small.resize((s, s), Image.LANCZOS) for s in (64, 48, 32, 16)]
    layers[0].save(OUT / "monitoring_icon.ico", format="ICO", append_images=layers[1:], sizes=[(l.width, l.height) for l in layers])
    print("ok")
