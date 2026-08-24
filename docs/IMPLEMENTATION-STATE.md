# SmartStudy SaaS Implementation State

## Target

- 5–10 schools
- One VPS initially
- Cloudflare/DNS
- Nginx + HTTPS
- Flask + Gunicorn
- Celery + Redis
- MySQL
- Separate database per tenant
- Object storage with tenant prefixes

## Current phase

- Phase 3 = FROZEN
- Phase 4 = IN PROGRESS; production verification pending
- Phase 5 = production verification pending
- Phase 6 = NOT STARTED

## Current release-candidate verification snapshot

The following is the authoritative current local status. Older phase sections
below are retained as an audit trail and may contain historical test counts.

- Full unittest discovery: **88 passed, 10 environment-gated skips, 0 failures**.
- Local disposable tenant provisioning: **PASS**.
- Separate `TENANT_GRANT_MYSQL_*` grant-account architecture: **PASS locally**.
- Temporary provisioning diagnostic: **reverted**.
- Disposable tenant resources and credentials: **cleaned up**.
- Production deployment: **NOT YET COMPLETED**.
- Staging deployment: **NOT YET DEPLOYED**.
- Phase 4 production verification: **PENDING**.
- Phase 5 production verification: **PENDING**.
- Real S3, ClamAV, HTTPS, Razorpay, SMTP, and off-host backup verification:
  **PENDING where applicable**.

## Completed

- Phase 0 audit completed
- `docs/PRODUCTION-AUDIT.md` created
- Phase 0 audit did not modify application code
- Confirmed blockers from the audit are recorded below

## Next phases

- Phase 1: Production security lockdown — IMPLEMENTED
- Phase 2: Multi-tenant and database isolation — IMPLEMENTED; broader authorization/storage blockers remain deferred
- Phase 3: Tenant provisioning hardening — FROZEN; local verification complete, production verification pending
- Phase 4: Object storage / file security — IN PROGRESS; private storage, optional S3 provider, scanning/quota/retention hooks, migration and backup utilities implemented; live provider verification pending
- Phase 5: Billing and Payments — IMPLEMENTED LOCALLY; real Razorpay/payment-provider verification pending
- Phase 6: Backup and disaster recovery — NOT STARTED
- Phase 7: VPS / Docker / Nginx / HTTPS deployment — NOT STARTED
- Phase 8: Final security audit and production testing — NOT STARTED

## Important constraints

- Do not rewrite the existing Flask architecture.
- Preserve MySQL.
- Preserve Celery + Redis.
- Preserve database-per-tenant architecture.
- Make the smallest safe changes.
- Do not work on multiple phases simultaneously.
- Every phase must have tests.
- Never commit secrets or production credentials.

## Confirmed blockers from `docs/PRODUCTION-AUDIT.md`

- `/init-db` is unauthenticated and seeds predictable accounts.
- Tenant runtime pools use global/root credentials instead of provisioned tenant credentials.
- Upload downloads require login but do not authorize file ownership, school, record, role, or tenant access.
- Demo and root credentials are committed or hardcoded in source/configuration.
- Razorpay is listed as a dependency, but no actual integration or webhook verification exists.
- OTPs use `random.randint` and have no expiry, retry/attempt limit, or rate limiting; reset flows reveal unknown accounts.
- Provisioning jobs and local tenant secrets use JSON files and are not durable or safe for multi-process production use.
- Backups omit important service data and have no verified restore, retention, encryption, or alerting process.
- MySQL and Redis are exposed by Compose, with root credentials passed to web and worker containers.
- CI runs compilation only and does not execute application, security, isolation, migration, dependency, secret, or container tests.

## Phase 1: Production security lockdown

### Status

- Implemented in the live runtime paths and covered by the regression suite.

### Confirmed issues fixed

- Removed the unauthenticated `/init-db` route; no replacement public initializer was added.
- Removed default and demo account seeding from the live setup helper and SQL seed files.
- Removed the audit-confirmed predictable credentials from production execution and migration paths.
- Production configuration now requires a non-root `MYSQL_USER`, `MYSQL_PASSWORD`, and a sufficiently long `SECRET_KEY`.
- Production startup no longer auto-creates a missing database or seeds accounts.
- The development `/test` route is not registered when `FLASK_ENV=production`.
- Docker Compose web and worker services now require externally supplied non-root application credentials.

