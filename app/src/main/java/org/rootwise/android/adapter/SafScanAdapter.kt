package org.rootwise.android.adapter

import android.content.ContentResolver
import android.net.Uri
import android.provider.DocumentsContract
import org.rootwise.android.core.adapter.EntryObservationResult
import org.rootwise.android.core.adapter.RawDirectoryEntry
import org.rootwise.android.core.adapter.ScanSourceAdapter
import org.rootwise.android.core.model.AdapterCapabilities
import org.rootwise.android.core.model.Observation
import org.rootwise.android.core.model.PathCanonicalizer
import org.rootwise.android.core.model.VolumeInfo
import org.rootwise.android.core.model.VolumeUnmountedException
import java.io.FileNotFoundException
import java.io.IOException

data class SafDocumentRow(
    val documentId: String,
    val displayName: String,
    val mimeType: String,
    val sizeBytes: Long,
    val lastModifiedMs: Long?,
    val flags: Int
) {
    val isDirectory: Boolean
        get() = mimeType == DocumentsContract.Document.MIME_TYPE_DIR ||
            mimeType == "vnd.android.document/directory"
}

interface SafTreeClient {
    val authority: String
    val treeDocumentId: String
    val treeUriString: String
    fun isTreeAccessible(): Boolean
    fun listChildren(parentDocumentId: String): List<SafDocumentRow>
    fun statDocument(documentId: String): SafDocumentRow?
}

/**
 * Android runtime [SafTreeClient] backed by [ContentResolver] and [DocumentsContract].
 * Strictly queries metadata columns (`COLUMN_DOCUMENT_ID`, `COLUMN_DISPLAY_NAME`,
 * `COLUMN_MIME_TYPE`, `COLUMN_SIZE`, `COLUMN_LAST_MODIFIED`, `COLUMN_FLAGS`).
 * Never opens input/output streams or file descriptors.
 */
class AndroidSafTreeClient(
    private val contentResolver: ContentResolver,
    private val treeUri: Uri
) : SafTreeClient {
    override val authority: String = treeUri.authority ?: "unknown"
    override val treeDocumentId: String = DocumentsContract.getTreeDocumentId(treeUri)
    override val treeUriString: String = treeUri.toString()

    override fun isTreeAccessible(): Boolean {
        return try {
            statDocument(treeDocumentId) != null
        } catch (_: Exception) {
            false
        }
    }

    override fun listChildren(parentDocumentId: String): List<SafDocumentRow> {
        val childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, parentDocumentId)
        val rows = mutableListOf<SafDocumentRow>()
        contentResolver.query(childrenUri, PROJECTION, null, null, null)?.use { cursor ->
            val idIdx = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DOCUMENT_ID)
            val nameIdx = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DISPLAY_NAME)
            val mimeIdx = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_MIME_TYPE)
            val sizeIdx = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_SIZE)
            val modIdx = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_LAST_MODIFIED)
            val flagsIdx = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_FLAGS)
            while (cursor.moveToNext()) {
                val docId = if (idIdx >= 0 && !cursor.isNull(idIdx)) cursor.getString(idIdx) else continue
                val name = if (nameIdx >= 0 && !cursor.isNull(nameIdx)) cursor.getString(nameIdx) else docId
                val mime = if (mimeIdx >= 0 && !cursor.isNull(mimeIdx)) cursor.getString(mimeIdx) else "application/octet-stream"
                val size = if (sizeIdx >= 0 && !cursor.isNull(sizeIdx)) cursor.getLong(sizeIdx) else 0L
                val mod = if (modIdx >= 0 && !cursor.isNull(modIdx)) cursor.getLong(modIdx) else null
                val flags = if (flagsIdx >= 0 && !cursor.isNull(flagsIdx)) cursor.getInt(flagsIdx) else 0
                rows.add(SafDocumentRow(docId, name, mime, size, mod, flags))
            }
        } ?: throw IOException("SAF query returned null cursor for parentDocumentId=$parentDocumentId")
        return rows.sortedBy { it.displayName }
    }

    override fun statDocument(documentId: String): SafDocumentRow? {
        val docUri = DocumentsContract.buildDocumentUriUsingTree(treeUri, documentId)
        contentResolver.query(docUri, PROJECTION, null, null, null)?.use { cursor ->
            if (!cursor.moveToFirst()) return null
            val idIdx = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DOCUMENT_ID)
            val nameIdx = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_DISPLAY_NAME)
            val mimeIdx = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_MIME_TYPE)
            val sizeIdx = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_SIZE)
            val modIdx = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_LAST_MODIFIED)
            val flagsIdx = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_FLAGS)
            return SafDocumentRow(
                documentId = if (idIdx >= 0 && !cursor.isNull(idIdx)) cursor.getString(idIdx) else documentId,
                displayName = if (nameIdx >= 0 && !cursor.isNull(nameIdx)) cursor.getString(nameIdx) else documentId,
                mimeType = if (mimeIdx >= 0 && !cursor.isNull(mimeIdx)) cursor.getString(mimeIdx) else "application/octet-stream",
                sizeBytes = if (sizeIdx >= 0 && !cursor.isNull(sizeIdx)) cursor.getLong(sizeIdx) else 0L,
                lastModifiedMs = if (modIdx >= 0 && !cursor.isNull(modIdx)) cursor.getLong(modIdx) else null,
                flags = if (flagsIdx >= 0 && !cursor.isNull(flagsIdx)) cursor.getInt(flagsIdx) else 0
            )
        }
        return null
    }

    companion object {
        private val PROJECTION = arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_SIZE,
            DocumentsContract.Document.COLUMN_LAST_MODIFIED,
            DocumentsContract.Document.COLUMN_FLAGS
        )
    }
}

