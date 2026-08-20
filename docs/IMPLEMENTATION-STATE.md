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

- Phase 1 / Production security lockdown implemented; runtime route verification is pending the unavailable Flask dependency in this environment

## Completed

- Phase 0 audit completed
- `docs/PRODUCTION-AUDIT.md` created
- Phase 0 audit did not modify application code
- Confirmed blockers from the audit are recorded below

## Next phases

- Phase 1: Production security lockdown — IMPLEMENTED; runtime verification pending
- Phase 2: Multi-tenant and database isolation — NOT STARTED
- Phase 3: Tenant provisioning hardening
- Phase 4: Object storage / file security
- Phase 5: Subscription and Razorpay
- Phase 6: Backup and disaster recovery
- Phase 7: VPS / Docker / Nginx / HTTPS deployment
- Phase 8: Final security audit and production testing

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

- Implemented in the live runtime paths; the Flask route test could not execute because Flask is not installed in the current environment.

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
