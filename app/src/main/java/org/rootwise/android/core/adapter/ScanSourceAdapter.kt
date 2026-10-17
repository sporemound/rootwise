package org.rootwise.android.core.adapter

import org.rootwise.android.core.model.AdapterCapabilities
import org.rootwise.android.core.model.Observation
import org.rootwise.android.core.model.VolumeInfo

/**
 * Lightweight handle to an enumerated child entry prior to fresh metadata observation.
 */
data class RawDirectoryEntry(
    val name: String,
    val handleId: String
)

/**
 * Result of observing a single directory entry at the Stage 0.21 fresh metadata boundary.
 */
data class EntryObservationResult(
    val observation: Observation,
    val traversableDirectory: Boolean
)

/**
 * Common scanner source adapter interface (Deliverable 3).
 * Decouples the metadata scanner core from the underlying Android storage surface:
 * - `PosixRootScanAdapter`: primary for rooted Android phones (`/data`, `/data/media/0`, `/mnt/media_rw/<uuid>`)
 *   and POSIX/NIO test trees; enforces `O_NOFOLLOW` / `NOFOLLOW_LINKS`, `st_dev` volume boundaries,
 *   and Stage 0.21 fresh `lstat` revalidation.
 * - `SafScanAdapter`: Storage Access Framework document tree adapter.
 * - `MediaStoreScanAdapter`: MediaStore metadata cursor adapter.
 */
interface ScanSourceAdapter {
    /**
     * Canonical representation of the source root (e.g., resolved POSIX path or SAF tree URI).
     */
    val sourceRoot: String

    /**
     * Resolve the authoritative volume identity for [sourceRoot].
     */
    fun resolveVolume(): VolumeInfo

    /**
     * Report adapter capabilities and blind spots for persisting into `scan_sessions.configuration_json`
     * and displaying in the review UI.
     */
    fun capabilities(): AdapterCapabilities

    /**
     * Verify the source volume is still mounted and reachable.
     */
    fun isVolumeMounted(): Boolean

    /**
     * Enumerate immediate child entries of [relativeDir] without following symlinks or crossing
     * unauthorized volume boundaries.
     *
     * @throws org.rootwise.android.core.model.VolumeUnmountedException if the volume unmounted mid-scan.
     * @throws java.io.IOException if the directory cannot be opened or read.
     */
    fun listDirectory(relativeDir: String): Sequence<RawDirectoryEntry>

    /**
     * Perform a fresh, non-following metadata lookup (`lstat`) on [entry] inside [relativeDir].
     * Never opens file contents.
     *
     * @throws java.io.IOException if the entry disappeared after enumeration (Stage 0.21 concurrent mutation)
     *   or metadata could not be read.
     */
    fun observeEntry(relativeDir: String, entry: RawDirectoryEntry): EntryObservationResult
}
