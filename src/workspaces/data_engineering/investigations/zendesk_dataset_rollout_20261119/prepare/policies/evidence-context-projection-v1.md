# Evidence context projection: dataset-edit-context/1

This deterministic context is for editing one existing dataset definition.
The complete frozen graph, full dataset bundle in target.json, and complete
original published request and response remain hash-pinned review artifacts.
The model receives artifact paths and hashes; these references do not mean
that the model has read the referenced content.

The model target retains exact dataset identity, kind, scope, generation,
bundle, source provenance, linked producer/consumer job identities and DAGs,
and every field identity, type, and nullable flag. Repeated source pins and
paths use lossless shared pools. Job and field machine/SME meaning, job
transformation inventories, field source lists, and other facets are omitted
from this compact target only. Full bundles remain in target.json. The
definition being edited is supplied once as the definition object.

The complete published targetNode is retained without projecting its schema,
resources, attributes, source locations, context, or transformations.
The complete published codeContext is retained byte-for-byte before JSON
serialization, with matching source/projected raw hashes and a canonical JSON
data hash. No code snippet or target operation is removed.

Published graphContext retains every incoming and outgoing relation, its
relationship kind, and each neighbor's exact ID, kind, namespace, name, and
version. Only non-target neighbor description, sourceLocations, and declared
transformations are omitted from model context. Their complete source values
remain in original-request.json at evidence.graphContext with its exact hash.
Unknown neighbor keys or code-like excerpts fail preparation. Do not infer
exact dataset-to-notebook execution from omitted neighbor inventories.

This is a bounded task context, not a change to source evidence. No source
array is shortened. All target schema/resource facts, target operation
inventory, direct relation identities, edge kinds, versions, and code remain
available as declared. Existing size limits continue to apply.
