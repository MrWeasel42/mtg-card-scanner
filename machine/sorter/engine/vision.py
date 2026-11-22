"""Small picture checks, copied from src/CardScanner.Core/Vision: border colour, printed marks (foil shooting star,
List symbol), the ★/• collector mark, the close-up detail compare and the crop refine (ECC overlay)."""
from __future__ import annotations

import math
import os

import cv2
import numpy as np

from . import detector

F32 = np.float32


# ------------------------------------------------------------------------------------------------ CardBorder
def _median_u8(a: np.ndarray) -> float:
    if a.size == 0:
        return 0.0
    return float(np.median(a.astype(np.float64)))


def border_measure(card, frm=0.012, to=0.035):
    h, w = card.shape[:2]
    o, i = int(frm * w), int(to * w)
    mask = np.zeros((h, w), np.uint8)
    mask[o:o + h - 2 * o, o:o + w - 2 * o] = 255
    mask[i:i + h - 2 * i, i:i + w - 2 * i] = 0
    hsv = cv2.cvtColor(card, cv2.COLOR_BGR2HSV)
    sel = hsv[mask != 0]
    return _median_u8(sel[:, 2]), _median_u8(sel[:, 1]), _median_u8(sel[:, 0])


def border_classify(card) -> str | None:
    v, s, _ = border_measure(card)
    measured = "black" if v < 70 else "white" if v > 150 and s < 60 else None
    if measured == "white":
        return measured
    v1, s1, _ = border_measure(card, 0.025, 0.04)
    v2, s2, _ = border_measure(card, 0.04, 0.055)
    if v1 > 140 and s1 < 60 and v2 > 150 and s2 < 60:
        return "white"
    return measured


# ------------------------------------------------------------------------------------------------ PrintedMark
class PrintedMark:
    """A small printed graphic in one area of a straightened 976 x 1360 card, matched on a top-hat filter."""

    def __init__(self, png_path, area, kernel, *scales):
        self.area, self.kernel, self.scales = area, kernel, scales
        t = cv2.imread(png_path, cv2.IMREAD_GRAYSCALE)
        if t is None:
            raise FileNotFoundError(png_path)
        self.template = t.astype(F32)

    def score(self, card) -> float:
        h, w = card.shape[:2]
        x, y = int(w * self.area[0]), int(h * self.area[1])
        rw, rh = int(w * self.area[2]), int(h * self.area[3])
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + rw, w), min(y + rh, h)
        region = card[y0:y1, x0:x1]
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (self.kernel, self.kernel))
        top = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k).astype(F32)
        best = -1.0
        for sc in self.scales:
            t = cv2.resize(self.template, None, fx=sc, fy=sc)
            if t.shape[0] >= top.shape[0] or t.shape[1] >= top.shape[1]:
                continue
            res = cv2.matchTemplate(top, t, cv2.TM_CCOEFF_NORMED)
            mx = cv2.minMaxLoc(res)[1]
            if not math.isnan(mx):
                best = max(best, mx)
        return best


SHOOTING_FOIL_AT, SHOOTING_NONFOIL_BELOW = 0.70, 0.50
LIST_SEEN_AT, LIST_ABSENT_BELOW = 0.72, 0.68


class Marks:
    def __init__(self, assets_dir):
        self.shooting = PrintedMark(os.path.join(assets_dir, "shooting_star.png"), (0, 0.80, 0.45, 0.17), 25, 0.85, 0.95, 1.05, 1.15)
        self.list = PrintedMark(os.path.join(assets_dir, "list_symbol.png"), (0, 0.88, 0.14, 0.12), 31, 0.8, 0.9, 1.0, 1.1, 1.25)


# ------------------------------------------------------------------------------------------------ StarMark (★ / •)
STAR_FOIL_AT, STAR_FOIL_LEAD, STAR_NONFOIL_AT, STAR_NONFOIL_LEAD = 0.88, 0.08, 0.86, 0.04
_SW, _SH = 976, 1360
_AREA = (20, 1250, 400, 110)
_X0, _X1, _Y0, _Y1 = 80, 125, 45, 75


def _star(size):
    n = size + 6
    c, R = n / 2.0, size / 2.0
    r = R * 0.42
    pts = []
    for i in range(10):
        rad = R if i % 2 == 0 else r
        a = i * math.pi / 5
        pts.append([int(round((c + rad * math.sin(a)) * 4)), int(round((c - rad * math.cos(a)) * 4))])
    t = np.zeros((n, n), F32)
    cv2.fillPoly(t, [np.array(pts, np.int32)], 1.0, cv2.LINE_AA, 2)
    return cv2.GaussianBlur(t, (3, 3), 0)


