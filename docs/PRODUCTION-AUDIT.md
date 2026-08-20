# SmartStudy Production Audit

Audit date: 2026-08-20  
Scope: repository-only inspection of the existing Flask application. No live MySQL, Redis, SMTP, DNS, Nginx, Cloudflare, object-storage, or Razorpay environment was assumed. `AGENTS.md` was not present in the repository.

Status vocabulary:

- **DONE** — implemented in the inspected code path, subject to the qualifications recorded here.
- **PARTIAL** — a working slice or scaffold exists, but it is incomplete or unsafe for production.
- **MISSING** — no verified implementation was found.
- **BLOCKER** — a release-blocking security, correctness, or operational issue.

## 1. Current architecture

**Status: PARTIAL**

- `playschool_app/app.py` is a single large Flask module with server-rendered Jinja templates under `playschool_app/templates/` and static CSS/JavaScript under `playschool_app/static/`.
- MySQL is accessed with `mysql.connector`; the main application queries use parameter placeholders and a central connection pool.
- `tenant_services/` is the tenant implementation imported by `app.py`. A duplicate `app/` tenant module tree is also present but is not the runtime import path.
- Gunicorn is declared in `playschool_app/Dockerfile` and `playschool_app/Procfile`.
- Celery is configured in `playschool_app/scripts/celery_app.py`, with Redis as the default broker/result backend and a worker in Compose.
- Database creation, schema creation, seed data, Alembic scaffolding, and a lightweight SQL migration runner are present.
- No Nginx configuration, Cloudflare/DNS configuration, HTTPS certificate procedure, systemd service, health/readiness endpoint, structured logging, metrics, alerting, or deployment runbook was found.

## 2. Existing SaaS functionality

**Status: PARTIAL**

Verified application paths include:

- public informational pages, privacy, and terms routes;
- email/password login followed by an email OTP;
- registration with email OTP;
- password reset with email OTP;
- admin, teacher, student, and Super Admin route areas;
- school management, users, homework, submissions, attendance, announcements, reports, fees, and student progress/game routes;
- school expiry checks using `schools.subscription_status` and `valid_until`;
- manual billing renewal through payment screenshot submission and Super Admin approval;
- Super Admin school/admin/payment/provisioning screens;
- a CLI tenant provisioning script and Celery provisioning task.

The repository does not contain a complete SaaS control plane: there is no verified plan/catalog model, entitlement system, invoice lifecycle, automated recurring billing, webhook processing, usage limits, tenant suspend/delete lifecycle, or durable cross-process provisioning state.

## 3. Existing tenant implementation

**Status: PARTIAL / BLOCKER**

- `playschool_app/app.py:238-251` resolves a tenant before each request through `tenant_services.middleware.tenant_resolver.resolve_tenant` and stores the result in `g.tenant`.
- `playschool_app/tenant_services/middleware/tenant_resolver.py:3-34` takes the first label from any host with at least three dot-separated labels and looks it up in the control database.
- `playschool_app/app.py:89-104` selects the tenant connection for non-control queries when `g.tenant` exists.
- `playschool_app/scripts/provision_tenant.py` creates a control record, a database, a tenant user, a schema, and a stored credential payload.

Confirmed gaps:

- The runtime tenant pool in `playschool_app/tenant_services/tenant_db.py:9-17,20-30` uses global `Config.MYSQL_USER` and `Config.MYSQL_PASSWORD`. It does not load the provisioned tenant credentials from `secrets_manager.py`.
- The runtime database name is constructed as `playschool_tenant_{subdomain}` from the host-derived value (`tenant_db.py:49-54`) rather than loaded from a validated server-side tenant mapping.
- Resolver exceptions are swallowed and converted to `None` (`tenant_resolver.py:30-34`), allowing infrastructure/database failures to fall through to an unscoped/control path.
- There is no configured canonical base domain, trusted-proxy policy, host allowlist, strict subdomain validation, IDNA handling, or explicit rejection of unexpected hosts.
- Provisioning is not transactional or fully idempotent. A failure after the control row, database, user, or grant is created can leave partial state.
- Tenant schema creation uses the central credentials and seeds default data, including demo accounts, in `mysql_setup.py`.

