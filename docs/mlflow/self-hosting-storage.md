# Self-Hosting, Storage, and Security

## Architecture

An MLflow deployment typically separates:

```text
client / agent
      │
      ▼
tracking server ─── backend store (metadata)
      │
      └──────────── artifact store (files, models, traces)
```

Canonical sources:

- [Self-hosting overview](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/self-hosting/index.mdx)
- [Architecture overview](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/self-hosting/architecture/overview.mdx)
- [Backend store](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/self-hosting/architecture/backend-store.mdx)
- [Artifact store](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/self-hosting/architecture/artifact-store.mdx)
- [Tracking server](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/self-hosting/architecture/tracking-server.mdx)

## Stores

The backend store holds experiments, runs, parameters, metrics, tags, model
metadata, and other server metadata. A database-backed store is the normal
enterprise choice. A local SQLite store is useful for development.

The artifact store holds files and model directories. Choose a filesystem or
object store appropriate to the deployment boundary, permissions, retention,
encryption, and backup policy.

Do not assume that protecting the tracking server automatically protects direct
artifact access. Validate both paths and use least-privilege credentials.

## Security controls

The tagged docs cover:

- basic HTTP authentication;
- SSO and role-based access control;
- network security and TLS termination;
- Kubernetes security;
- secure installation guidance;
- custom security extensions;
- webhooks and workspace permissions.

Canonical sources:

- [Security index](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/self-hosting/security)
- [Basic HTTP auth](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/self-hosting/security/basic-http-auth.mdx)
- [SSO](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/self-hosting/security/sso.mdx)
- [RBAC](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/self-hosting/security/role-based-access-control.mdx)
- [Network security](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/self-hosting/security/network.mdx)
- [Kubernetes security](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/self-hosting/security/kubernetes.mdx)

## Local enterprise baseline

- Bind local development services to loopback by default.
- Put authentication and TLS at the approved ingress boundary.
- Use a dedicated service identity for tracking metadata and artifacts.
- Restrict artifact roots to approved buckets or volumes.
- Redact secrets and sensitive prompts before trace logging.
- Back up the backend database and artifact store independently.
- Test restore, retention, deletion, and access revocation.
- Pin the MLflow server and client versions together during benchmark runs.

## Deployment options

The tagged docs include managed-cloud deployment notes for AWS, Azure, and
GCP, plus Kubernetes Helm and workspace configuration.

- [Kubernetes Helm](https://github.com/mlflow/mlflow/blob/v3.16.1/docs/docs/self-hosting/kubernetes-helm.mdx)
- [Cloud deployment](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/self-hosting/deploy-to-cloud)
- [Workspaces](https://github.com/mlflow/mlflow/tree/v3.16.1/docs/docs/self-hosting/workspaces)
