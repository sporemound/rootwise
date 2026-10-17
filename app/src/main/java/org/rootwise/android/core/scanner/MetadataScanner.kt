package org.rootwise.android.core.scanner

import org.rootwise.android.core.adapter.ScanSourceAdapter
import org.rootwise.android.core.db.InventoryDatabase
import org.rootwise.android.core.model.Observation
import org.rootwise.android.core.model.PathCanonicalizer
import org.rootwise.android.core.model.ResourceLimitExceededException
import org.rootwise.android.core.model.ScanConfig
import org.rootwise.android.core.model.ScanErrorRecord
import org.rootwise.android.core.model.SessionState
import org.rootwise.android.core.model.VolumeInfo
import org.rootwise.android.core.model.VolumeUnmountedException
import java.io.IOException
import java.nio.file.NoSuchFileException
import java.nio.file.Path
import kotlin.math.min

/**
 * Bounded, single-worker, metadata-only directory traversal.
 * Port of `src/rootwise/scanner.py` over [ScanSourceAdapter].
 *
 * Core Invariants Preserved:
 * - Zero third-party dependencies.
 * - Never opens source file contents or mutates source paths.
 * - Symlinks/reparse points are recorded (`SYMLINK`, `SYMLINK_DIRECTORY`) and never queued into `scan_frontier`.
 * - Stage 0.21 fresh metadata check via `adapter.observeEntry()` at the observation boundary.
 * - Persistent SQLite `scan_frontier` bounded by `config.batchSize`.
 * - Hard-excludes self-artifact directories when scanning parent partitions (e.g. `/data` on rooted Android)
 *   and records `SELF_ARTIFACT_ROOT_EXCLUDED` in `scan_events`.
 * - Volume unmount or resource limit stops record `STOPPED` (never `COMPLETE`).
 */