## 4. Database isolation status

**Status: BLOCKER**

The database-per-tenant design is present, but the current code does not establish a defensible isolation boundary.

- Separate tenant database names are created and selected for resolved requests.
- Tenant connection pools are cached in an LRU of 12 pools.
- The runtime identity remains the global MySQL user, which defaults to `root` in configuration and is explicitly `root` in Compose. The dedicated tenant user created by provisioning is not used by normal runtime queries.
- `docker-compose.yml` grants the web and worker containers root credentials and publishes MySQL to the host.
- Many queries include `school_id` predicates, but tenant selection and least-privilege credentials are the stronger boundary needed for this architecture and are incomplete.
- The control and tenant schemas both contain `schools` and user/application tables, leaving duplicated metadata and unclear authority.

Release condition: demonstrate with automated cross-tenant tests that each tenant request selects only its mapped database and that tenant credentials cannot read another tenant database or the control database.

## 5. Super Admin status

**Status: PARTIAL / BLOCKER**

- `role_required('super_admin')` protects the Super Admin dashboards, school list, admin management, payment review, and provisioning routes.
- Super Admin can create/edit/delete school admins, view schools and payments, and enqueue tenant provisioning jobs.
- `/init-db` is unauthenticated (`playschool_app/app.py:1318-1351`) and seeds a Super Admin, school admin, teacher, and student demo accounts when the user table is empty.
- Predictable credentials are present in `app.py`, `mysql_setup.py`, `schema.sql`, `sqlite_schema.sql`, helper scripts, and README guidance.
- Super Admin sessions are ordinary Flask cookie sessions. No step-up authentication, separate admin host, IP/VPN restriction, session policy, or complete privileged audit trail was verified.
- Admin creation/editing (`app.py:1579-1639`) hashes passwords but does not enforce the same visible strength policy and flashes raw database exceptions.
- Provisioning job metadata is stored in `scripts/.provision_jobs.json`; this is local JSON state and is unsafe for multiple web/worker processes or durable recovery.

## 6. Subscription status

**Status: PARTIAL**

- `schools.subscription_status` and `valid_until` are created in the schema.
- `check_school_subscription` in `app.py:253-274` redirects expired/inactive school sessions to `/school-expired`.
- A manual renewal flow exists under `/admin/billing`; Super Admin approval extends the school date in `app.py:1659-1702`.

Missing or incomplete:

- no plan, price, currency, seat/storage limit, trial, grace period, cancellation, refund, renewal retry, or entitlement tables;
- no automated renewal or reconciliation;
- expiry is based on session school state rather than a complete centralized authorization policy;
- no subscription event/audit history or immutable payment-to-entitlement record;
- payment amount and renewal months are accepted from browser form data without a server-controlled product catalog.

## 7. Razorpay status

**Status: MISSING / BLOCKER for online payments**

`razorpay` appears in `requirements.txt`, but no verified Razorpay client initialization, order creation, signature verification, webhook route, payment capture/refund handling, or webhook idempotency logic exists.

The implemented path is manual UPI/screenshot submission into `payments`, followed by Super Admin approval. It is not a Razorpay integration.

## 8. Storage status

**Status: PARTIAL / BLOCKER for production file handling**

- `secure_filename()` and an extension allowlist are used for profile pictures, homework, submissions, billing screenshots, and fee receipts.
- Flask limits request bodies to 16 MB.
- `tenant_services/s3_storage.py` provides minimal upload/download wrappers when `USE_S3` is enabled.

Confirmed gaps:

- Actual application uploads in `app.py:538-546,592-599,854-861,1240-1269` are written to `static/uploads`; the S3 wrapper is not used by those routes.
- No tenant prefix is applied to local or object-storage keys.
- `/uploads/<filename>` in `app.py:1274-1278` authorizes only login and serves by filename; it does not check user, school, record, role, or tenant ownership.
- Upload validation is extension-only. MIME/content inspection, malware scanning, private storage, signed URLs, quotas, retention, and durable object identity are absent.
- Allowed extensions include `mp4`, `doc`, and `docx`; files remain inside the static tree, and templates link directly to static upload paths.
- Timestamp-based filenames can collide under concurrent requests.

## 9. Backup status

**Status: PARTIAL / BLOCKER**

- `scripts/backup_tenants.py` can invoke `mysqldump` with `--single-transaction` and `--quick` and can optionally upload dumps through the minimal S3 wrapper.

This is not an operational backup system:

- it enumerates only the local `.tenant_secrets.json` file and does not enumerate tenant metadata from the control database or AWS Secrets Manager;
- it does not back up the control database, uploads, configuration, or provisioning job state;
- database credentials are passed as a `mysqldump` command-line argument;
- there is no schedule, encryption/key policy, checksum, retention, alerting, or restore test;
- no documented VPS cron/systemd timer or off-host recovery procedure exists.

## 10. Security status

**Status: BLOCKER**

Positive controls verified:

- password hashes use Werkzeug hashing;
- primary application SQL values use parameter placeholders;
- a per-session CSRF token is checked on unsafe methods when enabled;
- production requires a `SECRET_KEY` of at least 32 characters;
- cookies are HttpOnly, SameSite=Lax, and Secure by default in production;
- several security headers and a CSP are emitted.

Confirmed vulnerabilities and material gaps:

1. **Unauthenticated database initialization:** `/init-db` can create/seed data over HTTP, creates predictable accounts, and returns raw exception text.
2. **Committed/default credentials:** `docker-compose.yml` uses `rootpwd`; code and schema files seed `superadmin123`, `admin123`, `teacher123`, `nursery123`, `lkg123`, and `ukg123`; helper scripts contain test credentials.
3. **Tenant isolation failure:** runtime tenant pools use global/root credentials instead of provisioned tenant credentials.
4. **Missing file authorization:** any logged-in user who knows a filename can request it through `/uploads/<filename>`; static upload links add another authorization bypass.
5. **Host header trust:** tenant selection trusts the request host without a configured base-domain allowlist or trusted proxy policy.
6. **OTP weaknesses:** OTPs use `random.randint`, are stored in the client-side Flask session, have no expiry, retry/attempt limit, or rate limiting; forgot-password explicitly reports when an email is not found.
7. **Authorization/data ownership gaps:** teacher attendance accepts posted student IDs without verifying teacher/class ownership (`app.py:1364-1381`); the teacher `my-attendance` route queries attendance by the teacher's own ID as `student_id` (`app.py:1413-1425`); several reads rely on broad `school_id` filters rather than centralized ownership checks.
8. **Input/business-rule gaps:** billing amount, fee identifiers, payment method, file content, and several numeric values are largely trusted from browser input; duplicate submissions and server-controlled pricing are not comprehensively enforced.
9. **Error/data leakage:** raw exception strings are flashed in multiple routes; development fallback secret and debug execution remain available outside production mode; `/test` remains exposed without authentication.
10. **Dynamic SQL identifiers:** ordinary data-query values are parameterized, but database/schema setup and provisioning interpolate database/user/grant identifiers. Validation is not established before those statements are executed.
11. **Supply-chain/release gate gap:** Bandit and Safety are dependencies only; CI runs `python -m py_compile app.py` and does not run security scans, application tests, migration checks, secret scanning, or image checks.

No confirmed user-controlled value interpolation into a normal application data query was found during this audit; this does not remove the dynamic-identifier risk in setup and provisioning code.

## 11. Deployment status

**Status: PARTIAL / BLOCKER**

