package org.rootwise.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.rootwise.android.adapter.MediaStoreClient
import org.rootwise.android.adapter.MediaStoreEntryRow
import org.rootwise.android.adapter.MediaStoreScanAdapter
import org.rootwise.android.adapter.NioNoFollowPosixBackend
import org.rootwise.android.adapter.PosixMetadataBackend
import org.rootwise.android.adapter.PosixRootScanAdapter
import org.rootwise.android.adapter.PosixStatMetadata
import org.rootwise.android.adapter.RootShellPosixBackend
import org.rootwise.android.adapter.SafDocumentRow
import org.rootwise.android.adapter.SafScanAdapter
import org.rootwise.android.adapter.SafTreeClient
import org.rootwise.android.core.db.InventoryDatabase
import org.rootwise.android.core.db.JdbcSqliteDriver
import org.rootwise.android.core.export.CanonicalExporter
import org.rootwise.android.core.guard.WriteGuard
import org.rootwise.android.core.model.BoundaryViolationException
import org.rootwise.android.core.model.JsonCanonicalizer
import org.rootwise.android.core.model.PathCanonicalizer
import org.rootwise.android.core.model.ResourceLimitExceededException
import org.rootwise.android.core.model.ScanConfig
import org.rootwise.android.core.model.ScanStateException
import org.rootwise.android.core.model.SessionState
import org.rootwise.android.core.model.VolumeIdentityException
import org.rootwise.android.core.model.VolumeInfo
import org.rootwise.android.core.model.VolumeSeparationMode
import org.rootwise.android.core.scanner.CancellationToken
import org.rootwise.android.core.scanner.MetadataScanner
import org.rootwise.android.core.scanner.ResourceController
import org.rootwise.android.core.scanner.ResourcePolicy
import org.rootwise.android.core.volume.VolumeResolver
import org.rootwise.android.planning.ProposalExporter
import org.rootwise.android.viewer.DecisionConflictException
import org.rootwise.android.viewer.DecisionStore
import org.rootwise.android.viewer.InventoryReadException
import org.rootwise.android.viewer.InventoryReader
import org.rootwise.android.viewer.SortField
import org.rootwise.android.viewer.SortOrder
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.atomic.AtomicBoolean

class ScannerAndPipelineTest {
    @get:Rule
    val tempFolder = TemporaryFolder()

    private val sourceVol = VolumeInfo("posix-device:1001", "/mnt/media_rw/ext1", "exfat", "1001")
    private val destVol = VolumeInfo("posix-device:2002", "/data", "f2fs", "2002")

    private fun newDistinctGuard(allowedRoot: Path): WriteGuard = WriteGuard(
        sourceVolume = sourceVol,
        allowedRootPath = allowedRoot,
        destinationVolume = destVol,
        allowSameVolumeDisjointSubtree = false,
        sourceRootPath = null,
        volumeResolver = { destVol }
    )

    private fun writeString(path: Path, text: String) {
        Files.write(path, text.toByteArray(Charsets.UTF_8))
    }

    private fun readString(path: Path): String {
        return String(Files.readAllBytes(path), Charsets.UTF_8)
    }

