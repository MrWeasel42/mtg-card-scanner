# Third-party notices

This project uses the open-source software, models and data below. Each stays under its own license (the
project's licenses don't apply to them). Ship this file with every kit, and keep it current when dependencies
change.

## Data
| Item | Used for | Terms |
|---|---|---|
| Scryfall card data and images | Card catalog, recognition, display | [Scryfall API terms](https://scryfall.com/docs/api): free for Magic software; no paywalling; no altered images; no implied endorsement |
| Magic: The Gathering card names, text and art | Displayed and recognized | © Wizards of the Coast, used under the [Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy). Unofficial; not approved or endorsed by Wizards |

## Models
| Item | License |
|---|---|
| DINOv2 ViT-S/14 weights (Meta, via timm `vit_small_patch14_dinov2.lvd142m`) | Apache 2.0 |
| PaddleOCR PP-OCRv3 models (Baidu) | Apache 2.0 |

## Windows app (.NET)
| Package | License |
|---|---|
| Avalonia (incl. Desktop, Themes.Fluent, Fonts.Inter) | MIT (Inter font: SIL OFL 1.1) |
| CommunityToolkit.Mvvm | MIT |
| Microsoft.Data.Sqlite | MIT |
| Microsoft.ML.OnnxRuntime | MIT |
| OpenCvSharp4 / OpenCvSharp4.runtime.win | Apache 2.0 (bundles OpenCV, Apache 2.0) |

## Machine (Raspberry Pi)
| Package | License |
|---|---|
| Klipper firmware + Moonraker | GPLv3: source at https://github.com/Klipper3d/klipper and https://github.com/Arksine/moonraker; this repo's config is `machine/klipper/` |
| Raspberry Pi OS | Various open-source licenses (Debian-based) |
| onnxruntime | MIT |
| OpenCV (python3-opencv) | Apache 2.0 |
| NumPy | BSD-3-Clause |
| picamera2 | BSD-2-Clause |
| rapidfuzz | MIT |
| PyYAML | MIT |
| smbus2 | MIT |
| gpiozero | BSD-3-Clause |
| lgpio | Unlicense (public domain) |
| VL53L1X (Python) | MIT |

## Android app
| Package | License |
|---|---|
| AndroidX (core, appcompat, lifecycle, CameraX, exifinterface) | Apache 2.0 |
| Material Components for Android | Apache 2.0 |
| kotlinx.coroutines | Apache 2.0 |

## Catalog builder (developer tool, not shipped)
PyTorch (BSD-3), timm (Apache 2.0), ONNX (Apache 2.0), Pillow (MIT-CMU), requests (Apache 2.0), ijson (BSD-3),
tqdm (MPL 2.0 / MIT).
