# SmartStudy production deployment

This is the Phase 3 one-VPS deployment profile. It keeps Flask, MySQL, Redis and
Celery, and does not enable fakeredis, eager execution, local development secret
files, or MySQL root access in the web/worker application processes.

## Required services

- MySQL 8.0 for the control database, with persistent storage.
- Redis 6 or 7 with authentication and AOF persistence.
- Two supervised application processes: Gunicorn web and a Celery worker.
- One private ClamAV `clamd` service with persistent signature data; the web
  and worker images include only the `clamdscan` client.
- A protected writable volume for tenant credentials and a protected durable
  volume for the job journal and provisioning audit log.
- Nginx/HTTPS and the canonical tenant DNS policy described in the architecture
  document.

`playschool_app/docker-compose.production.yml` supplies the service supervision,
health checks, private service networking, Redis persistence, and restart policy.
It does not contain credentials. Keep the deployment `.env` file outside source
control with restrictive operator-only permissions.

## Required environment variables

The following values must be supplied by the deployment environment; there are
no production defaults for them:

```text
FLASK_ENV=production
SECRET_KEY=<random value, at least 32 characters>
MYSQL_DB=<control database name>
MYSQL_USER=<non-root control/application user>
MYSQL_PASSWORD=<control/application password>
MYSQL_ROOT_PASSWORD=<bootstrap/maintenance-only root password>
PROVISIONING_MYSQL_USER=<separate non-root provisioning account>
PROVISIONING_MYSQL_PASSWORD=<provisioning account password>
TENANT_GRANT_MYSQL_USER=<separate grant-only account>
TENANT_GRANT_MYSQL_PASSWORD=<grant-only account password>
REDIS_PASSWORD=<random Redis password>
TENANT_BASE_DOMAIN=<canonical production base domain>
TRUSTED_PROXY_COUNT=<exact number of trusted reverse proxies, normally 1 behind Nginx>
TENANT_UPLOAD_QUOTA_BYTES=<positive per-tenant quota in bytes>
UPLOAD_RETENTION_DAYS=<positive retention period>
```

