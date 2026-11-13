package com.mrweasel.mtgscanner

import android.graphics.Rect
import android.graphics.RectF

/**
 * The card box is stored as fractions (0..1) of the upright (portrait) camera picture. Camera buffers and saved
 * JPEGs are in the sensor's orientation, turned by [rotation] degrees clockwise to be upright. This maps the box
 * into a stored image of [w] x [h] pixels.
 */
object BoxMath {
    fun toStored(box: RectF, w: Int, h: Int, rotation: Int, margin: Float = 0f): Rect {
        val b = RectF(
            (box.left - margin * box.width()).coerceIn(0f, 1f), (box.top - margin * box.height()).coerceIn(0f, 1f),
            (box.right + margin * box.width()).coerceIn(0f, 1f), (box.bottom + margin * box.height()).coerceIn(0f, 1f),
        )
        val rot = ((rotation % 360) + 360) % 360
        val (wu, hu) = if (rot == 90 || rot == 270) h to w else w to h
        fun map(u: Float, v: Float): Pair<Float, Float> {
            val xu = u * wu; val yu = v * hu
            return when (rot) {
                90 -> yu to (h - xu)
                180 -> (w - xu) to (h - yu)
                270 -> (w - yu) to xu
                else -> xu to yu
            }
        }
        val p1 = map(b.left, b.top); val p2 = map(b.right, b.bottom)
        val l = minOf(p1.first, p2.first).toInt().coerceIn(0, w - 1)
        val r = maxOf(p1.first, p2.first).toInt().coerceIn(l + 1, w)
        val t = minOf(p1.second, p2.second).toInt().coerceIn(0, h - 1)
        val btm = maxOf(p1.second, p2.second).toInt().coerceIn(t + 1, h)
        return Rect(l, t, r, btm)
    }
}
