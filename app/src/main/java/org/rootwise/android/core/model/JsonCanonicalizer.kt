package org.rootwise.android.core.model

import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.TreeMap

/**
 * Zero-dependency deterministic JSON serializer matching upstream Python
 * `json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`.
 */
object JsonCanonicalizer {
    private val ISO_SECONDS_FORMATTER: DateTimeFormatter =
        DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'").withZone(ZoneOffset.UTC)

    fun utcNowIsoSeconds(): String = ISO_SECONDS_FORMATTER.format(Instant.now())

    /**
     * Formats nanosecond epoch timestamp into ISO-8601 UTC with microsecond precision
     * matching Python `datetime.fromtimestamp(ns / 1_000_000_000, timezone.utc).isoformat(timespec="microseconds")`.
     */
    fun formatTimestampNs(ns: Long?): String? {
        if (ns == null) return null
        val seconds = Math.floorDiv(ns, 1_000_000_000L)
        val nanos = Math.floorMod(ns, 1_000_000_000L)
        val micros = nanos / 1_000L
        val instant = Instant.ofEpochSecond(seconds)
        val base = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")
            .withZone(ZoneOffset.UTC)
            .format(instant)
        return String.format(java.util.Locale.ROOT, "%s.%06dZ", base, micros)
    }

    fun toCanonicalJson(value: Any?): String {
        val sb = StringBuilder()
        appendValue(sb, value)
        return sb.toString()
    }

    fun toCanonicalJsonLineBytes(value: Any?): ByteArray =
        (toCanonicalJson(value) + "\n").toByteArray(StandardCharsets.UTF_8)

    fun sha256Hex(bytes: ByteArray): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(bytes)
        return digest.joinToString("") { "%02x".format(it) }
    }

    fun sha256HexOfCanonical(value: Any?): String =
        sha256Hex(toCanonicalJson(value).toByteArray(StandardCharsets.UTF_8))

    private fun appendValue(sb: StringBuilder, value: Any?) {
        when (value) {
            null -> sb.append("null")
            is Boolean -> sb.append(if (value) "true" else "false")
            is Int, is Long, is Short, is Byte -> sb.append(value.toString())
            is Double -> {
                require(value.isFinite()) { "Non-finite Double cannot be serialized to canonical JSON: $value" }
                sb.append(formatNumber(value))
            }
            is Float -> {
                require(value.isFinite()) { "Non-finite Float cannot be serialized to canonical JSON: $value" }
                sb.append(formatNumber(value.toDouble()))
            }
            is String -> appendEscapedString(sb, value)
            is Enum<*> -> appendEscapedString(sb, value.name)
            is Map<*, *> -> {
                val sorted = TreeMap<String, Any?>()
                for ((k, v) in value) {
                    require(k is String) { "JSON object keys must be strings, got: $k" }
                    sorted[k] = v
                }
                sb.append('{')
                var first = true
                for ((k, v) in sorted) {
                    if (!first) sb.append(',')
                    first = false
                    appendEscapedString(sb, k)
                    sb.append(':')
                    appendValue(sb, v)
                }
                sb.append('}')
            }
            is Iterable<*> -> {
                sb.append('[')
                var first = true
                for (item in value) {
                    if (!first) sb.append(',')
                    first = false
                    appendValue(sb, item)
                }
                sb.append(']')
            }
            is Array<*> -> {
                sb.append('[')
                for (i in value.indices) {
                    if (i > 0) sb.append(',')
                    appendValue(sb, value[i])
                }
                sb.append(']')
            }
            else -> throw IllegalArgumentException("Unsupported type for canonical JSON: ${value::class.java.name}")
        }
    }

    private fun formatNumber(value: Double): String {
        return if (value == kotlin.math.floor(value) && !value.isInfinite() && kotlin.math.abs(value) < 1e15) {
            String.format(java.util.Locale.ROOT, "%.1f", value)
        } else {
            value.toString()
        }
    }

    private fun appendEscapedString(sb: StringBuilder, s: String) {
        sb.append('"')
        for (ch in s) {
            when (ch) {
                '"' -> sb.append("\\\"")
                '\\' -> sb.append("\\\\")
                '\b' -> sb.append("\\b")
                '\u000C' -> sb.append("\\f")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                else -> {
                    if (ch.code < 0x20) {
                        sb.append(String.format(java.util.Locale.ROOT, "\\u%04x", ch.code))
                    } else {
                        sb.append(ch)
                    }
                }
            }
        }
        sb.append('"')
    }
}
