package com.mrweasel.mtgscanner

import android.Manifest
import android.annotation.SuppressLint
import android.content.ContentValues
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapRegionDecoder
import android.graphics.Matrix
import android.graphics.RectF
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.util.Size
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.WindowManager
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.FocusMeteringAction
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.exifinterface.media.ExifInterface
import androidx.lifecycle.lifecycleScope
import com.google.android.material.button.MaterialButton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.Locale
import java.util.concurrent.Executors

/**
 * Phone scanner for the MTG Card Scanner PC app. The phone is only the camera: inside a scan session it takes a
 * photo of the card box each time a new card is placed, sends it to the PC, and shows what the PC found.
 *  - Nothing is taken while the PC isn't connected, and at most 2 photos ever wait to be sent (kept in memory
 *    only), so there is never a backlog. Stop (here or on the PC) ends the session and drops anything waiting.
 *  - Only the card box is sent, cropped and cut down to 2,400 px: faster to send and easier for the PC to read.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var preview: PreviewView
    private lateinit var overlay: BoxOverlay
    private lateinit var status: TextView
    private lateinit var watchText: TextView
    private lateinit var resultName: TextView
    private lateinit var resultDetail: TextView
    private lateinit var history: TextView
    private lateinit var btnStart: MaterialButton

    private val prefs by lazy { getSharedPreferences("scanner", Context.MODE_PRIVATE) }
    private val link by lazy { PcLink(this) }
    private val analysisExec = Executors.newSingleThreadExecutor()
    private var camera: Camera? = null
    private var imageCapture: ImageCapture? = null
    private lateinit var watcher: CardWatcher

    @Volatile private var pc: PcLink.Pc? = null
    @Volatile private var session = false          // a scan session is open on the PC
    @Volatile private var generation = 0           // bumps on Stop: anything still queued from before is dropped
    private val queue = Channel<Pair<Int, ByteArray>>(Channel.UNLIMITED)
    @Volatile private var waiting = 0
    private val maxWaiting = 2
    private var sent = 0
    private var lastScan: String? = null
    private var misses = 0
    private val beeper by lazy { ToneGenerator(AudioManager.STREAM_NOTIFICATION, 90) }

    private val askCamera = registerForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        if (ok) startCamera() else status.text = "The camera permission is needed to scan cards."
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.root)) { v, insets ->
            val b = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            v.setPadding(b.left, b.top, b.right, b.bottom)
            insets
        }
        preview = findViewById(R.id.preview)
        overlay = findViewById(R.id.box)
        status = findViewById(R.id.status)
        watchText = findViewById(R.id.watch)
        resultName = findViewById(R.id.resultName)
        resultDetail = findViewById(R.id.resultDetail)
        history = findViewById(R.id.history)
        btnStart = findViewById(R.id.btnStart)
        cacheDir.listFiles()?.filter { it.name.startsWith("scan_") }?.forEach { it.delete() }   // nothing carries over
        File(filesDir, "pending").deleteRecursively()                                            // old builds' backlog

        watcher = CardWatcher(
            onCapture = { runOnUiThread { takePhoto() } },
            onInfo = { t, hand -> runOnUiThread { watchText.text = t; overlay.handInBox = hand } },
        )
        watcher.stableMs = prefs.getLong("stableMs", 450L)
        val saved = loadBox()
        overlay.box = saved
        watcher.box = saved
        overlay.onChanged = { b -> saveBox(b); watcher.box = RectF(b) }
        if (!prefs.contains("box_l")) overlay.editing = true     // first run: ask for the box straight away

        btnStart.setOnClickListener { if (watcher.enabled) pauseWatching("Paused") else startOrResume() }
        findViewById<MaterialButton>(R.id.btnShoot).setOnClickListener {
            if (!session || pc == null) { toast("Press Start first (connected to the PC)"); return@setOnClickListener }
            watcher.markShot(); takePhoto()
        }
        findViewById<MaterialButton>(R.id.btnUndo).setOnClickListener { undoLast() }
        findViewById<MaterialButton>(R.id.btnStop).setOnClickListener { stopSession(tellPc = true, why = "Stopped.") }
        findViewById<MaterialButton>(R.id.btnMore).setOnClickListener { showSettings() }
        setupGestures()
        updateButtons()

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) startCamera()
        else askCamera.launch(Manifest.permission.CAMERA)

        lifecycleScope.launch { connectionLoop() }
        lifecycleScope.launch { senderLoop() }
        lifecycleScope.launch { statusLoop() }
    }

    override fun onStop() {
        super.onStop()
        // leaving the app pauses scanning; nothing keeps running in the background
        if (watcher.enabled) pauseWatching("Paused (app was in the background)")
    }

    private fun toast(t: String) = Toast.makeText(this, t, Toast.LENGTH_SHORT).show()

    private fun updateButtons() { btnStart.text = if (watcher.enabled) "⏸ Pause" else if (session) "▶ Resume" else "▶ Start" }

    // ---------------------------------------------------------------- card box

    private fun loadBox() = RectF(prefs.getFloat("box_l", 0.2f), prefs.getFloat("box_t", 0.2f),
        prefs.getFloat("box_r", 0.8f), prefs.getFloat("box_b", 0.75f))

    private fun saveBox(b: RectF) {
        prefs.edit().putFloat("box_l", b.left).putFloat("box_t", b.top).putFloat("box_r", b.right).putFloat("box_b", b.bottom).apply()
    }

    // ---------------------------------------------------------------- session

    private fun startOrResume() {
        val target = pc ?: run { toast("Not connected to the PC yet"); return }
        if (overlay.editing) { overlay.editing = false; saveBox(overlay.box); watcher.box = RectF(overlay.box) }
        lifecycleScope.launch {
            val ok = withContext(Dispatchers.IO) {
                try {
                    val st = link.status(target)
                    if (session && st.active && !st.stop) link.resumeSession(target) else link.startSession(target)
                    true
                } catch (_: Exception) { false }
            }
            if (!ok) { toast("The PC didn't answer"); return@launch }
            if (!session) { sent = 0; lastScan = null; history.text = "" }
            session = true
            watcher.start()
            resultName.text = "Scanning"
            resultDetail.text = "Keep the box empty for a second, then place cards one at a time and let go of each."
            updateButtons()
            showConnected()
        }
    }

    private fun pauseWatching(why: String) {
        watcher.pause()
        watchText.text = why
        updateButtons()
    }

    /** Ends the session: stops the camera watching, drops anything waiting, clears the list. */
    private fun stopSession(tellPc: Boolean, why: String) {
        watcher.pause()
        val had = session
        session = false
        generation++
        waiting = 0
        val target = pc
        if (tellPc && had && target != null) lifecycleScope.launch(Dispatchers.IO) { try { link.stopSession(target) } catch (_: Exception) {} }
        resultName.text = why
        resultDetail.text = if (sent > 0) "$sent card${if (sent == 1) "" else "s"} sent this session. Press Start for a new one." else "Press Start to scan."
        history.text = ""
        lastScan = null
        updateButtons()
        showConnected()
    }

    private fun undoLast() {
        val scan = lastScan ?: run { toast("Nothing to undo"); return }
        val target = pc ?: run { toast("Not connected"); return }
        lifecycleScope.launch {
            val err = withContext(Dispatchers.IO) { try { link.undo(target, scan) } catch (e: Exception) { e.message ?: "failed" } }
            if (err == null) {
                sent = maxOf(0, sent - 1)
                lastScan = null
                history.text = history.text.lines().drop(1).joinToString("\n")
                resultName.text = "↶ Removed $scan"
                resultDetail.text = "Place the card again, or the next one."
                watcher.markShot()
                showConnected()
            } else toast(err)
        }
    }

    // ---------------------------------------------------------------- camera

    private fun startCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            val provider = future.get()
            val ratio43 = AspectRatioStrategy.RATIO_4_3_FALLBACK_AUTO_STRATEGY
            val pv = Preview.Builder()
                .setResolutionSelector(ResolutionSelector.Builder().setAspectRatioStrategy(ratio43).build())
                .build().also { it.setSurfaceProvider(preview.surfaceProvider) }
            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                .setResolutionSelector(ResolutionSelector.Builder().setAspectRatioStrategy(ratio43)
                    .setResolutionStrategy(ResolutionStrategy.HIGHEST_AVAILABLE_STRATEGY).build())
                .setJpegQuality(95)
                .build()
            val analysis = ImageAnalysis.Builder()
                .setResolutionSelector(ResolutionSelector.Builder().setAspectRatioStrategy(ratio43).setResolutionStrategy(
                    ResolutionStrategy(Size(640, 480), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER)).build())
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
            analysis.setAnalyzer(analysisExec, watcher)
            try {
                provider.unbindAll()
                camera = provider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, pv, imageCapture, analysis)
                camera?.cameraControl?.setZoomRatio(prefs.getFloat("zoom", 1f))
                camera?.cameraControl?.enableTorch(prefs.getBoolean("torch", false))
            } catch (e: Exception) {
                status.text = "Camera error: ${e.message}"
            }
        }, ContextCompat.getMainExecutor(this))
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun setupGestures() {
        val scale = ScaleGestureDetector(this, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScale(d: ScaleGestureDetector): Boolean {
                val cam = camera ?: return true
                val z = cam.cameraInfo.zoomState.value ?: return true
                val r = (z.zoomRatio * d.scaleFactor).coerceIn(z.minZoomRatio, z.maxZoomRatio)
                cam.cameraControl.setZoomRatio(r)
                prefs.edit().putFloat("zoom", r).apply()
                return true
            }
        })
        preview.setOnTouchListener { _, ev ->
            scale.onTouchEvent(ev)
            if (ev.action == MotionEvent.ACTION_UP && !scale.isInProgress) {
                val pt = preview.meteringPointFactory.createPoint(ev.x, ev.y)
                camera?.cameraControl?.startFocusAndMetering(FocusMeteringAction.Builder(pt).build())
            }
            true
        }
    }

    private fun takePhoto() {
        val ic = imageCapture
        if (ic == null || !session || pc == null) { watcher.captureFinished(); return }
        val gen = generation
        val file = File(cacheDir, "scan_${System.currentTimeMillis()}.jpg")
        ic.takePicture(ImageCapture.OutputFileOptions.Builder(file).build(), ContextCompat.getMainExecutor(this),
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    lifecycleScope.launch {
                        val jpeg = withContext(Dispatchers.Default) {
                            try { cropToBox(file) } catch (e: Exception) { null } finally { file.delete() }
                        }
                        if (jpeg == null || gen != generation) { watcher.captureFinished(); return@launch }
                        if (prefs.getBoolean("keepCopy", false)) withContext(Dispatchers.IO) { saveCopyToGallery(jpeg) }
                        waiting++
                        queue.trySend(gen to jpeg)
                        if (waiting < maxWaiting) watcher.captureFinished()
                        resultName.text = "📷 Photo taken"
                        resultDetail.text = "Sending to ${pc?.name ?: "the PC"}…"
                        showConnected()
                    }
                }
                override fun onError(e: ImageCaptureException) {
                    file.delete()
                    watcher.captureFinished()
                    toast("Photo failed: ${e.message}")
                }
            })
    }

    /** The card box (plus 6% each way) from the full photo, turned upright, at most 2,400 px tall. */
    private fun cropToBox(file: File): ByteArray {
        val rot = ExifInterface(file.absolutePath).rotationDegrees
        @Suppress("DEPRECATION")
        val dec = BitmapRegionDecoder.newInstance(file.absolutePath, false)!!
        val r = BoxMath.toStored(RectF(overlay.box), dec.width, dec.height, rot, margin = 0.06f)
        var bmp = dec.decodeRegion(r, null)
        dec.recycle()
        if (rot != 0) {
            val m = Matrix().apply { postRotate(rot.toFloat()) }
            val turned = Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, m, true)
            if (turned !== bmp) bmp.recycle()
            bmp = turned
        }
        val long = maxOf(bmp.width, bmp.height)
        if (long > 2400) {
            val s = 2400f / long
            val small = Bitmap.createScaledBitmap(bmp, (bmp.width * s).toInt(), (bmp.height * s).toInt(), true)
            if (small !== bmp) bmp.recycle()
            bmp = small
        }
        val out = ByteArrayOutputStream()
        bmp.compress(Bitmap.CompressFormat.JPEG, 92, out)
        bmp.recycle()
        return out.toByteArray()
    }

    private fun saveCopyToGallery(jpeg: ByteArray) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return
        try {
            val values = ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, "scan_${System.currentTimeMillis()}.jpg")
                put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/MTG Scans")
            }
            val uri = contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: return
            contentResolver.openOutputStream(uri)?.use { it.write(jpeg) }
        } catch (_: Exception) {}
    }

    // ---------------------------------------------------------------- PC link

    @Suppress("DEPRECATION")
    private fun phoneIp(): String = try {
        val ip = (applicationContext.getSystemService(Context.WIFI_SERVICE) as android.net.wifi.WifiManager).connectionInfo.ipAddress
        if (ip == 0) "not on Wi-Fi" else "${ip and 255}.${ip shr 8 and 255}.${ip shr 16 and 255}.${ip shr 24 and 255}"
    } catch (_: Exception) { "?" }

    private suspend fun connectionLoop() {
        while (lifecycleScope.isActive) {
            if (pc == null) {
                if (misses < 2) withContext(Dispatchers.Main) { status.text = "Looking for the PC… (PC app: ⚙ Settings → Phone link)" }
                val manual = prefs.getString("host", "")!!.trim()
                val found = withContext(Dispatchers.IO) {
                    if (manual.isNotEmpty()) {
                        val (h, p) = manual.split(":").let { it[0] to (it.getOrNull(1)?.toIntOrNull() ?: 8770) }
                        link.hello(h, p)?.let { PcLink.Pc(h, p, it) }
                    } else link.discover()?.let { d -> link.hello(d.host, d.port)?.let { d.copy(name = it) } }
                }
                if (found != null) {
                    misses = 0
                    pc = found
                    withContext(Dispatchers.Main) { showConnected() }
                } else {
                    misses++
                    if (misses >= 2) withContext(Dispatchers.Main) {
                        status.text = if (manual.isNotEmpty()) "Can't reach the PC at $manual. Is the PC app's Phone link on?"
                        else "PC not found (this phone: ${phoneIp()}). Turn on Phone link in the PC app, or type the PC's address in ⚙."
                    }
                    delay(4000)
                }
            } else delay(3000)
        }
    }

    /** While a session is open, pick up Pause / Stop pressed on the PC. */
    private suspend fun statusLoop() {
        while (lifecycleScope.isActive) {
            delay(2000)
            val target = pc ?: continue
            if (!session) continue
            val st = withContext(Dispatchers.IO) { try { link.status(target) } catch (_: Exception) { null } } ?: continue
            if (st.stop || !st.active) stopSession(tellPc = false, why = "Stopped on the PC.")
            else if (st.paused && watcher.enabled) pauseWatching("Paused on the PC · press Resume to carry on")
        }
    }

    private fun showConnected() {
        val p = pc ?: return
        status.text = "✅ ${p.name} (${p.host})" + (if (session) " · $sent sent" else " · press Start") +
            (if (waiting > 0) " · $waiting waiting" else "")
    }

    private suspend fun senderLoop() {
        for ((gen, jpeg) in queue) {
            while (gen == generation) {
                val target = pc
                if (target == null) { delay(1000); continue }
                val reply = withContext(Dispatchers.IO) { try { link.send(target, jpeg) } catch (_: Exception) { null } }
                if (reply == null) {
                    pc = null    // lost the PC: stop taking photos; what's waiting (2 at most) goes when it's back
                    if (watcher.enabled) pauseWatching("Lost the PC · press Resume when it's back")
                    status.text = "PC not answering · reconnecting…"
                    delay(1500)
                    continue
                }
                if (gen == generation) handleReply(reply)
                break
            }
            waiting = maxOf(0, waiting - 1)
            if (waiting < maxWaiting) watcher.captureFinished()
            showConnected()
        }
    }

    private fun handleReply(r: PcLink.ScanReply) {
        val beep = prefs.getBoolean("beep", true)
        when {
            r.stop -> { stopSession(tellPc = false, why = "Stopped on the PC."); return }
            r.paused -> { pauseWatching("Paused on the PC · press Resume to carry on"); return }
            r.noCard -> {
                resultName.text = "No card in that photo"
                resultDetail.text = "Skipped: nothing was added on the PC."
                return
            }
            !r.ok || r.name == null -> {
                resultName.text = "⚠ ${r.error ?: "Couldn't read that one"}"
                resultDetail.text = "Check it on the PC."
                if (beep) beeper.startTone(ToneGenerator.TONE_SUP_ERROR, 300)
                return
            }
        }
        sent = if (r.count > 0) r.count else sent + 1
        lastScan = r.scan
        val check = !r.pinned || r.finishUnsure
        val setLine = listOfNotNull(r.setCode, r.number?.let { "#$it" }).joinToString(" ")
        val price = r.price?.let { String.format(Locale.US, " · $%.2f", it) } ?: ""
        resultName.text = (if (check) "⚠ " else "✓ ") + r.name
        resultDetail.text = buildString {
            append("${r.set ?: ""} ($setLine)")
            r.finish?.let { append(" · $it") }
            append(price)
            append("\n")
            append(
                when {
                    r.sameAsLast -> "Same printing as the last card. Tap Undo if it was taken twice."
                    !r.pinned -> "Not sure: verify it on the PC"
                    r.finishUnsure -> "Check the finish on the PC (foil?)"
                    else -> "📌 ${r.pinReason ?: "pinned"}"
                }
            )
        }
        if (beep) {
            if (check || r.sameAsLast) beeper.startTone(ToneGenerator.TONE_PROP_NACK, 250) else beeper.startTone(ToneGenerator.TONE_PROP_ACK, 150)
        }
        val lines = (listOf((if (check) "⚠ " else "✓ ") + "${r.name}  $setLine" + if (r.sameAsLast) "  (same as last)" else "") +
            history.text.lines()).filter { it.isNotBlank() }.take(40)
        history.text = lines.joinToString("\n")
    }

    // ---------------------------------------------------------------- settings

    private fun showSettings() {
        val pad = (16 * resources.displayMetrics.density).toInt()
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad / 2, pad, 0) }
        val hostLabel = TextView(this).apply { text = "PC address (leave blank to find it automatically)" }
        val host = EditText(this).apply { hint = "e.g. 192.168.1.20"; setText(prefs.getString("host", "")); isSingleLine = true }
        val keep = CheckBox(this).apply { text = "Also keep each photo in Pictures/MTG Scans"; isChecked = prefs.getBoolean("keepCopy", false) }
        val beep = CheckBox(this).apply { text = "Beep on each result"; isChecked = prefs.getBoolean("beep", true) }
        val torch = CheckBox(this).apply { text = "Phone flashlight on (can cause glare)"; isChecked = prefs.getBoolean("torch", false) }
        val stableLabel = TextView(this).apply { text = "Wait before each photo (ms): longer if photos come out blurry" }
        val stable = EditText(this).apply {
            setText(prefs.getLong("stableMs", 450L).toString()); inputType = android.text.InputType.TYPE_CLASS_NUMBER
        }
        val tips = TextView(this).apply {
            text = "\nEdit card box: drag it over the stand's card pocket, a little bigger than the card. Only what's " +
                "inside the box is watched and sent. Pinch to zoom, tap to focus. Let go of each card before the photo."
            textSize = 12f
        }
        listOf(hostLabel, host, keep, beep, torch, stableLabel, stable, tips).forEach { box.addView(it) }
        AlertDialog.Builder(this)
            .setTitle("Settings · v${packageManager.getPackageInfo(packageName, 0).versionName}")
            .setView(box)
            .setPositiveButton("Save") { _, _ ->
                val newHost = host.text.toString().trim()
                if (newHost != prefs.getString("host", "")) pc = null
                prefs.edit()
                    .putString("host", newHost)
                    .putBoolean("keepCopy", keep.isChecked)
                    .putBoolean("beep", beep.isChecked)
                    .putBoolean("torch", torch.isChecked)
                    .putLong("stableMs", stable.text.toString().toLongOrNull()?.coerceIn(200, 5000) ?: 450L)
                    .apply()
                watcher.stableMs = prefs.getLong("stableMs", 450L)
                camera?.cameraControl?.enableTorch(torch.isChecked)
            }
            .setNeutralButton("Edit card box") { _, _ ->
                pauseWatching("Editing the card box · press Start when done")
                overlay.editing = true
            }
            .setNegativeButton("Close", null)
            .show()
    }

    override fun onDestroy() {
        super.onDestroy()
        analysisExec.shutdown()
        beeper.release()
    }
}
