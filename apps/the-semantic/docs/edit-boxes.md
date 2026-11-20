# Document edit boxes

Use in-place editing for saved document text. Keep each field at its reading
location and keep the document order. Show one editable value for each field.
Hide its read view for the edit session. Cancel restores the read view without
a write. Save returns to the updated read view after the server confirms it.

`apps/desktop/src/edit-box.ts` owns field creation and styling hooks.
`apps/desktop/src/edit-box.css` owns the visual standard: warm paper fill,
thin rust border, square corners, regular body weight, serif title, visible
keyboard focus, and a right-aligned Save/Cancel row. Use the shared classes in
dialogs too. Keep field labels visible. Use native inputs and textareas with
accessible names, length limits, and required states. Long text supports vertical
resizing and line wrapping. Do not inherit bold text from a label.

`mountDocumentEditor` owns document reads, validation and versioned saves.
Pass `fieldTargets` to bind content names to their displayed elements. The
editor hides those elements and inserts fields beside them. Fields outside the
form use its native `form` association, so validation and submission still work.
Keep these targets stable until the editor is disposed. The existing SME region
uses one local editor with its source text hidden during editing.

Edit starts with the latest validated saved content. Save disables fields and
actions until it completes. A failed or uncertain save retains entered text and
the retry key. Navigation and closure protect unsaved text. History is read-only.
Keep optimistic version checks and document identity checks. Saving a proposal
does not accept it or start research. Agent versions and source evidence keep
their existing persistence rules.

Check Edit, Cancel, confirmed Save, failed Save, unchanged retry, validation,
keyboard access, narrow layouts and disposal. Confirm that a title remains at
the top, body fields keep their order, no read copy appears beside its editor,
and source evidence remains accessible. Use isolated fixtures for save checks.