def _dot(size):
    n = size + 8
    t = np.zeros((n, n), F32)
    cv2.circle(t, (n // 2, n // 2), size // 2, 1.0, -1)
    return cv2.GaussianBlur(t, (3, 3), 0)


_STARS = [_star(s) for s in (11, 13, 15, 17, 19)]
_DOTS = [_dot(s) for s in (5, 6, 7, 9)]


def _best(image, template):
    r = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    th, tw = template.shape
    x0, y0 = max(0, _X0 - tw // 2), max(0, _Y0 - th // 2)
    x1, y1 = min(r.shape[1] - 1, _X1 - tw // 2), min(r.shape[0] - 1, _Y1 - th // 2)
    if x1 < x0 or y1 < y0:
        return 0.0
    return cv2.minMaxLoc(r[y0:y1 + 1, x0:x1 + 1])[1]


def star_mark_score(card_jpeg: bytes):
    img = cv2.imdecode(np.frombuffer(card_jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None or img.size == 0:
        return 0.0, 0.0
    sized = cv2.resize(img, (_SW, _SH), interpolation=cv2.INTER_AREA)
    x, y, w, h = _AREA
    f = sized[y:y + h, x:x + w].astype(F32)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    e = cv2.morphologyEx(f, cv2.MORPH_TOPHAT, k)
    return max(_best(e, t) for t in _STARS), max(_best(e, t) for t in _DOTS)


def star_mark_read(s):
    star, dot = s
    if star >= STAR_FOIL_AT and star - dot >= STAR_FOIL_LEAD:
        return True
    if dot >= STAR_NONFOIL_AT and dot - star >= STAR_NONFOIL_LEAD:
        return False
    return None


# ------------------------------------------------------------------------------------------------ DetailCompare
DETAIL_REORDER_MARGIN, DETAIL_PIN_MARGIN = 0.03, 0.08
_REGIONS = [((0.78, 0.53, 0.17, 0.09), 0.04), ((0.04, 0.86, 0.76, 0.125), 0.035), ((0.06, 0.62, 0.88, 0.12), 0.035)]


def _prep(bgr):
    sized = cv2.resize(bgr, (_SW, _SH), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(sized, cv2.COLOR_BGR2GRAY).astype(F32)
    g = cv2.GaussianBlur(g, (5, 5), 0)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.GaussianBlur(cv2.magnitude(gx, gy), (5, 5), 0)


def _region_score(photo, cand, p, margin):
    W, H = _SW, _SH
    px, py, pw, ph = int(p[0] * W), int(p[1] * H), int(p[2] * W), int(p[3] * H)
    sx0, sy0 = max(0, int((p[0] - margin) * W)), max(0, int((p[1] - margin) * H))
    sx1, sy1 = min(W, int((p[0] + p[2] + margin) * W)), min(H, int((p[1] + p[3] + margin) * H))
    patch = cand[py:py + ph, px:px + pw]
    area = photo[sy0:sy1, sx0:sx1]
    mx = cv2.minMaxLoc(cv2.matchTemplate(area, patch, cv2.TM_CCOEFF_NORMED))[1]
    return 0.0 if math.isnan(mx) else mx


def detail_scores(photo_jpeg: bytes, candidates) -> list[tuple[str, float]]:
    """candidates: [(id, image path)] -> [(id, score 0..1)]"""
    out = []
    img = cv2.imdecode(np.frombuffer(photo_jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        return out
    photo = _prep(img)
    for cid, path in candidates:
        c = cv2.imread(path, cv2.IMREAD_COLOR)
        if c is None or c.size == 0:
            continue
        cand = _prep(c)
        out.append((cid, sum(_region_score(photo, cand, r, m) for r, m in _REGIONS) / len(_REGIONS)))
    return out


# ------------------------------------------------------------------------------------------------ CropRefine
_WD, _HD = 244, 340
_MAX_MOVE, _POLISH_MOVE, _BIG_MOVE, _BIG_MOVE_MIN_FIT = 0.15, 0.05, 0.08, 0.5


def _gray(bgr):
    g = cv2.GaussianBlur(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    return g.astype(F32)


def _pass(photo, corners, ref_gray, max_move):
    card = detector.warp(photo, corners, _WD, _HD)
    a = _gray(card)
    w0 = np.eye(3, dtype=F32)
    try:
        fit, wm = cv2.findTransformECC(ref_gray, a, w0, cv2.MOTION_HOMOGRAPHY,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5), None, 5)
    except cv2.error:
        return None
    frame = np.array([[0, 0], [_WD - 1, 0], [_WD - 1, _HD - 1], [0, _HD - 1]], F32)
    in_card = cv2.perspectiveTransform(frame.reshape(-1, 1, 2), wm).reshape(-1, 2)
    move = float(np.max(np.abs(in_card - frame))) / _WD
    if move > max_move or (move > _BIG_MOVE and fit < _BIG_MOVE_MIN_FIT):
        return None
    to_photo = cv2.getPerspectiveTransform(frame, np.asarray(corners, F32))
    return cv2.perspectiveTransform(in_card.reshape(-1, 1, 2).astype(F32), to_photo).reshape(-1, 2)


def crop_refine(photo, corners, reference, upside_down):
    if corners is None or len(corners) != 4:
        return None
    ref_small = cv2.resize(reference, (_WD, _HD), interpolation=cv2.INTER_AREA)
    if upside_down:
        ref_small = cv2.rotate(ref_small, cv2.ROTATE_180)
    b = _gray(ref_small)
    first = _pass(photo, corners, b, _MAX_MOVE)
    if first is None:
        return None
    second = _pass(photo, first, b, _POLISH_MOVE)
    return first if second is None else second
