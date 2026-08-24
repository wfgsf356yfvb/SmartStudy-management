# Phase 5: Billing and payments

Status: **IMPLEMENTED LOCALLY — PRODUCTION VERIFICATION PENDING**

Phase 5 separates the two money flows in the application:

1. **Platform subscription billing**: a school pays the SmartStudy platform
   for access. These records live in the control database in
   `platform_subscription_*` tables.
2. **School fee collection**: a student/parent pays the respective school.
   These records remain in `student_fee_payments`, are explicitly marked with
   the `school_fee` domain, and use the school’s own payment configuration.

No platform subscription callback writes a school-fee record, and no school
fee submission settles a platform subscription.

## Implemented locally

- Platform plan metadata is configurable in the control database; no plan
  prices are seeded in source code.
- Platform manual UPI renewal records have server-generated invoice numbers,
  private receipt storage, explicit duration, and idempotency keys.
- Platform Razorpay order creation is available only with environment-injected
  credentials and requires a caller-supplied `Idempotency-Key`.
- Razorpay payment signatures and webhook signatures use HMAC verification.
- Platform webhook events are persisted by unique event ID and duplicate
  deliveries are ignored; retryable events remain processable after a worker
  or database failure.
- Platform settlement locks the payment row, updates only the associated
  school subscription, and is safe to repeat after settlement.
- Expired subscriptions receive the configured grace window before access is
  blocked; inactive subscriptions remain blocked.
- School admins can configure their school’s manual UPI instructions in the
  control database. Browser input cannot configure a platform Razorpay secret.
- School fee payments validate the selected school-owned fee structure, the
  remaining amount, an allowlisted payment mode/method, and the school fee
  domain before recording a receipt.
- Sensitive payment payload fields are redacted by the shared billing helper.
- Refund and dispute webhook events are recorded against the platform payment
  with provider identifiers and reconciliation state; subscription access is
  not silently revoked by a financial callback.
- The explicit operator migration is idempotent and migrates legacy platform
  `payments` rows into the platform subscription table without mixing them
  with school fees.

## Production safeguards

- Production Razorpay order/webhook paths fail closed unless key ID, key
  secret, and webhook secret are securely injected at runtime.
- Credentials are never stored in source, templates, database payment records,
  webhook event metadata, or responses.
- Real Razorpay order creation is covered by an explicit opt-in sandbox test,
  but it was not run here because no sandbox credentials were provided. Real
  capture, webhook retries, refund/dispute callbacks, and settlement reports
  have not been verified in this environment.
- The operator must run `python migrate_phase5_billing.py` after a backup and
  before enabling the Phase 5 routes. The migration does not seed prices or
  secrets. Run it once for the control database and once per tenant with
  `--tenant-subdomain` and `--tenant-database`; the tenant database must match
  the server-side credential-provider mapping.
- Real payment-provider credentials, webhook endpoints, HTTPS, settlement,
  invoice delivery, reconciliation, refund/dispute procedures, and monitoring
  remain deployment prerequisites.

## Tests

`playschool_app/test_phase5_billing.py` covers domain separation, Razorpay
payment/webhook signatures, event identity, retryable/final event states,
refund/dispute classification, redaction, school-fee partial payment limits,
option allowlists, subscription extension, HTTPS/provider guards, migration
mapping checks, production secret requirements, and source-level separation of
platform callbacks from school-fee inserts. One real-provider sandbox test is
explicitly environment-gated.

The local Phase 5 tests do not claim Razorpay production verification,
reconciliation, or a migration rollback drill.
