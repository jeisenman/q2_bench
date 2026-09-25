# Vector search

The planned top-level `vectors` package implements exact cosine similarity with
NumPy. It is provider-independent and requires no API key.

## Pairwise similarity

```python
from vectors import cosine_similarity

scores = cosine_similarity(
    [[1.0, 0.0], [0.0, 1.0]],
    [[1.0, 1.0]],
)
```

For left shape `(m, dimensions)` and right shape `(n, dimensions)`, the result
has shape `(m, n)`. Inputs are normalized in a batch and multiplied as matrices
instead of comparing vectors in Python loops.

## Index and search

```python
from vectors import VectorIndex

index = VectorIndex(
    ids=("alpha", "beta"),
    vectors=[[1.0, 0.0], [0.0, 1.0]],
)
matches = index.search([0.9, 0.1], limit=1)
```

The exact index is appropriate for small and medium in-memory collections. For
large collections, keep the `VectorIndex` API boundary and add a dedicated
approximate-nearest-neighbor or remote vector-store adapter.

## Input contract

- Vectors must be two-dimensional when constructing an index.
- Query vectors must be one-dimensional.
- All vectors must have matching dimensions.
- Values must be finite.
- Zero-length vectors are rejected.
- Identifiers must be unique.