Present:

- Dockerfile runs Gunicorn on port 5000.
- Compose defines MySQL 8, Redis, web, and worker services.
- A basic GitHub Actions workflow runs dependency installation and Python compilation.
- Terraform contains an RDS scaffold.

Not production-ready:

- MySQL and Redis ports are published to the host.
- Compose hardcodes root credentials, has no Redis password/TLS, health checks, restart policies, resource limits, or readiness-aware startup.
- `depends_on` does not wait for service readiness.
- The web container has no controlled migration/bootstrap procedure.
- There is no Nginx/HTTPS configuration, Cloudflare configuration, certificate renewal procedure, trusted-proxy configuration, or domain allowlist.
- Gunicorn has no documented production timeout, forwarded-header, graceful-shutdown, or logging policy.
- Celery is present, but job/result durability and failure recovery are not operationally defined.

## 12. Missing features

**Status: MISSING**

- canonical control-plane schema and tenant metadata authority;
- server-side tenant database/credential mapping and least-privilege runtime identity;
- canonical base-domain and trusted-proxy handling;
- idempotent provisioning with rollback, migrations, and tenant lifecycle states;
- Razorpay order/payment/webhook integration;
- plan, entitlement, invoice, and subscription-event model;
- private tenant-prefixed storage with authorized or signed downloads;
- complete control DB, tenant DB, upload, configuration, and job-state backups;
- restore drills and recovery objectives;
- login/OTP rate limiting, lockout, password-reset hardening, and account-recovery policy;
- centralized privileged audit logging;
- health/readiness checks, monitoring, alerting, and error tracking;
- automated unit/integration/security tests, especially cross-tenant tests;
- CI/CD gates for dependencies, containers, secrets, migrations, and deployment smoke tests;
- VPS runbook for deployment, rollback, migrations, backups, restore, and incident response;
- finalized legal privacy and terms content: current templates identify themselves as samples/placeholders.

## 13. Critical vulnerabilities

**Status: BLOCKER**

| Priority | Finding | Evidence | Impact |
|---|---|---|---|
| P0 | Unauthenticated `/init-db` seeds predictable accounts | `app.py:1318-1351` | Remote initialization, known-credential compromise, and data modification |
| P0 | Tenant runtime uses global/root DB credentials | `tenant_services/tenant_db.py:9-17`, `docker-compose.yml` | Cross-tenant/control-DB compromise if any route or query is bypassed |
| P0 | Login-only filename access to uploads | `app.py:1274-1278`, upload links in templates | Disclosure of student work, receipts, profile data, and other tenant files |
| P0 | Demo/root credentials are committed or hardcoded | `mysql_setup.py:532-618`, `app.py:1330-1347`, `docker-compose.yml` | Immediate compromise if deployed unchanged |
| P1 | No verified Razorpay integration | `requirements.txt` only; manual billing in `app.py:579-608` | Online billing cannot be trusted or automated |
| P1 | OTP has no expiry, rate limit, or attempt counter | `app.py:293-435,457-472` | Account takeover and abuse risk |
| P1 | Provisioning state and local secrets use JSON files | `scripts/provision_jobs.py`, `tenant_services/secrets_manager.py` | Lost jobs, plaintext credential exposure, unsafe multi-process behavior |
| P1 | Backups are incomplete and untested | `scripts/backup_tenants.py` | Irrecoverable tenant/control data or files after failure |
| P1 | MySQL/Redis are exposed with hardcoded Compose credentials | `docker-compose.yml` | Network-level compromise on an exposed VPS |
| P1 | CI runs compilation only | `.github/workflows/ci.yml` | Security and authorization regressions can ship unnoticed |

## 14. Recommended implementation order

