package org.rootwise.android.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.rootwise.android.viewer.DecisionRecord
import org.rootwise.android.viewer.DecisionStore
import org.rootwise.android.viewer.InventoryItem
import org.rootwise.android.viewer.SessionSummary
import org.rootwise.android.viewer.SortField
import org.rootwise.android.viewer.SortOrder

enum class ScanSurfaceMode(val label: String) {
    ROOT_POSIX("Root POSIX (openat/lstat)"),
    SAF_TREE("SAF Document Tree"),
    MEDIA_STORE("MediaStore Index")
}

private val RootwiseDarkColorScheme = darkColorScheme(
    primary = Color(0xFF8AB4F8),
    secondary = Color(0xFF81C995),
    tertiary = Color(0xFFFDD663),
    background = Color(0xFF0E1116),
    surface = Color(0xFF161B22),
    onBackground = Color(0xFFE6EDF3),
    onSurface = Color(0xFFE6EDF3)
)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun RootwiseApp(
    statusMessage: String,
    isScanning: Boolean,
    selectedMode: ScanSurfaceMode,
    onSelectMode: (ScanSurfaceMode) -> Unit,
    posixPathInput: String,
    onPosixPathChange: (String) -> Unit,
    useRootSuHelper: Boolean,
    onToggleRootSuHelper: (Boolean) -> Unit,
    allowSameVolumeGuard: Boolean,
    onToggleSameVolumeGuard: (Boolean) -> Unit,
    selectedSafUriString: String?,
    onPickSafTree: () -> Unit,
    onRequestStorageScopes: () -> Unit = {},
    onOpenAllFilesSettings: () -> Unit = {},
    onStartScan: () -> Unit,
    sessions: List<SessionSummary>,
    activeSessionId: String?,
    onSelectSession: (String) -> Unit,
    searchQuery: String,
    onSearchQueryChange: (String) -> Unit,
    kindFilter: String?,
    onKindFilterChange: (String?) -> Unit,
    sortField: SortField,
    onSortFieldChange: (SortField) -> Unit,
    sortOrder: SortOrder,
    onSortOrderChange: (SortOrder) -> Unit,
    items: List<InventoryItem>,
    decisionsByPath: Map<String, DecisionRecord>,
    onRecordDecision: (String, String, String) -> Unit,
    onExportInventoryDb: () -> Unit,
    onExportProposalJson: () -> Unit,
    artifactDirectoryDisplay: String
) {
    var selectedItemForDecision by remember { mutableStateOf<InventoryItem?>(null) }

    MaterialTheme(colorScheme = RootwiseDarkColorScheme) {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = MaterialTheme.colorScheme.background
        ) {
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                item {
                    Text(
                        text = "Rootwise Audit Inventory (0.23.0-alpha port)",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "Metadata-only scanner • Query-only viewer • Separate decisions • Non-executable proposals",
                        style = MaterialTheme.typography.bodySmall,
                        color = Color(0xFF8B949E)
                    )
                }

                item {
                    Card(
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(
                                text = "Trust Boundary & Coverage Honesty",
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.SemiBold
                            )
                            Text(
                                text = "Artifact Store (outside scanned tree): $artifactDirectoryDisplay",
                                style = MaterialTheme.typography.bodySmall,
                                fontFamily = FontFamily.Monospace
                            )
                            val coverageNote = when (selectedMode) {
                                ScanSurfaceMode.ROOT_POSIX ->
                                    "Root POSIX Mode: Enforces O_NOFOLLOW/NOFOLLOW_LINKS, st_dev volume checks, and Stage 0.21 fresh lstat. " +
                                        "When scanning /storage/emulated/0, /data, or /data/media/0 on shared userdata, self-excludes org.rootwise.android artifact dirs."
                                ScanSurfaceMode.SAF_TREE ->
                                    "SAF Mode: Scoped to user-selected tree. Blind spots: Android/data, Android/obb, /data. " +
                                        "Records nofollow_enforced=false and kernel_st_dev_enforced=false in session metadata."
                                ScanSurfaceMode.MEDIA_STORE ->
                                    "MediaStore Mode: Queries indexed metadata columns only. Blind spots: Android/data, Android/obb, .nomedia, non-media files."
                            }
                            Text(
                                text = coverageNote,
                                style = MaterialTheme.typography.bodySmall,
                                color = Color(0xFFFDD663)
                            )
                        }
                    }
                }

                item {
                    Card(
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(
                                text = "1. Scan Source Surface & GrapheneOS Storage Access",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.SemiBold
                            )
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                OutlinedButton(onClick = onRequestStorageScopes) {
                                    Text("Grant Storage / Storage Scopes")
                                }
                                OutlinedButton(onClick = onOpenAllFilesSettings) {
                                    Text("All Files / Storage Scopes Settings")
                                }
                                OutlinedButton(onClick = onPickSafTree) {
                                    Text("Pick SAF Folder")
                                }
                            }
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                ScanSurfaceMode.entries.forEach { mode ->
                                    FilterChip(
                                        selected = selectedMode == mode,
                                        onClick = { onSelectMode(mode) },
                                        label = { Text(mode.label) }
                                    )
                                }
                            }

                            when (selectedMode) {
                                ScanSurfaceMode.ROOT_POSIX -> {
                                    OutlinedTextField(
                                        value = posixPathInput,
                                        onValueChange = onPosixPathChange,
                                        label = { Text("POSIX Mount / Directory Path") },
                                        modifier = Modifier.fillMaxWidth(),
                                        singleLine = true
                                    )
                                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                        listOf("/storage/emulated/0", "/data/media/0", "/data", "/mnt/media_rw", "/storage").forEach { preset ->
                                            OutlinedButton(onClick = { onPosixPathChange(preset) }) {
                                                Text(preset, fontFamily = FontFamily.Monospace)
                                            }
                                        }
                                    }
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Checkbox(checked = useRootSuHelper, onCheckedChange = onToggleRootSuHelper)
                                        Text(
                                            text = "Use root helper (su --mount-master toybox lstat/find) for protected paths",
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                    }
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Checkbox(checked = allowSameVolumeGuard, onCheckedChange = onToggleSameVolumeGuard)
                                        Text(
                                            text = "Allow shared userdata st_dev with disjoint-subtree & self-exclusion guard",
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                    }
                                }
                                ScanSurfaceMode.SAF_TREE -> {
                                    Text(
                                        text = "Selected Tree URI: ${selectedSafUriString ?: "None"}",
                                        style = MaterialTheme.typography.bodySmall,
                                        fontFamily = FontFamily.Monospace
                                    )
                                    OutlinedButton(onClick = onPickSafTree) {
                                        Text("Pick SAF Document Tree (Read-Only)")
                                    }
                                }
                                ScanSurfaceMode.MEDIA_STORE -> {
                                    Text(
                                        text = "Volume: MediaStore.VOLUME_EXTERNAL_PRIMARY (metadata projection only)",
                                        style = MaterialTheme.typography.bodySmall,
                                        fontFamily = FontFamily.Monospace
                                    )
                                }
                            }

                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button(
                                    onClick = onStartScan,
                                    enabled = !isScanning
                                ) {
                                    Text(if (isScanning) "Scanning..." else "Run Metadata Scan")
                                }
                                OutlinedButton(onClick = onExportInventoryDb) {
                                    Text("Export inventory.db")
                                }
                                OutlinedButton(onClick = onExportProposalJson) {
                                    Text("Export Proposal JSON")
                                }
                            }

                            Text(
                                text = statusMessage,
                                style = MaterialTheme.typography.bodySmall,
                                color = Color(0xFF81C995),
                                fontFamily = FontFamily.Monospace
                            )
                        }
                    }
                }

                if (sessions.isNotEmpty()) {
                    item {
                        Card(
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(
                                    text = "2. Recorded Scan Sessions (${sessions.size})",
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.SemiBold
                                )
                                sessions.forEach { sess ->
                                    val isSelected = sess.scanSessionId == activeSessionId
                                    Row(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .background(if (isSelected) Color(0xFF1F2937) else Color.Transparent)
                                            .clickable { onSelectSession(sess.scanSessionId) }
                                            .padding(6.dp),
                                        horizontalArrangement = Arrangement.SpaceBetween
                                    ) {
                                        Column {
                                            Text(
                                                text = "${sess.scanSessionId.take(8)} • ${sess.state} • ${sess.sourceRoot}",
                                                style = MaterialTheme.typography.bodySmall,
                                                fontFamily = FontFamily.Monospace
                                            )
                                            Text(
                                                text = "Observed: ${sess.observedCount} | Errors: ${sess.errorCount}",
                                                style = MaterialTheme.typography.bodySmall,
                                                color = Color(0xFF8B949E)
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                item {
                    Card(
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(
                                text = "3. Query-Only Inventory Review (${items.size} shown, max 500)",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.SemiBold
                            )
                            OutlinedTextField(
                                value = searchQuery,
                                onValueChange = onSearchQueryChange,
                                label = { Text("Search relative path (NFC-normalized)") },
                                modifier = Modifier.fillMaxWidth(),
                                singleLine = true
                            )
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                listOf(null to "All", "directory" to "Directories", "file" to "Files").forEach { (k, label) ->
                                    FilterChip(
                                        selected = kindFilter == k,
                                        onClick = { onKindFilterChange(k) },
                                        label = { Text(label) }
                                    )
                                }
                            }
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                SortField.entries.forEach { field ->
                                    FilterChip(
                                        selected = sortField == field,
                                        onClick = { onSortFieldChange(field) },
                                        label = { Text("Sort: ${field.name}") }
                                    )
                                }
                                FilterChip(
                                    selected = true,
                                    onClick = {
                                        onSortOrderChange(if (sortOrder == SortOrder.ASC) SortOrder.DESC else SortOrder.ASC)
                                    },
                                    label = { Text(sortOrder.name) }
                                )
                            }
                        }
                    }
                }

                selectedItemForDecision?.let { targetItem ->
                    item {
                        val existingDec = decisionsByPath[targetItem.relativePath]
                        Card(
                            colors = CardDefaults.cardColors(containerColor = Color(0xFF1E293B)),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(
                                    text = "Decision for: ${targetItem.relativePath}",
                                    style = MaterialTheme.typography.titleSmall,
                                    fontFamily = FontFamily.Monospace
                                )
                                Text(
                                    text = "Current: ${existingDec?.decision ?: "NONE"} (rev ${existingDec?.revision ?: 0})",
                                    style = MaterialTheme.typography.bodySmall
                                )
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    DecisionStore.DECISIONS.forEach { dec ->
                                        OutlinedButton(
                                            onClick = {
                                                onRecordDecision(targetItem.relativePath, dec, "Android review UI")
                                                selectedItemForDecision = null
                                            }
                                        ) {
                                            Text(dec, style = MaterialTheme.typography.labelSmall)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                items(items, key = { "${it.kind}:${it.relativePath}" }) { item ->
                    val dec = decisionsByPath[item.relativePath]
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(MaterialTheme.colorScheme.surface)
                            .clickable { selectedItemForDecision = item }
                            .padding(10.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                text = if (item.kind == "directory") "[DIR] ${item.relativePath}" else item.relativePath,
                                style = MaterialTheme.typography.bodyMedium,
                                fontFamily = FontFamily.Monospace,
                                modifier = Modifier.weight(1f)
                            )
                            Text(
                                text = "${item.logicalBytes} B",
                                style = MaterialTheme.typography.bodySmall,
                                fontFamily = FontFamily.Monospace,
                                color = Color(0xFF8AB4F8)
                            )
                        }
                        Spacer(modifier = Modifier.height(2.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                text = "depth=${item.depth} status=${item.observationStatus}",
                                style = MaterialTheme.typography.labelSmall,
                                color = Color(0xFF8B949E)
                            )
                            if (dec != null) {
                                Text(
                                    text = "${dec.decision} (v${dec.revision})",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = Color(0xFFFDD663),
                                    fontWeight = FontWeight.Bold
                                )
                            }
                        }
                        HorizontalDivider(modifier = Modifier.padding(top = 6.dp), color = Color(0xFF30363D))
                    }
                }
            }
        }
    }
}
