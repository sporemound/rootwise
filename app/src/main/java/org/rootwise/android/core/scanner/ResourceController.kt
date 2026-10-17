package org.rootwise.android.core.scanner

import org.rootwise.android.core.model.ResourceLimitExceededException
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.atomic.AtomicBoolean

class CancellationToken {
    private val flag = AtomicBoolean(false)

    fun cancel() {
        flag.set(true)
    }

    val isCancelled: Boolean
        get() = flag.get()
}

data class ResourcePolicy(
    val maxHeapBytes: Long?,
    val minFreeDestinationBytes: Long?,
    val activeWindowSeconds: Double = 30.0,
    val cooldownSeconds: Double = 2.0
)

/**
 * Bounded resource controller matching `src/rootwise/resources.py`.
 * Enforces heap usage bounds and destination free-space thresholds, transitioning
 * a scan to `STOPPED` (never `COMPLETE`) if exceeded.
 */
open class ResourceController(
    private val destinationDirectory: Path,
    private val policy: ResourcePolicy,
    private val memoryUsedBytesProvider: () -> Long = {
        val rt = Runtime.getRuntime()
        rt.totalMemory() - rt.freeMemory()
    },
    private val freeSpaceBytesProvider: (Path) -> Long = { dir ->
        Files.getFileStore(dir).usableSpace
    }
) {
    open fun check() {
        val maxHeap = policy.maxHeapBytes
        if (maxHeap != null) {
            val used = memoryUsedBytesProvider()
            if (used > maxHeap) {
                throw ResourceLimitExceededException(
                    "used heap ($used bytes) exceeded max_rss_mib limit ($maxHeap bytes)"
                )
            }
        }
        val minFree = policy.minFreeDestinationBytes
        if (minFree != null) {
            val usable = try {
                freeSpaceBytesProvider(destinationDirectory)
            } catch (e: Exception) {
                throw ResourceLimitExceededException(
                    "unable to verify destination free space at $destinationDirectory: ${e.message}",
                    e
                )
            }
            if (usable < minFree) {
                throw ResourceLimitExceededException(
                    "destination usable space ($usable bytes) fell below minimum ($minFree bytes)"
                )
            }
        }
    }

    companion object {
        const val MIB: Long = 1024L * 1024L
    }
}
