package com.mrweasel.mtgscanner

import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import kotlin.math.abs

/**
 * Watches low-res preview frames and says when to take a photo: a card is on the bed (the frame differs from
 * the empty bed), nothing has moved for [stableMs], and it isn't the card we already took (works whether you
 * swap cards or stack the next one on top, like the TCG Archivist stand).
 *
 * Each frame is shrunk to a 40 x 30 grid of average brightness; all the tests are on that grid.
 */
class CardWatcher(
    private val onCapture: () -> Unit,
    private val onInfo: (String) -> Unit,
) : ImageAnalysis.Analyzer {

    companion object {
        const val GW = 40
        const val GH = 30
        const val CELL_DIFF = 22f        // brightness change (0-255) that counts a grid cell as "different"
        const val PRESENT_FRAC = 0.06f   // this much of the frame differs from the empty bed → a card is there
        const val NEW_FRAC = 0.05f       // this much differs from the last photo → it's a new card, even with no hand seen
        const val NEW_FRAC_AFTER_HAND = 0.012f  // after a hand went past, a much smaller change counts (similar-looking cards)
        const val MOTION_MAX = 3.0f      // mean change between frames below this counts as still
        const val HAND_MOTION = 7.0f     // a frame changing this much means a hand is swapping the card
    }

    @Volatile var enabled = false   // starts paused: press Start with the bed clear
    @Volatile var stableMs = 600L
    @Volatile private var busy = false

    private var prev: FloatArray? = null
    private var background: FloatArray? = null
    private var lastShot: FloatArray? = null
    private var stillSince = 0L
    private var handSeen = false
    private var bgCandidateSince = 0L
    @Volatile private var resetBackground = true

    /** Next still frame becomes the empty-bed picture. */
    fun setEmptyBed() { resetBackground = true; lastShot = null; handSeen = false }

    /** Start watching: re-learns the empty bed first, so start with the bed clear. */
    fun start() { setEmptyBed(); enabled = true }
    fun pause() { enabled = false }

    /** The photo is done (sent or saved): watch for the next card. */
    fun captureFinished() { busy = false }

    /** Manual shot: remember this frame so auto doesn't take the same card again. */
    fun markShot() { lastShot = prev?.copyOf(); handSeen = false }

    override fun analyze(image: ImageProxy) {
        try {
            val g = grid(image)
            val now = System.currentTimeMillis()
            val p = prev
            val motion = if (p == null) 99f else meanDiff(g, p)
            prev = g
            if (motion < MOTION_MAX) { if (stillSince == 0L) stillSince = now } else stillSince = 0L
            if (motion > HAND_MOTION && p != null) handSeen = true
            val stillFor = if (stillSince == 0L) 0L else now - stillSince

            if (!enabled) { onInfo("Paused · clear the bed and press Start"); return }
            if (resetBackground) {
                if (stillFor >= 800) { background = g.copyOf(); resetBackground = false; lastShot = null }
                onInfo("Learning the empty bed… keep it clear and still")
                return
            }
            val bg = background ?: return
            val present = cardPresence(g, bg)
            val change = lastShot?.let { fracDiffComp(g, it) } ?: 1f
            val cardThere = present >= PRESENT_FRAC
            if (!cardThere) lastShot = null
            val isNew = change >= NEW_FRAC || (handSeen && change >= NEW_FRAC_AFTER_HAND)

            val state = when {
                busy -> "taking photo…"
                !cardThere -> "waiting for a card"
                stillFor < stableMs -> "card moving"
                !isNew -> "same card — place the next one"
                else -> "capture"
            }
            onInfo(String.format("%s · card %.0f%% · new %.1f%% · motion %.1f%s", state, present * 100, change * 100, motion, if (handSeen) " · hand" else ""))
            if (state == "capture") {
                busy = true
                handSeen = false
                lastShot = g.copyOf()
                onCapture()
            }
        } finally {
            image.close()
        }
    }

    private fun grid(image: ImageProxy): FloatArray {
        val plane = image.planes[0]          // Y (brightness)
        val buf = plane.buffer
        val rowStride = plane.rowStride
        val pixStride = plane.pixelStride
        val w = image.width; val h = image.height
        val out = FloatArray(GW * GH)
        val cw = w / GW; val ch = h / GH
        val step = 4
        for (gy in 0 until GH) for (gx in 0 until GW) {
            var sum = 0; var n = 0
            var y = gy * ch
            while (y < (gy + 1) * ch) {
                var x = gx * cw
                val row = y * rowStride
                while (x < (gx + 1) * cw) {
                    sum += buf.get(row + x * pixStride).toInt() and 0xFF
                    n++
                    x += step
                }
                y += step
            }
            out[gy * GW + gx] = if (n > 0) sum.toFloat() / n else 0f
        }
        return out
    }

    private fun meanDiff(a: FloatArray, b: FloatArray): Float {
        var s = 0f
        for (i in a.indices) s += abs(a[i] - b[i])
        return s / a.size
    }

    /** Brightness shift between two frames from the outer ring of cells (where a card rarely sits), so the camera's
     *  auto-exposure drifting doesn't look like a card. */
    private fun exposureOffset(a: FloatArray, b: FloatArray): Float {
        val d = ArrayList<Float>(2 * (GW + GH))
        for (x in 0 until GW) { d.add(a[x] - b[x]); d.add(a[(GH - 1) * GW + x] - b[(GH - 1) * GW + x]) }
        for (y in 1 until GH - 1) { d.add(a[y * GW] - b[y * GW]); d.add(a[y * GW + GW - 1] - b[y * GW + GW - 1]) }
        d.sort()
        return d[d.size / 2].coerceIn(-40f, 40f)
    }

    private fun fracDiffComp(a: FloatArray, b: FloatArray): Float {
        val off = exposureOffset(a, b)
        var n = 0
        for (i in a.indices) if (abs(a[i] - b[i] - off) > CELL_DIFF) n++
        return n.toFloat() / a.size
    }

    /** Share of the frame covered by a card: the cells that differ from the empty bed must form one solid patch
     *  (at least 45% of their bounding box), so scattered glare or shadows on the desk don't count. */
    private fun cardPresence(g: FloatArray, bg: FloatArray): Float {
        val off = exposureOffset(g, bg)
        var n = 0; var x0 = GW; var x1 = -1; var y0 = GH; var y1 = -1
        for (y in 0 until GH) for (x in 0 until GW) {
            val i = y * GW + x
            if (abs(g[i] - bg[i] - off) > CELL_DIFF) {
                n++
                if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y
            }
        }
        if (n == 0) return 0f
        val box = (x1 - x0 + 1) * (y1 - y0 + 1)
        return if (n.toFloat() / box >= 0.45f) n.toFloat() / g.size else 0f
    }

    private fun fracDiff(a: FloatArray, b: FloatArray): Float {
        var n = 0
        for (i in a.indices) if (abs(a[i] - b[i]) > CELL_DIFF) n++
        return n.toFloat() / a.size
    }
}
