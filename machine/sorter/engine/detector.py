"""Finding and straightening the card: a copy of src/CardScanner.Core/Vision/CardDetector.cs and WhiteBorder.cs."""
from __future__ import annotations

import math

import cv2
import numpy as np

F32 = np.float32
WIDTH, HEIGHT = 488, 680            # Scryfall "normal" size, which the catalog fingerprints came from
CARD_ASPECT = 63.0 / 88.0


def _dist(a, b) -> float:
    return math.sqrt((float(a[0]) - float(b[0])) ** 2 + (float(a[1]) - float(b[1])) ** 2)


def _unit(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1])
    return (v[0] / n, v[1] / n)


def _median(xs) -> float:
    a = sorted(xs)
    n = len(a)
    if n == 0:
        return 0.0
    return float(a[n // 2]) if n % 2 == 1 else (a[n // 2 - 1] + a[n // 2]) / 2


def order_corners(pts) -> np.ndarray:
    """TL, TR, BR, BL with the card upright (portrait)."""
    p = [tuple(map(float, q)) for q in np.asarray(pts).reshape(-1, 2)]
    tl = min(p, key=lambda q: q[0] + q[1])
    br = max(p, key=lambda q: q[0] + q[1])           # first maximum, like OrderByDescending().First()
    tr = min(p, key=lambda q: q[1] - q[0])
    bl = max(p, key=lambda q: q[1] - q[0])
    o = [tl, tr, br, bl]
    if _dist(o[0], o[1]) > _dist(o[0], o[3]):          # lying sideways: long side vertical
        o = [o[3], o[0], o[1], o[2]]
    return np.array(o, F32)


def warp(photo, corners, width=WIDTH, height=HEIGHT):
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], F32)
    m = cv2.getPerspectiveTransform(np.asarray(corners, F32), dst)
    return cv2.warpPerspective(photo, m, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


class Detected:
    def __init__(self, card, corners, method):
        self.card, self.corners, self.method = card, corners, method

    @property
    def found(self) -> bool:
        return self.corners is not None and len(self.corners) == 4


def detect(photo) -> Detected:
    scale = min(1.0, 1400.0 / max(photo.shape[1], photo.shape[0]))
    small = cv2.resize(photo, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    quad, refit = _find_card_quad(small, cv2.RETR_EXTERNAL)
    inner = False
    if quad is None:
        quad, _ = _find_card_quad(small, cv2.RETR_LIST, max_fraction=0.7)
        inner = quad is not None
    if quad is None:
        whole = cv2.resize(photo, (WIDTH, HEIGHT), interpolation=cv2.INTER_CUBIC)
        return Detected(whole, None, "none (whole photo)")
    method = "inner outline" if inner else "refit" if refit else "outline"
    if refit or inner:
        quad = snap_to_edges(small, quad)
        method += "+snap"
    wider = white_border_extend(small, quad)
    if wider is not None:
        quad = wider
        method += "+white border"
    corners = np.array([[F32(p[0] / scale), F32(p[1] / scale)] for p in quad], F32)
    return Detected(warp(photo, corners), corners, method)


def _edge_masks(color, gray):
    edges = np.zeros(gray.shape, np.uint8)
    for ch in cv2.split(color):
        edges = cv2.bitwise_or(edges, cv2.Canny(ch, 30, 90))
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, k, iterations=2)
    _, binm = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    return [edges, binm, cv2.bitwise_not(binm)]


def _find_card_quad(img, mode, max_fraction=0.9):
    blurred = cv2.GaussianBlur(img, (5, 5), 0)
    gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)
    h, w = img.shape[:2]
    min_area = w * h * 0.08
    for mask in _edge_masks(blurred, gray):
        contours, _ = cv2.findContours(mask, mode, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(contours, key=cv2.contourArea, reverse=True):
            area = cv2.contourArea(c)
            if area < min_area:
                break
            if area > w * h * max_fraction:
                continue
            quad = _quad_from_contour(c, area)
            if quad is not None and (_touches_edge(quad, w, h) or not looks_like_card(quad)):
                continue
            if quad is not None and is_square(quad):
                return order_corners(quad), False
            refit = _refit_quad(c, w, h)
            if refit is not None:
                return order_corners(refit), True
    return None, False


def _quad_from_contour(contour, area):
    peri = cv2.arcLength(contour, True)
    for eps in (0.02, 0.03, 0.05):
        approx = cv2.approxPolyDP(contour, eps * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return approx.reshape(4, 2).astype(F32)
    rect = cv2.minAreaRect(contour)
    if area / max(rect[1][0] * rect[1][1], 1) > 0.85:
        return cv2.boxPoints(rect).astype(F32)
    return None


def snap_to_edges(img, quad, inward=0.06, outward=0.015):
    """Slide each side onto the strongest brightness edge between 6% inside and 1.5% outside."""
    o = order_corners(quad)
    w = (_dist(o[0], o[1]) + _dist(o[3], o[2])) / 2
    h = (_dist(o[0], o[3]) + _dist(o[1], o[2])) / 2
    k = 1 + 2 * outward + 0.01
    s = 600 / w
    W, H = int(w * s * k), int(h * s * k)
    cx, cy = float(np.mean(o[:, 0], dtype=np.float64)), float(np.mean(o[:, 1], dtype=np.float64))
    big = np.array([[cx + (p[0] - cx) * k, cy + (p[1] - cy) * k] for p in o], F32)
    m = cv2.getPerspectiveTransform(big, np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], F32))
    wp = cv2.warpPerspective(img, m, (W, H), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REPLICATE)
    g = cv2.cvtColor(wp, cv2.COLOR_BGR2GRAY).astype(F32)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    ax = np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3))
    ay = np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    ix0, iy0 = (W - w * s) / 2, (H - h * s) / 2
    lo, hi = int(-inward * 600), int(outward * 600)

    def shift(side):
        best, bd = -1.0, 0
        horiz = side in ("top", "bottom")
        n = W if horiz else H
        a, b = int(n * 0.2), int(n * 0.8)
        for d in range(lo, hi + 1):
            line = {"top": int(iy0) - d, "bottom": int(H - iy0) + d, "left": int(ix0) - d}.get(side, int(W - ix0) + d)
            if line < 0 or line >= (H if horiz else W):
                continue
            vals = np.sort(ay[line, a:b] if horiz else ax[a:b, line])
            med = float(vals[len(vals) // 2])
            if med > best:
                best, bd = med, d
        return bd / s

    t, bt, l, r = shift("top"), shift("bottom"), shift("left"), shift("right")
    return _move_sides(o, t, bt, l, r)


def _move_sides(o, t, bt, l, r):
    ux = _unit(((o[1][0] - o[0][0] + o[2][0] - o[3][0]) / 2, (o[1][1] - o[0][1] + o[2][1] - o[3][1]) / 2))
    uy = _unit(((o[3][0] - o[0][0] + o[2][0] - o[1][0]) / 2, (o[3][1] - o[0][1] + o[2][1] - o[1][1]) / 2))
    return np.array([
        [o[0][0] - ux[0] * l - uy[0] * t, o[0][1] - ux[1] * l - uy[1] * t],
        [o[1][0] + ux[0] * r - uy[0] * t, o[1][1] + ux[1] * r - uy[1] * t],
        [o[2][0] + ux[0] * r + uy[0] * bt, o[2][1] + ux[1] * r + uy[1] * bt],
        [o[3][0] - ux[0] * l + uy[0] * bt, o[3][1] - ux[1] * l + uy[1] * bt],
    ], F32)


def is_square(quad, max_angle_error=8, min_side_ratio=0.93) -> bool:
    o = order_corners(quad)
    for i in range(4):
        a, b, c = o[(i + 3) % 4], o[i], o[(i + 1) % 4]
        v1x, v1y = float(a[0] - b[0]), float(a[1] - b[1])
        v2x, v2y = float(c[0] - b[0]), float(c[1] - b[1])
        cos = (v1x * v2x + v1y * v2y) / (math.sqrt(v1x * v1x + v1y * v1y) * math.sqrt(v2x * v2x + v2y * v2y) + 1e-9)
        if abs(math.degrees(math.acos(max(-1.0, min(1.0, cos)))) - 90) > max_angle_error:
            return False
    s0, s1, s2, s3 = _dist(o[0], o[1]), _dist(o[1], o[2]), _dist(o[2], o[3]), _dist(o[3], o[0])
    return min(s0, s2) / max(s0, s2) >= min_side_ratio and min(s1, s3) / max(s1, s3) >= min_side_ratio


def _refit_quad(contour, w, h):
    hull = cv2.convexHull(contour)
    peri = cv2.arcLength(hull, True)
    options = []
    for eps in (0.01, 0.02, 0.03, 0.05):
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4:
            options.append(approx.reshape(4, 2).astype(F32))
    options.append(cv2.boxPoints(cv2.minAreaRect(contour)).astype(F32))
    best, best_fit = None, 0.95
    for q in options:
        if _touches_edge(q, w, h) or not looks_like_card(q) or not is_square(q):
            continue
        fit = _overlap(q, hull, w, h)
        if fit > best_fit:
            best_fit, best = fit, q
    return best


def _overlap(quad, hull, w, h) -> float:
    a = np.zeros((h, w), np.uint8)
    b = np.zeros((h, w), np.uint8)
    cv2.fillPoly(a, [np.array([[int(p[0]), int(p[1])] for p in quad], np.int32)], 1)
    cv2.fillPoly(b, [hull.reshape(-1, 2).astype(np.int32)], 1)
    inter = cv2.countNonZero(cv2.bitwise_and(a, b))
    union = cv2.countNonZero(cv2.bitwise_or(a, b))
    return inter / max(union, 1)


def _touches_edge(quad, w, h) -> bool:
    m = 3
    return sum(1 for p in quad if p[0] <= m or p[1] <= m or p[0] >= w - 1 - m or p[1] >= h - 1 - m) >= 2


def looks_like_card(quad) -> bool:
    o = order_corners(quad)
    w = (_dist(o[0], o[1]) + _dist(o[3], o[2])) / 2
    h = (_dist(o[0], o[3]) + _dist(o[1], o[2])) / 2
    if w < 1 or h < 1:
        return False
    return abs(min(w, h) / max(w, h) - CARD_ASPECT) < 0.12


# ------------------------------------------------------------------------------------------------ white border
MAX_GROW, SCALE = 1.16, 600


def white_border_extend(img, quad):
    """White-bordered card on a light table: move the outline from the frame out to the real card edge."""
    o = order_corners(quad)
    w = (_dist(o[0], o[1]) + _dist(o[3], o[2])) / 2
    h = (_dist(o[0], o[3]) + _dist(o[1], o[2])) / 2
    if w < 20 or h < 20:
        return None
    s = SCALE / w
    W, H = int(w * s * MAX_GROW), int(h * s * MAX_GROW)
    cx, cy = float(np.mean(o[:, 0], dtype=np.float64)), float(np.mean(o[:, 1], dtype=np.float64))
    big = np.array([[cx + (p[0] - cx) * MAX_GROW, cy + (p[1] - cy) * MAX_GROW] for p in o], F32)
    m = cv2.getPerspectiveTransform(big, np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], F32))
    wp = cv2.warpPerspective(img, m, (W, H), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REPLICATE)
    g = cv2.cvtColor(wp, cv2.COLOR_BGR2GRAY).astype(F32)
    mu = cv2.blur(g, (5, 5))
    mu2 = cv2.blur(g * g, (5, 5))
    sat = cv2.split(cv2.cvtColor(wp, cv2.COLOR_BGR2HSV))[1]
    tex = np.sqrt(np.maximum(mu2 - mu * mu, F32(0)).astype(np.float64))   # float32 like the C# (same rounding)

    ix0, iy0 = (W - w * s) / 2, (H - h * s) / 2
    ix1, iy1 = W - ix0, H - iy0

    def profile(side):
        res = []
        horiz = side in ("top", "bottom")
        start = (int(iy0) - 1 if side == "top" else int(iy1)) if horiz else (int(ix0) - 1 if side == "left" else int(ix1))
        step = -1 if side in ("top", "left") else 1
        limit = H if horiz else W
        n = W if horiz else H
        lo2, hi2 = int(n * 0.2), int(n * 0.8)
        k = start
        while 0 <= k < limit:
            if horiz:
                v, t, sa = g[k, lo2:hi2], tex[k, lo2:hi2], sat[k, lo2:hi2]
            else:
                v, t, sa = g[lo2:hi2, k], tex[lo2:hi2, k], sat[lo2:hi2, k]
            res.append((float(np.median(v.astype(np.float64))), float(np.median(t)), float(np.median(sa.astype(np.float64)))))
            k += step
        return res

    offs: dict[str, float] = {}
    not_white = []
    for side in ("top", "bottom", "left", "right"):
        p = profile(side)
        a, b = 4, max(8, int(0.02 * SCALE))
        if len(p) <= b:
            return None
        ring = p[a:b]
        bV, bT, bS = _median([r[0] for r in ring]), _median([r[1] for r in ring]), _median([r[2] for r in ring])
        if bV < 150 or bS > 60 or bT > 8:
            not_white.append(side)
            continue
        edge = None
        for d in range(b, len(p) - 3):
            nV = (p[d][0] + p[d + 1][0] + p[d + 2][0] + p[d + 3][0]) / 4
            nT = (p[d][1] + p[d + 1][1] + p[d + 2][1] + p[d + 3][1]) / 4
            nS = (p[d][2] + p[d + 1][2] + p[d + 2][2] + p[d + 3][2]) / 4
            if abs(nV - bV) > 18 or nT > max(2.2 * bT, bT + 4) or abs(nS - bS) > 18:
                edge = d
                break
        if edge is None:
            return None
        offs[side] = edge / s

    if len(offs) == 3 and len(not_white) == 1:
        offs[not_white[0]] = _median(offs.values())
    if len(offs) < 4:
        return None
    rel = {k: v / w for k, v in offs.items()}
    med = _median(rel.values())
    odd = [k for k, v in rel.items() if v < 0.65 * med or v > 1.5 * med]
    if len(odd) == 1:
        rel[odd[0]] = med
        offs[odd[0]] = med * w
    top2 = sorted(rel.values())[-2:]
    width = (top2[0] + top2[1]) / 2
    if width < 0.025 or width > 0.08 or top2[1] / top2[0] >= 1.4:
        return None
    for key in list(rel):
        if rel[key] < width:
            offs[key] = width * w
    nq = _move_sides(o, offs["top"], offs["bottom"], offs["left"], offs["right"])
    return nq if looks_like_card(nq) else None