    @Test
    fun testEmptyDirsSymlinksAndUnreadableEntries() {
        val sourceRoot = tempFolder.newFolder("source_fixture").toPath()
        val artifactRoot = tempFolder.newFolder("artifacts_fixture").toPath()

        val emptyDir = Files.createDirectories(sourceRoot.resolve("empty_dir"))
        assertNotNull(emptyDir)

        val readableDir = Files.createDirectories(sourceRoot.resolve("project/src"))
        writeString(readableDir.resolve("main.kt"), "fun main() = Unit")
        writeString(sourceRoot.resolve("project/.hidden"), "hidden")

        val unreadableDir = Files.createDirectories(sourceRoot.resolve("locked_dir"))
        writeString(unreadableDir.resolve("secret.txt"), "not readable")
        val unreadableFile = sourceRoot.resolve("project/unreadable.bin")
        Files.write(unreadableFile, byteArrayOf(1, 2, 3, 4))

        // Create a target outside or inside and test symlink handling (both file symlink and dir symlink)
        val symlinkTargetDir = Files.createDirectories(sourceRoot.resolve("real_dir"))
        writeString(symlinkTargetDir.resolve("inside_real.txt"), "real content")

        val symlinkCreated = try {
            Files.createSymbolicLink(sourceRoot.resolve("link_to_dir"), symlinkTargetDir)
            Files.createSymbolicLink(sourceRoot.resolve("link_to_file"), readableDir.resolve("main.kt"))
            true
        } catch (_: Throwable) {
            // On Windows without developer mode privileges, simulate symlink via PosixMetadataBackend wrapper
            false
        }

        val baseBackend = NioNoFollowPosixBackend(
            volumeResolver = { sourceVol },
            unreadablePaths = setOf(
                unreadableDir.toAbsolutePath().normalize(),
                unreadableFile.toAbsolutePath().normalize()
            )
        )

        val testBackend = object : PosixMetadataBackend by baseBackend {
            override fun listChildNames(directory: Path): List<String> {
                val baseList = baseBackend.listChildNames(directory).toMutableList()
                if (!symlinkCreated && directory.toAbsolutePath().normalize() == sourceRoot.toAbsolutePath().normalize()) {
                    baseList.add("simulated_symlink_dir")
                    baseList.add("simulated_symlink_file")
                    baseList.sort()
                }
                return baseList
            }

            override fun statNoFollow(path: Path): PosixStatMetadata {
                val name = path.fileName?.toString() ?: ""
                if (!symlinkCreated && name == "simulated_symlink_dir") {
                    return PosixStatMetadata(
                        isSymbolicLink = true,
                        isDirectory = true,
                        isRegularFile = false,
                        logicalBytes = 0L,
                        createdNs = 1000L,
                        modifiedNs = 2000L,
                        accessedNs = 3000L,
                        attributes = NioNoFollowPosixBackend.REPARSE_POINT_FLAG,
                        volumeIdentity = sourceVol.identity
                    )
                }
                if (!symlinkCreated && name == "simulated_symlink_file") {
                    return PosixStatMetadata(
                        isSymbolicLink = true,
                        isDirectory = false,
                        isRegularFile = false,
                        logicalBytes = 999L,
                        createdNs = 1000L,
                        modifiedNs = 2000L,
                        accessedNs = 3000L,
                        attributes = NioNoFollowPosixBackend.REPARSE_POINT_FLAG,
                        volumeIdentity = sourceVol.identity
                    )
                }
                return baseBackend.statNoFollow(path)
            }
        }

        val adapter = PosixRootScanAdapter(
            rootPath = sourceRoot,
            backend = testBackend,
            volumeOverride = sourceVol
        )
        val dbPath = artifactRoot.resolve("inventory.db")
        val guard = newDistinctGuard(artifactRoot)
        val config = ScanConfig(
            source = adapter.sourceRoot,
            database = dbPath.toString(),
            maxFilesPerSecond = 10_000.0,
            batchSize = 4,
            sleepMsPerBatch = 0
        )

        InventoryDatabase(dbPath, guard).use { db ->
            val scanner = MetadataScanner(
                adapter = adapter,
                volume = sourceVol,
                database = db,
                config = config,
                sleeper = {}
            )
            val (sessionId, state) = scanner.run()
            assertEquals(SessionState.COMPLETE, state)

            // Verify symlinks were recorded with 0 logical bytes and NEVER followed into scan_frontier
            val dirTypes = db.connection.query(
                "SELECT relative_path, entry_type, logical_bytes FROM directories WHERE scan_session_id=?",
                listOf(sessionId)
            ) { r -> Triple(r.getStringAt(0) ?: "", r.getStringAt(1) ?: "", r.getLongAt(2) ?: -1L) }
                .associate { it.first to Pair(it.second, it.third) }

            assertTrue(dirTypes.containsKey("empty_dir"))
            assertEquals("DIRECTORY", dirTypes["empty_dir"]?.first)
            assertEquals(0L, dirTypes["empty_dir"]?.second)

            val expectedSymlinkDirName = if (symlinkCreated) "link_to_dir" else "simulated_symlink_dir"
            assertEquals("SYMLINK_DIRECTORY", dirTypes[expectedSymlinkDirName]?.first)

            val frontierPaths = db.connection.query(
                "SELECT relative_path FROM scan_frontier WHERE scan_session_id=?",
                listOf(sessionId)
            ) { it.getStringAt(0) ?: "" }.toSet()
            assertFalse("Symlink directory must never enter scan_frontier", frontierPaths.contains(expectedSymlinkDirName))

            // Verify file symlink has entry_type=SYMLINK and logical_bytes=0
            val expectedSymlinkFileName = if (symlinkCreated) "link_to_file" else "simulated_symlink_file"
            val fileRow = db.connection.querySingleOrNull(
                "SELECT entry_type, logical_bytes FROM files WHERE scan_session_id=? AND relative_path=?",
                listOf(sessionId, expectedSymlinkFileName)
            ) { Pair(it.getStringAt(0) ?: "", it.getLongAt(1) ?: -1L) }
            assertNotNull(fileRow)
            assertEquals("SYMLINK", fileRow?.first)
            assertEquals(0L, fileRow?.second)

            // Verify structured errors for unreadable_file (stat) and locked_dir (scandir)
            val errors = db.connection.query(
                "SELECT relative_path, operation, error_type FROM scan_errors WHERE scan_session_id=? ORDER BY relative_path",
                listOf(sessionId)
            ) { Triple(it.getStringAt(0) ?: "", it.getStringAt(1) ?: "", it.getStringAt(2) ?: "") }

            assertTrue(errors.any { it.first == "locked_dir" && it.second == "scandir" && it.third == "PermissionError" })
            assertTrue(errors.any { it.first == "project/unreadable.bin" && it.second == "stat" && it.third == "PermissionError" })
        }
    }