### Files changed

- `playschool_app/app.py`
- `playschool_app/config.py`
- `playschool_app/mysql_setup.py`
- `playschool_app/migrate_db.py`
- `playschool_app/scripts/run_migrations.py`
- `playschool_app/scripts/provision_tenant.py`
- `playschool_app/schema.sql`
- `playschool_app/sqlite_schema.sql`
- `playschool_app/docker-compose.yml`
- `playschool_app/README.md`
- `playschool_app/test_phase1_security.py`

### Tests added and executed

- Added `playschool_app/test_phase1_security.py` covering production secret requirements, root-account rejection, removed routes, removed runtime credentials, and Compose credential requirements.
- Executed `python -m unittest -v test_phase1_security.py`: 5 tests passed; 2 Flask route tests were skipped because Flask is unavailable.
- Executed `python -m py_compile` for the changed Python runtime and support files successfully.

### Remaining blockers

- Full tenant-specific credential mapping and database isolation remain Phase 2 blockers.
- Upload authorization, provisioning durability, Razorpay/webhooks, OTP/reset hardening, backups, and deployment hardening remain deferred to their audited phases.
- A dependency-complete environment is still required to execute the live Flask route tests.

## Phase 2: Multi-tenant and database isolation

### Status

- Credential-provider hardening and confirmed tenant-isolation changes are implemented and verified locally.
- Broader upload/storage authorization and production-service verification remain outstanding; no further Phase 2 redesign is part of the frozen baseline.

### Changes recorded

- Host resolution now requires the configured canonical base domain, a strict single-label tenant subdomain, an allowed port, and a control-DB tenant record.
- Resolver, control lookup, credential lookup, pool creation, and tenant session binding fail closed.
- Tenant runtime connections use the existing server-side tenant credential provider rather than global credentials or host-derived database names.
- Production requires an explicit `environment`, `protected_file`, or `aws` tenant credential provider and never silently falls back to `.tenant_secrets.json`.
- Development local JSON credentials require explicit `TENANT_CREDENTIAL_PROVIDER=local_file` and `ALLOW_LOCAL_TENANT_CREDENTIALS=1`.
- Missing production provider configuration, missing tenant credentials, unavailable providers, and root tenant users fail closed.
- Tenant pools are keyed by tenant and credential mapping, rotate safely when credentials change, and close on eviction.
- Browser-provided tenant/database values cannot override resolved request context.
- Confirmed tenant-owned route IDOR cases were tightened for teacher homework/submissions/grading, weekly progress, student homework submission, attendance, and admin user deletion.
- Celery provisioning jobs now carry explicit validated tenant references and do not return tenant passwords in results.

### Files changed

- `playschool_app/app.py`
- `playschool_app/config.py`
- `playschool_app/tenant_services/middleware/tenant_resolver.py`
- `playschool_app/tenant_services/tenant_db.py`
- `playschool_app/tenant_services/secrets_manager.py`
- `playschool_app/tenant_services/job_context.py`
- `playschool_app/scripts/provision_tasks.py`
- `playschool_app/scripts/provision_tenant.py`
- `playschool_app/scripts/run_provision_e2e.py`
- `playschool_app/test_phase2_tenant_isolation.py`
- `docs/multi-tenant-architecture.md`
- `docs/IMPLEMENTATION-STATE.md`

### Tests added and executed

- Added `playschool_app/test_phase2_tenant_isolation.py`.
- Executed `python -m unittest -v test_phase2_tenant_isolation.py`: 13 tests passed.
- Executed Python syntax compilation for the changed runtime, tenant, Celery, and test files successfully.

### Remaining blockers

- Live MySQL privilege tests, live Flask route tests, and live Redis/Celery worker tests require services and dependencies unavailable in this environment.
- `scripts/run_alembic.py` is an operator CLI caller of the credential provider and is not part of the Flask request path; it still requires separate operational review for secret-safe logging.
- Provisioning hardening is recorded below; live MySQL privilege and worker verification still require services unavailable in this environment.
- Broader upload authorization, storage isolation, billing, backups, and deployment controls remain deferred to their phases.

## Phase 3: Tenant provisioning hardening

### Status

