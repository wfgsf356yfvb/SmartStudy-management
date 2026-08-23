# Phase 4 Production Verification Runbook

Status: **PENDING REAL INFRASTRUCTURE — Phase 4 remains IN PROGRESS**

This runbook covers only the remaining Phase 4 production gates. It must be
executed on the target deployment with disposable test tenants and securely
injected secrets before Phase 4 can be marked complete. Local mocks, test
brokers, eager Celery execution, or development credential files are not
evidence of production verification.

## Evidence and safety rules

- Record timestamps, service versions, test tenant identifiers, pass/fail
  results, and sanitized log/audit references in the release evidence record.
- Never record passwords, access keys, tokens, connection strings, private
  keys, uploaded file contents, or secret-bearing job results.
- Use a disposable tenant and disposable test files. Remove them after the
  drill and retain only sanitized evidence and checksums where required.
- Stop and mark the gate failed if any control falls back to public storage,
  an unscanned upload, a control database in a tenant request, root
  credentials, or an unvalidated tenant identity.
- A failed gate requires an incident-safe rollback and remediation before
  retesting. Do not weaken a test to obtain a pass.

## Preconditions

- [ ] Target host, DNS/HTTPS, reverse proxy, application, MySQL, Redis,
      Celery worker, object storage, and malware scanner are available.
- [ ] Production secrets are supplied through the approved secret store or
      protected environment injection. No secret is present in source,
      Compose files, fixtures, documentation, logs, job results, or audit
      metadata.
- [ ] Production configuration rejects public storage, disabled scanning,
      missing scanner configuration, unsafe S3/local fallback, root tenant
      credentials, and development `.tenant_secrets.json` fallback.
- [ ] Control DB backup exists and rollback operators are identified.
- [ ] A disposable test tenant and test object set are approved for the drill.
- [ ] Baseline local regression is recorded: 50 passed, 9 explicit
      dependency-gated skips, 0 failures.

## 1. Real S3/object-storage provider

- [ ] Inject the object-storage endpoint, bucket/container, region, and
      credentials through the production secret/configuration mechanism.
- [ ] Verify the bucket/container is private, has no public-read policy, and
      uses the intended encryption and lifecycle controls.
- [ ] Upload a clean file for Tenant A and verify the generated key is
      tenant-prefixed and not derived from browser input.
- [ ] Download the file through the authorized application route and verify
      content and checksum.
- [ ] Confirm Tenant B, an unowned user, an invalid tenant, and a traversal or
      altered-key request are denied.
- [ ] Confirm the same object cannot be fetched by changing tenant, object
      identifier, path, or browser MIME metadata.
- [ ] Temporarily make the provider unavailable and verify the upload/download
      operation fails closed without writing or reading a local/public copy.
- [ ] Verify provider credentials and object keys are absent from responses,
      logs, job results, and audit records.

Acceptance evidence: private-provider policy, sanitized upload/download
results, denial results, failure result, and redaction check.

## 2. Real malware scanner

The deployment integration uses the private Compose service
`malware-scanner`, the persistent `clamav_signatures` volume, and the
`clamdscan --stream --config-file=/etc/clamav/clamdscan.conf --no-summary`
command. This is configuration only; it is not evidence that the real
scanner is running or healthy.

- [ ] Configure the approved scanner service and health check through secure
      environment/configuration injection.
- [ ] Upload a known clean test file and verify scan success is required before
      the object becomes available.
- [ ] Submit the scanner-approved malware test file supplied by the scanner
      vendor and verify the upload is rejected and not downloadable.
- [ ] Stop or isolate the scanner and verify uploads fail closed; no
      `ALLOW_UNSCANNED_UPLOADS` behavior is enabled in production.
- [ ] Restart the scanner and verify clean uploads resume without stale scan
      state or cross-tenant reuse.
- [ ] Verify scanner output, command arguments, file contents, and credentials
      are not persisted in logs, job results, or audit metadata.

Acceptance evidence: clean/rejected/unavailable scan results, scanner health
and restart timestamps, and sanitized redaction evidence.

