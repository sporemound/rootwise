package org.rootwise.android.core.guard

import org.rootwise.android.core.model.BoundaryViolationException
import org.rootwise.android.core.model.PathCanonicalizer
import org.rootwise.android.core.model.ScanStateException
import org.rootwise.android.core.model.VolumeIdentityException
import org.rootwise.android.core.model.VolumeInfo
import org.rootwise.android.core.model.VolumeSeparationMode
import java.io.Closeable
import java.io.OutputStream
import java.io.RandomAccessFile
import java.nio.channels.FileLock
import java.nio.channels.OverlappingFileLockException
import java.nio.file.FileAlreadyExistsException
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import java.util.concurrent.ConcurrentHashMap

/**
 * Central authorization point for every audit-scanner write path.
 * Port of `src/rootwise/write_guard.py` with the approved Android `userdata`
 * disjoint-subtree and self-exclusion guard (see `docs/PORTING-NOTES-ANDROID.md`).
 */
class WriteGuard(
    val sourceVolume: VolumeInfo,
    allowedRootPath: Path,
    val destinationVolume: VolumeInfo,
    val allowSameVolumeDisjointSubtree: Boolean = false,
    private val sourceRootPath: Path? = null,
    private val volumeResolver: (Path) -> VolumeInfo
) {
    val allowedRoot: Path
    val separationMode: VolumeSeparationMode

    init {
        if (Files.isSymbolicLink(allowedRootPath)) {
            throw BoundaryViolationException("write root is link-like: $allowedRootPath")
        }
        if (!Files.exists(allowedRootPath, LinkOption.NOFOLLOW_LINKS) ||
            !Files.isDirectory(allowedRootPath, LinkOption.NOFOLLOW_LINKS)
        ) {
            throw BoundaryViolationException("write root is not a directory: $allowedRootPath")
        }
        allowedRoot = allowedRootPath.toRealPath(LinkOption.NOFOLLOW_LINKS)
        separationMode = validateVolumesAndSubtrees(
            sourceVolume = sourceVolume,
            destinationVolume = destinationVolume,
            allowSameVolumeDisjointSubtree = allowSameVolumeDisjointSubtree,
            sourceRootPath = sourceRootPath,
            allowedRoot = allowedRoot
        )
    }

    fun authorize(candidatePath: Path): Path {
        val absolute = if (candidatePath.isAbsolute) candidatePath else allowedRoot.resolve(candidatePath)
        val parent = absolute.parent
            ?: throw BoundaryViolationException("write target has no parent directory: $absolute")
        if (!Files.exists(parent, LinkOption.NOFOLLOW_LINKS) ||
            Files.isSymbolicLink(parent)
        ) {
            throw BoundaryViolationException("write parent does not exist or is link-like: $parent")
        }
        val realParent = parent.toRealPath(LinkOption.NOFOLLOW_LINKS)
        val resolved = realParent.resolve(absolute.fileName)
        if (!resolved.startsWith(allowedRoot)) {
            throw BoundaryViolationException("write escapes approved root: $resolved")
        }
        val currentDestination = volumeResolver(realParent)
        if (currentDestination.identity != destinationVolume.identity) {
            throw BoundaryViolationException("write path changed destination volume: ${currentDestination.identity}")
        }
        validateVolumesAndSubtrees(
            sourceVolume = sourceVolume,
            destinationVolume = currentDestination,
            allowSameVolumeDisjointSubtree = allowSameVolumeDisjointSubtree,
            sourceRootPath = sourceRootPath,
            allowedRoot = allowedRoot
        )
        return resolved
    }

    fun verifyExisting(candidatePath: Path): Path {
        val authorized = authorize(candidatePath)
        if (Files.isSymbolicLink(authorized)) {
            throw BoundaryViolationException("write target is link-like: $authorized")
        }
        if (!Files.exists(authorized, LinkOption.NOFOLLOW_LINKS)) {
            throw BoundaryViolationException("write target does not exist: $authorized")
        }
        val realTarget = authorized.toRealPath(LinkOption.NOFOLLOW_LINKS)
        if (!realTarget.startsWith(allowedRoot)) {
            throw BoundaryViolationException("write target resolves outside approved root: $realTarget")
        }
        if (!Files.isRegularFile(realTarget, LinkOption.NOFOLLOW_LINKS)) {
            throw BoundaryViolationException("write target is not a regular file: $realTarget")
        }
        val currentDestination = volumeResolver(realTarget)
        if (currentDestination.identity != destinationVolume.identity) {
            throw BoundaryViolationException("opened write target is on an unauthorized volume")
        }
        return realTarget
    }

    fun authorizeSqliteJournal(databasePath: Path): Path {
        val journalCandidate = Path.of(databasePath.toString() + "-journal")
        val authorized = authorize(journalCandidate)
        if (Files.isSymbolicLink(authorized)) {
            throw BoundaryViolationException("SQLite journal path is link-like: $authorized")
        }
        return authorized
    }

    fun openDatabaseLease(databasePath: Path): DatabaseLease {
        val leaseCandidate = Path.of(databasePath.toString() + "-scanlock")
        val authorized = authorize(leaseCandidate)
        if (Files.isSymbolicLink(authorized)) {
            throw BoundaryViolationException("database lease path is link-like: $authorized")
        }
        if (!Files.exists(authorized, LinkOption.NOFOLLOW_LINKS)) {
            Files.newByteChannel(
                authorized,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE
            ).use { channel ->
                channel.write(java.nio.ByteBuffer.wrap(byteArrayOf(0)))
            }
        }
        verifyExisting(authorized)
        val canonicalKey = authorized.toString()
        if (!ACTIVE_PROCESS_LEASES.add(canonicalKey)) {
            throw ScanStateException("inventory database is already leased in this process: $authorized")
        }
        var raf: RandomAccessFile? = null
        var lock: FileLock? = null
        try {
            raf = RandomAccessFile(authorized.toFile(), "rw")
            if (raf.length() == 0L) {
                raf.writeByte(0)
                raf.fd.sync()
            }
            lock = try {
                raf.channel.tryLock(0L, 1L, false)
            } catch (e: OverlappingFileLockException) {
                null
            }
            if (lock == null) {
                throw ScanStateException("inventory database is already leased by another process")
            }
            return DatabaseLease(canonicalKey, raf, lock)
        } catch (t: Throwable) {
            try {
                lock?.release()
            } catch (_: Throwable) {
            }
            try {
                raf?.close()
            } catch (_: Throwable) {
            }
            ACTIVE_PROCESS_LEASES.remove(canonicalKey)
            if (t is ScanStateException || t is BoundaryViolationException) throw t
            throw ScanStateException("inventory database is already leased by another process", t)
        }
    }

    fun <T> openNewBinary(path: Path, writer: (Path, OutputStream) -> T): T {
        val authorized = authorize(path)
        if (Files.isSymbolicLink(authorized) || Files.exists(authorized, LinkOption.NOFOLLOW_LINKS)) {
            throw BoundaryViolationException("output file must not already exist: $authorized")
        }
        val stream = try {
            Files.newOutputStream(authorized, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)
        } catch (e: FileAlreadyExistsException) {
            throw BoundaryViolationException("output file already exists: $authorized", e)
        }
        return stream.use { out ->
            val verified = verifyExisting(authorized)
            writer(verified, out)
        }
    }

    /**
     * Computes normalized relative paths under [sourceRoot] that must be hard-excluded
     * before directory traversal so the scanner never observes or mutates its own
     * artifact directory when scanning a parent partition (such as `/data` on a rooted phone).
     */
    fun excludedRelativeSubtrees(sourceRoot: Path): Set<String> {
        val realSource = if (Files.exists(sourceRoot, LinkOption.NOFOLLOW_LINKS)) {
            sourceRoot.toRealPath(LinkOption.NOFOLLOW_LINKS)
        } else {
            sourceRoot.normalize()
        }
        val excluded = linkedSetOf<String>()
        if (allowedRoot.startsWith(realSource) && allowedRoot != realSource) {
            val rel = realSource.relativize(allowedRoot).toString().replace('\\', '/')
            excluded.add(PathCanonicalizer.inventoryPath(rel))
        }
        val realSourcePosix = realSource.toString().replace('\\', '/').trimEnd('/')
        for (protectedAbs in ANDROID_SELF_ARTIFACT_DIRS) {
            if (protectedAbs.startsWith("$realSourcePosix/")) {
                val rel = protectedAbs.removePrefix("$realSourcePosix/")
                if (rel.isNotEmpty()) {
                    excluded.add(PathCanonicalizer.inventoryPath(rel))
                }
            }
        }
        return excluded
    }

    class DatabaseLease(
        private val canonicalKey: String,
        private val raf: RandomAccessFile,
        private val lock: FileLock
    ) : Closeable {
        @Volatile
        private var closed = false

        override fun close() {
            if (closed) return
            closed = true
            try {
                if (lock.isValid) {
                    lock.release()
                }
            } catch (_: Throwable) {
            } finally {
                try {
                    raf.close()
                } catch (_: Throwable) {
                }
                ACTIVE_PROCESS_LEASES.remove(canonicalKey)
            }
        }
    }

    companion object {
        private val ACTIVE_PROCESS_LEASES = ConcurrentHashMap.newKeySet<String>()

        val ANDROID_SELF_ARTIFACT_DIRS = listOf(
            "/data/data/org.rootwise.android",
            "/data/user/0/org.rootwise.android",
            "/data/user_de/0/org.rootwise.android",
            "/storage/emulated/0/Android/data/org.rootwise.android",
            "/sdcard/Android/data/org.rootwise.android"
        )

        fun validateVolumesAndSubtrees(
            sourceVolume: VolumeInfo,
            destinationVolume: VolumeInfo,
            allowSameVolumeDisjointSubtree: Boolean,
            sourceRootPath: Path?,
            allowedRoot: Path
        ): VolumeSeparationMode {
            if (sourceVolume.identity.isBlank() || destinationVolume.identity.isBlank()) {
                throw VolumeIdentityException("empty volume identity is not an authorization boundary")
            }
            if (sourceVolume.identity != destinationVolume.identity) {
                return VolumeSeparationMode.STRICT_DISTINCT_VOLUME
            }
            if (!allowSameVolumeDisjointSubtree) {
                throw VolumeIdentityException("database/output destination is on the source volume")
            }
            val sourceRoot = sourceRootPath
                ?: throw BoundaryViolationException(
                    "same-volume disjoint-subtree guard requires an explicit sourceRootPath"
                )
            val normalizedSource = if (Files.exists(sourceRoot, LinkOption.NOFOLLOW_LINKS)) {
                sourceRoot.toRealPath(LinkOption.NOFOLLOW_LINKS)
            } else {
                sourceRoot.toAbsolutePath().normalize()
            }
            if (normalizedSource.startsWith(allowedRoot)) {
                throw BoundaryViolationException(
                    "source root ($normalizedSource) cannot be equal to or inside allowed artifact root ($allowedRoot)"
                )
            }
            return VolumeSeparationMode.SAME_VOLUME_DISJOINT_SUBTREE
        }
    }
}
