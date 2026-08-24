# SmartStudy Multi-Tenant Architecture

## Scope

Phase 2 preserves the existing Flask, MySQL, Celery, Redis, and database-per-tenant architecture. The live tenant code is under `playschool_app/tenant_services/`; the duplicate `playschool_app/app/` tenant tree is not used by `playschool_app/app.py`.

## Control DB responsibility

The control database owns tenant metadata in `schools`, including the canonical `subdomain`, subscription state, and lifecycle metadata. Tenant requests never choose a database by submitting a database name, tenant ID, or school ID.

For a tenant hostname, the resolver performs a control-DB lookup by the validated subdomain. A missing record, malformed host, lookup error, or mapping mismatch rejects the request. The resolver does not fall back to the control DB after a tenant lookup failure.

## Tenant resolution flow

```text
trusted request host
        |
        v
canonical base-domain and port validation
        |
        v
strict single-label subdomain validation
        |
        v
control DB: schools.subdomain
        |
        v
resolved server-side tenant record
        |
        v
server-side credential provider
        |
        v
tenant-specific MySQL pool and connection
```

The canonical base domain is configured with `TENANT_BASE_DOMAIN`. Production must configure it. `www`, `api`, `app`, `admin`, and `control` are reserved labels. Nested subdomains, unrelated domains, malformed hosts, unexpected ports, and unknown tenants are rejected.

## Canonical hostname and trusted proxy rules

Only the configured base domain and one validated tenant label are accepted. Production accepts only ports configured by `TENANT_ALLOWED_PORTS`, which defaults to `80,443`. If the deployment is behind a trusted reverse proxy, `TRUSTED_PROXY_COUNT` enables Werkzeug `ProxyFix` for the configured number of proxy hops. It must not be enabled for an untrusted direct-client path.

The control host is the bare canonical base domain. A Super Admin session must use the control host; it cannot be reused on a tenant host. A non-Super-Admin session is bound to the resolved tenant subdomain and is rejected if moved to another tenant or to the control host.

## Tenant database mapping and credential provider

The runtime does not construct a tenant database name from the request host. After control-DB resolution, `tenant_services.tenant_db` loads the credential record for that server-side subdomain through `tenant_services.secrets_manager`.

For the initial VPS, production may use the explicitly selected `environment` provider or `protected_file` provider. The protected file must be an operator-owned 0600 path configured with `TENANT_DB_CREDENTIALS_FILE`; the historical `.tenant_secrets.json` path is never accepted in production. Production may explicitly select `aws`, but never falls back to local files if AWS is unavailable. Local JSON requires both `TENANT_CREDENTIAL_PROVIDER=local_file` and `ALLOW_LOCAL_TENANT_CREDENTIALS=1`, and is development-only. The provider interface is `get_tenant_db_credentials(subdomain)`, so a managed secret provider can replace the local provider without changing request code.

The credential payload supplies the server-side host, port, database, username, and password. It is validated before use. Root users, empty credentials, invalid database identifiers, invalid hosts, and invalid ports are rejected. Credentials are never read from browser input and are not returned in provisioning results or job responses.

## Connection pool design

Pools are cached by resolved tenant subdomain. Each cache entry also stores a fingerprint of the complete server-side credential/database mapping. If the mapping changes, the old pool is removed and its connections are closed before a new pool is created. Pool names include the tenant and mapping fingerprint, and LRU eviction closes removed pools.

The application passes the resolved tenant record from `g.tenant` to `get_connection_for_tenant`. A plain browser-supplied string is not accepted as a tenant connection reference.

## Request lifecycle

1. Trusted proxy handling, if explicitly configured, normalizes the request host.
2. Tenant middleware validates the host and resolves the control-DB tenant record.
3. The request session is checked against the resolved tenant subdomain.
4. Tenant queries use the tenant-specific credential record and pool.
5. Explicit `use_control=True` is reserved for control-plane metadata and Super Admin operations.
6. Tenant-owned object queries remain in the resolved tenant database and include ownership checks for the confirmed Phase 2 IDOR cases.

## Celery tenant context

Background work uses a serializable tenant reference containing a job ID and validated subdomain. The worker does not infer tenant identity from Flask request state, worker globals, or worker hostname. The reference is checked for presence, syntax, consistency, and control-record validity before tenant work.

The current Celery task is the provisioning task, which is a control-plane operation. No other tenant-data Celery task was found. Future tenant-data tasks must call the same explicit-reference validation before obtaining a tenant connection.

Celery integration is tested through the real Kombu Redis transport. Automated tests use an isolated RESP2 Redis-protocol TCP service backed by `fakeredis`; this is not the production broker and is destroyed after each test run. Production must use a supervised Redis 6/7-compatible service.

For the one-VPS deployment, `docker-compose.production.yml` enables Redis AOF,
authentication, restart supervision, and private networking. The production
Celery configuration rejects missing brokers, non-Redis/test brokers, and eager
execution. The job journal and audit log are placed on a protected durable
volume through `PROVISION_JOBS_FILE` and `PROVISION_AUDIT_FILE`; audit entries
redact sensitive fields before being persisted.

## Failure behavior

- Invalid, malformed, unexpected, or untrusted host: reject.
- Unknown tenant: reject.
- Control-DB lookup failure: reject.
- Missing or invalid tenant credentials: reject the tenant connection.
- Root or universal tenant credentials: reject.
- Tenant/session mismatch: reject and clear the session.
- Missing, inconsistent, deleted, or disabled background-job tenant context: reject the job.

No tenant-resolution failure silently selects the control database.

## Isolation guarantees

Within the implemented boundary:

- Tenant A resolves to its own control mapping and credential-backed database only.
- Tenant B resolves independently to its own database and credentials.
- Browser parameters cannot override the host-derived tenant context.
- A tenant connection cannot be selected with a browser-supplied database name or credential.
- Pool entries and credential rotations cannot cross-contaminate tenants.
- Confirmed teacher homework, grading, attendance, weekly-progress, student-homework, and admin-user object ownership gaps are checked within the current tenant.

These guarantees assume the control DB mapping, credential store, MySQL grants, trusted proxy configuration, and deployment secrets are administered securely. Provisioning now uses a dedicated non-root provisioning account, explicit-host tenant users with database-scoped grants, publishes the control mapping last, and compensates by dropping created resources and stored credentials on failure.

## Phase 4 private file boundary

New application uploads use the private storage helper and are stored under a
server-generated `tenant/<subdomain>/<category>/<random-key>` prefix outside
the static tree. Download authorization checks the resolved tenant and owning
database record/role. The legacy static upload path is denied. The current
baseline is local private storage; S3 integration, scanning, quotas, retention,
and backup/restore verification remain Phase 4 follow-up work.

## Testing strategy

`playschool_app/test_phase2_tenant_isolation.py` uses safe in-memory control mappings, fake MySQL pools, and fake credential records. `test_phase3_provisioning_integration.py` uses a disposable MySQL instance for database/user/grant/rollback verification. `test_phase3_celery_redis_integration.py` uses the real Kombu Redis transport against an isolated Redis-protocol TCP service and verifies enqueue, worker execution, failure/retry states, duplicate handling, and worker restart recovery. Install `playschool_app/requirements-test.txt` for the deterministic test service. No production credentials are used.
