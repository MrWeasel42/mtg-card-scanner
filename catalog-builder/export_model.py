"""Exports the card-fingerprint AI model to ONNX so the C# app and the Raspberry Pi can run it.

    python export_model.py --out model.onnx

Run once per model version. The resulting file is published as a GitHub release asset and
reused by every weekly catalog build, so fingerprints always come from the exact same model.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import torch
import timm

MODEL_NAME = "vit_small_patch14_dinov2.lvd142m"
WIDTH, HEIGHT = 224, 308  # multiples of 14 (the model's patch size); card aspect ratio


def export(out: Path, pretrained: bool = True) -> None:
    model = timm.create_model(
        MODEL_NAME, pretrained=pretrained, num_classes=0, img_size=(HEIGHT, WIDTH)
    ).eval()

    class Normalized(torch.nn.Module):
        """Adds unit-length normalization so the output is ready for cosine matching."""

        def __init__(self, inner):
            super().__init__()
            self.inner = inner

        def forward(self, x):
            v = self.inner(x)
            return v / (v.norm(dim=1, keepdim=True) + 1e-8)

    wrapped = Normalized(model).eval()
    dummy = torch.zeros(1, 3, HEIGHT, WIDTH)
    torch.onnx.export(
        wrapped, dummy, str(out),
        input_names=["image"], output_names=["fingerprint"],
        dynamic_axes={"image": {0: "batch"}, "fingerprint": {0: "batch"}},
        opset_version=17, dynamo=False,
    )
    print(f"Exported {MODEL_NAME} -> {out} ({out.stat().st_size / 1e6:.0f} MB)")

    # Make sure the ONNX file gives the same answers as the original model.
    import numpy as np
    import onnxruntime as ort

    x = torch.rand(2, 3, HEIGHT, WIDTH)
    with torch.no_grad():
        expected = wrapped(x).numpy()
    got = ort.InferenceSession(str(out)).run(None, {"image": x.numpy()})[0]
    diff = float(np.abs(expected - got).max())
    print(f"ONNX vs PyTorch max difference: {diff:.2e}")
    if diff > 1e-3:
        raise SystemExit("ONNX export does not match the original model")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("model.onnx"))
    ap.add_argument("--random-weights", action="store_true", help="Testing only: skip the weight download")
    args = ap.parse_args()
    export(args.out, pretrained=not args.random_weights)
