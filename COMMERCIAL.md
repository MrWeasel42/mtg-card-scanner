# Commercial use and kits

This project is free for anyone to use, build and share for noncommercial purposes (see [License](#licenses)).
**Selling it is reserved for the project owner.** Eric (GitHub: MrWeasel42) owns the copyright in the software
and the hardware designs. He may sell kits himself or through his own company (an LLC, once formed), and he can
grant that right to others in writing. Nobody else may sell the software, the designs, kits, assembled machines,
or parts made from the design files without that written permission.

## Official kit tiers

| Tier | What you get | Price |
|---|---|---|
| **1. Design files** | The software plus every hardware design file (CAD, STLs, STEP, wiring, board files), the parts list and the assembly guide. You source, print and build everything. | **Free** (download from GitHub) |
| **2. Electronics kit** | Tier 1 plus the complete electronics kit (hub board, bin boards, pre-made cables, Pi, servos, motors, power harness, hardware bag). You print the parts at home and assemble. | Paid (physical parts) |
| **3. Complete kit** | Tier 2 plus all structural parts already made (printed, or aluminum/metal from PCBWay). Assembly only. | Paid (physical parts) |

**The software is always free, in every tier.** Kits charge for physical parts and the work of putting them
together, never for the software or for card data. This is required: the card database is built from
[Scryfall](https://scryfall.com) data, and Scryfall's terms don't allow card data to be paywalled (users can't
be required to pay or subscribe to get it). Tier 1 stays free for the same reason, and because the files are
already public on GitHub.

## Rules every kit must follow

- **Card data and images:** used under Scryfall's API terms and the Wizards of the Coast
  [Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy). Don't paywall card data. Don't
  crop off or alter the copyright or artist credit on card images. Don't use Scryfall's name or logo in a way
  that implies they endorse the product.
- **Trademarks:** "Magic: The Gathering", "Magic" and "MTG" are Wizards of the Coast trademarks. A product sold
  for money needs its own name. "for Magic: The Gathering cards" is fine as a description; "MTG" or "Magic" as
  the product's brand name is not. The kit gets its own name before the first sale.
- **No endorsement:** this project is unofficial and not affiliated with or endorsed by Wizards of the Coast or
  Scryfall. Kit listings and packaging say so.
- **Open-source parts:** ship the notices in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) with every kit.
  Klipper (motor firmware) is GPLv3: each kit includes a link to its source and to this repo's Klipper config.
- **Mains power:** kits that include the AC power harness use a certified power supply, inlet and cord, and
  include the warnings in [hardware/SAFETY.md](hardware/SAFETY.md).

## Before the first sale (checklist)

- [ ] Form the LLC; license or assign the copyright from Eric to the LLC in writing
- [ ] Pick the kit's own product name (see Trademarks)
- [ ] Talk to a small-business lawyer: product liability for the AC power harness, kit terms of sale, insurance
- [ ] Check FCC requirements for the electronics kit (it's built mostly from already-certified modules)
- [ ] Every outside contributor has agreed to [CONTRIBUTING.md](CONTRIBUTING.md) (needed to sell their work)
- [ ] THIRD_PARTY_NOTICES.md is current

## Licenses

- Software: [PolyForm Noncommercial 1.0.0](LICENSE.md)
- Hardware designs: [CC BY-NC-SA 4.0](hardware/LICENSE.md)

Both allow personal, hobby and educational use, building your own machine, and sharing changes. Neither allows
others to sell. To ask about selling, open an issue on the GitHub repo.

*This file explains how the project plans to handle commercial use. It isn't legal advice.*
