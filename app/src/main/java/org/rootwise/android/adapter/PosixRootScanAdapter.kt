package org.rootwise.android.adapter

import org.rootwise.android.core.adapter.EntryObservationResult
import org.rootwise.android.core.adapter.RawDirectoryEntry
import org.rootwise.android.core.adapter.ScanSourceAdapter
import org.rootwise.android.core.model.AdapterCapabilities
import org.rootwise.android.core.model.Observation
import org.rootwise.android.core.model.PathCanonicalizer
import org.rootwise.android.core.model.VolumeInfo
import org.rootwise.android.core.model.VolumeUnmountedException
import org.rootwise.android.core.volume.VolumeResolver
import java.io.FileNotFoundException
import java.io.IOException
import java.nio.file.AccessDeniedException
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.NoSuchFileException
import java.nio.file.Path
import java.nio.file.attribute.BasicFileAttributes
import java.nio.file.attribute.DosFileAttributes
import java.nio.file.attribute.PosixFileAttributes
import java.util.concurrent.TimeUnit

data class PosixStatMetadata(
    val isSymbolicLink: Boolean,
    val isDirectory: Boolean,
    val isRegularFile: Boolean,
    val logicalBytes: Long,
    val createdNs: Long?,
    val modifiedNs: Long?,
    val accessedNs: Long?,
    val attributes: Int,
    val volumeIdentity: String? = null
)

interface PosixMetadataBackend {
    val usesRootHelper: Boolean
    fun isMounted(root: Path, expectedVolume: VolumeInfo): Boolean
    fun statNoFollow(path: Path): PosixStatMetadata
    fun listChildNames(directory: Path): List<String>
}

/**
 * Default non-following NIO/POSIX metadata backend using `LinkOption.NOFOLLOW_LINKS` (`lstat`).
 * Used when the process has direct POSIX access (e.g. `/storage/emulated/0`, root-context process,
 * or JVM unit test fixtures).
 */
