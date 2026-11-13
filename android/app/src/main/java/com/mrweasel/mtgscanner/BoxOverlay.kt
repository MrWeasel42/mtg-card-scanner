package com.mrweasel.mtgscanner

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import kotlin.math.hypot

/**
 * Draws the card box over the camera picture and, in edit mode, lets you drag its corners (or the whole box)
 * onto the stand's card pocket. The picture is shown "fit" (whole frame visible, 3:4 portrait), so the box is
 * stored as fractions of that picture and maps straight onto the camera frames.
 */
class BoxOverlay @JvmOverloads constructor(ctx: Context, attrs: AttributeSet? = null) : View(ctx, attrs) {

    var box = RectF(0.2f, 0.2f, 0.8f, 0.75f)
        set(v) { field = v; invalidate() }
    var editing = false
        set(v) { field = v; invalidate() }
    var handInBox = false
        set(v) { if (field != v) { field = v; postInvalidate() } }
    var onChanged: ((RectF) -> Unit)? = null

    private val dp = resources.displayMetrics.density
    private val shade = Paint().apply { color = Color.argb(110, 0, 0, 0) }
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 2.5f * dp }
    private val knob = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; textSize = 15f * dp; textAlign = Paint.Align.CENTER }

    /** Where the 3:4 camera picture sits inside this view. */
    private fun content(): RectF {
        val w = width.toFloat(); val h = height.toFloat()
        val aspect = 3f / 4f
        return if (w / h > aspect) { val cw = h * aspect; RectF((w - cw) / 2, 0f, (w + cw) / 2, h) }
        else { val ch = w / aspect; RectF(0f, (h - ch) / 2, w, (h + ch) / 2) }
    }

    private fun screenBox(): RectF {
        val c = content()
        return RectF(c.left + box.left * c.width(), c.top + box.top * c.height(), c.left + box.right * c.width(), c.top + box.bottom * c.height())
    }

    override fun onDraw(canvas: Canvas) {
        val b = screenBox()
        canvas.drawRect(0f, 0f, width.toFloat(), b.top, shade)
        canvas.drawRect(0f, b.bottom, width.toFloat(), height.toFloat(), shade)
        canvas.drawRect(0f, b.top, b.left, b.bottom, shade)
        canvas.drawRect(b.right, b.top, width.toFloat(), b.bottom, shade)
        line.color = when { editing -> Color.WHITE; handInBox -> Color.rgb(240, 160, 40); else -> Color.rgb(43, 179, 163) }
        canvas.drawRect(b, line)
        if (editing) {
            for ((x, y) in listOf(b.left to b.top, b.right to b.top, b.left to b.bottom, b.right to b.bottom)) canvas.drawCircle(x, y, 9 * dp, knob)
            canvas.drawText("Drag the corners onto the card pocket", b.centerX(), b.centerY(), text)
            canvas.drawText("(a little bigger than the card)", b.centerX(), b.centerY() + 20 * dp, text)
        }
    }

    private var drag = -1          // 0..3 corner, 4 = move, -1 none
    private var lastX = 0f; private var lastY = 0f

    override fun onTouchEvent(e: MotionEvent): Boolean {
        if (!editing) return false
        val c = content(); val b = screenBox()
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                val corners = listOf(b.left to b.top, b.right to b.top, b.left to b.bottom, b.right to b.bottom)
                val near = corners.withIndex().minByOrNull { (_, p) -> hypot(e.x - p.first, e.y - p.second) }!!
                drag = if (hypot(e.x - near.value.first, e.y - near.value.second) < 40 * dp) near.index else if (b.contains(e.x, e.y)) 4 else -1
                lastX = e.x; lastY = e.y
            }
            MotionEvent.ACTION_MOVE -> {
                if (drag < 0) return true
                val u = ((e.x - c.left) / c.width()).coerceIn(0f, 1f)
                val v = ((e.y - c.top) / c.height()).coerceIn(0f, 1f)
                val nb = RectF(box)
                when (drag) {
                    0 -> { nb.left = u; nb.top = v }
                    1 -> { nb.right = u; nb.top = v }
                    2 -> { nb.left = u; nb.bottom = v }
                    3 -> { nb.right = u; nb.bottom = v }
                    4 -> {
                        val du = (e.x - lastX) / c.width(); val dv = (e.y - lastY) / c.height()
                        val mu = du.coerceIn(-nb.left, 1f - nb.right); val mv = dv.coerceIn(-nb.top, 1f - nb.bottom)
                        nb.offset(mu, mv)
                    }
                }
                lastX = e.x; lastY = e.y
                if (nb.width() > 0.08f && nb.height() > 0.08f) box = RectF(minOf(nb.left, nb.right), minOf(nb.top, nb.bottom), maxOf(nb.left, nb.right), maxOf(nb.top, nb.bottom))
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> { if (drag >= 0) onChanged?.invoke(box); drag = -1 }
        }
        return true
    }
}
