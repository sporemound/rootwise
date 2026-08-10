# Stage 0.24 Accessibility Contract

Status: **DESIGNED**. Existing palette-safe decision presentation has received a visible Windows
retest, but the complete viewer has not yet passed an accessibility audit. Accessibility is a
release property of every view, not a final cosmetic stage.

## Keyboard and focus

- Every command and Context menu item is reachable without a mouse.
- Tab order follows location, search/filter, results, paging/status, then decision editor.
- Focus remains visible using the active Qt/Windows palette in Details view, Compact list view, and
  Tile view.
- View switching restores focus to the selected result when possible.
- Focus is not silently moved after Loading state completion, preference restoration, or decision
  recording.
- Default buttons do not cause Enter in search or note editors to perform an unrelated action.
- Shortcut conflicts are documented and tested; editor-owned keys take precedence.

## Names, roles, and announcements

Controls require accessible names independent of icon or position. Results expose observed Name,
Type, selected state, Decision state, and position in the bounded page. Breadcrumb segments expose
their full inventory-relative location and ancestor order. Loading state, Empty state, Error state,
decision success, and decision conflict are announced as text without requiring a modal dialog for
ordinary progress.

Icon, color, font weight, or position alone never conveys directory/file Type, current Decision,
error severity, sort direction, selection, uncertainty, or disabled state. Generic File-type icons
must have equivalent text. Recorded decisions retain explicit text rather than relying on bold.

## Contrast and themes

- Use Qt palette roles and native selection rendering; do not hard-code foreground/background pairs.
- Selected and unselected text must remain legible in Windows light, dark, high-contrast, inactive,
  focused, and unfocused states.
- Decision badges and analytical status use text plus shape/icon where appropriate.
- Custom delegates must paint selection consistently across the entire row/tile.
- Disabled text cannot be the only explanation for an unavailable safety-boundary action.

No contrast claim is made until visible review and measured contrast inspection are performed on
the final widgets. The previous white-on-white defect is a required regression scenario.

## High-DPI and layout

High-DPI behavior uses logical pixels and device-independent icons. Default Tile view size is
proposed as 128 logical pixels. At 100%, 150%, 200%, and mixed-monitor scaling:

- text is not clipped at the supported Windows text scale;
- icons remain crisp without controlling layout size through bitmap pixels;
- movable/resizable columns retain usable minimum widths;
- long names elide visually but remain available to assistive technology and tooltips;
- dialogs fit the available screen and remain keyboard movable;
- saved geometry outside current screens is clamped to a visible display.

## Motion, latency, and bounded work

Rootwise should not use decorative animation. A query that outlives the immediate interaction shows
a textual Loading state and preserves cancellation/failure semantics. Rendering remains bounded by
`ResultPage`; File-type icons and later thumbnail caches have explicit count/byte limits. A frozen
window is an accessibility failure even if the query eventually completes.

## Capability boundary

Accessibility metadata, generic icons, focus, keyboard behavior, preference restoration, and
announcements are `METADATA_ONLY`. Accessible decision editing remains `DECISIONS_ONLY`. Describing
source-derived Thumbnails or previews is `PERMISSIONED_CONTENT_READ` only after the separate
preview service supplies a result. Assistive technology must never trigger `PROHIBITED_EXECUTION`
such as launching, editing, moving, renaming, deleting, or archiving an observed source path.

No source path is opened to obtain an icon, accessible name, tooltip, description, or preview in
Stages 0.24–0.29.

## Verification matrix

Automated checks should cover accessible names, tab order, shortcut ownership, selection retention,
textual state labels, bounded row/tile counts, invalid saved geometry, long/Unicode names, and
query-only inventory access. These will be **UNIT TESTED** and **INTEGRATION TESTED** as each view
is implemented.

Manual Windows review must cover keyboard-only operation, Narrator or an equivalent accessibility
client, 100–200% scaling, light/dark/high-contrast themes, inactive-window selection, and the
white-on-white regression. Until that review occurs, these behaviors are **NOT VISUALLY TESTED**,
**NOT SCALE TESTED**, and **NOT WINDOWS TESTED** for the proposed view architecture. No accessibility
claim is based solely on the current offscreen Qt construction test.