    @Test
    fun testStage021ConcurrentMutationBetweenEnumerationAndObservation() {
        val sourceRoot = tempFolder.newFolder("mutation_source").toPath()
        val artifactRoot = tempFolder.newFolder("mutation_artifacts").toPath()

        val stableFile = sourceRoot.resolve("stable.txt")
        val vanishingFile = sourceRoot.resolve("vanishing.txt")
        val vanishingDir = Files.createDirectories(sourceRoot.resolve("vanishing_dir"))
        writeString(stableFile, "stay")
        writeString(vanishingFile, "gone")
        writeString(vanishingDir.resolve("child.txt"), "never reached")

        val adapter = PosixRootScanAdapter(
            rootPath = sourceRoot,
            backend = NioNoFollowPosixBackend(volumeResolver = { sourceVol }),
            volumeOverride = sourceVol,
            beforeObserveHook = { relativePath ->
                if (relativePath == "vanishing.txt") {
                    Files.deleteIfExists(vanishingFile)
                } else if (relativePath == "vanishing_dir") {
                    Files.deleteIfExists(vanishingDir.resolve("child.txt"))
                    Files.deleteIfExists(vanishingDir)
                }
            }
        )

        val dbPath = artifactRoot.resolve("inventory.db")
        val guard = newDistinctGuard(artifactRoot)
        val config = ScanConfig(source = adapter.sourceRoot, database = dbPath.toString(), sleepMsPerBatch = 0)

        InventoryDatabase(dbPath, guard).use { db ->
            val scanner = MetadataScanner(adapter = adapter, volume = sourceVol, database = db, config = config, sleeper = {})
            val (sessionId, state) = scanner.run()
            assertEquals(SessionState.COMPLETE, state)

            val observedFiles = db.connection.query(
                "SELECT relative_path FROM files WHERE scan_session_id=?",
                listOf(sessionId)
            ) { it.getStringAt(0) ?: "" }
            assertEquals(listOf("stable.txt"), observedFiles)

            val observedDirs = db.connection.query(
                "SELECT relative_path FROM directories WHERE scan_session_id=?",
                listOf(sessionId)
            ) { it.getStringAt(0) ?: "" }
            assertTrue(observedDirs.isEmpty())

            val errors = db.connection.query(
                "SELECT relative_path, operation, error_type FROM scan_errors WHERE scan_session_id=? ORDER BY relative_path",
                listOf(sessionId)
            ) { Triple(it.getStringAt(0) ?: "", it.getStringAt(1) ?: "", it.getStringAt(2) ?: "") }
            assertEquals(2, errors.size)
            assertEquals(Triple("vanishing.txt", "stat", "FileNotFoundError"), errors[0])
            assertEquals(Triple("vanishing_dir", "stat", "FileNotFoundError"), errors[1])
        }
    }

    @Test
    fun testMidScanVolumeUnmountAndResumeRecovery() {
        val sourceRoot = tempFolder.newFolder("unmount_source").toPath()
        val artifactRoot = tempFolder.newFolder("unmount_artifacts").toPath()

        Files.createDirectories(sourceRoot.resolve("dirA"))
        Files.createDirectories(sourceRoot.resolve("dirB"))
        writeString(sourceRoot.resolve("dirA/a.txt"), "alpha")
        writeString(sourceRoot.resolve("dirB/b.txt"), "beta")

        val mounted = AtomicBoolean(true)
        val adapter = PosixRootScanAdapter(
            rootPath = sourceRoot,
            backend = NioNoFollowPosixBackend(
                volumeResolver = { sourceVol },
                mountStateSupplier = { mounted.get() }
            ),
            volumeOverride = sourceVol,
            beforeObserveHook = { rel ->
                if (rel == "dirB/b.txt") {
                    mounted.set(false)
                }
            }
        )

        val dbPath = artifactRoot.resolve("inventory.db")
        val guard = newDistinctGuard(artifactRoot)
        val config = ScanConfig(source = adapter.sourceRoot, database = dbPath.toString(), batchSize = 1, sleepMsPerBatch = 0)

        var firstSessionId = ""
        InventoryDatabase(dbPath, guard).use { db ->
            val scanner = MetadataScanner(adapter = adapter, volume = sourceVol, database = db, config = config, sleeper = {})
            val (sessionId, state) = scanner.run()
            firstSessionId = sessionId
            assertEquals("Volume unmount must transition to STOPPED, never COMPLETE", SessionState.STOPPED, state)

            val events = db.connection.query(
                "SELECT event_type FROM scan_events WHERE scan_session_id=?",
                listOf(sessionId)
            ) { it.getStringAt(0) ?: "" }
            assertTrue(events.contains("VOLUME_UNMOUNTED"))
        }

        // Remount volume and resume the stopped session to completion
        mounted.set(true)
        val remountedAdapter = PosixRootScanAdapter(
            rootPath = sourceRoot,
            backend = NioNoFollowPosixBackend(volumeResolver = { sourceVol }),
            volumeOverride = sourceVol
        )
        InventoryDatabase(dbPath, guard).use { db ->
            val scanner = MetadataScanner(
                adapter = remountedAdapter,
                volume = sourceVol,
                database = db,
                config = config,
                sleeper = {}
            )
            val (resumedId, finalState) = scanner.run(resume = true)
            assertEquals(firstSessionId, resumedId)
            assertEquals(SessionState.COMPLETE, finalState)
        }
    }

