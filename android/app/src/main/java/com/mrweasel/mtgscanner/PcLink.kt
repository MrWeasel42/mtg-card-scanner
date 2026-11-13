package com.mrweasel.mtgscanner

import android.content.Context
import android.net.wifi.WifiManager
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.URL

/**
 * Talks to the desktop app's phone link: finds the PC with a UDP broadcast on port 8771, then HTTP on port 8770:
 *   GET /api/hello · POST /api/session/start|resume|stop · GET /api/status · POST /api/scan (one JPEG) · POST /api/undo
 * All calls block: run them off the main thread.
 */
class PcLink(private val context: Context) {

    data class Pc(val host: String, val port: Int, val name: String)

    data class ScanReply(
        val ok: Boolean, val scan: String, val name: String?, val set: String?, val setCode: String?,
        val number: String?, val finish: String?, val finishUnsure: Boolean, val pinned: Boolean,
        val pinReason: String?, val price: Double?, val error: String?, val noCard: Boolean,
        val sameAsLast: Boolean, val count: Int, val paused: Boolean, val stop: Boolean,
    )

    data class Status(val active: Boolean, val paused: Boolean, val stop: Boolean, val count: Int)

    fun discover(timeoutMs: Int = 1500): Pc? {
        DatagramSocket().use { sock ->
            sock.broadcast = true
            sock.soTimeout = timeoutMs
            val msg = "MTGSCAN?".toByteArray()
            for (addr in broadcastAddresses()) {
                try { sock.send(DatagramPacket(msg, msg.size, addr, 8771)) } catch (_: Exception) {}
            }
            val buf = ByteArray(256)
            val pkt = DatagramPacket(buf, buf.size)
            return try {
                sock.receive(pkt)
                val parts = String(pkt.data, 0, pkt.length).trim().split(" ", limit = 3)
                if (parts.size >= 2 && parts[0] == "MTGSCAN")
                    Pc(pkt.address.hostAddress ?: return null, parts[1].toIntOrNull() ?: 8770, parts.getOrElse(2) { "PC" })
                else null
            } catch (_: Exception) { null }
        }
    }

    private fun broadcastAddresses(): List<InetAddress> {
        val list = mutableListOf(InetAddress.getByName("255.255.255.255"))
        try {
            @Suppress("DEPRECATION")
            val dhcp = (context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager).dhcpInfo
            if (dhcp != null && dhcp.ipAddress != 0) {
                val bc = (dhcp.ipAddress and dhcp.netmask) or dhcp.netmask.inv()
                val b = ByteArray(4) { k -> (bc shr (k * 8) and 0xFF).toByte() }
                list.add(InetAddress.getByAddress(b))
            }
        } catch (_: Exception) {}
        return list
    }

    private fun call(pc: Pc, method: String, path: String, body: ByteArray? = null, type: String = "text/plain",
                     readTimeout: Int = 8000): JSONObject {
        val c = (URL("http://${pc.host}:${pc.port}$path").openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 3000
            this.readTimeout = readTimeout
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", type)
                setFixedLengthStreamingMode(body.size)
            }
        }
        if (body != null) c.outputStream.use { it.write(body) }
        val stream = if (c.responseCode in 200..299) c.inputStream else c.errorStream
        return JSONObject(stream.bufferedReader().use { it.readText() })
    }

    /** Returns the PC name if it answers. */
    fun hello(host: String, port: Int): String? = try {
        call(Pc(host, port, ""), "GET", "/api/hello").optString("pc", "PC")
    } catch (_: Exception) { null }

    private fun status(j: JSONObject) = Status(j.optBoolean("active"), j.optBoolean("paused"), j.optBoolean("stop"), j.optInt("count"))

    fun status(pc: Pc): Status = status(call(pc, "GET", "/api/status"))
    fun startSession(pc: Pc): Status = status(call(pc, "POST", "/api/session/start", ByteArray(0)))
    fun resumeSession(pc: Pc): Status = status(call(pc, "POST", "/api/session/resume", ByteArray(0)))
    fun stopSession(pc: Pc) { call(pc, "POST", "/api/session/stop", ByteArray(0)) }

    fun undo(pc: Pc, scan: String): String? {
        val j = call(pc, "POST", "/api/undo", scan.toByteArray())
        return if (j.optBoolean("ok")) null else j.optString("error", "Couldn't undo")
    }

    fun send(pc: Pc, jpeg: ByteArray): ScanReply {
        val j = call(pc, "POST", "/api/scan", jpeg, "image/jpeg", readTimeout = 90000)
        fun s(k: String) = if (j.isNull(k)) null else j.optString(k)
        return ScanReply(
            ok = j.optBoolean("ok"), scan = j.optString("scan", ""), name = s("name"), set = s("set"),
            setCode = s("setCode"), number = s("number"), finish = s("finish"),
            finishUnsure = j.optBoolean("finishUnsure"), pinned = j.optBoolean("pinned"),
            pinReason = s("pinReason"), price = if (j.isNull("price") || !j.has("price")) null else j.optDouble("price"),
            error = s("error"), noCard = j.optBoolean("noCard"), sameAsLast = j.optBoolean("sameAsLast"),
            count = j.optInt("count"), paused = j.optBoolean("paused"), stop = j.optBoolean("stop"),
        )
    }
}
