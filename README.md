# MTG Card Scanner

A free tool that identifies Magic: The Gathering cards — exact printing, set, collector number, foil and foil type — sorts them into bins, and exports CSV files for ManaBox and Moxfield. Built to run on a desktop PC now and inside a DIY scanning machine later.

> **Status:** in development. The cloud catalog builder is working; the desktop app is next.

## For users
A one-click Windows installer will be posted under **Releases** once the app is ready.

## How it fits together
| Part | Where | What it does |
|---|---|---|
| Catalog builder | `catalog-builder/` + `.github/workflows/catalog.yml` | Every week, GitHub's cloud machines download all card data from Scryfall, fingerprint every printing, and publish the result to the `catalog-latest` release. |
| Desktop app | *(coming next)* | Downloads the catalog, identifies cards, runs scan sessions, review, and CSV export. |
| Machine | *(later)* | Feeder, camera, lighting and bins driven by a Raspberry Pi 5 and a microcontroller. |

The full design is in [docs/blueprint.md](docs/blueprint.md).

## License
Free for personal, hobby, educational and other noncommercial use. **You may not sell this software or use it to make money.**

- **Software:** [PolyForm Noncommercial 1.0.0](LICENSE.md)
- **Machine designs** (PCB, 3D-printed parts, wiring), once added: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) — build and share it freely, give credit, no commercial use, and share your changes under the same terms.

## Credits
Card data and images from [Scryfall](https://scryfall.com). Magic: The Gathering is © Wizards of the Coast; this project is unofficial fan content and is not affiliated with or endorsed by Wizards of the Coast.