    @Test
    fun testSameVolumeDisjointSubtreeAndSelfExclusionOnRootedUserdata() {
        val simulatedDataPartition = tempFolder.newFolder("simulated_data_partition").toPath()
        val appPrivateArtifacts = Files.createDirectories(
            simulatedDataPartition.resolve("user/0/org.rootwise.android/databases")
        )
        val userMediaDir = Files.createDirectories(simulatedDataPartition.resolve("media/0/DCIM"))
        writeString(userMediaDir.resolve("photo.jpg"), "jpeg_header_not_read")

        val sharedUserdataVol = VolumeInfo("posix-device:42", "/data", "f2fs", "42")

        // 1. Without allowSameVolumeDisjointSubtree, same volume is rejected
        try {
            WriteGuard(
                sourceVolume = sharedUserdataVol,
                allowedRootPath = appPrivateArtifacts,
                destinationVolume = sharedUserdataVol,
                allowSameVolumeDisjointSubtree = false,
                sourceRootPath = simulatedDataPartition,
                volumeResolver = { sharedUserdataVol }
            )
            fail("Expected VolumeIdentityException when allowSameVolumeDisjointSubtree=false")
        } catch (_: VolumeIdentityException) {
            // Expected
        }

        // 2. Source root inside allowed artifact root is rejected even when allowSameVolumeDisjointSubtree=true
        try {
            WriteGuard(
                sourceVolume = sharedUserdataVol,
                allowedRootPath = appPrivateArtifacts,
                destinationVolume = sharedUserdataVol,
                allowSameVolumeDisjointSubtree = true,
                sourceRootPath = appPrivateArtifacts,
                volumeResolver = { sharedUserdataVol }
            )
            fail("Expected BoundaryViolationException when sourceRoot is inside allowedRoot")
        } catch (_: BoundaryViolationException) {
            // Expected
        }

        // 3. Scanning parent /data with allowSameVolumeDisjointSubtree=true hard-excludes the artifact directory
        val guard = WriteGuard(
            sourceVolume = sharedUserdataVol,
            allowedRootPath = appPrivateArtifacts,
            destinationVolume = sharedUserdataVol,
            allowSameVolumeDisjointSubtree = true,
            sourceRootPath = simulatedDataPartition,
            volumeResolver = { sharedUserdataVol }
        )
        assertEquals(VolumeSeparationMode.SAME_VOLUME_DISJOINT_SUBTREE, guard.separationMode)
        val excluded = guard.excludedRelativeSubtrees(simulatedDataPartition)
        assertTrue(excluded.contains("user/0/org.rootwise.android/databases"))

        val adapter = PosixRootScanAdapter(
            rootPath = simulatedDataPartition,
            backend = NioNoFollowPosixBackend(volumeResolver = { sharedUserdataVol }),
            volumeOverride = sharedUserdataVol
        )
        val dbPath = appPrivateArtifacts.resolve("inventory.db")
        val config = ScanConfig(
            source = adapter.sourceRoot,
            database = dbPath.toString(),
            allowSameVolumeDisjointSubtree = true,
            sleepMsPerBatch = 0
        )

        InventoryDatabase(dbPath, guard).use { db ->
            val scanner = MetadataScanner(
                adapter = adapter,
                volume = sharedUserdataVol,
                database = db,
                config = config,
                excludedRelativeSubtrees = excluded,
                sleeper = {}
            )
            val (sessionId, state) = scanner.run()
            assertEquals(SessionState.COMPLETE, state)

            val allFiles = db.connection.query(
                "SELECT relative_path FROM files WHERE scan_session_id=?",
                listOf(sessionId)
            ) { it.getStringAt(0) ?: "" }
            assertEquals(listOf("media/0/DCIM/photo.jpg"), allFiles)
            assertFalse("Scanner must never observe its own inventory.db", allFiles.any { it.contains("inventory.db") })

            val events = db.connection.query(
                "SELECT event_type, detail_json FROM scan_events WHERE scan_session_id=?",
                listOf(sessionId)
            ) { Pair(it.getStringAt(0) ?: "", it.getStringAt(1) ?: "") }
            assertTrue(events.any { it.first == "SELF_ARTIFACT_ROOT_EXCLUDED" })
        }
    }

