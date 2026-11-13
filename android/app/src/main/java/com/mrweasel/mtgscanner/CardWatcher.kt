package com.mrweasel.mtgscanner

import android.graphics.RectF
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import kotlin.math.abs

/**
 * Watches low-res preview frames, only inside the card box, and says when to take a photo:
 *  - a card is in the box (one solid patch that differs from the empty box),
 *  - no hand is on the box edge (a thumb still holding the card),
 *  - nothing has moved for [stableMs],
 *  - a hand has been in since the last photo (so a foil's sparkle or a light change never counts as a new
 *    card) and the picture really changed.
 * The box is shrunk to a 24 x 32 grid of average brightness; all the tests are on that grid.
 */
class CardWatcher(
    private val onCapture: () -> Unit,
    private val onInfo: (String, Boolean) -> Unit,      // text, hand in the box
) : ImageAnalysis.Analyzer {

    companion object {
        const val GW = 24
        const val GH = 32
        const val CELL_DIFF = 22f          // brightness change (0-255) that counts a grid cell as different
        const val PRESENT_FRAC = 0.20f     // this much of the box differs from the empty box → a card is there
        const val NEW_FRAC = 0.012f        // after a hand went past, this much change from the last photo = a new card
        const val RING_BUSY = 0.22f        // this much of the box's edge ring covered → a hand is in the way
        const val MOTION_MAX = 3.0f        // mean change between frames below this counts as still
        const val HAND_MOTION = 7.0f       // a frame changing this much means a hand is moving in the box
    }

    @Volatile var enabled = false
    @Volatile var stableMs = 450L
    @Volatile var box = RectF(0.2f, 0.2f, 0.8f, 0.75f)
        set(v) { field = v; setEmptyBed() }
    @Volatile private var busy = false

    private var prev: FloatArray? = null
    private var background: FloatArray? = null
    private var lastShot: FloatArray? = null
    private var stillSince = 0L
    private var handSeen = false
    private var firstShot = true
    @Volatile private var resetBackground = true

    fun setEmptyBed() { resetBackground = true; lastShot = null; handSeen = false; firstShot = true; prev = null }
    /** Start watching: re-learns the empty box first, so start with the box empty. */
    fun start() { setEmptyBed(); busy = false; enabled = true }
    fun pause() { enabled = false }
    /** Ready for the next photo (the last one is saved and there's room in the queue). */
    fun captureFinished() { busy = false }
    /** Manual shot: remember this frame so auto doesn't take the same card again. */
    fun markShot() { lastShot = prev?.copyOf(); handSeen = false; firstShot = false }

    override fun analyze(image: ImageProxy) {
        try {
            if (!enabled) { onInfo("Paused", false); return }
            val g = grid(image)
            val now = System.currentTimeMillis()
            val p = prev
            val motion = if (p == null) 99f else meanDiff(g, p)
            prev = g
            if (motion < MOTION_MAX) { if (stillSince == 0L) stillSince = now } else stillSince = 0L
            if (motion > HAND_MOTION && p != null) handSeen = true
            val stillFor = if (stillSince == 0L) 0L else now - stillSince

            if (resetBackground) {
                if (stillFor >= 800) { background = g.copyOf(); resetBackground = false; lastShot = null; handSeen = false; firstShot = true }
                onInfo("Learning the empty box… keep it empty and still", false)
                return
            }
            if (busy) { onInfo("Taking photo…", false); return }
            val bg = background ?: return
            if (bg.size != g.size) { setEmptyBed(); return }
            val off = exposureOffset(g, bg)
            val present = cardPresence(g, bg, off)
            val ring = ringCovered(g, bg, off)
            val change = lastShot?.let { fracDiffComp(g, it) } ?: 1f
            val cardThere = present >= PRESENT_FRAC
            val hand = ring >= RING_BUSY || motion > HAND_MOTION

            val state = when {
                !cardThere && ring < RING_BUSY -> "Waiting for a card"
                hand -> "Hand in the box"
                !cardThere -> "Waiting for a card"
                stillFor < stableMs -> "Hold still…"
                !(handSeen || firstShot) || change < NEW_FRAC -> "Same card · place the next one"
                else -> "capture"
            }
            onInfo(String.format("%s · card %.0f%% · edge %.0f%% · new %.1f%%", if (state == "capture") "Photo" else state,
                present * 100, ring * 100, change * 100), hand)
            if (state == "capture") {
                busy = true
                handSeen = false
                firstShot = false
                lastShot = g.copyOf()
                onCapture()
            }
        } finally {
            image.close()
        }
    }

    private var ringW = GW
    private var ringH = GH

    /** The box's brightness grid, sampled from the Y plane in the sensor's orientation. */
    private fun grid(image: ImageProxy): FloatArray {
        val plane = image.planes[0]
        val buf = plane.buffer
        val rowStride = plane.rowStride
        val pixStride = plane.pixelStride
        val rot = image.imageInfo.rotationDegrees
        val roi = BoxMath.toStored(box, image.width, image.height, rot)
        val (gx, gy) = if (rot == 90 || rot == 270) GH to GW else GW to GH
        val out = FloatArray(gx * gy)
        val cw = maxOf(1, roi.width() / gx); val ch = maxOf(1, roi.height() / gy)
        val step = maxOf(1, minOf(cw, ch) / 4)
        for (j in 0 until gy) for (i in 0 until gx) {
            var sum = 0; var n = 0
            var y = roi.top + j * ch
            val yEnd = minOf(roi.top + (j + 1) * ch, image.height)
            while (y < yEnd) {
                val row = y * rowStride
                var x = roi.left + i * cw
                val xEnd = minOf(roi.left + (i + 1) * cw, image.width)
                while (x < xEnd) {
                    sum += buf.get(row + x * pixStride).toInt() and 0xFF
                    n++
                    x += step
                }
                y += step
            }
            out[j * gx + i] = if (n > 0) sum.toFloat() / n else 0f
        }
        ringW = gx; ringH = gy
        return out
    }

    private fun ringIndices(): List<Int> {
        val w = ringW; val h = ringH
        val r = ArrayList<Int>(2 * (w + h))
        for (x in 0 until w) { r.add(x); r.add((h - 1) * w + x) }
        for (y in 1 until h - 1) { r.add(y * w); r.add(y * w + w - 1) }
        return r
    }

    /** Brightness shift (auto-exposure) between two frames, from the box's edge ring where the card doesn't sit. */
    private fun exposureOffset(a: FloatArray, b: FloatArray): Float {
        val d = ringIndices().map { a[it] - b[it] }.sorted()
        return d[d.size / 2].coerceIn(-40f, 40f)
    }

    private fun ringCovered(g: FloatArray, bg: FloatArray, off: Float): Float {
        val ring = ringIndices()
        return ring.count { abs(g[it] - bg[it] - off) > CELL_DIFF }.toFloat() / ring.size
    }

    private fun fracDiffComp(a: FloatArray, b: FloatArray): Float {
        if (a.size != b.size) return 1f
        val off = exposureOffset(a, b)
        var n = 0
        for (i in a.indices) if (abs(a[i] - b[i] - off) > CELL_DIFF) n++
        return n.toFloat() / a.size
    }

    /** Share of the box covered by a card: the cells that differ from the empty box must form one solid patch
     *  (at least 45% of their bounding box), so glare or shadows don't count. */
    private fun cardPresence(g: FloatArray, bg: FloatArray, off: Float): Float {
        val w = ringW; val h = ringH
        var n = 0; var x0 = w; var x1 = -1; var y0 = h; var y1 = -1
        for (y in 0 until h) for (x in 0 until w) {
            val i = y * w + x
            if (abs(g[i] - bg[i] - off) > CELL_DIFF) {
                n++
                if (x < x0) x0 = x
                if (x > x1) x1 = x
                if (y < y0) y0 = y
                if (y > y1) y1 = y
            }
        }
        if (n == 0) return 0f
        val area = (x1 - x0 + 1) * (y1 - y0 + 1)
        return if (n.toFloat() / area >= 0.45f) n.toFloat() / g.size else 0f
    }

    private fun meanDiff(a: FloatArray, b: FloatArray): Float {
        if (a.size != b.size) return 99f
        var s = 0f
        for (i in a.indices) s += abs(a[i] - b[i])
        return s / a.size
    }
}
