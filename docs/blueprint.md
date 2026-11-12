# Blueprint

The agreed design for the MTG Card Scanner. Code should follow this; change this file first if the design changes.

## Goal
Identify Magic: The Gathering cards with very high accuracy (exact printing, set, collector number, foil and foil type), sort them into bins, and export CSV files for ManaBox (primary) and Moxfield (backup). Shareable with non-technical friends via a single installer.

## Scope
- Magic only, English only.
- Eras: Alpha/Unlimited/Revised through current sets, including Secret Lair and The List.
- Output per session: one CSV (Catalog mode only). No running master list.
- Prices: used for sorting only; ManaBox remains the place to check prices.

## Modes
| Mode | Pipeline | Output |
|---|---|---|
| **Catalog** | feed → capture → identify → route to bin → review flagged | CSV for the session |
| **Sort** | feed → capture → identify → route to bin | On-screen summary, no CSV |

Sort mode with name-only rules (e.g. alphabetical) needs name-level recognition only, so fewer cards get flagged.

## Bin rules
- Rule types: **color, set, collector number, alphabetical, price** (all available).
- Each bin has a rule; rules are evaluated in order, **first match wins**, so types can be combined (e.g. bin 1 = $10+, bins 2–6 by color).
- The **last bin is always Flagged/Unidentified**.
- Saved as named presets, chosen at session start. The software supports any number of bins; the machine may start with 2 and grow to 7.
- Alphabetical: front-face name, "Æ" files under A, accents ignored; the app can suggest balanced letter ranges.
- Price: uses the foil or etched price for foils; cards with no price go to Flagged.

## Session lifecycle
- **Start**: choose mode, rule preset, session name.
- **Running** → hopper empty → **Waiting** (auto-resumes when cards are detected). Never stops on its own.
- **Paused**: manual, or automatic when a bin is full.
- **Stopped**: only by the user. Then end-of-session review, then CSV export (Catalog mode).
- Progress is saved after every card; a crash or power loss resumes where it left off.

## Review
- Live review panel during the run, plus end-of-session review for anything unresolved.
- Shows the card's photos and top candidates. Review happens on the desktop.
- Flagged-bin order matches the review list order.

## Machine flowpath
1. Feeder pulls one card; sensor confirms it is at the camera.
2. Capture two images (cross-polarized for recognition, angled light for foil check); assign sequence number.
3. Card advances to a holding position; next card feeds; recognition runs in the background (no pause).
4. Result arrives; gate routes the held card to its bin. Pauses only if a result is late.

## Recognition
1. Find and straighten the card.
2. Image fingerprint → nearest catalog printings (top 5).
3. Read the bottom-left collector line: set code, collector number, ★ (foil) / • (non-foil).
4. Foil evidence by era, from the per-set foil rules:
   - `nonfoil_only` (pre-Urza's Legacy): automatically non-foil.
   - `separate_printings` (e.g. black-bordered 7th Edition foils): image match decides.
   - `shooting_star` (old-frame foils): shooting star in the text box.
   - `collector_star`: ★/• in the collector line.
   - `none`: lighting check only; flagged until the rig exists.
5. Combine evidence; below-threshold or conflicting results go to review. Expensive look-alikes (e.g. Unlimited vs Revised) are always reviewed.
6. Special foils (surge, etched, galaxy...) come from the exact printing, which the collector number pins down.
7. **Marker checks** for reprints that share art *and* collector line with the original. Each check looks at a fixed
   spot on the straightened card and is calibrated in the cloud build against Scryfall images, with its accuracy reported:
   - **The List** (`plst`, also `ulst`): small planeswalker symbol in the bottom-left corner. Scryfall stores these as
     separate printings (e.g. Citanul Hierophants USG #244 ≈ $2.87 vs PLST USG-244 ≈ $0.46).
   - Later: promo stamps (P, date stamps, planeswalker stamp), other set-specific marks. Sets that may share the List
     symbol (e.g. Mystery Booster 2) must be verified.
   - Symbol clearly present → List printing; clearly absent → original; unsure → review, showing both candidates with
     the corner zoomed in. Pairs with a big price gap need a confident result or go to review.

## Architecture
- **App**: C# (.NET), Windows first, also runs on Raspberry Pi 5 (Linux ARM64). Installer built by GitHub Actions; self-updating.
- **AI**: DINOv2 ViT-S/14 exported to ONNX, run with ONNX Runtime (GPU via DirectML/CUDA, CPU fallback).
- **Catalog**: built weekly in the cloud (`.github/workflows/catalog.yml`), published to the `catalog-latest` release; the app downloads it. Works fully offline after download.
- **Machine**: Raspberry Pi 5 (brain) + microcontroller on a custom PCB (motors, LEDs, sensors). Plug-and-play: the app detects it and loads firmware.
- **Data sources**: Scryfall bulk data (kept free; no paywall).
