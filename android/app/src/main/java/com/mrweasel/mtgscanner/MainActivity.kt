package com.mrweasel.mtgscanner

import android.Manifest
import android.annotation.SuppressLint
import android.content.ContentValues
import android.content.Context
import android.content.pm.PackageManager
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
import androidx.lifecycle.lifecycleScope
import com.google.android.material.button.MaterialButton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors

/**
 * Phone scanner for the MTG Card Scanner desktop app. The phone is only the camera: each photo goes to the PC
 * over Wi-Fi and the PC identifies it (same recognizer, logs and review pages as dropped-in photos).
 * If the PC can't be reached, photos wait on the phone and go as soon as it's back.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var preview: PreviewView
    private lateinit var status: TextView
    private lateinit var watchText: TextView
    private lateinit var resultName: TextView
    private lateinit var resultDetail: TextView
    private lateinit var history: TextView
    private lateinit var btnAuto: MaterialButton

    private val prefs by lazy { getSharedPreferences("scanner", Context.MODE_PRIVATE) }
    private val link by lazy { PcLink(this) }
    private val analysisExec = Executors.newSingleThreadExecutor()
    private var camera: Camera? = null
    private var imageCapture: ImageCapture? = null
    private lateinit var watcher: CardWatcher

    @Volatile private var pc: PcLink.Pc? = null
    private val queue = Channel<File>(Channel.UNLIMITED)
    private val queued = HashSet<String>()
    private var shots = 0
    private var sent = 0
    private val beeper by lazy { ToneGenerator(AudioManager.STREAM_NOTIFICATION, 90) }
    private val pendingDir by lazy { File(filesDir, "pending").apply { mkdirs() } }

    private val askCamera = registerForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        if (ok) startCamera() else status.text = "The camera permission is needed to scan cards."
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        // Android 15 draws apps under the status and navigation bars: keep the panels and buttons clear of them
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.root)) { v, insets ->
            val b = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            v.setPadding(b.left, b.top, b.right, b.bottom)
            insets
        }
        preview = findViewById(R.id.preview)
        status = findViewById(R.id.status)
        watchText = findViewById(R.id.watch)
        resultName = findViewById(R.id.resultName)
        resultDetail = findViewById(R.id.resultDetail)
        history = findViewById(R.id.history)
        btnAuto = findViewById(R.id.btnAuto)

        watcher = CardWatcher(
            onCapture = { runOnUiThread { takePhoto(auto = true) } },
            onInfo = { t -> runOnUiThread { watchText.text = t } },
        )
        watcher.enabled = prefs.getBoolean("auto", true)
        watcher.stableMs = prefs.getLong("stableMs", 450L)
        updateAutoButton()

        btnAuto.setOnClickListener {
            watcher.enabled = !watcher.enabled
            prefs.edit().putBoolean("auto", watcher.enabled).apply()
            updateAutoButton()
        }
        findViewById<MaterialButton>(R.id.btnShoot).setOnClickListener { watcher.markShot(); takePhoto(auto = false) }
        findViewById<MaterialButton>(R.id.btnMore).setOnClickListener { showSettings() }
        setupGestures()

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) startCamera()
        else askCamera.launch(Manifest.permission.CAMERA)

        lifecycleScope.launch { connectionLoop() }
        lifecycleScope.launch { senderLoop() }
    }

    private fun updateAutoButton() { btnAuto.text = if (watcher.enabled) "Auto: on" else "Auto: off" }

    // ---------------------------------------------------------------- camera

    private fun startCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            val provider = future.get()
            val pv = Preview.Builder().build().also { it.setSurfaceProvider(preview.surfaceProvider) }
            val sel43 = ResolutionSelector.Builder()
                .setAspectRatioStrategy(AspectRatioStrategy.RATIO_4_3_FALLBACK_AUTO_STRATEGY)
                .setResolutionStrategy(ResolutionStrategy.HIGHEST_AVAILABLE_STRATEGY)
                .build()
            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                .setResolutionSelector(sel43)
                .setJpegQuality(92)
                .build()
            val analysis = ImageAnalysis.Builder()
                .setResolutionSelector(
                    ResolutionSelector.Builder().setResolutionStrategy(
                        ResolutionStrategy(Size(640, 480), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER)
                    ).build()
                )
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

    private fun takePhoto(auto: Boolean) {
        val ic = imageCapture ?: run { watcher.captureFinished(); return }
        val stamp = SimpleDateFormat("yyyyMMdd_HHmmss_SSS", Locale.US).format(Date())
        val file = File(pendingDir, "scan_$stamp.jpg")
        ic.takePicture(ImageCapture.OutputFileOptions.Builder(file).build(), ContextCompat.getMainExecutor(this),
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    shots++
                    watcher.captureFinished()
                    if (prefs.getBoolean("keepCopy", true)) saveCopyToGallery(file)
                    enqueue(file)
                    resultName.text = "📷 Scan $shots taken"
                    resultDetail.text = if (pc != null) "Sending to ${pc!!.name}…" else "Saved on the phone — it goes to the PC when it's found."
                }
                override fun onError(e: ImageCaptureException) {
                    watcher.captureFinished()
                    Toast.makeText(this@MainActivity, "Photo failed: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            })
    }

    private fun saveCopyToGallery(file: File) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return
        try {
            val values = ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, file.name)
                put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/MTG Scans")
            }
            val uri = contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: return
            contentResolver.openOutputStream(uri)?.use { out -> file.inputStream().use { it.copyTo(out) } }
        } catch (_: Exception) {}
    }

    // ---------------------------------------------------------------- PC link

    private fun enqueue(file: File) {
        synchronized(queued) { if (!queued.add(file.name)) return }
        queue.trySend(file)
    }

    private var misses = 0

    @Suppress("DEPRECATION")
    private fun phoneIp(): String = try {
        val ip = (applicationContext.getSystemService(Context.WIFI_SERVICE) as android.net.wifi.WifiManager).connectionInfo.ipAddress
        if (ip == 0) "not on Wi-Fi" else "${ip and 255}.${ip shr 8 and 255}.${ip shr 16 and 255}.${ip shr 24 and 255}"
    } catch (_: Exception) { "?" }

    private suspend fun connectionLoop() {
        while (lifecycleScope.isActive) {
            if (pc == null) {
                if (misses < 2) withContext(Dispatchers.Main) { status.text = "Looking for the PC… (turn on Settings → Phone link in the PC app)" }
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
                    pendingDir.listFiles()?.sortedBy { it.name }?.forEach { enqueue(it) }
                } else {
                    misses++
                    if (misses >= 2) withContext(Dispatchers.Main) {
                        status.text = if (manual.isNotEmpty())
                            "Can't reach the PC at $manual. Check the address, and that the PC app's Phone link is on."
                        else "PC not found (phone ${phoneIp()}). Turn on Phone link in the PC app, or type the PC's address in Settings."
                    }
                    delay(4000)
                }
            } else delay(3000)
        }
    }

    private fun showConnected() {
        val p = pc ?: return
        val waiting = pendingDir.listFiles()?.size ?: 0
        status.text = "✅ ${p.name} (${p.host}) · $sent sent" + if (waiting > 0) " · $waiting waiting" else ""
    }

    private suspend fun senderLoop() {
        for (file in queue) {
            while (true) {
                val target = pc
                if (target == null) { delay(1500); continue }
                val reply = withContext(Dispatchers.IO) {
                    try { link.send(target.host, target.port, file) } catch (e: Exception) { null }
                }
                if (reply == null) {
                    pc = null    // connection lost: rediscover, keep the photo
                    withContext(Dispatchers.Main) { status.text = "PC not answering — photos are kept and will be sent" }
                    delay(1500)
                    continue
                }
                sent++
                file.delete()
                synchronized(queued) { queued.remove(file.name) }
                showReply(reply)
                showConnected()
                break
            }
        }
    }

    private fun showReply(r: PcLink.ScanReply) {
        val beep = prefs.getBoolean("beep", true)
        if (!r.ok || r.name == null) {
            resultName.text = "⚠ ${r.error ?: "No card found"}"
            resultDetail.text = "Check the photo on the PC (${r.scan})."
            if (beep) beeper.startTone(ToneGenerator.TONE_SUP_ERROR, 300)
            addHistory("⚠ ${r.scan}  ${r.error ?: "no card"}")
            return
        }
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
                    !r.pinned -> "Not sure — verify it on the PC"
                    r.finishUnsure -> "Check the finish on the PC (foil?)"
                    else -> "📌 ${r.pinReason ?: "pinned"}"
                }
            )
        }
        if (beep) {
            if (check) beeper.startTone(ToneGenerator.TONE_PROP_NACK, 250) else beeper.startTone(ToneGenerator.TONE_PROP_ACK, 150)
        }
        addHistory((if (check) "⚠ " else "✓ ") + "${r.name}  $setLine")
    }

    private fun addHistory(line: String) {
        val lines = (listOf(line) + history.text.lines()).filter { it.isNotBlank() }.take(40)
        history.text = lines.joinToString("\n")
    }

    // ---------------------------------------------------------------- settings

    private fun showSettings() {
        val pad = (16 * resources.displayMetrics.density).toInt()
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad / 2, pad, 0) }
        val hostLabel = TextView(this).apply { text = "PC address (leave blank to find it automatically)" }
        val host = EditText(this).apply { hint = "e.g. 192.168.1.20"; setText(prefs.getString("host", "")); isSingleLine = true }
        val keep = CheckBox(this).apply { text = "Keep a copy in Pictures/MTG Scans"; isChecked = prefs.getBoolean("keepCopy", true) }
        val beep = CheckBox(this).apply { text = "Beep on each result"; isChecked = prefs.getBoolean("beep", true) }
        val torch = CheckBox(this).apply { text = "Phone flashlight on (can cause glare)"; isChecked = prefs.getBoolean("torch", false) }
        val stableLabel = TextView(this).apply { text = "Wait before auto photo (ms): longer if photos come out blurry" }
        val stable = EditText(this).apply {
            setText(prefs.getLong("stableMs", 450L).toString()); inputType = android.text.InputType.TYPE_CLASS_NUMBER
        }
        val tips = TextView(this).apply {
            text = "\nTips: pinch to zoom so the card fills most of the screen; tap to focus. " +
                "Use a dark, plain background. \"Re-learn empty bed\" if auto-capture fires with no card."
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
            .setNeutralButton("Re-learn empty bed") { _, _ -> watcher.setEmptyBed() }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onDestroy() {
        super.onDestroy()
        analysisExec.shutdown()
        beeper.release()
    }
}