/**
 * SAF (Storage Access Framework) document tree adapter implementing [ScanSourceAdapter].
 *
 * Per approved Q2 in `docs/PORTING-NOTES-ANDROID.md`:
 * - Records `volumes.identity` as `android-saf:<authority>:<treeDocumentId>`.
 * - Records `nofollow_enforced = false`, `kernel_st_dev_enforced = false`, `fresh_stat_enforced = false`
 *   and known scoped-storage blind spots (`Android/data`, `Android/obb`, `/data`).
 * - Re-queries individual document metadata via `client.statDocument()` at the observation boundary.
 */
class SafScanAdapter(
    private val client: SafTreeClient
) : ScanSourceAdapter {
    override val sourceRoot: String = client.treeUriString

    private val relativePathToDocId = HashMap<String, String>().apply {
        put("", client.treeDocumentId)
    }

    override fun resolveVolume(): VolumeInfo = VolumeInfo(
        identity = "android-saf:${client.authority}:${client.treeDocumentId}",
        mountPath = client.treeUriString,
        filesystemType = "saf-documents-provider",
        device = client.authority
    )

    override fun capabilities(): AdapterCapabilities = AdapterCapabilities(
        adapterType = "ANDROID_SAF_TREE",
        nofollowEnforced = false,
        kernelStDevEnforced = false,
        freshStatEnforced = false,
        rootAccessUsed = false,
        blindSpots = SAF_KNOWN_BLIND_SPOTS
    )

    override fun isVolumeMounted(): Boolean = client.isTreeAccessible()

    override fun listDirectory(relativeDir: String): Sequence<RawDirectoryEntry> {
        if (!isVolumeMounted()) {
            throw VolumeUnmountedException(relativeDir, "SAF document tree is no longer accessible or permission was revoked")
        }
        val cleanRel = PathCanonicalizer.inventoryPath(relativeDir)
        val parentDocId = relativePathToDocId[cleanRel]
            ?: throw IOException("Unmapped SAF relative directory: $cleanRel")
        val children = client.listChildren(parentDocId)
        return children.asSequence().map { row ->
            val childRel = PathCanonicalizer.inventoryPath(
                if (cleanRel.isEmpty()) row.displayName else "$cleanRel/${row.displayName}"
            )
            if (row.isDirectory) {
                relativePathToDocId[childRel] = row.documentId
            }
            RawDirectoryEntry(name = row.displayName, handleId = row.documentId)
        }
    }

    override fun observeEntry(relativeDir: String, entry: RawDirectoryEntry): EntryObservationResult {
        val relative = PathCanonicalizer.inventoryPath(
            if (relativeDir.isEmpty()) entry.name else "$relativeDir/${entry.name}"
        )
        val freshRow = client.statDocument(entry.handleId)
            ?: throw FileNotFoundException("SAF document disappeared before observation: $relative (${entry.handleId})")

        val isDir = freshRow.isDirectory
        val entryType = if (isDir) "DIRECTORY" else "FILE"
        if (isDir) {
            relativePathToDocId[relative] = freshRow.documentId
        }
        val parent = if (relativeDir.isEmpty()) null else PathCanonicalizer.inventoryPath(relativeDir)
        val display = if (relativeDir.isEmpty()) entry.name else "$relativeDir/${entry.name}"
        val modifiedNs = freshRow.lastModifiedMs?.let { it * 1_000_000L }

        val observation = Observation(
            relativePath = relative,
            comparisonPath = PathCanonicalizer.comparisonPath(relative),
            parentPath = parent,
            name = entry.name,
            extension = PathCanonicalizer.extractExtension(entry.name),
            entryType = entryType,
            logicalBytes = if (entryType == "FILE") freshRow.sizeBytes else 0L,
            createdNs = null,
            modifiedNs = modifiedNs,
            accessedNs = null,
            attributes = freshRow.flags,
            depth = PathCanonicalizer.depthOf(relative),
            displayPath = display,
            observationStatus = "OBSERVED"
        )
        return EntryObservationResult(observation = observation, traversableDirectory = isDir)
    }

    companion object {
        val SAF_KNOWN_BLIND_SPOTS = listOf(
            "Android/data (blocked by Android 11+ SAF DocumentsProvider restrictions)",
            "Android/obb (blocked by Android 11+ SAF DocumentsProvider restrictions)",
            "/data and root partitions (invisible without PosixRootScanAdapter)"
        )
    }
}
