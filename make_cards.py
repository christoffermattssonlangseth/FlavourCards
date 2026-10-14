"""Generate print-ready molecule <-> flavour matching cards.

Usage:
    python make_cards.py              # cards.pdf, backs.pdf, answer_key.pdf
    python make_cards.py --hide-names # molecule cards show structure + formula only

Structures are fetched from PubChem by CID once and cached in structures_cache.json.
"""

import argparse
import io
import json
import math
import re
from pathlib import Path
from xml.sax.saxutils import escape

import requests
from PIL import Image, ImageDraw, ImageFont
from rdkit import Chem
from rdkit.Chem import rdDepictor, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).parent
CACHE = HERE / "structures_cache.json"
EMOJI_FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"
AVENIR = "/System/Library/Fonts/Avenir Next.ttc"

CARD_W, CARD_H = 63 * mm, 88 * mm  # poker size
COLS, ROWS = 3, 3
PAGE_W, PAGE_H = A4
MARGIN_X = (PAGE_W - COLS * CARD_W) / 2
MARGIN_Y = (PAGE_H - ROWS * CARD_H) / 2
RADIUS = 3 * mm
BAND_H = 9 * mm

MOL_COLOUR = colors.HexColor("#1F3A5F")
FLAV_COLOUR = colors.HexColor("#D9604C")
INK = colors.HexColor("#1E1E1E")
GREY = colors.HexColor("#6B6B6B")
CUT = colors.HexColor("#BBBBBB")
FOOTER = "MolNeuro Retreat 2026"

pdfmetrics.registerFont(TTFont("Avenir", AVENIR, subfontIndex=7))
pdfmetrics.registerFont(TTFont("Avenir-Demi", AVENIR, subfontIndex=2))
pdfmetrics.registerFont(TTFont("Avenir-Bold", AVENIR, subfontIndex=0))
pdfmetrics.registerFont(TTFont("Avenir-Heavy", AVENIR, subfontIndex=8))

FORMULA_OVERRIDES = {5234: "NaCl"}
BOND_PX = 110  # bond length in the rendered structure image
MAX_BOND = 9 * mm  # small molecules are not upscaled beyond this bond length


def load_smiles(pairs):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    missing = [p["cid"] for p in pairs if str(p["cid"]) not in cache]
    if missing:
        url = ("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/"
               f"{','.join(map(str, missing))}/property/SMILES/JSON")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        for row in r.json()["PropertyTable"]["Properties"]:
            cache[str(row["CID"])] = row["SMILES"]
        CACHE.write_text(json.dumps(cache, indent=1))
    return {int(k): v for k, v in cache.items()}


def draw_structure(smiles, size=(1400, 1100)):
    mol = Chem.MolFromSmiles(smiles)
    rdDepictor.SetPreferCoordGen(True)
    rdDepictor.Compute2DCoords(mol)
    d = rdMolDraw2D.MolDraw2DCairo(*size)
    o = d.drawOptions()
    o.setBackgroundColour((1, 1, 1, 0))
    o.fixedBondLength = BOND_PX
    o.bondLineWidth = 5
    o.minFontSize = 38
    o.maxFontSize = 60
    o.padding = 0.06
    o.addStereoAnnotation = False
    rdMolDraw2D.PrepareAndDrawMolecule(d, mol)
    d.FinishDrawing()
    img = Image.open(io.BytesIO(d.GetDrawingText())).convert("RGBA")
    return img.crop(img.getbbox()), mol


def render_emoji(ch):
    font = ImageFont.truetype(EMOJI_FONT, 160)
    img = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((20, 20), ch, font=font, embedded_color=True)
    return img.crop(img.getbbox())


def formula_markup(mol, cid):
    f = FORMULA_OVERRIDES.get(cid) or rdMolDescriptors.CalcMolFormula(mol)
    return re.sub(r"(\d+)", r"<sub>\1</sub>", f)


def draw_image_fit(c, img, x, y, w, h, max_scale=float("inf")):
    """Draw a PIL image centred in box (x, y, w, h), preserving aspect ratio."""
    iw, ih = img.size
    s = min(w / iw, h / ih, max_scale)
    dw, dh = iw * s, ih * s
    c.drawImage(ImageReader(img), x + (w - dw) / 2, y + (h - dh) / 2, dw, dh, mask="auto")


def paragraph(c, text, style, x, y_top, w):
    p = Paragraph(text, style)
    _, ph = p.wrap(w, 100 * mm)
    p.drawOn(c, x, y_top - ph)
    return ph


