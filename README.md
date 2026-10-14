# Molecule ↔ Flavour matching cards

20 pairs: a **molecule card** (structure, name and formula) and a **flavour card** (food picture, flavour and foods). Players match each molecule to its flavour.

## Build

```bash
mamba create -n flavourcards -c conda-forge python=3.11 rdkit reportlab pillow requests
conda run -n flavourcards python make_cards.py               # output/cards.pdf
conda run -n flavourcards python make_cards.py --hide-names  # output/cards_hard.pdf (structure + formula only)
```

Edit `pairs.json` to swap pairs. You only need a PubChem CID; structures are fetched once and cached in `structures_cache.json`. The emoji are rendered with Apple Color Emoji, so the build needs macOS.

## Output

| File | What |
|---|---|
| `cards.pdf` | Pages 1–3 are molecule cards, pages 4–6 are flavour cards (9 per A4 sheet, 63×88 mm) |
| `cards_hard.pdf` | Same, but no names on the molecule cards |
| `backs.pdf` | Matching card backs; print duplex (flip on long edge) with `cards.pdf` |
| `answer_key.pdf` | Pairs, receptors and a fun fact for each pair |

Print at **100% / actual size** and cut along the crop marks.

## Ways to play

- **Mingle:** give everyone one card at arrival; they find their match over coffee.
- **Memory:** table groups play face-down pairs with the two decks.
- **Sniff round:** put real samples in opaque jars (vanilla, mint, caraway, banana sweets, cinnamon, clove…) and have teams match jar → molecule.
- **Talking points:** the carvone enantiomers (#15/#16), plus the genetics cards PTC (TAS2R38), androstenone (OR7D4) and coriander (OR6A2).