class MetadataScanner(
    private val adapter: ScanSourceAdapter,
    private val volume: VolumeInfo = adapter.resolveVolume(),
    private val database: InventoryDatabase,
    private val config: ScanConfig,
    private val cancellation: CancellationToken = CancellationToken(),
    private val excludedRelativeSubtrees: Set<String> = emptySet(),
    resourceController: ResourceController? = null,
    private val sleeper: (Long) -> Unit = { ms -> if (ms > 0) Thread.sleep(ms) }
) {
    private val resources: ResourceController
    private var processedCount: Int = 0
    private val rateStartedNanos: Long = System.nanoTime()

    init {
        config.validate()
        val destParent = Path.of(config.database).toAbsolutePath().parent ?: database.path.parent
        resources = resourceController ?: ResourceController(
            destinationDirectory = destParent,
            policy = ResourcePolicy(
                maxHeapBytes = config.maxRssMib?.let { it.toLong() * ResourceController.MIB },
                minFreeDestinationBytes = config.minFreeDestinationMib?.let { it.toLong() * ResourceController.MIB },
                activeWindowSeconds = config.activeWindowSeconds,
                cooldownSeconds = config.cooldownSeconds
            )
        )
    }

    fun run(resume: Boolean = false): Pair<String, SessionState> {
        val sessionId = if (resume) {
            database.resumeSession(volume, adapter.sourceRoot)
        } else {
            database.startSession(volume, config, adapter.sourceRoot, adapter.capabilities())
        }
        try {
            resources.check()
            while (!cancellation.isCancelled) {
                if (!adapter.isVolumeMounted()) {
                    throw VolumeUnmountedException("", "source volume ${volume.identity} is no longer mounted")
                }
                val relativeDir = database.nextDirectory(sessionId)
                if (relativeDir == null) {
                    database.finish(sessionId, SessionState.COMPLETE)
                    return Pair(sessionId, SessionState.COMPLETE)
                }
                scanDirectory(sessionId, relativeDir)
                if (config.stopAfter != null && processedCount >= config.stopAfter) {
                    cancellation.cancel()
                }
            }
            database.finish(sessionId, SessionState.STOPPED)
            return Pair(sessionId, SessionState.STOPPED)
        } catch (exc: VolumeUnmountedException) {
            database.recordError(
                sessionId = sessionId,
                relativePath = exc.relativePath,
                operation = "volume_mount_check",
                errorType = "VolumeUnmountedException",
                errorCode = null,
                message = exc.message ?: "volume unmounted during scan"
            )
            database.recordEvent(
                sessionId = sessionId,
                eventType = "VOLUME_UNMOUNTED",
                detail = mapOf(
                    "message" to (exc.message ?: "volume unmounted"),
                    "relative_path" to exc.relativePath
                )
            )
            database.finish(sessionId, SessionState.STOPPED)
            return Pair(sessionId, SessionState.STOPPED)
        } catch (exc: ResourceLimitExceededException) {
            database.recordError(
                sessionId = sessionId,
                relativePath = "",
                operation = "resource_check",
                errorType = "ResourceLimitExceeded",
                errorCode = null,
                message = exc.message ?: "resource limit exceeded"
            )
            database.recordEvent(
                sessionId = sessionId,
                eventType = "RESOURCE_STOP",
                detail = mapOf(
                    "error_type" to "ResourceLimitExceeded",
                    "message" to (exc.message ?: "resource limit exceeded")
                )
            )
            database.finish(sessionId, SessionState.STOPPED)
            return Pair(sessionId, SessionState.STOPPED)
        } catch (exc: InterruptedException) {
            Thread.currentThread().interrupt()
            database.finish(sessionId, SessionState.STOPPED)
            throw exc
        } catch (exc: Exception) {
            database.recordError(
                sessionId = sessionId,
                relativePath = "",
                operation = "scanner",
                errorType = exc::class.java.simpleName.ifEmpty { "Exception" },
                errorCode = null,
                message = exc.message ?: exc.toString()
            )
            database.finish(sessionId, SessionState.FAILED)
            throw exc
        }
    }

    private fun scanDirectory(sessionId: String, relativeDir: String) {
        val observations = ArrayList<Observation>(min(config.batchSize, 512))
        val children = ArrayList<String>()
        val errors = ArrayList<ScanErrorRecord>()

        try {
            val entries = adapter.listDirectory(relativeDir)
            for (entry in entries) {
                if (cancellation.isCancelled) {
                    break
                }
                val entryRelative = PathCanonicalizer.inventoryPath(
                    if (relativeDir.isEmpty()) entry.name else "$relativeDir/${entry.name}"
                )
                if (isExcludedSubtree(entryRelative)) {
                    database.recordEvent(
                        sessionId = sessionId,
                        eventType = "SELF_ARTIFACT_ROOT_EXCLUDED",
                        detail = mapOf("excluded_relative_path" to entryRelative)
                    )
                    continue
                }
                try {
                    val result = adapter.observeEntry(relativeDir, entry)
                    observations.add(result.observation)
                    if (result.traversableDirectory) {
                        children.add(result.observation.relativePath)
                    }
                } catch (exc: VolumeUnmountedException) {
                    throw exc
                } catch (exc: IOException) {
                    errors.add(toErrorRecord(entryRelative, "stat", exc))
                }
                processedCount += 1
                rateLimit()
                if (observations.size + errors.size >= config.batchSize) {
                    flush(sessionId, relativeDir, observations, children, errors, done = false)
                }
                if (config.stopAfter != null && processedCount >= config.stopAfter) {
                    cancellation.cancel()
                    break
                }
            }
        } catch (exc: VolumeUnmountedException) {
            if (observations.isNotEmpty() || children.isNotEmpty() || errors.isNotEmpty()) {
                flush(sessionId, relativeDir, observations, children, errors, done = false)
            }
            throw exc
        } catch (exc: IOException) {
            errors.add(toErrorRecord(relativeDir, "scandir", exc))
            flush(sessionId, relativeDir, observations, children, errors, done = true)
            return
        }

        flush(
            sessionId = sessionId,
            relativeDir = relativeDir,
            observations = observations,
            children = children,
            errors = errors,
            done = !cancellation.isCancelled
        )
    }

    private fun isExcludedSubtree(relativePath: String): Boolean {
        if (excludedRelativeSubtrees.isEmpty()) return false
        return excludedRelativeSubtrees.any { excluded ->
            relativePath == excluded || relativePath.startsWith("$excluded/")
        }
    }

    private fun flush(
        sessionId: String,
        relativeDir: String,
        observations: MutableList<Observation>,
        children: MutableList<String>,
        errors: MutableList<ScanErrorRecord>,
        done: Boolean
    ) {
        database.commitDirectory(
            sessionId = sessionId,
            relativePath = relativeDir,
            observations = observations,
            childDirectories = children,
            errors = errors,
            done = done
        )
        observations.clear()
        children.clear()
        errors.clear()
        if (config.sleepMsPerBatch > 0) {
            sleeper(config.sleepMsPerBatch.toLong())
        }
        resources.check()
    }

    private fun rateLimit() {
        val expectedSeconds = processedCount.toDouble() / config.maxFilesPerSecond
        val elapsedSeconds = (System.nanoTime() - rateStartedNanos).toDouble() / 1_000_000_000.0
        val remainingSeconds = expectedSeconds - elapsedSeconds
        if (remainingSeconds > 0.0) {
            val sleepMs = (min(remainingSeconds, 0.25) * 1000.0).toLong()
            if (sleepMs > 0L) {
                sleeper(sleepMs)
            }
        }
    }

    private fun toErrorRecord(path: String, operation: String, exc: IOException): ScanErrorRecord {
        val errorType = when (exc) {
            is NoSuchFileException, is java.io.FileNotFoundException -> "FileNotFoundError"
            is java.nio.file.AccessDeniedException -> "PermissionError"
            else -> exc::class.java.simpleName.ifEmpty { "IOException" }
        }
        return ScanErrorRecord(
            relativePath = path,
            operation = operation,
            errorType = errorType,
            errorCode = null,
            message = exc.message ?: exc.toString()
        )
    }
}