class NioNoFollowPosixBackend(
    private val volumeResolver: (Path) -> VolumeInfo = { VolumeResolver.resolveVolume(it) },
    private val unreadablePaths: Set<Path> = emptySet(),
    private val mountStateSupplier: () -> Boolean = { true }
) : PosixMetadataBackend {
    override val usesRootHelper: Boolean = false

    override fun isMounted(root: Path, expectedVolume: VolumeInfo): Boolean {
        if (!mountStateSupplier()) return false
        if (!Files.exists(root, LinkOption.NOFOLLOW_LINKS)) return false
        return try {
            volumeResolver(root).identity == expectedVolume.identity
        } catch (_: Exception) {
            false
        }
    }

    override fun statNoFollow(path: Path): PosixStatMetadata {
        val normalized = path.toAbsolutePath().normalize()
        if (normalized in unreadablePaths && !Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
            throw AccessDeniedException(path.toString(), null, "Simulated permission denial")
        }
        val attrs = Files.readAttributes(path, BasicFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
        val isSymlink = attrs.isSymbolicLink || Files.isSymbolicLink(path)
        var rawAttrFlags = 0
        var targetIsDirectory = attrs.isDirectory
        if (!isSymlink) {
            try {
                val dos = Files.readAttributes(path, DosFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
                if (dos.isReadOnly) rawAttrFlags = rawAttrFlags or 0x1
                if (dos.isHidden) rawAttrFlags = rawAttrFlags or 0x2
                if (dos.isSystem) rawAttrFlags = rawAttrFlags or 0x4
                if (dos.isArchive) rawAttrFlags = rawAttrFlags or 0x20
            } catch (_: Throwable) {
            }
            try {
                val posix = Files.readAttributes(path, PosixFileAttributes::class.java, LinkOption.NOFOLLOW_LINKS)
                rawAttrFlags = posix.permissions().size
            } catch (_: Throwable) {
            }
        } else {
            rawAttrFlags = REPARSE_POINT_FLAG
            // Determine if symlink target is a directory metric without traversing into it
            targetIsDirectory = try {
                val target = Files.readSymbolicLink(path)
                val resolvedTarget = path.parent?.resolve(target) ?: target
                Files.isDirectory(resolvedTarget, LinkOption.NOFOLLOW_LINKS)
            } catch (_: Throwable) {
                false
            }
        }
        val volId = try {
            if (!isSymlink) volumeResolver(path).identity else null
        } catch (_: Throwable) {
            null
        }
        return PosixStatMetadata(
            isSymbolicLink = isSymlink,
            isDirectory = targetIsDirectory,
            isRegularFile = attrs.isRegularFile && !isSymlink,
            logicalBytes = if (attrs.isRegularFile && !isSymlink) attrs.size() else 0L,
            createdNs = attrs.creationTime()?.to(TimeUnit.NANOSECONDS),
            modifiedNs = attrs.lastModifiedTime()?.to(TimeUnit.NANOSECONDS),
            accessedNs = attrs.lastAccessTime()?.to(TimeUnit.NANOSECONDS),
            attributes = rawAttrFlags,
            volumeIdentity = volId
        )
    }

    override fun listChildNames(directory: Path): List<String> {
        val normalized = directory.toAbsolutePath().normalize()
        if (normalized in unreadablePaths) {
            throw AccessDeniedException(directory.toString(), null, "Simulated directory permission denial")
        }
        Files.newDirectoryStream(directory).use { stream ->
            val names = mutableListOf<String>()
            for (entry in stream) {
                names.add(entry.fileName.toString())
            }
            return names.sorted()
        }
    }

    companion object {
        const val REPARSE_POINT_FLAG = 0x400
    }
}

/**
 * Rooted Android `su --mount-master` metadata backend for paths requiring root elevation
 * (`/data`, `/data/media/0`, `/mnt/media_rw/<UUID>`) when the UI runs as unprivileged app UID.
 *
 * Strictly executes non-following `toybox stat` / `find -maxdepth 1` metadata queries;
 * NEVER reads file contents or mutates the filesystem.
 */
class RootShellPosixBackend(
    private val fallbackNio: NioNoFollowPosixBackend = NioNoFollowPosixBackend(),
    private val rootCommandRunner: (List<String>) -> RootCommandResult = ::defaultSuRunner
) : PosixMetadataBackend {
    override val usesRootHelper: Boolean = true

    data class RootCommandResult(val exitCode: Int, val stdout: String, val stderr: String)

    override fun isMounted(root: Path, expectedVolume: VolumeInfo): Boolean {
        if (Files.isReadable(root)) {
            return fallbackNio.isMounted(root, expectedVolume)
        }
        val escaped = shellSingleQuote(root.toString().replace('\\', '/'))
        val res = rootCommandRunner(listOf("su", "--mount-master", "-c", "toybox stat -c '%d' -- $escaped"))
        return res.exitCode == 0 && res.stdout.trim().isNotEmpty()
    }

    override fun statNoFollow(path: Path): PosixStatMetadata {
        if (Files.exists(path.parent ?: path, LinkOption.NOFOLLOW_LINKS) && Files.isReadable(path.parent ?: path)) {
            try {
                return fallbackNio.statNoFollow(path)
            } catch (_: AccessDeniedException) {
                // Fall through to root stat
            }
        }
        val posixPath = path.toString().replace('\\', '/')
        val escaped = shellSingleQuote(posixPath)
        val res = rootCommandRunner(
            listOf("su", "--mount-master", "-c", "toybox stat -c '%F|%s|%Y|%X|%Z|%d' -- $escaped")
        )
        if (res.exitCode != 0) {
            if (res.stderr.contains("No such file", ignoreCase = true)) {
                throw NoSuchFileException(posixPath)
            }
            throw IOException("root stat failed for $posixPath: ${res.stderr.trim()}")
        }
        return parseToyboxStatLine(res.stdout.trim())
    }

    override fun listChildNames(directory: Path): List<String> {
        if (Files.isReadable(directory)) {
            try {
                return fallbackNio.listChildNames(directory)
            } catch (_: AccessDeniedException) {
                // Fall through to root find
            }
        }
        val posixDir = directory.toString().replace('\\', '/')
        val escaped = shellSingleQuote(posixDir)
        val res = rootCommandRunner(
            listOf("su", "--mount-master", "-c", "toybox find $escaped -mindepth 1 -maxdepth 1")
        )
        if (res.exitCode != 0) {
            throw IOException("root directory listing failed for $posixDir: ${res.stderr.trim()}")
        }
        val prefix = if (posixDir.endsWith("/")) posixDir else "$posixDir/"
        return res.stdout.lineSequence()
            .map { it.trim() }
            .filter { it.isNotEmpty() && it.startsWith(prefix) }
            .map { it.removePrefix(prefix) }
            .filter { it.isNotEmpty() && !it.contains('/') }
            .sorted()
            .toList()
    }

    companion object {
        fun shellSingleQuote(raw: String): String =
            "'" + raw.replace("'", "'\\''") + "'"

        fun parseToyboxStatLine(line: String): PosixStatMetadata {
            val parts = line.split('|')
            if (parts.size < 6) {
                throw IOException("Malformed toybox stat output: $line")
            }
            val fileTypeDesc = parts[0].lowercase()
            val sizeBytes = parts[1].toLongOrNull() ?: 0L
            val mtimeSec = parts[2].toLongOrNull()
            val atimeSec = parts[3].toLongOrNull()
            val ctimeSec = parts[4].toLongOrNull()
            val devNum = parts[5].trim()

            val isSymlink = fileTypeDesc.contains("symbolic link")
            val isDir = fileTypeDesc.contains("directory") && !isSymlink
            val isReg = fileTypeDesc.contains("regular") && !isSymlink

            return PosixStatMetadata(
                isSymbolicLink = isSymlink,
                isDirectory = isDir,
                isRegularFile = isReg,
                logicalBytes = if (isReg) sizeBytes else 0L,
                createdNs = ctimeSec?.let { it * 1_000_000_000L },
                modifiedNs = mtimeSec?.let { it * 1_000_000_000L },
                accessedNs = atimeSec?.let { it * 1_000_000_000L },
                attributes = if (isSymlink) NioNoFollowPosixBackend.REPARSE_POINT_FLAG else 0,
                volumeIdentity = if (devNum.isNotEmpty()) "posix-device:$devNum" else null
            )
        }

        private fun defaultSuRunner(cmd: List<String>): RootCommandResult {
            val proc = ProcessBuilder(cmd).start()
            val stdout = proc.inputStream.bufferedReader().readText()
            val stderr = proc.errorStream.bufferedReader().readText()
            val code = proc.waitFor()
            return RootCommandResult(code, stdout, stderr)
        }
    }
}

/**
 * Primary POSIX/Root scanner adapter for rooted Android phones and local POSIX/JVM fixtures.
 *
 * Enforces:
 * - Component-by-component non-following directory validation (`O_NOFOLLOW` / `NOFOLLOW_LINKS` equivalent).
 * - Volume boundary verification (`st_dev` / `VolumeInfo.identity`) on every queued directory.
 * - Stage 0.21 fresh `lstat` at the `observeEntry` boundary.
 */
class PosixRootScanAdapter(
    rootPath: Path,
    private val backend: PosixMetadataBackend = NioNoFollowPosixBackend(),
    private val volumeOverride: VolumeInfo? = null,
    private val beforeObserveHook: ((String) -> Unit)? = null
) : ScanSourceAdapter {
    val root: Path = if (Files.exists(rootPath, LinkOption.NOFOLLOW_LINKS)) {
        rootPath.toRealPath(LinkOption.NOFOLLOW_LINKS)
    } else {
        rootPath.toAbsolutePath().normalize()
    }

    override val sourceRoot: String = root.toString()

    private val cachedVolume: VolumeInfo by lazy {
        volumeOverride ?: VolumeResolver.resolveVolume(root)
    }

    override fun resolveVolume(): VolumeInfo = cachedVolume

    override fun capabilities(): AdapterCapabilities = AdapterCapabilities(
        adapterType = if (backend.usesRootHelper) "POSIX_ROOT_SU" else "POSIX_NOFOLLOW",
        nofollowEnforced = true,
        kernelStDevEnforced = true,
        freshStatEnforced = true,
        rootAccessUsed = backend.usesRootHelper,
        blindSpots = emptyList()
    )

    override fun isVolumeMounted(): Boolean = backend.isMounted(root, cachedVolume)

    override fun listDirectory(relativeDir: String): Sequence<RawDirectoryEntry> {
        if (!isVolumeMounted()) {
            throw VolumeUnmountedException(relativeDir, "source volume ${cachedVolume.identity} unmounted")
        }
        val targetDir = verifyAndResolveDirectoryChain(relativeDir)
        val childNames = backend.listChildNames(targetDir)
        return childNames.asSequence().map { name ->
            val childRelative = if (relativeDir.isEmpty()) name else "$relativeDir/$name"
            RawDirectoryEntry(name = name, handleId = childRelative)
        }
    }

    override fun observeEntry(relativeDir: String, entry: RawDirectoryEntry): EntryObservationResult {
        val relative = PathCanonicalizer.inventoryPath(
            if (relativeDir.isEmpty()) entry.name else "$relativeDir/${entry.name}"
        )
        beforeObserveHook?.invoke(relative)

        if (!isVolumeMounted()) {
            throw VolumeUnmountedException(relative, "source volume ${cachedVolume.identity} unmounted before stat")
        }

        val entryPath = if (relativeDir.isEmpty()) {
            root.resolve(entry.name)
        } else {
            var current = root
            for (part in relativeDir.split('/').filter { it.isNotEmpty() }) {
                current = current.resolve(part)
            }
            current.resolve(entry.name)
        }

        // Stage 0.21: Fresh non-following metadata lookup at the observation boundary
        val metadata = backend.statNoFollow(entryPath)
        val linkLike = metadata.isSymbolicLink || (metadata.attributes and NioNoFollowPosixBackend.REPARSE_POINT_FLAG) != 0
        val entryType = when {
            linkLike -> if (metadata.isDirectory) "SYMLINK_DIRECTORY" else "SYMLINK"
            metadata.isDirectory -> "DIRECTORY"
            metadata.isRegularFile -> "FILE"
            else -> "OTHER"
        }

        if (!linkLike && metadata.isDirectory && metadata.volumeIdentity != null &&
            metadata.volumeIdentity != cachedVolume.identity
        ) {
            throw IOException("directory escaped authorized volume (${metadata.volumeIdentity} != ${cachedVolume.identity}): $relative")
        }

        val parent = if (relativeDir.isEmpty()) null else PathCanonicalizer.inventoryPath(relativeDir)
        val display = if (relativeDir.isEmpty()) entry.name else "$relativeDir/${entry.name}"
        val observation = Observation(
            relativePath = relative,
            comparisonPath = PathCanonicalizer.comparisonPath(relative),
            parentPath = parent,
            name = entry.name,
            extension = if (entryType == "DIRECTORY" || entryType == "SYMLINK_DIRECTORY") {
                PathCanonicalizer.extractExtension(entry.name)
            } else {
                PathCanonicalizer.extractExtension(entry.name)
            },
            entryType = entryType,
            logicalBytes = if (entryType == "FILE") metadata.logicalBytes else 0L,
            createdNs = metadata.createdNs,
            modifiedNs = metadata.modifiedNs,
            accessedNs = metadata.accessedNs,
            attributes = metadata.attributes,
            depth = PathCanonicalizer.depthOf(relative),
            displayPath = display,
            observationStatus = "OBSERVED"
        )
        val traversable = metadata.isDirectory && !linkLike
        return EntryObservationResult(observation = observation, traversableDirectory = traversable)
    }

    /**
     * Verifies every path component from [root] down to [relativeDir] without following symlinks,
     * rejecting link-like directories or mount-point crossings (`st_dev` mismatch).
     */
    private fun verifyAndResolveDirectoryChain(relativeDir: String): Path {
        var current = root
        val rootStat = backend.statNoFollow(current)
        if (rootStat.isSymbolicLink || !rootStat.isDirectory) {
            throw IOException("source root is link-like or not a directory: $current")
        }
        if (rootStat.volumeIdentity != null && rootStat.volumeIdentity != cachedVolume.identity) {
            throw IOException("source root volume identity changed: ${rootStat.volumeIdentity}")
        }
        if (relativeDir.isEmpty()) {
            return current
        }
        val cleanRelative = PathCanonicalizer.inventoryPath(relativeDir)
        for (component in cleanRelative.split('/')) {
            current = current.resolve(component)
            val stat = backend.statNoFollow(current)
            if (stat.isSymbolicLink || !stat.isDirectory) {
                throw IOException("queued path is link-like or not a directory: $current")
            }
            if (stat.volumeIdentity != null && stat.volumeIdentity != cachedVolume.identity) {
                throw IOException("queued directory escaped the authorized volume: $current")
            }
        }
        return current
    }
}