def card_frame(c, x, y, colour, label):
    c.setStrokeColor(CUT)
    c.setLineWidth(0.4)
    c.setFillColor(colors.white)
    c.roundRect(x, y, CARD_W, CARD_H, RADIUS, stroke=1, fill=1)
    # header band, clipped to the rounded top
    c.saveState()
    path = c.beginPath()
    path.roundRect(x, y, CARD_W, CARD_H, RADIUS)
    c.clipPath(path, stroke=0, fill=0)
    c.setFillColor(colour)
    c.rect(x, y + CARD_H - BAND_H, CARD_W, BAND_H, stroke=0, fill=1)
    c.restoreState()
    c.setFillColor(colors.white)
    c.setFont("Avenir-Heavy", 9)
    c.drawCentredString(x + CARD_W / 2, y + CARD_H - BAND_H + 3.2 * mm, label)
    c.setFillColor(GREY)
    c.setFont("Avenir", 5.5)
    c.drawCentredString(x + CARD_W / 2, y + 3 * mm, FOOTER)


NAME = ParagraphStyle("name", fontName="Avenir-Demi", fontSize=11.5, leading=13.5,
                      alignment=TA_CENTER, textColor=INK)
FORMULA = ParagraphStyle("formula", fontName="Avenir", fontSize=8, leading=10,
                         alignment=TA_CENTER, textColor=GREY)
FLAVOUR = ParagraphStyle("flavour", fontName="Avenir-Bold", fontSize=14.5, leading=17,
                         alignment=TA_CENTER, textColor=INK)
FOODS = ParagraphStyle("foods", fontName="Avenir", fontSize=8.5, leading=10.5,
                       alignment=TA_CENTER, textColor=GREY)


def molecule_card(c, x, y, pair, img, mol, hide_names):
    card_frame(c, x, y, MOL_COLOUR, "MOLECULE")
    pad = 4 * mm
    text_h = 10 * mm if hide_names else 19 * mm
    box_top = y + CARD_H - BAND_H - 3 * mm
    box_bottom = y + 6 * mm + text_h
    draw_image_fit(c, img, x + pad, box_bottom, CARD_W - 2 * pad, box_top - box_bottom,
                   max_scale=MAX_BOND / BOND_PX)
    ty = box_bottom - 1 * mm
    if not hide_names:
        ty -= paragraph(c, escape(pair["name"]), NAME, x + pad, ty, CARD_W - 2 * pad) + 1 * mm
    paragraph(c, formula_markup(mol, pair["cid"]), FORMULA, x + pad, ty, CARD_W - 2 * pad)


def flavour_card(c, x, y, pair, emoji):
    card_frame(c, x, y, FLAV_COLOUR, "FLAVOUR")
    pad = 4 * mm
    draw_image_fit(c, emoji, x + pad, y + 40 * mm, CARD_W - 2 * pad, 30 * mm)
    ty = y + 36 * mm
    ty -= paragraph(c, escape(pair["flavour"]), FLAVOUR, x + pad, ty, CARD_W - 2 * pad) + 2 * mm
    paragraph(c, escape(pair["foods"]), FOODS, x + pad, ty, CARD_W - 2 * pad)


