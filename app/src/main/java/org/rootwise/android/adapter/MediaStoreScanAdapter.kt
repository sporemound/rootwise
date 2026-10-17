package org.rootwise.android.adapter

import android.content.ContentResolver
import android.provider.MediaStore
import org.rootwise.android.core.adapter.EntryObservationResult
import org.rootwise.android.core.adapter.RawDirectoryEntry
import org.rootwise.android.core.adapter.ScanSourceAdapter
import org.rootwise.android.core.model.AdapterCapabilities
import org.rootwise.android.core.model.Observation
import org.rootwise.android.core.model.PathCanonicalizer
import org.rootwise.android.core.model.VolumeInfo
import java.io.FileNotFoundException

data class MediaStoreEntryRow(
    val id: Long,
    val relativeDirectoryPath: String,
    val displayName: String,
    val sizeBytes: Long,
    val dateModifiedSeconds: Long?,
    val dateAddedSeconds: Long?
)

interface MediaStoreClient {
    val volumeName: String
    fun isVolumeAvailable(): Boolean
    fun queryAllEntries(): List<MediaStoreEntryRow>
    fun queryEntryById(id: Long): MediaStoreEntryRow?
}

/**
 * Android runtime [MediaStoreClient] querying [MediaStore.Files] metadata columns only.
 */
class AndroidMediaStoreClient(
    private val contentResolver: ContentResolver,
    override val volumeName: String = MediaStore.VOLUME_EXTERNAL_PRIMARY
) : MediaStoreClient {
    private val contentUri = MediaStore.Files.getContentUri(volumeName)

    override fun isVolumeAvailable(): Boolean {
        return try {
            val cursor = contentResolver.query(
                contentUri,
                arrayOf(MediaStore.Files.FileColumns._ID),
                null,
                null,
                null
            )
            val available = cursor != null
            cursor?.close()
            available
        } catch (_: Throwable) {
            false
        }
    }

    override fun queryAllEntries(): List<MediaStoreEntryRow> {
        val results = mutableListOf<MediaStoreEntryRow>()
        contentResolver.query(contentUri, PROJECTION, null, null, null)?.use { cursor ->
            val idIdx = cursor.getColumnIndex(MediaStore.Files.FileColumns._ID)
            val relIdx = cursor.getColumnIndex(MediaStore.Files.FileColumns.RELATIVE_PATH)
            val nameIdx = cursor.getColumnIndex(MediaStore.Files.FileColumns.DISPLAY_NAME)
            val sizeIdx = cursor.getColumnIndex(MediaStore.Files.FileColumns.SIZE)
            val modIdx = cursor.getColumnIndex(MediaStore.Files.FileColumns.DATE_MODIFIED)
            val addIdx = cursor.getColumnIndex(MediaStore.Files.FileColumns.DATE_ADDED)
            while (cursor.moveToNext()) {
                val id = if (idIdx >= 0 && !cursor.isNull(idIdx)) cursor.getLong(idIdx) else continue
                val rel = if (relIdx >= 0 && !cursor.isNull(relIdx)) cursor.getString(relIdx) else ""
                val name = if (nameIdx >= 0 && !cursor.isNull(nameIdx)) cursor.getString(nameIdx) else continue
                val size = if (sizeIdx >= 0 && !cursor.isNull(sizeIdx)) cursor.getLong(sizeIdx) else 0L
                val mod = if (modIdx >= 0 && !cursor.isNull(modIdx)) cursor.getLong(modIdx) else null
                val add = if (addIdx >= 0 && !cursor.isNull(addIdx)) cursor.getLong(addIdx) else null
                results.add(
                    MediaStoreEntryRow(
                        id = id,
                        relativeDirectoryPath = PathCanonicalizer.inventoryPath(rel.trim('/')),
                        displayName = name,
                        sizeBytes = size,
                        dateModifiedSeconds = mod,
                        dateAddedSeconds = add
                    )
                )
            }
        }
        return results
    }

    override fun queryEntryById(id: Long): MediaStoreEntryRow? {
        val sel = "${MediaStore.Files.FileColumns._ID}=?"
        val args = arrayOf(id.toString())
        contentResolver.query(contentUri, PROJECTION, sel, args, null)?.use { cursor ->
            if (!cursor.moveToFirst()) return null
            val relIdx = cursor.getColumnIndex(MediaStore.Files.FileColumns.RELATIVE_PATH)
            val nameIdx = cursor.getColumnIndex(MediaStore.Files.FileColumns.DISPLAY_NAME)
            val sizeIdx = cursor.getColumnIndex(MediaStore.Files.FileColumns.SIZE)
            val modIdx = cursor.getColumnIndex(MediaStore.Files.FileColumns.DATE_MODIFIED)
            val addIdx = cursor.getColumnIndex(MediaStore.Files.FileColumns.DATE_ADDED)
            val rel = if (relIdx >= 0 && !cursor.isNull(relIdx)) cursor.getString(relIdx) else ""
            val name = if (nameIdx >= 0 && !cursor.isNull(nameIdx)) cursor.getString(nameIdx) else return null
            val size = if (sizeIdx >= 0 && !cursor.isNull(sizeIdx)) cursor.getLong(sizeIdx) else 0L
            val mod = if (modIdx >= 0 && !cursor.isNull(modIdx)) cursor.getLong(modIdx) else null
            val add = if (addIdx >= 0 && !cursor.isNull(addIdx)) cursor.getLong(addIdx) else null
            return MediaStoreEntryRow(
                id = id,
                relativeDirectoryPath = PathCanonicalizer.inventoryPath(rel.trim('/')),
                displayName = name,
                sizeBytes = size,
                dateModifiedSeconds = mod,
                dateAddedSeconds = add
            )
        }
        return null
    }

    companion object {
        private val PROJECTION = arrayOf(
            MediaStore.Files.FileColumns._ID,
            MediaStore.Files.FileColumns.RELATIVE_PATH,
            MediaStore.Files.FileColumns.DISPLAY_NAME,
            MediaStore.Files.FileColumns.SIZE,
            MediaStore.Files.FileColumns.DATE_MODIFIED,
            MediaStore.Files.FileColumns.DATE_ADDED
        )
    }
}