Optional values include `WEB_BIND_ADDRESS`, `WEB_PORT`, `MAIL_SERVER`,
`MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `UPI_ID`, and `UPI_NAME`.
SMTP login/reset tests remain opt-in and require environment-provided test
credentials and services; they are never enabled by the deployment profile.

File storage is explicit:

```text
FILE_STORAGE_PROVIDER=local       # protected volume, or s3
OBJECT_STORAGE_BUCKET=<required only when FILE_STORAGE_PROVIDER=s3>
FILE_SCANNER_PROVIDER=command
FILE_SCANNER_COMMAND=clamdscan --stream --config-file=/etc/clamav/clamdscan.conf --no-summary
ALLOW_UNSCANNED_UPLOADS=0
```

The local option uses the private `uploads_data` volume. The S3 option uses a
private bucket and tenant-prefixed objects with server-side encryption; it does
not fall back to local storage if S3 is unavailable. Scanner failure rejects
the upload. Install and supervise ClamAV/`clamdscan` (or an equivalent
command-compatible scanner) before enabling uploads.

Production tenant provisioning also requires `TENANT_DB_USER_HOST`. Set this
to the exact private Docker/VPC subnet pattern used by the MySQL client
containers, for example `172.20.%`; a global `%` host is rejected. Credential
provider selection is server configuration only and is never a browser option.

The `scheduler` service runs tenant-scoped Phase 4 retention and protected
off-host upload-backup work. It requires `UPLOAD_BACKUP_BUCKET` and an explicit
server-generated `FILE_MAINTENANCE_TENANTS_JSON` list. Missing or invalid
maintenance configuration fails closed. All Compose services use bounded JSON
log rotation (`10m`, five files).

The production Compose profile adds `malware-scanner` using the official
`clamav/clamav:stable-debian13-slim` image. It exposes only the internal
Compose port `3310`; it publishes no host port and receives no public firewall
rule. The web and worker images install the `clamdscan` client and use
`/etc/clamav/clamdscan.conf` to reach `malware-scanner:3310`. `--stream` sends
the temporary upload contents to the daemon over the private Compose network,
so the daemon does not need access to the application container filesystem.
ClamAV signature data is persisted in the protected `clamav_signatures`
volume. The scanner has a restart policy and health check, and web/worker
startup waits for scanner health. The real staging service must still be
started and tested before uploads are enabled.

The compose profile sets these required production values internally:

```text
TENANT_CREDENTIAL_PROVIDER=protected_file
TENANT_DB_CREDENTIALS_FILE=/var/lib/smartstudy/tenant-credentials/tenant_credentials.json
CELERY_EAGER=0
PROVISION_JOBS_FILE=/var/lib/smartstudy/provision/jobs.json
PROVISION_AUDIT_FILE=/var/lib/smartstudy/provision/audit.log
```

The protected credential file must be created on the mounted credential volume
with owner-only permissions. The application refuses `.tenant_secrets.json` in
production and refuses to fall back to development local-file storage. The
provisioning account is used only by the worker for database/user creation; the
web process receives only the non-root control database account. Neither process
receives MySQL root credentials.

## MySQL account prerequisites

The tenant grant account is a separate non-root account used only by the
provisioning worker for the exact tenant grant. It must differ from
`PROVISIONING_MYSQL_USER`, must not be `root`, and must not have `CREATE USER`,
`CREATE`, `DROP`, or `ALTER`. Its bootstrap scope is the four tenant DML
privileges (`SELECT`, `INSERT`, `UPDATE`, and `DELETE`) with `GRANT OPTION` so
MySQL 8.0 can delegate those privileges to a dynamically created tenant
database account. The tenant runtime user itself never receives `GRANT OPTION`.

`TENANT_GRANT_MYSQL_USER` and `TENANT_GRANT_MYSQL_PASSWORD` are injected only
into the Celery provisioning worker. They are not provided to `web`,
`scheduler`, or ordinary application processes. Store them in the protected
deployment environment and rotate them through the normal MySQL bootstrap/
maintenance procedure; never put them in Git, images, logs, audit records, or
job results. Local Windows development uses a disposable localhost grant-only
account configured through the same two environment variables.

Because this MySQL privilege is inherently sensitive, restrict the grant
account's MySQL host to the private worker network and monitor its use. Existing
tenants are not rewritten automatically. Audit their grants first, migrate only
through an approved maintenance operation, and preserve the existing
compensating rollback behavior if a new grant fails.

Use root only during a controlled bootstrap/maintenance operation. Create the
control application account and the separate provisioning account with the
minimum control-plane privileges required by the existing schema and
provisioning flow. The provisioning code creates each tenant user with an exact
database-scoped grant set and never grants `ALL PRIVILEGES` or a `%` host.

Do not put tenant passwords in SQL files, images, logs, API responses, or audit
records. Tenant credentials are generated server-side and stored through the
configured protected provider.

## Startup order

1. Provision the host directories/volumes and operator-only environment file.
2. Start MySQL and wait for its authenticated health check.
3. Apply the control schema using the existing controlled migration/bootstrap
   procedure.
4. Start Redis with AOF enabled and wait for its authenticated `PING` health
   check.
5. Start the Celery worker and confirm it is connected to the Redis broker.
6. Start Gunicorn, then place Nginx/HTTPS in front of it.
7. Create tenants only through the existing super-admin provisioning UI/API.

For Compose, use the production file from `playschool_app`:

```text
docker compose -f docker-compose.production.yml up -d control-db redis
docker compose -f docker-compose.production.yml up -d worker web
```

Do not use the development compose profile for production. It publishes MySQL
and Redis ports and does not provide the protected production configuration.

## Health checks and smoke tests

Verify all of the following without printing credentials:

- MySQL is healthy and web/worker connect as non-root users.
- Redis authenticated `PING` succeeds and an expiring namespaced key can be
  written/read, proving connectivity and persistence configuration.
- Celery reports a worker connected to Redis; `CELERY_EAGER` is `0`.
- A real provisioning request moves pending → running → completed and its job
  and audit records persist on the mounted provision volume.
- An intentional provisioning failure persists a redacted error and removes the
  tenant database, tenant user, control mapping and credential record.
- Duplicate requests are rejected safely; retry attempts and timestamps remain
  in the durable job record.
- Restart the worker, enqueue a new isolated test job, and verify it is consumed.
- Resolve two test tenant hostnames and verify each connects only to its own
  database; unknown and malformed hosts fail closed.

The repository's Redis/Celery integration test uses a test-only fakeredis TCP
service and real Kombu Redis transport. It is not a production broker and is
never selected by production configuration. The live MySQL provisioning suite
requires an explicitly provisioned isolated MySQL service and
`PHASE3_LIVE_TEST=1`.

## Rollback

1. Stop new provisioning requests at Nginx/super-admin access while allowing
   currently running jobs to finish or be marked failed.
2. Keep the job/audit and credential volumes intact; do not delete them during
   rollback.
3. Revert the application image/configuration to the last verified release and
   restart worker before web so queued jobs have a consumer.
4. If a provisioning job failed, use its persisted job ID and audit record to
   verify compensating cleanup. Do not manually reuse a tenant database name or
   credential from a failed attempt.
5. Restore the control database and Redis volumes only from verified backups if
   data corruption is confirmed. Redis AOF recovery must complete before workers
   restart.
6. Re-run the smoke checks and a disposable tenant provisioning test before
   reopening traffic.

## Verification commands

From `playschool_app`, the non-live suite is:

```text
python -m unittest discover -s . -p "test*.py" -v
python -m compileall -q .
git diff --check
```

SMTP, HTTP login, reset-flow, and live MySQL checks are intentionally opt-in;
run them only when the operator has supplied the corresponding service
credentials. A skipped opt-in test is an environment prerequisite, not proof
that the external service is healthy.