- Implemented and verified in the live provisioning callable, CLI, Celery task, credential provider, and super-admin retry path. MySQL provisioning and tenant-connection integration was verified against an isolated temporary MySQL 8.0 instance. Celery enqueue, Redis-protocol broker delivery, worker execution, failure/retry status handling, and worker restart recovery were verified against an isolated RESP2 Redis test service.

### Confirmed issues addressed

- Celery jobs validate an explicit tenant reference and matching job ID, then validate the resulting control-DB mapping before completion.
- A dedicated non-root `PROVISIONING_MYSQL_USER` / `PROVISIONING_MYSQL_PASSWORD` account is required for database and account administration; tenant runtime credentials remain separate.
- Tenant databases and users are created with validated identifiers, an explicit account host, and database-scoped grants; wildcard host and `ALL PRIVILEGES` grants were removed.
- Credentials are stored only through the explicitly selected environment/AWS/protected-file provider. Protected local files are atomic and 0600; the historical `.tenant_secrets.json` fallback is rejected in production.
- Control-DB mapping is published after database, user, schema, and credential storage succeed.
- Duplicate subdomains and orphaned credential records are rejected; failures compensate by removing created credentials, users, and databases where possible.
- Job status persists input, attempts, timestamps, result, and redacted errors. Manual retry is restricted to failed/error jobs and uses original job input.
- Provisioning audit events contain job/tenant/status metadata only and never tenant passwords.

### Files changed

- `playschool_app/config.py`
- `playschool_app/mysql_setup.py`
- `playschool_app/scripts/provision_tenant.py`
- `playschool_app/scripts/provision_tasks.py`
- `playschool_app/scripts/provision_jobs.py`
- `playschool_app/tenant_services/job_context.py`
- `playschool_app/tenant_services/secrets_manager.py`
- `playschool_app/app.py`
- `playschool_app/test_provisioning.py`
- `playschool_app/test_phase3_celery_redis_integration.py`
- `playschool_app/requirements-test.txt`
- `playschool_app/test_email.py`
- `playschool_app/test_login.py`
- `playschool_app/test_reset_flow.py`
- `docs/multi-tenant-architecture.md`
- `docs/IMPLEMENTATION-STATE.md`

### Tests

- `python -m unittest -v test_provisioning.py`: 5 passed.
- `python -m unittest -v test_phase2_tenant_isolation.py`: 13 passed.
- `python -m unittest -v test_phase1_security.py`: 5 passed; Flask surface tests skipped because Flask is unavailable.
- `PHASE3_LIVE_TEST=1 python -m unittest -v test_phase3_provisioning_integration.py`: 5 passed against temporary MySQL 8.0, including control mapping, exact grants, tenant connection, duplicate rejection, rollback cleanup, job persistence, and host denial.
- Python compilation and `git diff --check` passed.

### Remaining blockers

- Live MySQL tests for database/user creation, grants, rollback, and tenant connection passed against a disposable temporary MySQL service; the temporary tenant, database, users, credentials, and datadir were removed afterward.
- Redis/Celery integration passed with `fakeredis`'s isolated TCP service and the real Kombu Redis transport. The test service, worker threads, broker state, job files, and temporary resources were removed after execution.
- SMTP, HTTP login, and reset-flow tests are explicit opt-in integration tests and remain skipped unless their real credentials/services are configured.

### Final verification

- Full discovery: 36 tests passed, 9 dependency-gated tests skipped, 0 failures.
- Redis/Celery integration: 2 tests passed.
- MySQL provisioning integration: 5 tests passed; audit redaction assertion passed independently after the live run.
- Phase 1 security suite: 7 tests passed.
- Phase 2 isolation suite: 13 tests passed.
- Provisioning unit suite: 5 tests passed.
- Python compilation and `git diff --check`: passed.

### Production deployment prerequisites

