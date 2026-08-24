# Phase 4: Object storage and file security

Phase 4 is partially implemented in the local release-candidate runtime. The
Flask/MySQL/Celery/Redis architecture and the frozen Phase 3 provisioning paths
are unchanged.

## Implemented baseline

- New uploads are stored outside Flask's public `static` tree.
- Each object receives a server-generated key under
  `tenant/<validated-subdomain>/<category>/<random-id>.<extension>`.
- Browser filenames, paths, MIME declarations, tenant names, and object IDs do
  not control the final storage location.
- Extension allowlisting is retained and lightweight content signatures are
  checked for PDF, Office, image, and MP4 uploads.
- Private downloads require the resolved tenant prefix and an owning record and
  role relationship.
- Profile pictures, homework files, submissions, payment screenshots, and fee
  receipts have explicit ownership checks.
- The historical `/static/uploads/*` path is denied.
- Production Compose persists the private upload directory through
  `uploads_data`.
- Production Compose now contains a private ClamAV `clamd` service, a
  persistent signature volume, scanner health dependency, and the
  `clamdscan --stream` client configuration used by web/worker containers.

## Remaining Phase 4 blockers

- S3/object-storage integration is implemented behind an explicit provider but
  has not been verified against real object-storage infrastructure.
- Malware scanning, quotas, retention/deletion, checksums, and backup/restore
  controls have deterministic local verification; the ClamAV deployment
  integration is now present, but production scanner availability, signature
  updates, scheduling, permissions, and off-host operation remain pending.
- Existing legacy filenames require a controlled migration into private
  tenant-prefixed storage; they are not served through the old public path.
- Production volume permissions, off-host backup, and restore verification are
  deployment/backup prerequisites.

The complete real-infrastructure gate is documented in
[`docs/phase4-production-verification.md`](phase4-production-verification.md).
It must be executed with securely injected production configuration before
Phase 4 can be marked complete. Local mocks and dependency-gated tests are not
production evidence.

## Testing

`playschool_app/test_phase4_file_security.py` verifies tenant-prefixed keys,
invalid-content rejection, traversal rejection, browser MIME spoofing
rejection, scanner fail-closed behavior, quota enforcement, S3-provider key
selection, ownership authorization, migration rollback, and backup/restore
checksums. The full suite must continue to pass before extending this phase.

Local deterministic coverage also verifies retention scoping/deletion, S3
provider selection through a safe mock, production rejection of public storage
and disabled scanning, migration idempotency and partial-failure cleanup, and
atomic backup restore failure handling.

The deployment now includes a supervised Celery beat `scheduler` service for
tenant-scoped retention and protected off-host backup execution. It validates
each server-generated tenant reference against the control database before
deleting expired files or creating an encrypted S3 backup archive. Missing
backup destination, invalid tenant context, unavailable storage, and failed
checksums fail closed. Real staging execution remains required.
