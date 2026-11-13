package com.mrweasel.mtgscanner

import android.content.Context
import android.net.wifi.WifiManager
import org.json.JSONObject
import java.io.File
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.URL

/**
 * Talks to the desktop app's phone link: finds the PC with a UDP broadcast on port 8771, checks it with
 * GET /api/hello, and sends each photo with POST /api/scan (one JPEG) on port 8770.
 * All calls block: run them off the main thread.
 */
class PcLink(private val context: Context) {

    data class Pc(val host: String, val port: Int, val name: String)

    data class ScanReply(
        val ok: Boolean, val scan: String, val name: String?, val set: String?, val setCode: String?,
        val number: String?, val finish: String?, val finishUnsure: Boolean, val pinned: Boolean,
        val pinReason: String?, val price: Double?, val error: String?,
    )

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

    /** Returns the PC name if it answers. */
    fun hello(host: String, port: Int): String? = try {
        val c = (URL("http://$host:$port/api/hello").openConnection() as HttpURLConnection).apply {
            connectTimeout = 2500; readTimeout = 4000
        }
        c.inputStream.bufferedReader().use { JSONObject(it.readText()).optString("pc", "PC") }
    } catch (_: Exception) { null }

    fun send(host: String, port: Int, jpeg: File): ScanReply {
        val c = (URL("http://$host:$port/api/scan").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 4000
            readTimeout = 90000
            setRequestProperty("Content-Type", "image/jpeg")
            setFixedLengthStreamingMode(jpeg.length())
        }
        c.outputStream.use { out -> jpeg.inputStream().use { it.copyTo(out) } }
        val stream = if (c.responseCode in 200..299) c.inputStream else c.errorStream
        val j = JSONObject(stream.bufferedReader().use { it.readText() })
        fun s(k: String) = if (j.isNull(k)) null else j.optString(k)
        return ScanReply(
            ok = j.optBoolean("ok"), scan = j.optString("scan", ""), name = s("name"), set = s("set"),
            setCode = s("setCode"), number = s("number"), finish = s("finish"),
            finishUnsure = j.optBoolean("finishUnsure"), pinned = j.optBoolean("pinned"),
            pinReason = s("pinReason"), price = if (j.isNull("price")) null else j.optDouble("price"),
            error = s("error"),
        )
    }
}
