package org.rootwise.android.core.model

import java.text.Normalizer

enum class SessionState(val wireValue: String) {
    RUNNING("RUNNING"),
    COMPLETE("COMPLETE"),
    STOPPED("STOPPED"),
    FAILED("FAILED");

    companion object {
        fun fromWire(value: String): SessionState =
            entries.firstOrNull { it.wireValue == value }
                ?: throw IllegalArgumentException("Unknown SessionState: $value")
    }
}

enum class VolumeSeparationMode(val wireValue: String) {
    STRICT_DISTINCT_VOLUME("STRICT_DISTINCT_VOLUME"),
    SAME_VOLUME_DISJOINT_SUBTREE("SAME_VOLUME_DISJOINT_SUBTREE")
}

data class VolumeInfo(
    val identity: String,
    val mountPath: String,
    val filesystemType: String?,
    val device: String?
)

data class AdapterCapabilities(
    val adapterType: String,
    val nofollowEnforced: Boolean,
    val kernelStDevEnforced: Boolean,
    val freshStatEnforced: Boolean,
    val rootAccessUsed: Boolean,
    val blindSpots: List<String>
) {
    fun toMap(): Map<String, Any?> = linkedMapOf(
        "adapter_type" to adapterType,
        "blind_spots" to blindSpots,
        "fresh_stat_enforced" to freshStatEnforced,
        "kernel_st_dev_enforced" to kernelStDevEnforced,
        "nofollow_enforced" to nofollowEnforced,
        "root_access_used" to rootAccessUsed
    )
}

data class ScanConfig(
    val source: String,
    val database: String,
    val maxFilesPerSecond: Double = 250.0,
    val batchSize: Int = 256,
    val sleepMsPerBatch: Int = 25,
    val stopAfter: Int? = null,
    val maxRssMib: Int? = 256,
    val minFreeDestinationMib: Int? = 64,
    val activeWindowSeconds: Double = 30.0,
    val cooldownSeconds: Double = 2.0,
    val allowSameVolumeDisjointSubtree: Boolean = false
) {
    fun validate() {
        require(maxFilesPerSecond.isFinite() && maxFilesPerSecond > 0.0) {
            "max_files_per_second must be positive"
        }
        require(batchSize in 1..10_000) {
            "batch_size must be between 1 and 10000"
        }
        require(sleepMsPerBatch in 0..60_000) {
            "sleep_ms_per_batch must be between 0 and 60000"
        }
        if (stopAfter != null) {
            require(stopAfter >= 1) { "stop_after must be positive" }
        }
        if (maxRssMib != null) {
            require(maxRssMib >= 32) { "max_rss_mib must be at least 32 or disabled" }
        }
        if (minFreeDestinationMib != null) {
            require(minFreeDestinationMib >= 1) { "min_free_destination_mib must be positive or disabled" }
        }
        require(activeWindowSeconds.isFinite() && activeWindowSeconds > 0.0) {
            "active_window_seconds must be finite and positive"
        }
        require(cooldownSeconds.isFinite() && cooldownSeconds >= 0.0) {
            "cooldown_seconds must be finite and nonnegative"
        }
    }

    fun toConfigurationMap(
        capabilities: AdapterCapabilities,
        separationMode: VolumeSeparationMode
    ): Map<String, Any?> = linkedMapOf(
        "active_window_seconds" to activeWindowSeconds,
        "adapter_capabilities" to capabilities.toMap(),
        "allow_same_volume_disjoint_subtree" to allowSameVolumeDisjointSubtree,
        "batch_size" to batchSize,
        "cooldown_seconds" to cooldownSeconds,
        "database" to database,
        "max_files_per_second" to maxFilesPerSecond,
        "max_rss_mib" to maxRssMib,
        "min_free_destination_mib" to minFreeDestinationMib,
        "sleep_ms_per_batch" to sleepMsPerBatch,
        "source" to source,
        "stop_after" to stopAfter,
        "volume_separation_mode" to separationMode.wireValue
    )
}

data class Observation(
    val relativePath: String,
    val comparisonPath: String,
    val parentPath: String?,
    val name: String,
    val extension: String,
    val entryType: String,
    val logicalBytes: Long,
    val createdNs: Long?,
    val modifiedNs: Long?,
    val accessedNs: Long?,
    val attributes: Int,
    val depth: Int,
    val displayPath: String,
    val observationStatus: String = "OBSERVED"
)

data class ScanErrorRecord(
    val relativePath: String,
    val operation: String,
    val errorType: String,
    val errorCode: Int?,
    val message: String
)

object PathCanonicalizer {
    /**
     * Normalize separators while preserving the exact Unicode spelling.
     * Port of `inventory_path` from `src/rootwise/scanner.py`.
     */
    fun inventoryPath(relativePath: String, normalizeBackslash: Boolean = false): String {
        val raw = if (normalizeBackslash) relativePath.replace('\\', '/') else relativePath
        require(!raw.startsWith("/")) { "relative path became absolute: $relativePath" }
        require(!raw.contains('\u0000')) { "relative path contains NUL byte" }
        if (raw.isEmpty()) return ""
        val clean = mutableListOf<String>()
        for (part in raw.split('/')) {
            if (part.isEmpty() || part == ".") continue
            if (part == "..") {
                throw IllegalArgumentException("relative path contains unresolved parent escape: $relativePath")
            }
            clean.add(part)
        }
        return clean.joinToString("/")
    }

    /**
     * Create a comparison-only NFC-normalized path without altering the filesystem name.
     * Port of `comparison_path` from `src/rootwise/scanner.py`.
     */
    fun comparisonPath(relativePath: String, normalizeBackslash: Boolean = false): String {
        val inv = inventoryPath(relativePath, normalizeBackslash)
        if (inv.isEmpty()) return ""
        return inv.split('/').joinToString("/") { Normalizer.normalize(it, Normalizer.Form.NFC) }
    }

    /**
     * Extract file extension matching Python `Path(entry.name).suffix`.
     * Note: `.bashrc` has no suffix in Python pathlib (`""`), while `archive.tar.gz` has `.gz`.
     */
    fun extractExtension(name: String): String {
        val dotIndex = name.lastIndexOf('.')
        if (dotIndex <= 0 || dotIndex == name.length - 1) {
            return ""
        }
        return name.substring(dotIndex)
    }

    fun depthOf(relativePath: String): Int {
        val inv = inventoryPath(relativePath)
        if (inv.isEmpty()) return 0
        return inv.count { it == '/' } + 1
    }
}