def slot(i):
    col, row = i % COLS, (i // COLS) % ROWS
    return MARGIN_X + col * CARD_W, PAGE_H - MARGIN_Y - (row + 1) * CARD_H


def crop_marks(c):
    c.setStrokeColor(CUT)
    c.setLineWidth(0.3)
    L = 4 * mm
    for k in range(COLS + 1):
        x = MARGIN_X + k * CARD_W
        c.line(x, PAGE_H - MARGIN_Y + 1 * mm, x, PAGE_H - MARGIN_Y + 1 * mm + L)
        c.line(x, MARGIN_Y - 1 * mm, x, MARGIN_Y - 1 * mm - L)
    for k in range(ROWS + 1):
        y = MARGIN_Y + k * CARD_H
        c.line(MARGIN_X - 1 * mm, y, MARGIN_X - 1 * mm - L, y)
        c.line(PAGE_W - MARGIN_X + 1 * mm, y, PAGE_W - MARGIN_X + 1 * mm + L, y)


def lay_out(c, items, draw):
    for i, item in enumerate(items):
        if i and i % (COLS * ROWS) == 0:
            c.showPage()
        if i % (COLS * ROWS) == 0:
            crop_marks(c)
        draw(c, *slot(i), item)
    c.showPage()


def make_cards(pairs, smiles, out, hide_names):
    structures = {p["cid"]: draw_structure(smiles[p["cid"]]) for p in pairs}
    c = canvas.Canvas(str(out), pagesize=A4)
    c.setTitle("Molecule cards + Flavour cards")
    lay_out(c, pairs, lambda c, x, y, p: molecule_card(c, x, y, p, *structures[p["cid"]], hide_names))
    lay_out(c, pairs, lambda c, x, y, p: flavour_card(c, x, y, p, render_emoji(p["emoji"])))
    c.save()


def card_back(c, x, y, colour, label, glyph):
    c.setFillColor(colour)
    c.setStrokeColor(CUT)
    c.setLineWidth(0.4)
    c.roundRect(x, y, CARD_W, CARD_H, RADIUS, stroke=1, fill=1)
    c.setStrokeColor(colors.Color(1, 1, 1, alpha=0.35))
    c.setLineWidth(1)
    c.roundRect(x + 3 * mm, y + 3 * mm, CARD_W - 6 * mm, CARD_H - 6 * mm, RADIUS, stroke=1, fill=0)
    cx, cy = x + CARD_W / 2, y + CARD_H / 2 + 4 * mm
    if glyph == "benzene":
        c.setStrokeColor(colors.white)
        c.setLineWidth(2.2)
        r = 11 * mm
        pts = [(cx + r * math.cos(math.radians(90 + 60 * k)),
                cy + r * math.sin(math.radians(90 + 60 * k))) for k in range(6)]
        path = c.beginPath()
        path.moveTo(*pts[0])
        for pt in pts[1:]:
            path.lineTo(*pt)
        path.close()
        c.drawPath(path, stroke=1, fill=0)
        c.circle(cx, cy, r * 0.58, stroke=1, fill=0)
    else:
        c.setFillColor(colors.white)
        c.setFont("Avenir-Heavy", 60)
        c.drawCentredString(cx, cy - 7 * mm, glyph)
    c.setFillColor(colors.white)
    c.setFont("Avenir-Heavy", 11)
    c.drawCentredString(x + CARD_W / 2, y + 16 * mm, label)
    c.setFont("Avenir", 6)
    c.drawCentredString(x + CARD_W / 2, y + 10 * mm, FOOTER)


def make_backs(n_pairs, out):
    """Backs with the same page count/order as cards.pdf, for duplex printing.

    Every slot is filled, so mirrored columns on the reverse side don't matter.
    """
    c = canvas.Canvas(str(out), pagesize=A4)
    c.setTitle("Card backs")
    per_page = COLS * ROWS
    n_slots = math.ceil(n_pairs / per_page) * per_page
    for colour, label, glyph in [(MOL_COLOUR, "MOLECULE", "benzene"), (FLAV_COLOUR, "FLAVOUR", "?")]:
        lay_out(c, range(n_slots), lambda c, x, y, _: card_back(c, x, y, colour, label, glyph))
    c.save()


def make_answer_key(pairs, out):
    doc = SimpleDocTemplate(str(out), pagesize=landscape(A4), leftMargin=12 * mm,
                            rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title="Answer key")
    cell = ParagraphStyle("cell", fontName="Avenir", fontSize=8.5, leading=10.5)
    bold = ParagraphStyle("bold", parent=cell, fontName="Avenir-Demi")
    head = ParagraphStyle("head", parent=cell, fontName="Avenir-Heavy", textColor=colors.white)
    title = ParagraphStyle("title", fontName="Avenir-Bold", fontSize=16, leading=20)
    rows = [[Paragraph(h, head) for h in ("#", "Molecule", "Flavour card", "Found in",
                                           "Receptor", "Fun fact")]]
    for p in pairs:
        rows.append([Paragraph(str(p["id"]), cell)] + [
            Paragraph(escape(p[k]), bold if k in ("name", "flavour") else cell)
            for k in ("name", "flavour", "foods", "receptor", "fact")])
    t = Table(rows, colWidths=[8 * mm, 45 * mm, 40 * mm, 45 * mm, 45 * mm, 90 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), MOL_COLOUR),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F1EE")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    doc.build([Paragraph("Molecule – Flavour: answer key", title), Spacer(1, 4 * mm), t])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hide-names", action="store_true",
                    help="molecule cards show only the structure and formula (hard mode)")
    ap.add_argument("--out", type=Path, default=HERE / "output")
    args = ap.parse_args()

    pairs = json.loads((HERE / "pairs.json").read_text())
    smiles = load_smiles(pairs)
    args.out.mkdir(exist_ok=True)
    name = "cards_hard.pdf" if args.hide_names else "cards.pdf"
    make_cards(pairs, smiles, args.out / name, args.hide_names)
    make_backs(len(pairs), args.out / "backs.pdf")
    make_answer_key(pairs, args.out / "answer_key.pdf")
    print(f"wrote {args.out}/{name}, backs.pdf, answer_key.pdf")


if __name__ == "__main__":
    main()
