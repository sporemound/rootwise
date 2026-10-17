package org.rootwise.android

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import org.rootwise.android.adapter.AndroidMediaStoreClient
import org.rootwise.android.adapter.AndroidSafTreeClient
import org.rootwise.android.adapter.MediaStoreScanAdapter
import org.rootwise.android.adapter.NioNoFollowPosixBackend
import org.rootwise.android.adapter.PosixRootScanAdapter
import org.rootwise.android.adapter.RootShellPosixBackend
import org.rootwise.android.adapter.SafScanAdapter
import org.rootwise.android.core.adapter.ScanSourceAdapter
import org.rootwise.android.core.db.AndroidSqliteDriver
import org.rootwise.android.core.db.InventoryDatabase
import org.rootwise.android.core.guard.WriteGuard
import org.rootwise.android.core.model.ScanConfig
import org.rootwise.android.core.scanner.MetadataScanner
import org.rootwise.android.core.volume.VolumeResolver
import org.rootwise.android.planning.ProposalExporter
import org.rootwise.android.ui.RootwiseApp
import org.rootwise.android.ui.ScanSurfaceMode
import org.rootwise.android.viewer.DecisionRecord
import org.rootwise.android.viewer.DecisionStore
import org.rootwise.android.viewer.InventoryItem
import org.rootwise.android.viewer.InventoryReader
import org.rootwise.android.viewer.SessionSummary
import org.rootwise.android.viewer.SortField
import org.rootwise.android.viewer.SortOrder
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.Executors

class MainActivity : ComponentActivity() {
    private val backgroundExecutor = Executors.newSingleThreadExecutor()

    private var statusMessage by mutableStateOf("Ready. Grant GrapheneOS Storage Scopes, pick a SAF folder, or use Root POSIX.")
    private var isScanning by mutableStateOf(false)
    private var selectedMode by mutableStateOf(ScanSurfaceMode.ROOT_POSIX)
    private var posixPathInput by mutableStateOf("/storage/emulated/0")
    private var useRootSuHelper by mutableStateOf(true)
    private var allowSameVolumeGuard by mutableStateOf(true)
    private var selectedSafUri by mutableStateOf<Uri?>(null)

    private var sessions by mutableStateOf<List<SessionSummary>>(emptyList())
    private var activeSessionId by mutableStateOf<String?>(null)
    private var items by mutableStateOf<List<InventoryItem>>(emptyList())
    private var decisionsByPath by mutableStateOf<Map<String, DecisionRecord>>(emptyMap())

    private var searchQuery by mutableStateOf("")
    private var kindFilter by mutableStateOf<String?>(null)
    private var sortField by mutableStateOf(SortField.PATH)
    private var sortOrder by mutableStateOf(SortOrder.ASC)

    private fun artifactRootDir(): Path {
        val dbFile = getDatabasePath("inventory.db")
        val parent = dbFile.parentFile ?: filesDir
        if (!parent.exists()) {
            parent.mkdirs()
        }
        return parent.toPath()
    }

    private fun inventoryDbPath(): Path = artifactRootDir().resolve("inventory.db")
    private fun decisionsDbPath(): Path = artifactRootDir().resolve("decisions.db")