1. **Contain exposure:** remove or disable `/init-db` and `/test` in production, remove seeded/demo/root credentials from deployable paths, rotate any credentials that may have been used, and enforce production-only configuration.
2. **Establish the control boundary:** define control DB versus tenant DB ownership, map each tenant to a validated server-side database and credential record, use dedicated least-privilege runtime users, and add cross-tenant isolation tests.
3. **Harden request identity:** configure one canonical base domain, trusted proxy handling, host allowlisting, strict subdomain validation, session renewal after login, OTP expiry/attempt/rate limits, generic reset responses, and privileged audit logging.
4. **Harden authorization and files:** enforce tenant/school ownership on every read and write, validate relationships server-side, move files outside public static paths, use tenant-prefixed private storage, and authorize or sign every download.
5. **Make provisioning durable:** use a durable queue/result store, idempotent state transitions, migrations per tenant, rollback/cleanup, safe admin onboarding, and no universal seeded passwords.
6. **Implement billing correctly:** add plan/subscription/payment records, server-controlled pricing, Razorpay order creation, signature verification, webhook idempotency, renewal/refund states, and entitlement checks. Keep manual UPI explicitly separate if retained.
7. **Build VPS operations:** Cloudflare DNS/proxy → Nginx TLS → Gunicorn Flask → Celery worker → Redis → private MySQL, with readiness checks, restart policies, resource limits, firewall rules, logging, monitoring, migration, and rollback procedures.
8. **Back up and prove recovery:** nightly encrypted off-host backups for control DB, every tenant DB, uploads, and required configuration; add checksums, retention, alerting, and restore drills.
9. **Add release gates:** unit/integration, tenant-isolation, authorization, upload, payment-webhook, migration, dependency, secret, container, and deployment smoke tests.

## Phased implementation plan

### Phase 1: Production security lockdown

Disable unsafe initialization/test surfaces, remove and rotate committed/default credentials, require production secrets, harden session/OTP/password-reset handling, restrict exposed services, and add baseline security tests.

### Phase 2: Multi-tenant and database isolation

Keep Flask, MySQL, Celery, Redis, and database-per-tenant architecture. Define control DB ownership, use validated tenant mappings, connect with tenant-specific least-privilege credentials, and prove isolation with automated cross-tenant tests.

### Phase 3: Tenant provisioning hardening

Make provisioning idempotent and rollback-capable, add lifecycle states and durable job state, run versioned migrations, validate subdomains/database identifiers, and onboard tenant admins without seeded universal credentials.

### Phase 4: Object storage / file security

Move files outside public static paths, apply immutable tenant prefixes, use private storage, enforce record/role/tenant authorization on downloads, add content validation/scanning, quotas, retention, and backup coverage.

### Phase 5: Subscription and Razorpay

Add server-controlled plans and entitlements, create Razorpay orders, verify signatures, process idempotent webhooks, record payment/subscription events, and reconcile renewal/refund states.

### Phase 6: Backup and disaster recovery

Back up control and tenant databases, uploads, and required configuration to encrypted off-host storage; define retention and alerts; protect credentials; and run documented tenant-level and whole-service restores.

### Phase 7: VPS / Docker / Nginx / HTTPS deployment

Deploy the requested Cloudflare/DNS → Nginx/HTTPS → Gunicorn → Celery/Redis → private MySQL topology with readiness checks, restricted networking, restart/resource policies, log rotation, monitoring, and rollback procedures.

### Phase 8: Final security audit and production testing

Run full authorization, tenant-isolation, upload, authentication, billing/webhook, migration, backup/restore, dependency, secret, container, and deployment smoke tests; review all findings; and approve onboarding only after release blockers are closed.

## Verification notes

- The repository contains three small test-like scripts (`test_login.py`, `test_reset_flow.py`, `test_email.py`) and helper scripts, but no discoverable pytest/unittest suite or CI test execution.
- `privacy.html` calls itself a sample policy, and `terms.html` contains only generic usage text; neither is production-ready legal documentation.
- No application code, templates, static assets, configuration, migrations, deployment files, or tests were modified during this audit.