    @Test
    fun testTenThousandFileFixtureScanExportViewerDecisionsAndProposalRoundTrip() {
        val sourceRoot = tempFolder.newFolder("ten_k_source").toPath()
        val artifactRoot = tempFolder.newFolder("ten_k_artifacts").toPath()

        // Create 10,000 files across 20 directories (500 files per directory)
        val dirCount = 20
        val filesPerDir = 500
        for (d in 0 until dirCount) {
            val dirName = String.format(java.util.Locale.ROOT, "bucket_%02d", d)
            val dirPath = Files.createDirectories(sourceRoot.resolve(dirName))
            for (f in 0 until filesPerDir) {
                val fileName = String.format(java.util.Locale.ROOT, "item_%04d.dat", f)
                Files.createFile(dirPath.resolve(fileName))
            }
        }

        val adapter = PosixRootScanAdapter(
            rootPath = sourceRoot,
            backend = NioNoFollowPosixBackend(volumeResolver = { sourceVol }),
            volumeOverride = sourceVol
        )
        val dbPath = artifactRoot.resolve("inventory.db")
        val ndjsonPath = artifactRoot.resolve("inventory.ndjson")
        val decisionsPath = artifactRoot.resolve("decisions.db")
        val guard = newDistinctGuard(artifactRoot)
        val config = ScanConfig(
            source = adapter.sourceRoot,
            database = dbPath.toString(),
            maxFilesPerSecond = 1_000_000.0,
            batchSize = 1000,
            sleepMsPerBatch = 0,
            maxRssMib = 512,
            minFreeDestinationMib = 1
        )

        var completedSessionId = ""
        InventoryDatabase(dbPath, guard).use { db ->
            val scanner = MetadataScanner(
                adapter = adapter,
                volume = sourceVol,
                database = db,
                config = config,
                sleeper = {}
            )
            val (sessionId, state) = scanner.run()
            completedSessionId = sessionId
            assertEquals(SessionState.COMPLETE, state)

            val exportResult = CanonicalExporter.exportCanonical(db, guard, sessionId, ndjsonPath)
            assertTrue(Files.exists(exportResult.outputPath))
            // 1 session header + 20 directories + 10,000 files + 2 events (STARTED, COMPLETE) = 10,023 lines
            assertEquals(10_023, exportResult.recordCount)
            assertEquals(64, exportResult.sha256.length)
        }

        // Verify query-only viewer browsing & local sorting/searching
        InventoryReader(dbPath, driver = JdbcSqliteDriver).use { reader ->
            assertTrue(reader.isQueryOnly)
            assertEquals(completedSessionId, reader.latestCompleteSession())
            val sessions = reader.sessions()
            assertEquals(1, sessions.size)
            assertEquals(10_020L, sessions[0].observedCount)

            val bucket05Files = reader.search(
                sessionId = completedSessionId,
                query = "bucket_05",
                kind = "file",
                limit = 500,
                offset = 0,
                sortField = SortField.PATH,
                sortOrder = SortOrder.DESC
            )
            assertEquals(500, bucket05Files.size)
            assertEquals("bucket_05/item_0499.dat", bucket05Files.first().relativePath)

            val single = reader.item(completedSessionId, "bucket_00/item_0000.dat")
            assertNotNull(single)
            assertEquals(".dat", single?.extension)

            val rootDirs = reader.search(
                completedSessionId,
                query = "bucket_",
                kind = "directory",
                sortField = SortField.PATH,
                sortOrder = SortOrder.ASC
            )
            assertEquals(20, rootDirs.size)
            val modSorted = reader.search(
                completedSessionId,
                query = "item_0000",
                kind = "file",
                sortField = SortField.MODIFIED,
                sortOrder = SortOrder.ASC,
                limit = 5
            )
            assertEquals(5, modSorted.size)
        }

        // Record revision-checked human decisions in decisions.db
        DecisionStore(decisionsPath, dbPath, driver = JdbcSqliteDriver).use { store ->
            val r1 = store.setDecision(completedSessionId, "bucket_00", "ARCHIVE_ELIGIBLE", note = "Cold bucket")
            assertEquals(1, r1.revision)

            val r2 = store.setDecision(
                completedSessionId,
                "bucket_00",
                "ARCHIVE_ELIGIBLE",
                note = "Confirmed cold bucket",
                expectedRevision = 1
            )
            assertEquals(2, r2.revision)
            assertEquals("ARCHIVE_ELIGIBLE", store.current(completedSessionId, "bucket_00")?.decision)

            try {
                store.setDecision(completedSessionId, "bucket_00", "KEEP", expectedRevision = 1)
                fail("Expected DecisionConflictException on stale revision")
            } catch (_: DecisionConflictException) {
                // Expected
            }

            store.setDecision(completedSessionId, "bucket_01", "PROTECT", note = "Critical bucket")
            assertEquals(2, store.history(completedSessionId, "bucket_00").size)
            val pageMap = store.currentForPaths(completedSessionId, listOf("bucket_00", "bucket_01"))
            assertEquals("ARCHIVE_ELIGIBLE", pageMap["bucket_00"]?.decision)
            assertEquals("PROTECT", pageMap["bucket_01"]?.decision)
            assertEquals(2, store.allCurrentDecisions(completedSessionId).size)
        }

        // Generate non-executable proposal JSON and verify round-trip
        val proposal = ProposalExporter.buildProposal(
            inventoryPath = dbPath,
            decisionsPath = decisionsPath,
            sessionId = completedSessionId,
            driver = JdbcSqliteDriver
        )
        assertEquals(completedSessionId, proposal.scanSessionId)
        assertEquals(20, proposal.actions.size)
        val bucket00Action = proposal.actions.first { it.relativePath == "bucket_00" }
        assertEquals("ARCHIVE_AS_UNIT", bucket00Action.action)
        assertEquals(500, bucket00Action.fileCount)
        assertNotNull(bucket00Action.proposedArchiveLabel)

        val bucket01Action = proposal.actions.first { it.relativePath == "bucket_01" }
        assertEquals("PROTECTED", bucket01Action.action)
        assertNull(bucket01Action.proposedArchiveLabel)

        val jsonText = String(proposal.jsonBytes, StandardCharsets.UTF_8)
        assertTrue(jsonText.contains("\"execution_authorized\":false"))
        assertTrue(jsonText.contains("\"archive_creation_authorized\":false"))
        assertTrue(jsonText.contains("\"original_removal_authorized\":false"))
        assertTrue(jsonText.contains("\"state\":\"PROPOSAL_ONLY_NON_EXECUTABLE\""))
    }

