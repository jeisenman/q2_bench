---
name: semantic-edit-box
description: Build or revise document edit boxes in The Semantic desktop app using the shared in-place editing component and design standard. Use for editor consistency across its tabs and dialogs.
---

# Semantic edit boxes

Read [the design standard](../../../apps/the-semantic/docs/edit-boxes.md) and the
desktop AGENTS.md before changes. Use `edit-box.ts` and `edit-box.css` for fields;
use `mountDocumentEditor` for versioned document edits. Keep domain-specific
validation and persistence in their existing layers.

Bind displayed text through `fieldTargets` when using the document editor.
Keep each field in its reading position and hide the corresponding read value
until Save or Cancel. Keep target elements stable while the editor is mounted.
Dialogs use the same field and action classes. Do not add another form above a
complete read view or duplicate the persistence bridge for a visual change.

Preserve explicit Save/Cancel, visible keyboard focus, accessible names,
version checks, uncertain-save text and keys, navigation guards, and read-only
history. Use isolated document fixtures to verify writes and cancellation.
Report actual checks and any unverified visual behavior.
