"""Text reader: a line-for-line copy of src/CardScanner.Core/Ocr/CardTextReader.cs.

PaddleOCR PP-OCRv3 models (the same ONNX files the Windows app ships, src/CardScanner.Core/OcrModels):
a DB text detector finds the lines, a CTC recognizer reads each one.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime as ort

F32 = np.float32
MEAN = np.array([0.485, 0.456, 0.406], F32)
STD = np.array([0.229, 0.224, 0.225], F32)


@dataclass
class TextLine:
    text: str
    confidence: float
    box: np.ndarray          # 4 x 2 float32: TL, TR, BR, BL

    @property
    def top(self) -> float:
        return float(self.box[:, 1].min())

    @property
    def left(self) -> float:
        return float(self.box[:, 0].min())


def session(path: str, threads: int) -> ort.InferenceSession:
    o = ort.SessionOptions()
    o.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    o.intra_op_num_threads = threads
    return ort.InferenceSession(path, o, providers=["CPUExecutionProvider"])


def _dist(a, b) -> float:
    return math.sqrt((float(a[0]) - float(b[0])) ** 2 + (float(a[1]) - float(b[1])) ** 2)


def _order(p: np.ndarray) -> np.ndarray:
    xs = sorted(p.tolist(), key=lambda q: q[0])                  # stable, like LINQ OrderBy
    left = sorted(xs[:2], key=lambda q: q[1])
    right = sorted(xs[2:], key=lambda q: q[1])
    return np.array([left[0], right[0], right[1], left[1]], F32)


class CardTextReader:
    def __init__(self, model_dir: str, threads: int | None = None):
        threads = threads or max(1, (os.cpu_count() or 2) // 2)
        self._det = session(os.path.join(model_dir, "text_det.onnx"), threads)
        self._rec = session(os.path.join(model_dir, "text_rec.onnx"), threads)
        self._det_in = self._det.get_inputs()[0].name
        self._rec_in = self._rec.get_inputs()[0].name
        d = self._rec.get_modelmeta().custom_metadata_map["character"]
        self._chars = [c.rstrip("\r") for c in d.split("\n")] + [" "]

    def read(self, bgr: np.ndarray, min_confidence: float = 0.5) -> list[TextLine]:
        lines = []
        for box in self.detect(bgr):
            crop = self._crop(bgr, box)
            text, conf = self.recognize(crop)
            if len(text) > 0 and conf >= min_confidence:
                lines.append(TextLine(text, conf, box))
        return lines

    # ---------------- detection
    def detect(self, bgr, limit=736, thresh=0.3, box_thresh=0.5, unclip=1.6) -> list[np.ndarray]:
        h, w = bgr.shape[:2]
        r = limit / min(h, w) if min(h, w) < limit else 1.0
        rh = max(32, int(round(h * r / 32)) * 32)        # round() is banker's rounding, like Math.Round
        rw = max(32, int(round(w * r / 32)) * 32)
        resized = cv2.resize(bgr, (rw, rh))
        x = (resized.astype(F32) / F32(255) - MEAN) / STD    # channel order as loaded (B, G, R), like the reference
        inp = np.ascontiguousarray(x.transpose(2, 0, 1)[None])
        pred = self._det.run(None, {self._det_in: inp})[0][0, 0].astype(F32)

        _, bitmap = cv2.threshold(pred, thresh, 255, cv2.THRESH_BINARY)
        bitmap = bitmap.astype(np.uint8)
        bitmap = cv2.dilate(bitmap, np.ones((2, 2), np.uint8))
        contours, _ = cv2.findContours(bitmap, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        boxes = []
        for c in contours[:1000]:
            (cx, cy), (bw, bh), ang = cv2.minAreaRect(c)
            if min(bw, bh) < 3:
                continue
            if self._box_score(pred, cv2.boxPoints(((cx, cy), (bw, bh), ang)), rw, rh) < box_thresh:
                continue
            bw, bh = F32(bw), F32(bh)
            d = F32(bw * bh * F32(unclip) / (F32(2) * (bw + bh)))
            big = ((cx, cy), (float(bw + 2 * d), float(bh + 2 * d)), ang)
            if min(big[1]) < 5:
                continue
            pts = cv2.boxPoints(big).astype(F32)
            sx = np.clip(np.round((pts[:, 0] / F32(rw) * F32(w)).astype(np.float64)), 0, w - 1)
            sy = np.clip(np.round((pts[:, 1] / F32(rh) * F32(h)).astype(np.float64)), 0, h - 1)
            o = _order(np.stack([sx, sy], 1).astype(F32))
            if _dist(o[0], o[1]) > 3 and _dist(o[0], o[3]) > 3:
                boxes.append(o)
        boxes.sort(key=lambda b: (float(b[0][1]), float(b[0][0])))
        return boxes

    @staticmethod
    def _box_score(pred, pts, w, h) -> float:
        x0 = min(max(int(math.floor(pts[:, 0].min())), 0), w - 1)
        y0 = min(max(int(math.floor(pts[:, 1].min())), 0), h - 1)
        x1 = min(max(int(math.ceil(pts[:, 0].max())), 0), w - 1)
        y1 = min(max(int(math.ceil(pts[:, 1].max())), 0), h - 1)
        mask = np.zeros((y1 - y0 + 1, x1 - x0 + 1), np.uint8)
        poly = np.array([[int(p[0] - x0), int(p[1] - y0)] for p in pts], np.int32)
        cv2.fillPoly(mask, [poly], 1)
        return cv2.mean(pred[y0:y1 + 1, x0:x1 + 1], mask)[0]

    # ---------------- recognition
    @staticmethod
    def _crop(img, b):
        w = max(int(max(_dist(b[0], b[1]), _dist(b[2], b[3]))), 1)
        h = max(int(max(_dist(b[0], b[3]), _dist(b[1], b[2]))), 1)
        dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], F32)
        m = cv2.getPerspectiveTransform(b.astype(F32), dst)
        out = cv2.warpPerspective(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        if h >= 1.5 * w:
            out = cv2.rotate(out, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return out

    def recognize(self, line) -> tuple[str, float]:
        h, w = line.shape[:2]
        ratio = w / max(h, 1)
        img_w = max(320, int(math.ceil(48 * ratio)))
        rw = min(img_w, int(math.ceil(48 * ratio)))
        resized = cv2.resize(line, (rw, 48))
        inp = np.zeros((1, 3, 48, img_w), F32)                         # zero-padded on the right
        inp[0, :, :, :rw] = ((resized.astype(F32) / F32(255) - F32(0.5)) / F32(0.5)).transpose(2, 0, 1)
        probs = self._rec.run(None, {self._rec_in: inp})[0][0]          # T x classes
        best = probs.argmax(1)
        best_p = probs[np.arange(len(best)), best]
        out, conf, n, prev = [], 0.0, 0, -1
        for t in range(len(best)):
            b = int(best[t])
            if b != 0 and b != prev and b - 1 < len(self._chars):
                out.append(self._chars[b - 1])
                conf += float(best_p[t])
                n += 1
            prev = b
        return "".join(out), (F32(conf) / n if n else 0.0)
