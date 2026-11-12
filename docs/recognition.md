# How card recognition works (v0.2)

## Why not just match the picture?
v0.1 matched the whole card image against every printing's fingerprint. On 45 real phone photos it named the
wrong card 19 times: most modern cards share the same frame layout, so lighting, glare and sleeves were enough
to tip it to a different card. The crops themselves were fine.

## The pipeline
1. **Find the card** in the photo and straighten it (`Vision/CardDetector`). Works raw, single- and
   double-sleeved on a plain background.
2. **Read the name** (`Ocr/CardTextReader`, PaddleOCR PP-OCRv3 models bundled as ONNX). The top 20% of the
   card is read both ways up; each line (and words on the same row joined together) is fuzzy-matched against
   every card name (`Recognition/CardIndex`, ratio = 2·LCS / total length, min 0.85). If nothing matches,
   the whole card is read (borderless/showcase cards put the name elsewhere; min 0.90, 5+ letters).
   Tokens, emblems and art cards are never matched by name.
3. **Which way up?** Each orientation is scored by its best name reading plus how well the picture matches
   that card; the better one wins.
4. **Read the collector line** (bottom-left small print), e.g. `R0381 DSK • EN` → number 381, set DSK,
   non-foil. `★` = foil, `•` = non-foil (`Recognition/CollectorLine`).
5. **Score printings** of the card named (plus anything the collector line points at directly):

   `2 × picture similarity + name score + 0.30 (number matches) + 0.20 (set matches) + 0.50 (both match)`

6. **Confidence**
   - *Pinned*: name, set and number all agree.
   - *Flagged* (needs a look): name and collector line unreadable; picture disagrees with an unpinned match;
     or look-alike printings of the same card differ a lot in price (e.g. Alpha/Beta/Unlimited/Revised
     duals, which have no collector line).

## Measured on real photos (336 phone photos: raw, single and double sleeved)
See the release notes for the latest numbers.

## Known limits
- Non-English cards aren't in the catalog (English only by design); they get flagged.
- Pre-2015 cards have no set code/number on them, so the edition comes from the picture alone.
- Foil detection only uses the ★/• marker for now; the lighting check comes with the machine.