    @Test
    fun testSafAndMediaStoreAdaptersAndRootShellBackend() {
        val artifactRoot = tempFolder.newFolder("adapter_artifacts").toPath()

        // 1. Test SafScanAdapter with mid-scan deletion and capabilities
        val safDocs = mutableMapOf(
            "rootDoc" to SafDocumentRow("rootDoc", "Root", "vnd.android.document/directory", 0L, 1000L, 0),
            "subDir" to SafDocumentRow("subDir", "Music", "vnd.android.document/directory", 0L, 1000L, 0),
            "song1" to SafDocumentRow("song1", "track.flac", "audio/flac", 4096L, 2000L, 0),
            "vanishingDoc" to SafDocumentRow("vanishingDoc", "temp.tmp", "application/octet-stream", 128L, 2000L, 0)
        )
        val safChildren = mapOf(
            "rootDoc" to listOf(safDocs.getValue("subDir"), safDocs.getValue("vanishingDoc")),
            "subDir" to listOf(safDocs.getValue("song1"))
        )
        val safClient = object : SafTreeClient {
            override val authority: String = "com.android.externalstorage.documents"
            override val treeDocumentId: String = "rootDoc"
            override val treeUriString: String = "content://com.android.externalstorage.documents/tree/rootDoc"
            override fun isTreeAccessible(): Boolean = true
            override fun listChildren(parentDocumentId: String): List<SafDocumentRow> =
                safChildren[parentDocumentId].orEmpty()
            override fun statDocument(documentId: String): SafDocumentRow? {
                if (documentId == "vanishingDoc") return null // Simulate mid-scan deletion
                return safDocs[documentId]
            }
        }
        val safAdapter = SafScanAdapter(safClient)
        assertFalse(safAdapter.capabilities().nofollowEnforced)
        assertTrue(safAdapter.capabilities().blindSpots.isNotEmpty())

        val safDbPath = artifactRoot.resolve("saf_inventory.db")
        val safGuard = WriteGuard(
            sourceVolume = safAdapter.resolveVolume(),
            allowedRootPath = artifactRoot,
            destinationVolume = destVol,
            volumeResolver = { destVol }
        )
        InventoryDatabase(safDbPath, safGuard).use { db ->
            val scanner = MetadataScanner(
                adapter = safAdapter,
                database = db,
                config = ScanConfig(source = safAdapter.sourceRoot, database = safDbPath.toString(), sleepMsPerBatch = 0),
                sleeper = {}
            )
            val (sessionId, state) = scanner.run()
            assertEquals(SessionState.COMPLETE, state)
            val files = db.connection.query("SELECT relative_path,logical_bytes FROM files WHERE scan_session_id=?", listOf(sessionId)) {
                Pair(it.getStringAt(0), it.getLongAt(1))
            }
            assertEquals(listOf(Pair("Music/track.flac", 4096L)), files)
            val errors = db.connection.query("SELECT relative_path,error_type FROM scan_errors WHERE scan_session_id=?", listOf(sessionId)) {
                Pair(it.getStringAt(0), it.getStringAt(1))
            }
            assertEquals(listOf(Pair("temp.tmp", "FileNotFoundError")), errors)
        }

        // 2. Test MediaStoreScanAdapter
        val mediaClient = object : MediaStoreClient {
            override val volumeName: String = "external_primary"
            override fun isVolumeAvailable(): Boolean = true
            override fun queryAllEntries(): List<MediaStoreEntryRow> = listOf(
                MediaStoreEntryRow(1L, "DCIM/Camera", "IMG_001.jpg", 2048L, 1700000000L, 1690000000L)
            )
            override fun queryEntryById(id: Long): MediaStoreEntryRow? =
                queryAllEntries().firstOrNull { it.id == id }
        }
        val mediaAdapter = MediaStoreScanAdapter(mediaClient)
        val mediaDbPath = artifactRoot.resolve("media_inventory.db")
        val mediaGuard = WriteGuard(
            sourceVolume = mediaAdapter.resolveVolume(),
            allowedRootPath = artifactRoot,
            destinationVolume = destVol,
            volumeResolver = { destVol }
        )
        InventoryDatabase(mediaDbPath, mediaGuard).use { db ->
            val scanner = MetadataScanner(
                adapter = mediaAdapter,
                database = db,
                config = ScanConfig(source = mediaAdapter.sourceRoot, database = mediaDbPath.toString(), sleepMsPerBatch = 0),
                sleeper = {}
            )
            val (sessionId, state) = scanner.run()
            assertEquals(SessionState.COMPLETE, state)
            val files = db.connection.query("SELECT relative_path FROM files WHERE scan_session_id=?", listOf(sessionId)) {
                it.getStringAt(0)
            }
            assertEquals(listOf("DCIM/Camera/IMG_001.jpg"), files)
        }

        // 3. Test RootShellPosixBackend toybox stat parsing, su command runner fallback, and VolumeResolver
        val parsedStat = RootShellPosixBackend.parseToyboxStatLine("symbolic link|0|1700000000|1700000001|1700000002|64768")
        assertTrue(parsedStat.isSymbolicLink)
        assertFalse(parsedStat.isDirectory)
        assertEquals("posix-device:64768", parsedStat.volumeIdentity)

        val lockedTarget = artifactRoot.resolve("su_only_dir")
        val rootBackend = RootShellPosixBackend(
            fallbackNio = NioNoFollowPosixBackend(
                volumeResolver = { sourceVol },
                unreadablePaths = setOf(lockedTarget.toAbsolutePath().normalize())
            ),
            rootCommandRunner = { cmd ->
                val joined = cmd.joinToString(" ")
                when {
                    joined.contains("toybox stat -c '%d'") ->
                        RootShellPosixBackend.RootCommandResult(0, "64768\n", "")
                    joined.contains("toybox stat") ->
                        RootShellPosixBackend.RootCommandResult(0, "regular file|512|1700000000|1700000001|1700000002|64768\n", "")
                    joined.contains("toybox find") -> {
                        val posixDir = lockedTarget.toString().replace('\\', '/').trimEnd('/')
                        RootShellPosixBackend.RootCommandResult(0, "$posixDir/root_child.txt\n", "")
                    }
                    else -> RootShellPosixBackend.RootCommandResult(1, "", "unexpected command")
                }
            }
        )
        assertTrue(rootBackend.usesRootHelper)
        assertTrue(rootBackend.isMounted(lockedTarget, sourceVol))
        val rootStat = rootBackend.statNoFollow(lockedTarget.resolve("root_child.txt"))
        assertTrue(rootStat.isRegularFile)
        assertEquals(512L, rootStat.logicalBytes)
        val rootChildren = rootBackend.listChildNames(lockedTarget)
        assertEquals(listOf("root_child.txt"), rootChildren)

        val resolvedHostVol = VolumeResolver.resolveVolume(artifactRoot.resolve("nonexistent/child/path"))
        assertTrue(resolvedHostVol.identity.isNotEmpty())
        assertEquals(artifactRoot.toAbsolutePath().normalize(), VolumeResolver.existingProbe(artifactRoot.resolve("a/b/c")))

        val procMountsSample = """
            /dev/block/dm-5 /data f2fs rw,lazytime,seclabel,noatime 0 0
            /dev/fuse /storage/emulated/0 fuse rw,nosuid,nodev 0 0
            /dev/block/vold/public:8,1 /mnt/media_rw/ABCD-1234 exfat rw,dirsync,nosuid 0 0
        """.trimIndent()
        assertEquals("exfat", VolumeResolver.parseLinuxFilesystemType("/mnt/media_rw/ABCD-1234", procMountsSample))
        val mounts = VolumeResolver.discoverAndroidMounts(procMountsSample)
        assertEquals(3, mounts.size)
    }

