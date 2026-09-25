# Updating the Local MLflow Docs

This local documentation is a curated index, not a vendored copy of MLflow.
Refresh it when changing the MLflow package, server image, or benchmark
contract.

## Refresh procedure

1. Check the official [MLflow releases](https://github.com/mlflow/mlflow/releases)
   for the newest stable 3.x release.
2. Verify the tag, release date, tag commit, Python requirement, license, and
   release notes in `mlflow/mlflow`.
3. Inspect the tagged paths under:
   - [`docs/docs/classic-ml`](https://github.com/mlflow/mlflow/tree/master/docs/docs/classic-ml)
   - [`docs/docs/genai`](https://github.com/mlflow/mlflow/tree/master/docs/docs/genai)
   - [`docs/docs/self-hosting`](https://github.com/mlflow/mlflow/tree/master/docs/docs/self-hosting)
   - [`docs/api_reference`](https://github.com/mlflow/mlflow/tree/master/docs/api_reference)
4. Update the version and provenance in `README.md`.
5. Update canonical links and feature notes in the topic guides.
6. Recheck that no local document exceeds 400 lines.
7. Run `uv run python scripts/check.py`.

## Reproducible shell checks

```bash
VERSION=v3.16.1
REPO=https://github.com/mlflow/mlflow.git

git ls-remote "$REPO" "refs/tags/$VERSION"
curl -fsSL "https://api.github.com/repos/mlflow/mlflow/releases/tags/$VERSION"
curl -fsSL "https://raw.githubusercontent.com/mlflow/mlflow/$VERSION/LICENSE.txt"
```

The release API response is the authoritative source for publication date and
release notes. `git ls-remote` is the authoritative source for the tag commit.

## Version recommendation rules

Prefer the newest stable MLflow 3.x patch release that:

- supports Python 3.11;
- has an immutable or verifiable tag;
- passes the repository's tracking, artifacts, registry, GenAI, and serving
  smoke tests;
- has no unresolved security or compatibility issue for the target deployment.

Do not silently switch to `latest` in reproducibility-sensitive benchmarks.