## 3. Production quota and retention

- [ ] Configure the real scheduler/Celery worker responsible for retention and
      verify it is supervised and monitored.
- [ ] Create files for Tenant A up to its quota and verify the next upload is
      rejected without partial storage.
- [ ] Verify Tenant B has an independent quota and cannot consume, inspect, or
      alter Tenant A's quota accounting.
- [ ] Create expired and non-expired objects for two tenants; run the real
      scheduled cleanup and verify only eligible objects for the correct tenant
      are removed.
- [ ] Verify cleanup is idempotent, records sanitized outcome metadata, and
      recovers safely after worker/storage failure.
- [ ] Verify service and storage permissions permit only the intended worker
      and application operations.

Acceptance evidence: quota boundary results, tenant-scoped cleanup manifest,
scheduler/worker execution record, failure/recovery record, and permissions
review.

## 4. Legacy upload migration

- [ ] Select controlled legacy records whose tenant ownership is confirmed in
      the control/tenant data.
- [ ] Run migration in a maintenance window with a protected rollback manifest.
- [ ] Verify ownership validation rejects ambiguous, missing, or cross-tenant
      records before copying data.
- [ ] Verify migrated keys are private, tenant-prefixed, checksum-recorded,
      and served only through authorized routes.
- [ ] Rerun the same migration and verify idempotency without duplicate files
      or manifest corruption.
- [ ] Trigger a controlled partial failure and verify owner metadata,
      destination object, manifest, and source state are restored or safely
      recoverable according to the rollback manifest.
- [ ] Verify migration audit evidence contains identifiers/status/checksums
      only, never file contents or secrets.

Acceptance evidence: sanitized ownership decision, manifest/checksum record,
idempotent rerun, rollback/partial-failure result, and audit review.

## 5. Backup and restore

- [ ] Configure an off-host backup destination with protected credentials and
      verify private uploads are included without exposing their contents.
- [ ] Create a backup manifest containing tenant/key/size/checksum metadata
      only, then verify the backup itself is protected and retained as intended.
- [ ] Restore a disposable Tenant A backup and verify checksum and content.
- [ ] Attempt restore into Tenant B, with a tampered archive, with traversal
      keys, and with a mismatched checksum; verify each is rejected atomically.
- [ ] Run a restore drill after simulated storage/service failure and verify
      application access returns only after validation completes.
- [ ] Verify backup retention and deletion policies, alerting, and failure
      recovery with the real backup service.

Acceptance evidence: off-host backup location/policy, checksum manifest,
successful restore, rejected tamper/wrong-tenant cases, retention result, and
failure/recovery record.

## 6. Production deployment and recovery

- [ ] Start the application only after MySQL, Redis, object storage, and the
      scanner health checks pass.
- [ ] Verify Gunicorn/Flask, Redis, Celery worker, MySQL, S3, and scanner
      health checks report the expected state.
- [ ] Run the final disposable-tenant smoke test: authorized upload,
      scan-gated availability, authorized download, denied cross-tenant access,
      quota boundary, retention, backup, and restore.
- [ ] Restart the application, Redis, MySQL, scanner, and Celery worker one at
      a time; verify queued work, tenant context, storage state, job status,
      audit persistence, and health checks recover correctly.
- [ ] Verify logs and audit records are sanitized, durable, access-controlled,
      and sufficient to investigate failures without secrets.
- [ ] Exercise the documented rollback procedure using disposable data and
      verify old public paths remain unavailable after rollback.
- [ ] Remove all temporary tenants, objects, manifests, credentials, and test
      files; retain only sanitized evidence.

Acceptance evidence: startup order, health checks, restart/recovery results,
final smoke result, sanitized logs/audit review, rollback result, and cleanup
confirmation.

## Completion gate

Phase 4 may be changed from **IN PROGRESS** to **COMPLETE** only when every
section above has real infrastructure evidence and no failed or unverified
control remains. Until then, the status is **IN PROGRESS** and production
verification is **PENDING**.

Phase 3 is frozen and must remain unchanged. Phase 5 has **NOT STARTED**.
