package org.rootwise.android.core.volume

import org.rootwise.android.core.model.VolumeIdentityException
import org.rootwise.android.core.model.VolumeInfo
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path

/**
 * Fail-closed OS volume identity resolution.
 * Port of `src/rootwise/volume.py` with `/proc/mounts` parsing for rooted Android/Linux
 * and `FileStore` / POSIX `dev` resolution.
 */
object VolumeResolver {
    fun resolveVolume(
        path: Path,
        procMountsSupplier: () -> String? = ::defaultProcMounts
    ): VolumeInfo {
        val probe = existingProbe(path)
        return try {
            val unixDev = try {
                val attr = Files.getAttribute(probe, "unix:dev", LinkOption.NOFOLLOW_LINKS)
                (attr as? Number)?.toLong()
            } catch (_: Throwable) {
                null
            }
            if (unixDev != null) {
                var mount = probe
                while (mount.parent != null && mount.parent != mount) {
                    val parentDev = try {
                        (Files.getAttribute(mount.parent, "unix:dev", LinkOption.NOFOLLOW_LINKS) as? Number)?.toLong()
                    } catch (e: Exception) {
                        throw VolumeIdentityException("mount identity resolution failed: ${e.message}", e)
                    }
                    if (parentDev != unixDev) break
                    mount = mount.parent
                }
                val mountStr = mount.toString().replace('\\', '/')
                val fsType = parseLinuxFilesystemType(mountStr, procMountsSupplier())
                return VolumeInfo(
                    identity = "posix-device:$unixDev",
                    mountPath = mountStr,
                    filesystemType = fsType,
                    device = unixDev.toString()
                )
            }

            // Fallback on non-POSIX host JVM (e.g. Windows test host) using FileStore + root component
            val store = Files.getFileStore(probe)
            val root = probe.root ?: throw VolumeIdentityException("path has no volume root: $probe")
            val storeType = store.type().ifBlank { null }
            val storeName = store.name().ifBlank { root.toString() }
            val identityKey = "filestore:${root.toString().trimEnd('\\', '/').lowercase()}:${storeType ?: "unknown"}"
            VolumeInfo(
                identity = identityKey,
                mountPath = root.toString(),
                filesystemType = storeType,
                device = storeName
            )
        } catch (e: VolumeIdentityException) {
            throw e
        } catch (e: Exception) {
            throw VolumeIdentityException("stat/FileStore failed for volume probe $path: ${e.message}", e)
        }
    }

    fun existingProbe(path: Path): Path {
        val absolute = if (path.isAbsolute) path.normalize() else Path.of("").toAbsolutePath().resolve(path).normalize()
        var probe: Path? = absolute
        while (probe != null && !Files.exists(probe, LinkOption.NOFOLLOW_LINKS)) {
            val parent = probe.parent
            if (parent == null || parent == probe) {
                throw VolumeIdentityException("no existing ancestor for path: $path")
            }
            probe = parent
        }
        return probe ?: throw VolumeIdentityException("no existing ancestor for path: $path")
    }

    fun parseLinuxFilesystemType(mountPath: String, procMountsContent: String?): String? {
        if (procMountsContent.isNullOrBlank()) return null
        var bestLength = -1
        var bestFsType: String? = null
        for (line in procMountsContent.lineSequence()) {
            val parts = line.trim().split(Regex("\\s+"))
            if (parts.size >= 3) {
                val mountedAt = parts[1].replace("\\040", " ")
                if (mountedAt == mountPath && mountedAt.length >= bestLength) {
                    bestLength = mountedAt.length
                    bestFsType = parts[2]
                }
            }
        }
        return bestFsType
    }

    /**
     * Parses `/proc/mounts` on a rooted Android device to surface candidate physical/logical
     * mount points (`/data`, `/data/media/0`, `/mnt/media_rw/<UUID>`, `/storage/<UUID>`).
     */
    fun discoverAndroidMounts(procMountsContent: String?): List<VolumeInfo> {
        if (procMountsContent.isNullOrBlank()) return emptyList()
        val discovered = mutableListOf<VolumeInfo>()
        val seenMounts = mutableSetOf<String>()
        val relevantPrefixes = listOf("/data", "/mnt/media_rw/", "/storage/")
        val ignoredFsTypes = setOf("proc", "sysfs", "selinuxfs", "cgroup", "cgroup2", "devpts", "pstore", "bpf", "tracefs")

        for (line in procMountsContent.lineSequence()) {
            val parts = line.trim().split(Regex("\\s+"))
            if (parts.size >= 3) {
                val device = parts[0]
                val mountedAt = parts[1].replace("\\040", " ")
                val fsType = parts[2]
                if (fsType in ignoredFsTypes) continue
                if (relevantPrefixes.any { mountedAt == it || mountedAt.startsWith(it) } && seenMounts.add(mountedAt)) {
                    discovered.add(
                        VolumeInfo(
                            identity = "posix-mount:$device@$mountedAt",
                            mountPath = mountedAt,
                            filesystemType = fsType,
                            device = device
                        )
                    )
                }
            }
        }
        return discovered
    }

    private fun defaultProcMounts(): String? {
        val procMounts = Path.of("/proc/mounts")
        if (!Files.isRegularFile(procMounts)) return null
        return try {
            String(Files.readAllBytes(procMounts), Charsets.UTF_8)
        } catch (_: Exception) {
            null
        }
    }
}