    @Test
    fun testDatabaseLeaseAndResourceControllerLimits() {
        val sourceRoot = tempFolder.newFolder("lease_source").toPath()
        val artifactRoot = tempFolder.newFolder("lease_artifacts").toPath()
        writeString(sourceRoot.resolve("f1.txt"), "one")

        val guard = newDistinctGuard(artifactRoot)
        val dbPath = artifactRoot.resolve("inventory.db")

        // Verify exclusive -scanlock rejects a second concurrent InventoryDatabase on the same file
        InventoryDatabase(dbPath, guard).use {
            try {
                InventoryDatabase(dbPath, guard).close()
                fail("Expected ScanStateException when opening already-leased database")
            } catch (_: ScanStateException) {
                // Expected
            }
        }

        // Verify ResourceController heap limit transitions scan to STOPPED
        val adapter = PosixRootScanAdapter(
            rootPath = sourceRoot,
            backend = NioNoFollowPosixBackend(volumeResolver = { sourceVol }),
            volumeOverride = sourceVol
        )
        val failingResourceController = ResourceController(
            destinationDirectory = artifactRoot,
            policy = ResourcePolicy(maxHeapBytes = 32L * ResourceController.MIB, minFreeDestinationBytes = 1024L),
            memoryUsedBytesProvider = { 64L * ResourceController.MIB }
        )
        InventoryDatabase(dbPath, guard).use { db ->
            val scanner = MetadataScanner(
                adapter = adapter,
                volume = sourceVol,
                database = db,
                config = ScanConfig(source = adapter.sourceRoot, database = dbPath.toString(), sleepMsPerBatch = 0),
                resourceController = failingResourceController,
                sleeper = {}
            )
            val (_, state) = scanner.run()
            assertEquals(SessionState.STOPPED, state)
        }
    }