    private fun openAllFilesOrAppSettings() {
        try {
            val intent = Intent(
                Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                Uri.parse("package:$packageName")
            )
            startActivity(intent)
        } catch (_: Exception) {
            try {
                val fallback = Intent(
                    Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.parse("package:$packageName")
                )
                startActivity(fallback)
            } catch (e: Exception) {
                statusMessage = "Could not open Settings: ${e.message}"
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        refreshInventoryState()

        setContent {
            val storagePermissionLauncher = rememberLauncherForActivityResult(
                contract = ActivityResultContracts.RequestMultiplePermissions()
            ) { result: Map<String, Boolean> ->
                val anyGranted = result.values.any { it } || Environment.isExternalStorageManager()
                statusMessage = if (anyGranted) {
                    "Storage / GrapheneOS Storage Scopes active. Ready to scan."
                } else {
                    "Tip: On GrapheneOS, tap 'All Files / Storage Scopes Settings' to enable Storage Scopes."
                }
            }

            val safTreePicker = rememberLauncherForActivityResult(
                contract = ActivityResultContracts.OpenDocumentTree()
            ) { uri: Uri? ->
                if (uri != null) {
                    try {
                        contentResolver.takePersistableUriPermission(
                            uri,
                            Intent.FLAG_GRANT_READ_URI_PERMISSION
                        )
                    } catch (_: SecurityException) {
                    }
                    selectedSafUri = uri
                    selectedMode = ScanSurfaceMode.SAF_TREE
                    statusMessage = "Selected SAF tree (read-only grant): $uri"
                }
            }

            val exportInventoryLauncher = rememberLauncherForActivityResult(
                contract = ActivityResultContracts.CreateDocument("application/x-sqlite3")
            ) { uri: Uri? ->
                if (uri != null) {
                    exportInventoryDatabaseToUri(uri)
                }
            }

            val exportProposalLauncher = rememberLauncherForActivityResult(
                contract = ActivityResultContracts.CreateDocument("application/json")
            ) { uri: Uri? ->
                if (uri != null) {
                    exportProposalJsonToUri(uri)
                }
            }

            RootwiseApp(
                statusMessage = statusMessage,
                isScanning = isScanning,
                selectedMode = selectedMode,
                onSelectMode = { selectedMode = it },
                posixPathInput = posixPathInput,
                onPosixPathChange = { posixPathInput = it },
                useRootSuHelper = useRootSuHelper,
                onToggleRootSuHelper = { useRootSuHelper = it },
                allowSameVolumeGuard = allowSameVolumeGuard,
                onToggleSameVolumeGuard = { allowSameVolumeGuard = it },
                selectedSafUriString = selectedSafUri?.toString(),
                onPickSafTree = { safTreePicker.launch(null) },
                onRequestStorageScopes = {
                    val perms = if (Build.VERSION.SDK_INT >= 34) {
                        arrayOf(
                            Manifest.permission.READ_MEDIA_IMAGES,
                            Manifest.permission.READ_MEDIA_VIDEO,
                            Manifest.permission.READ_MEDIA_AUDIO,
                            Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED
                        )
                    } else if (Build.VERSION.SDK_INT >= 33) {
                        arrayOf(
                            Manifest.permission.READ_MEDIA_IMAGES,
                            Manifest.permission.READ_MEDIA_VIDEO,
                            Manifest.permission.READ_MEDIA_AUDIO
                        )
                    } else {
                        arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
                    }
                    storagePermissionLauncher.launch(perms)
                },
                onOpenAllFilesSettings = { openAllFilesOrAppSettings() },
                onStartScan = { triggerScan() },
                sessions = sessions,
                activeSessionId = activeSessionId,
                onSelectSession = { sessionId ->
                    activeSessionId = sessionId
                    reloadItems()
                },
                searchQuery = searchQuery,
                onSearchQueryChange = {
                    searchQuery = it
                    reloadItems()
                },
                kindFilter = kindFilter,
                onKindFilterChange = {
                    kindFilter = it
                    reloadItems()
                },
                sortField = sortField,
                onSortFieldChange = {
                    sortField = it
                    reloadItems()
                },
                sortOrder = sortOrder,
                onSortOrderChange = {
                    sortOrder = it
                    reloadItems()
                },
                items = items,
                decisionsByPath = decisionsByPath,
                onRecordDecision = { relativePath, decision, note ->
                    recordDecision(relativePath, decision, note)
                },
                onExportInventoryDb = {
                    exportInventoryLauncher.launch("rootwise-inventory.db")
                },
                onExportProposalJson = {
                    exportProposalLauncher.launch("rootwise-proposal.json")
                },
                artifactDirectoryDisplay = artifactRootDir().toString()
            )
        }
    }

    private fun triggerScan() {
        if (isScanning) return
        isScanning = true
        statusMessage = "Running metadata-only scan..."

        backgroundExecutor.execute {
            try {
                val adapter: ScanSourceAdapter
                val sourceRootForGuard: Path?
                when (selectedMode) {
                    ScanSurfaceMode.ROOT_POSIX -> {
                        val targetPath = Path.of(posixPathInput.trim())
                        val backend = if (useRootSuHelper) {
                            RootShellPosixBackend()
                        } else {
                            NioNoFollowPosixBackend()
                        }
                        adapter = PosixRootScanAdapter(targetPath, backend = backend)
                        sourceRootForGuard = targetPath
                    }
                    ScanSurfaceMode.SAF_TREE -> {
                        val uri = selectedSafUri
                            ?: throw IllegalStateException("Pick a SAF document tree first.")
                        adapter = SafScanAdapter(AndroidSafTreeClient(contentResolver, uri))
                        sourceRootForGuard = null
                    }
                    ScanSurfaceMode.MEDIA_STORE -> {
                        adapter = MediaStoreScanAdapter(AndroidMediaStoreClient(contentResolver))
                        sourceRootForGuard = null
                    }
                }

                val rootDir = artifactRootDir()
                val sourceVolume = adapter.resolveVolume()
                val destVolume = VolumeResolver.resolveVolume(rootDir)
                val guard = WriteGuard(
                    sourceVolume = sourceVolume,
                    allowedRootPath = rootDir,
                    destinationVolume = destVolume,
                    allowSameVolumeDisjointSubtree = allowSameVolumeGuard,
                    sourceRootPath = sourceRootForGuard,
                    volumeResolver = { VolumeResolver.resolveVolume(it) }
                )
                val excluded = if (sourceRootForGuard != null) {
                    guard.excludedRelativeSubtrees(sourceRootForGuard)
                } else {
                    emptySet()
                }
                val config = ScanConfig(
                    source = adapter.sourceRoot,
                    database = inventoryDbPath().toString(),
                    maxFilesPerSecond = 500.0,
                    batchSize = 256,
                    sleepMsPerBatch = 5,
                    maxRssMib = 256,
                    minFreeDestinationMib = 32,
                    allowSameVolumeDisjointSubtree = allowSameVolumeGuard
                )

                val result = InventoryDatabase(
                    targetPath = inventoryDbPath(),
                    guard = guard,
                    driver = AndroidSqliteDriver
                ).use { db ->
                    val scanner = MetadataScanner(
                        adapter = adapter,
                        volume = sourceVolume,
                        database = db,
                        config = config,
                        excludedRelativeSubtrees = excluded
                    )
                    scanner.run(resume = false)
                }

                runOnUiThread {
                    isScanning = false
                    statusMessage = "Scan ${result.second.wireValue}: session ${result.first.take(8)}..."
                    refreshInventoryState(preferSessionId = result.first)
                }
            } catch (t: Throwable) {
                runOnUiThread {
                    isScanning = false
                    statusMessage = "Scan failed closed: ${t.message ?: t::class.java.simpleName}"
                    refreshInventoryState()
                }
            }
        }
    }

    private fun refreshInventoryState(preferSessionId: String? = null) {
        backgroundExecutor.execute {
            val invPath = inventoryDbPath()
            if (!Files.exists(invPath)) {
                runOnUiThread {
                    sessions = emptyList()
                    activeSessionId = null
                    items = emptyList()
                    decisionsByPath = emptyMap()
                }
                return@execute
            }
            try {
                InventoryReader(invPath, driver = AndroidSqliteDriver).use { reader ->
                    val loadedSessions = reader.sessions()
                    val chosen = preferSessionId
                        ?: activeSessionId?.takeIf { id -> loadedSessions.any { it.scanSessionId == id && it.state == "COMPLETE" } }
                        ?: loadedSessions.lastOrNull { it.state == "COMPLETE" }?.scanSessionId
                    val loadedItems = if (chosen != null) {
                        reader.search(
                            sessionId = chosen,
                            query = searchQuery,
                            kind = kindFilter,
                            limit = 200,
                            offset = 0,
                            sortField = sortField,
                            sortOrder = sortOrder
                        )
                    } else {
                        emptyList()
                    }
                    val loadedDecisions = if (chosen != null && loadedItems.isNotEmpty() && Files.exists(decisionsDbPath())) {
                        DecisionStore(decisionsDbPath(), invPath, driver = AndroidSqliteDriver).use { ds ->
                            ds.currentForPaths(chosen, loadedItems.map { it.relativePath })
                        }
                    } else {
                        emptyMap()
                    }
                    runOnUiThread {
                        sessions = loadedSessions
                        activeSessionId = chosen
                        items = loadedItems
                        decisionsByPath = loadedDecisions
                    }
                }
            } catch (t: Throwable) {
                runOnUiThread {
                    statusMessage = "Inventory read notice: ${t.message}"
                }
            }
        }
    }

    private fun reloadItems() {
        refreshInventoryState(preferSessionId = activeSessionId)
    }

    private fun recordDecision(relativePath: String, decision: String, note: String) {
        val sessionId = activeSessionId ?: return
        backgroundExecutor.execute {
            try {
                val invPath = inventoryDbPath()
                val decPath = decisionsDbPath()
                DecisionStore(decPath, invPath, driver = AndroidSqliteDriver).use { store ->
                    val existing = store.current(sessionId, relativePath)
                    store.setDecision(
                        sessionId = sessionId,
                        relativePath = relativePath,
                        decision = decision,
                        note = note,
                        expectedRevision = existing?.revision ?: 0
                    )
                }
                runOnUiThread {
                    statusMessage = "Recorded decision $decision on $relativePath"
                    reloadItems()
                }
            } catch (t: Throwable) {
                runOnUiThread {
                    statusMessage = "Decision error: ${t.message}"
                }
            }
        }
    }

    private fun exportInventoryDatabaseToUri(destinationUri: Uri) {
        backgroundExecutor.execute {
            try {
                val invPath = inventoryDbPath()
                require(Files.exists(invPath)) { "No inventory.db exists to export yet." }
                contentResolver.openOutputStream(destinationUri, "w")?.use { out ->
                    Files.copy(invPath, out)
                } ?: throw IllegalStateException("Unable to open SAF output stream for $destinationUri")
                runOnUiThread {
                    statusMessage = "Exported inventory.db snapshot to $destinationUri"
                }
            } catch (t: Throwable) {
                runOnUiThread {
                    statusMessage = "Export inventory.db failed: ${t.message}"
                }
            }
        }
    }

    private fun exportProposalJsonToUri(destinationUri: Uri) {
        backgroundExecutor.execute {
            try {
                val invPath = inventoryDbPath()
                require(Files.exists(invPath)) { "No inventory.db exists to build a proposal." }
                val proposal = ProposalExporter.buildProposal(
                    inventoryPath = invPath,
                    decisionsPath = decisionsDbPath().takeIf { Files.exists(it) },
                    sessionId = activeSessionId,
                    driver = AndroidSqliteDriver
                )
                contentResolver.openOutputStream(destinationUri, "w")?.use { out ->
                    out.write(proposal.jsonBytes)
                } ?: throw IllegalStateException("Unable to open SAF output stream for $destinationUri")
                runOnUiThread {
                    statusMessage = "Exported non-executable proposal (${proposal.proposalDigest.take(12)}...)"
                }
            } catch (t: Throwable) {
                runOnUiThread {
                    statusMessage = "Proposal export failed: ${t.message}"
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        backgroundExecutor.shutdownNow()
    }
}