/**
 * MediaStore metadata adapter implementing [ScanSourceAdapter].
 * Synthesizes directory hierarchy from indexed `RELATIVE_PATH` values without touching file contents.
 */
class MediaStoreScanAdapter(
    private val client: MediaStoreClient
) : ScanSourceAdapter {
    override val sourceRoot: String = "content://media/${client.volumeName}/file"

    private val indexedTree by lazy { buildHierarchy(client.queryAllEntries()) }

    override fun resolveVolume(): VolumeInfo = VolumeInfo(
        identity = "android-mediastore:${client.volumeName}",
        mountPath = sourceRoot,
        filesystemType = "mediastore-index",
        device = client.volumeName
    )

    override fun capabilities(): AdapterCapabilities = AdapterCapabilities(
        adapterType = "ANDROID_MEDIASTORE",
        nofollowEnforced = false,
        kernelStDevEnforced = false,
        freshStatEnforced = false,
        rootAccessUsed = false,
        blindSpots = MEDIASTORE_BLIND_SPOTS
    )

    override fun isVolumeMounted(): Boolean = client.isVolumeAvailable()

    override fun listDirectory(relativeDir: String): Sequence<RawDirectoryEntry> {
        val cleanRel = PathCanonicalizer.inventoryPath(relativeDir)
        val childDirs = indexedTree.childDirectoriesByParent[cleanRel].orEmpty()
        val childFiles = indexedTree.filesByParent[cleanRel].orEmpty()
        val entries = mutableListOf<RawDirectoryEntry>()
        for (dirName in childDirs.sorted()) {
            entries.add(RawDirectoryEntry(name = dirName, handleId = "dir:$cleanRel/$dirName".trimStart('/')))
        }
        for (fileRow in childFiles.sortedBy { it.displayName }) {
            entries.add(RawDirectoryEntry(name = fileRow.displayName, handleId = "file:${fileRow.id}"))
        }
        return entries.asSequence()
    }

    override fun observeEntry(relativeDir: String, entry: RawDirectoryEntry): EntryObservationResult {
        val relative = PathCanonicalizer.inventoryPath(
            if (relativeDir.isEmpty()) entry.name else "$relativeDir/${entry.name}"
        )
        val parent = if (relativeDir.isEmpty()) null else PathCanonicalizer.inventoryPath(relativeDir)
        val display = if (relativeDir.isEmpty()) entry.name else "$relativeDir/${entry.name}"

        if (entry.handleId.startsWith("dir:")) {
            val obs = Observation(
                relativePath = relative,
                comparisonPath = PathCanonicalizer.comparisonPath(relative),
                parentPath = parent,
                name = entry.name,
                extension = PathCanonicalizer.extractExtension(entry.name),
                entryType = "DIRECTORY",
                logicalBytes = 0L,
                createdNs = null,
                modifiedNs = null,
                accessedNs = null,
                attributes = 0,
                depth = PathCanonicalizer.depthOf(relative),
                displayPath = display,
                observationStatus = "OBSERVED"
            )
            return EntryObservationResult(observation = obs, traversableDirectory = true)
        }

        val id = entry.handleId.removePrefix("file:").toLongOrNull()
            ?: throw FileNotFoundException("Invalid MediaStore handleId: ${entry.handleId}")
        val fresh = client.queryEntryById(id)
            ?: throw FileNotFoundException("MediaStore row disappeared before observation: $relative (id=$id)")

        val obs = Observation(
            relativePath = relative,
            comparisonPath = PathCanonicalizer.comparisonPath(relative),
            parentPath = parent,
            name = entry.name,
            extension = PathCanonicalizer.extractExtension(entry.name),
            entryType = "FILE",
            logicalBytes = fresh.sizeBytes,
            createdNs = fresh.dateAddedSeconds?.let { it * 1_000_000_000L },
            modifiedNs = fresh.dateModifiedSeconds?.let { it * 1_000_000_000L },
            accessedNs = null,
            attributes = 0,
            depth = PathCanonicalizer.depthOf(relative),
            displayPath = display,
            observationStatus = "OBSERVED"
        )
        return EntryObservationResult(observation = obs, traversableDirectory = false)
    }

    private class HierarchyIndex(
        val childDirectoriesByParent: Map<String, Set<String>>,
        val filesByParent: Map<String, List<MediaStoreEntryRow>>
    )

    private fun buildHierarchy(rows: List<MediaStoreEntryRow>): HierarchyIndex {
        val dirsByParent = HashMap<String, MutableSet<String>>()
        val filesByParent = HashMap<String, MutableList<MediaStoreEntryRow>>()
        for (row in rows) {
            val relDir = PathCanonicalizer.inventoryPath(row.relativeDirectoryPath)
            if (relDir.isNotEmpty()) {
                val parts = relDir.split('/')
                var parent = ""
                for (part in parts) {
                    dirsByParent.getOrPut(parent) { linkedSetOf() }.add(part)
                    parent = if (parent.isEmpty()) part else "$parent/$part"
                }
            }
            filesByParent.getOrPut(relDir) { mutableListOf() }.add(row)
        }
        return HierarchyIndex(dirsByParent, filesByParent)
    }

    companion object {
        val MEDIASTORE_BLIND_SPOTS = listOf(
            "Android/data and Android/obb directories",
            ".nomedia directories and non-indexed system/app directories",
            "Non-media files owned by other packages when storage permissions are scoped"
        )
    }
}
