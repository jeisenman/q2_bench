---
name: upgrade-dependencies
description: Research, plan, implement, and verify Python, package, system-library, and container-image upgrades prompted by end-of-life risk, compatibility needs, or security advisories.
---

# Upgrade Dependencies

Upgrade Python projects with evidence-backed compatibility analysis and
deterministic verification. Use stateless Luna workers for independent
research and review tasks when they are available.

## Inputs

Before changing files, establish:

- the repository and component in scope;
- the upgrade trigger: security advisory, package end of life, Python end of
  life, compatibility requirement, or routine maintenance;
- the affected package, system library, container image, or Python version;
- the requested deadline and acceptable target version;
- whether dependency-manager migration is in scope.

If a security report names a system library such as FreeType, first determine
whether it comes from the base image, an operating-system package, a Python
wheel, or an application dependency. Do not assume every reported
vulnerability can be fixed by changing a Python requirement.

## Project discovery

Inspect the repository before selecting an upgrade command. Include:

- `pyproject.toml`, `uv.lock`, `requirements*.txt`, and constraint files;
- `Dockerfile*`, container manifests, and pinned base images;
- CI workflows, deployment manifests, and runtime configuration;
- Python version files and classifiers;
- source imports, dependency APIs, and existing tests.

Use the project's existing package manager:

- For a uv project, update `pyproject.toml` and regenerate `uv.lock` with uv.
- For a pip project, update its requirements and constraints files.
- Do not create an empty `pyproject.toml`. Migrate a pip project only when
  migration is explicitly in scope, and create complete, valid project
  metadata as part of that migration.
- Preserve exact pins and constraints unless the upgrade requires changing
  them. Never delete a lock or constraint file to force resolution.

Record the current test, lint, type-check, and build commands. Run an
appropriate baseline before editing when the project can execute locally.

## Research with Luna

Delegate independent research to stateless `openai.gpt-5.6-luna` workers with
high reasoning. Give each worker only the package or upgrade range it owns and
require source URLs, version dates, and explicit uncertainty. Do not give a
worker conclusions from another worker.

Useful parallel assignments include:

1. package and Python compatibility;
2. release notes, migration guides, removals, and deprecations;
3. security advisory scope and fixed versions;
4. container base-image and operating-system package provenance;
5. an independent review of the completed upgrade.

For every version crossed between the current and target versions, research
the published release notes and migration guides. Report all documented
breaking changes, removals, and deprecations relevant to the traversed range.
Include standard-library changes when upgrading Python. Do not claim the list
is complete when upstream documentation is missing or ambiguous; identify the
gap instead.

Prefer authoritative sources:

- official package documentation, release notes, and migration guides;
- PyPI release metadata for release history and `Requires-Python`;
- Python release and porting documentation;
- official security advisories, NVD, CISA KEV, and OS-vendor advisories;
- official container registries and base-image release notes.

PyPI metadata alone is not proof that a project is supported or end of life.

## Upgrade report

Create `upgrade.md` at the repository root. Keep it current throughout the
work and include the evidence date.

Use this inventory table:

| Component | Kind | Current | Target | Direct or transitive | Reason | Support status | Compatibility | Fixed version | Source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `example` | Python package, Python, OS package, or image | `1.0` | `2.0` | Direct | CVE, EOL, or maintenance | Supported, near EOL, EOL, or unknown | Supported Python range and known blockers | First non-vulnerable version or N/A | Authoritative reference |

For each component, document:

- where its current version is declared or resolved;
- why the target was selected;
- support or end-of-life evidence;
- every traversed breaking change, removal, and relevant deprecation;
- affected source locations, or `no usage found`;
- required code, configuration, test, and deployment changes;
- unresolved questions and evidence gaps.

Add a compact dependency graph or version timeline only when it makes a
transitive relationship or multi-stage upgrade materially easier to
understand.

## Implementation workflow

1. Inventory direct dependencies, resolved transitive dependencies, Python
   versions, system packages, and container images.
2. Select the smallest supported target that resolves the stated trigger,
   unless the user requests a newer target.
3. Complete the Luna research and record evidence in `upgrade.md`.
4. Search the codebase with `rg` for removed or changed APIs, imports,
   configuration keys, command-line flags, and version declarations.
5. Record every match before editing. Distinguish application use from test,
   example, generated, vendored, and dead code.
6. Update dependency declarations and code in reviewable groups. Preserve
   backward compatibility when practical.
7. Regenerate lock files with the existing package manager. Review unexpected
   transitive changes instead of accepting them silently.
8. Update tests and documentation for changed behavior.
9. Build affected container images when applicable and confirm that the
   vulnerable layer or package is replaced.
10. Update `upgrade.md` with implemented changes, verification results, and
    remaining risks.

Fail fast when the target has no compatible release, the resolver introduces
an unexplained downgrade, required upstream evidence is unavailable, or the
security advisory cannot be mapped to a concrete installed component.

## Verification

Run the repository's required quality command plus targeted checks for each
changed integration. Verification should cover:

- dependency resolution from a clean environment;
- supported Python versions;
- unit, integration, lint, formatting, and type checks required by the
  repository;
- imports and startup paths;
- container build and vulnerability rescan when the trigger is a container
  finding;
- runtime smoke tests for changed external integrations.

Use stateless Luna workers to review independent areas of the final diff and
the evidence in `upgrade.md`. Each worker must report the files and checks it
examined. The primary agent resolves conflicting findings and remains
responsible for final verification; worker review does not replace executable
checks.

## Final report

Summarize:

- versions changed and the trigger they resolve;
- compatibility changes made in source and configuration;
- lock-file and transitive dependency changes;
- verification commands and outcomes;
- security-rescan status when applicable;
- remaining risks, blocked checks, and rollback considerations.