- Use `playschool_app/docker-compose.production.yml` with a supervised Redis 7-compatible service (AOF enabled), persistent MySQL, Gunicorn, and a restart-supervised Celery worker.
- Run MySQL with a non-root control/application account and a separate non-root provisioning account configured through `PROVISIONING_MYSQL_USER` and `PROVISIONING_MYSQL_PASSWORD`; root is bootstrap/maintenance-only.
- Configure `TENANT_CREDENTIAL_PROVIDER=protected_file` and an operator-owned protected credential volume for the one-VPS option. Production never falls back to `.tenant_secrets.json` or local development storage.
- Configure `SECRET_KEY`, `MYSQL_DB`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD` (bootstrap-only), `PROVISIONING_MYSQL_USER`, `PROVISIONING_MYSQL_PASSWORD`, `REDIS_PASSWORD`, `TENANT_BASE_DOMAIN`, and `TRUSTED_PROXY_COUNT` before startup.
- Job and audit paths are configurable through `PROVISION_JOBS_FILE` and `PROVISION_AUDIT_FILE`; the production profile mounts them on a durable protected volume and redacts sensitive fields before persistence.
- Run the documented startup, health, restart/recovery, success/failure/rollback, and duplicate/retry smoke checks in `docs/production-deployment.md` with disposable tenant data before opening traffic.
- SMTP, HTTP login, and reset tests remain opt-in and require environment-provided services/credentials.
- Schema migration completeness, object-storage authorization, billing, and verified backups remain later-phase production blockers.

## Phase 3 production deployment finalization

### Status

- Stable release-candidate baseline frozen. Local verification is complete; real production Redis/MySQL/Celery service smoke verification remains pending because operator services are not available in this workspace.

### Changes

- Added `docker-compose.production.yml` with private MySQL/Redis networking, Redis authentication and AOF persistence, durable job/audit and tenant-credential volumes, non-root web/worker credentials, health checks, and restart supervision.
- Production Celery rejects missing/non-Redis/fakeredis brokers and result backends and rejects eager execution.
- Job and audit storage paths are environment-configurable; atomic job writes create their durable parent path and audit records redact sensitive keys/values before persistence.
- Added the exact environment-variable, startup, health-check, smoke-test, and rollback checklist in `docs/production-deployment.md`.

### Verification

- Full discovery baseline remains 36 passed; one additional release-candidate artifact test now brings the suite to 37 passed with 9 explicit dependency-gated skips.
- Python compilation and `git diff --check` pass.
- The deterministic Redis/Celery test service and disposable MySQL integration tests remain test-only and are not production fallbacks.

## Phase 4: Object storage / file security

### Status

- In progress. The private local-storage and download-authorization baseline is implemented and locally verified. Phase 3 remains frozen and unchanged in behavior.

### Implemented progress

- Moved new uploads outside the public static tree.
- Added immutable server-generated tenant/category storage keys.
- Added content-signature validation and traversal/MIME-spoofing rejection.
- Added tenant, record, and role authorization for profile, homework, submission, payment, and fee-receipt downloads.
- Denied the historical `/static/uploads/*` public path.
- Added a persistent private upload volume to the production Compose profile.
- Added explicit `local`/`s3` storage-provider selection with no unsafe fallback.
- Added command-scanner integration that fails closed when scanning is unavailable or unsuccessful.
- Added per-tenant quota enforcement and retention cleanup helpers.
- Added ownership-validated legacy migration primitives with manifest rollback.
- Added checksum-verified private-upload backup/restore helpers for the local backend.
- Added deployment-level private ClamAV `clamd` integration with persistent
  signatures, internal streaming `clamdscan`, and scanner health dependency;
  real scanner verification remains pending.

### Tests

- Added `playschool_app/test_phase4_file_security.py` with 13 focused tests.
- Full discovery: 50 passed, 9 explicit dependency-gated skips, 0 failures.
- Python compilation and `git diff --check` passed.

### Remaining blockers

- S3/object-storage provider integration and live malware-scanner verification remain pending; the deployment scanner wiring is present but has not been run on the staging VPS.
- Production quota/retention scheduling and permissions remain pending.
- Legacy migration rollout and production backup/restore drills remain pending.
- Production-only deployment verification remains deferred.

### Production verification runbook

- `docs/phase4-production-verification.md` records the remaining real-
  infrastructure gates for S3, malware scanning, quota/retention scheduling,
  legacy migration, backup/restore, deployment health, restart/recovery, and
  sanitized evidence collection.
- Phase 4 remains IN PROGRESS until every runbook gate has real production
  evidence. Phase 5 has NOT STARTED.

## Final release-candidate audit

- Phase 3 remains frozen; Phase 4 is in progress.
- Removed unsafe legacy default/demo credentials and root fallbacks from diagnostic/bootstrap utilities.
- Removed default-school mutation from the obsolete SQLite migration helper.
- Prevented the eager provisioning helper and legacy account utilities from running in production.
- Prevented the legacy backup helper from silently reading `.tenant_secrets.json`; the complete backup workflow remains Phase 6 work.
- Removed generated Flask/provisioning log artifacts from the working tree.
- Redacted tenant passwords from the Alembic operational status message and aligned stale deployment documentation with the live provider/grant rules.
- Full regression discovery, compilation, and `git diff --check` passed: 50 tests passed and 9 explicit dependency-gated tests skipped. SMTP, HTTP, reset, live MySQL, live object storage/scanner, and live production-service checks remain environment-gated prerequisites.

## Phase 5: Billing and Payments

### Status

- Implemented locally with strict platform-subscription and school-fee domain separation. Production Razorpay credentials, callbacks, settlement, reconciliation, refunds, and payment-provider verification remain pending.
- Phase 3 remains frozen. Phase 4 remains in progress and its production verification is unchanged.

### Implemented changes

- Added control-database platform subscription plan, payment, webhook-event, and school payment configuration tables.
- Added explicit platform subscription invoice/idempotency records and atomic subscription settlement with grace-period handling.
- Added environment-only Razorpay order creation, payment signature verification, webhook signature verification, retry-safe duplicate-event handling, refund/dispute event recording, and fail-closed provider configuration.
- Added school-specific manual UPI configuration and server-side school-fee amount/domain validation for partial/full payments.
- Added explicit operator migration at `playschool_app/migrate_phase5_billing.py`; it does not seed prices or credentials, preserves legacy platform payment records separately from school fees, and applies the school-fee domain marker per tenant database through the server-side credential mapping with failure handling and backup-based recovery requirements.
- Updated billing, fee, Super Admin, and selling-facing templates to describe the two payment domains accurately.

### Tests

- Added `playschool_app/test_phase5_billing.py` with 18 focused tests: 17 deterministic local tests and one explicit real-provider sandbox test.
- Phase 5 focused suite: 17 passed, 1 sandbox test skipped because credentials were unavailable.
- Python compilation and `git diff --check`: passed.
- Full regression discovery and production Razorpay verification remain required before marking Phase 5 complete.

### Remaining blockers

- Real Razorpay credentials, order/capture flow, signature callbacks, duplicate webhook delivery, refund/dispute callbacks, and provider failure/retry tests.
- Provider settlement reconciliation, invoice delivery, refund/dispute operational procedures, and monitoring.
- Production HTTPS and database migration/rollback verification with real school/platform payment separation.

### Phase 5 acceptance gate

- Domain separation, local signature/idempotency/redaction/expiry/fee validation: **PASS locally**.
- Refund/dispute event state handling and retry recovery: **PASS by deterministic local tests; real provider callbacks pending**.
- Razorpay sandbox/provider verification: **BLOCKED — no sandbox credentials or controlled provider environment**.
- Settlement reconciliation: **BLOCKED — no provider settlement report/reconciliation service configured**.
- Migration rollback and production failure recovery: **BLOCKED — requires disposable production-like MySQL and backup evidence**.
- HTTPS, receipts, tenant isolation, and production deployment verification: **BLOCKED — requires real staging/production services**.
- Phase 5 is not complete. Phase 6 has **NOT STARTED**.

### Final pre-deployment blocker fixes — local verification

- Hardened the tenant request boundary so authenticated school users cannot use
  the control host as an unscoped database path.
- Restricted public registration to a resolved tenant and approved roles;
  browser-provided school IDs are ignored.
- Added a validated private-subnet tenant MySQL account-host requirement and
  removed request-controlled credential-provider mutation.
- Added ownership-aware provisioning reservation/activation cleanup for
  concurrent duplicate requests and active-state job-context validation.
- Added secure OTP generation, expiry/attempt limits, session revalidation,
  attendance ownership fixes, audit error redaction, paginated S3 quota usage,
  restrictive migrated-file permissions, bounded Compose logs, and the Phase 4
  scheduler/backup maintenance path.
- Corrected the admin fee-payment endpoint reference and hardened `.env.example`
  to contain placeholders only.
- These changes are locally tested only; no EC2, DNS, HTTPS, Razorpay, or
  production infrastructure was modified.
- Final local regression after these fixes: 76 tests passed, 10
  environment-gated skips, 0 failures; compilation and `git diff --check`
  passed.