    @Test
    fun testStaticSafetyAndManifestZeroPermissions() {
        val projectDir = Path.of("").toAbsolutePath()
        val appDir = if (Files.exists(projectDir.resolve("app"))) projectDir.resolve("app") else projectDir
        val manifestFile = appDir.resolve("src/main/AndroidManifest.xml")
        assertTrue("AndroidManifest.xml must exist", Files.exists(manifestFile))
        val manifestText = readString(manifestFile)

        // Ensure INTERNET is strictly removed and GrapheneOS Storage Scopes permissions are declared
        assertTrue(manifestText.contains("android:name=\"android.permission.INTERNET\""))
        assertTrue(manifestText.contains("tools:node=\"remove\""))
        assertTrue(manifestText.contains("android.permission.READ_MEDIA_IMAGES"))
        assertTrue(manifestText.contains("android.permission.MANAGE_EXTERNAL_STORAGE"))
        assertFalse(manifestText.contains("WRITE_EXTERNAL_STORAGE"))

        // Inspect all core scanner Kotlin files for forbidden network, subprocess, or file deletion calls
        val coreDir = appDir.resolve("src/main/java/org/rootwise/android/core")
        val forbiddenTokens = listOf(
            "java.net.Socket",
            "java.net.HttpURLConnection",
            "java.net.URL",
            "okhttp3",
            "retrofit2",
            "ProcessBuilder",
            "Runtime.getRuntime().exec",
            "Files.delete",
            "Files.move",
            "File.delete"
        )
        Files.walk(coreDir).use { stream ->
            stream.filter { Files.isRegularFile(it) && it.toString().endsWith(".kt") }.forEach { ktFile ->
                val content = readString(ktFile)
                for (token in forbiddenTokens) {
                    assertFalse(
                        "Forbidden token '$token' found in core module ${ktFile.fileName}",
                        content.contains(token)
                    )
                }
            }
        }
    }
}
