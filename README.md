# MTG Card Scanner

A free tool that identifies Magic: The Gathering cards — exact printing, set, collector number, foil and foil type — sorts them into bins, and exports CSV files for ManaBox and Moxfield. Runs on a Windows PC, and on a DIY card-sorting machine (Raspberry Pi 5) that can identify cards by itself.

> **Status:** testing. The desktop app does scan sessions, bins, review and CSV export (phone or machine as the camera); the machine is being built.

## For users
Download the latest `MTGCardScanner_Setup_x.y.z.exe` from [Releases](https://github.com/MrWeasel42/mtg-card-scanner/releases/latest) and double-click it. Windows may warn that the app is unrecognized (it isn't code-signed yet): click **More info → Run anyway**.

## How it fits together
| Part | Where | What it does |
|---|---|---|
| Catalog builder | `catalog-builder/` + `.github/workflows/catalog.yml` | Every week, GitHub's cloud machines download all card data from Scryfall, fingerprint every printing, and publish the result to the `catalog-latest` release. |
| Desktop app | `src/` | Downloads the catalog, identifies cards, runs scan sessions, review, and CSV export. |
| Machine | `hardware/`, `machine/` | 9-bin card sorter: feeder, camera hood, trapdoor bins. The Pi 5 runs the touchscreen app and sessions, and identifies cards itself whenever the PC app isn't connected. |

The Windows app and the machine's touchscreen are one app on two screens: same features, same review, same exports. See [docs/apps.md](docs/apps.md).

The full design is in [docs/blueprint.md](docs/blueprint.md).

## License
Free for personal, hobby, educational and other noncommercial use. **You may not sell this software or use it to make money.**

- **Software:** [PolyForm Noncommercial 1.0.0](LICENSE.md)
- **Machine designs** (PCB, 3D-printed parts, wiring), once added: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) — build and share it freely, give credit, no commercial use, and share your changes under the same terms.

## Credits
Card data and images from [Scryfall](https://scryfall.com). Magic: The Gathering is © Wizards of the Coast; this project is unofficial fan content and is not affiliated with or endorsed by Wizards of the Coast.
