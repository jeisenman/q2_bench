# Caller policy: single-luna-audit-cleanup/1

Trusted user instruction for this rollout: use the same single Luna pass to
remove audit clauses, preserve technical text, and add only relevant article
context. This caller policy supplements the frozen prompt 2.0.0.

Remove existing Zendesk audit, support-status, and documentation-absence prose.
Preserve technical behavior, filters, keys, units, windows, row multiplicity,
source pins, material limits, and useful source citations. Keep technical
caveats even when they share a sentence with an audit clause. Do not replace
missing source evidence with product documentation.

Add attributed article context only when the supplied article text is relevant
to this exact target or its explicitly attributed product context. Use only
supplied original article URLs. If no article is relevant, only audit cleanup
is allowed; preserve the remaining definition unchanged.

For a definition marked pending_single_luna_cleanup, the full original text is
supplied because deterministic preparation could not safely separate an audit
clause from useful technical text. Perform that cleanup and any relevant
article edit in this same single pass. Do not request or run another model pass.

Return the existing definition format and keys only. Do not add audit tables,
support verdicts, confidence scores, evidence appendices, or approval language.
Do not claim SME approval. Do not publish or change graph evidence.
