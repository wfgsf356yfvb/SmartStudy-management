import hashlib
import hmac
import json
import os
import secrets
import unittest
from datetime import datetime
from decimal import Decimal

from billing_domain import (
    PLATFORM_SUBSCRIPTION_DOMAIN,
    SCHOOL_FEE_DOMAIN,
    PaymentProviderUnavailable,
    PaymentValidationError,
    DISPUTE_EVENTS,
    FINAL_WEBHOOK_STATUSES,
    REFUND_EVENTS,
    payload_hash,
    provider_credentials_from_env,
    provider_event_entity,
    redact_payment_payload,
    safe_event_id,
    subscription_expiry,
    validate_payment_options,
    validate_school_fee_amount,
    verify_razorpay_payment_signature,
    verify_razorpay_webhook_signature,
)


class BillingDomainTests(unittest.TestCase):
    def test_payment_domains_are_distinct(self):
        self.assertNotEqual(PLATFORM_SUBSCRIPTION_DOMAIN, SCHOOL_FEE_DOMAIN)
        self.assertEqual(PLATFORM_SUBSCRIPTION_DOMAIN, 'platform_subscription')
        self.assertEqual(SCHOOL_FEE_DOMAIN, 'school_fee')

    def test_platform_payment_signature(self):
        secret = 'test-secret-only'
        signature = hmac.new(secret.encode(), b'order_123|pay_123', hashlib.sha256).hexdigest()
        self.assertTrue(verify_razorpay_payment_signature('order_123', 'pay_123', signature, secret))
        self.assertFalse(verify_razorpay_payment_signature('order_123', 'pay_other', signature, secret))

    def test_webhook_signature_and_payload_hash(self):
        body = json.dumps({'id': 'evt_12345678', 'event': 'payment.captured'}).encode()
        secret = 'webhook-secret-only'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_razorpay_webhook_signature(body, signature, secret))
        self.assertFalse(verify_razorpay_webhook_signature(body + b'!', signature, secret))
        self.assertEqual(payload_hash(body), hashlib.sha256(body).hexdigest())

    def test_webhook_event_identity_is_required(self):
        self.assertEqual(safe_event_id({'id': 'evt_12345678'}), 'evt_12345678')
        with self.assertRaises(PaymentValidationError):
            safe_event_id({'id': 'short'})

    def test_refund_and_dispute_event_entities_are_separate(self):
        refund = {'payload': {'refund': {'entity': {'id': 'rfnd_123', 'payment_id': 'pay_123'}}}}
        dispute = {'payload': {'dispute': {'entity': {'id': 'disp_123', 'payment_id': 'pay_123'}}}}
        self.assertEqual(provider_event_entity(refund, 'refund.processed')['payment_id'], 'pay_123')
        self.assertEqual(provider_event_entity(dispute, 'payment.dispute.created')['id'], 'disp_123')
        self.assertIn('refund.processed', REFUND_EVENTS)
        self.assertIn('payment.dispute.created', DISPUTE_EVENTS)
        self.assertEqual(FINAL_WEBHOOK_STATUSES, {'processed', 'ignored', 'rejected'})

    def test_sensitive_payment_payload_is_redacted(self):
        safe = redact_payment_payload({'payment_id': 'pay_123', 'signature': 'secret', 'amount': 100})
        self.assertEqual(safe['signature'], '[redacted]')
        self.assertEqual(safe['payment_id'], 'pay_123')
        self.assertEqual(safe['amount'], 100)

    def test_school_fee_partial_payment_cannot_exceed_due(self):
        self.assertEqual(validate_school_fee_amount('125.50', '200'), Decimal('125.50'))
        with self.assertRaises(PaymentValidationError):
            validate_school_fee_amount('200.01', '200')

    def test_payment_options_are_allowlisted(self):
        self.assertEqual(validate_payment_options('partial', 'upi'), ('partial', 'upi'))
        with self.assertRaises(PaymentValidationError):
            validate_payment_options('crypto', 'upi')
        with self.assertRaises(PaymentValidationError):
            validate_payment_options('partial', 'platform_subscription')

    def test_subscription_extension_uses_existing_future_expiry(self):
        expiry = subscription_expiry('2030-01-01', 30, datetime(2029, 1, 1))
        self.assertEqual(str(expiry), '2030-01-31')

    def test_production_provider_requires_all_razorpay_secrets(self):
        with self.assertRaises(PaymentProviderUnavailable):
            provider_credentials_from_env('production', 'key_id', '', 'webhook')
        credentials = provider_credentials_from_env('development', 'key_id', 'secret', 'webhook')
        self.assertEqual(credentials['key_id'], 'key_id')

    def test_amount_and_duration_boundaries_fail_closed(self):
        with self.assertRaises(PaymentValidationError):
            validate_school_fee_amount('1', '0')
        with self.assertRaises(PaymentValidationError):
            subscription_expiry(None, 0, datetime(2029, 1, 1))


class BillingSeparationSourceTests(unittest.TestCase):
    ROOT = os.path.dirname(os.path.abspath(__file__))

    def _read(self, name):
        with open(os.path.join(self.ROOT, name), encoding='utf-8') as handle:
            return handle.read()

    def test_platform_callbacks_only_reference_platform_tables(self):
        source = self._read('app.py')
        self.assertIn("/webhooks/razorpay/platform", source)
        self.assertIn('platform_payment_events', source)
        self.assertIn('platform_subscription_payments', source)
        section = source[source.index("def platform_razorpay_webhook"):source.index("@app.route('/admin/dashboard')")]
        self.assertNotIn("INSERT INTO student_fee_payments", section)

    def test_school_fee_insert_has_explicit_school_domain(self):
        source = self._read('app.py')
        section = source[source.index('def student_pay_fee'):source.index('# Private file serving')]
        self.assertIn('SCHOOL_FEE_DOMAIN', section)
        self.assertIn('payment_domain', section)
        self.assertNotIn('platform_subscription_payments', section)

    def test_migration_contains_no_seed_prices_or_credentials(self):
        source = self._read('migrate_phase5_billing.py')
        self.assertIn('platform_subscription_plans', source)
        self.assertIn('school_payment_config', source)
        self.assertNotIn('RAZORPAY_KEY_SECRET =', source)
        self.assertNotIn('INSERT INTO platform_subscription_plans', source)
        self.assertIn('run_tenant_fee_migration', source)

    def test_migration_failure_and_tenant_mapping_guards_are_present(self):
        source = self._read('migrate_phase5_billing.py')
        self.assertIn('conn.rollback()', source)
        self.assertIn('Tenant database does not match', source)
        self.assertIn('MYSQL_USER and MYSQL_PASSWORD', source)

    def test_production_https_and_retry_recovery_guards_are_present(self):
        source = self._read('app.py')
        config = self._read('config.py')
        self.assertIn('REQUIRE_HTTPS', config)
        self.assertIn('HTTPS is required.', source)
        self.assertIn('FINAL_WEBHOOK_STATUSES', source)
        self.assertIn("status='refunded'", source)
        self.assertIn("status='disputed'", source)

    def test_reconciliation_is_not_falsely_advertised(self):
        docs = os.path.join(os.path.dirname(self.ROOT), 'docs', 'phase5-billing-payments.md')
        with open(os.path.abspath(docs), encoding='utf-8') as handle:
            content = handle.read()
        self.assertIn('reconciliation', content.lower())
        self.assertIn('not been verified', content.lower())


class RazorpaySandboxTests(unittest.TestCase):
    """Real-provider test; never runs unless explicitly enabled by the operator."""

    @unittest.skipUnless(
        os.environ.get('RUN_PHASE5_RAZORPAY_SANDBOX') == '1',
        'Razorpay sandbox requires explicit opt-in and environment credentials',
    )
    def test_real_sandbox_order_creation(self):
        import razorpay
        key_id = os.environ.get('RAZORPAY_KEY_ID', '')
        key_secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
        self.assertTrue(key_id and key_secret)
        client = razorpay.Client(auth=(key_id, key_secret))
        order = client.order.create({
            'amount': int(os.environ.get('RAZORPAY_SANDBOX_AMOUNT_PAISE', '100')),
            'currency': os.environ.get('RAZORPAY_SANDBOX_CURRENCY', 'INR'),
            'receipt': f"phase5-test-{secrets.token_hex(8)}",
            'notes': {'purpose': 'phase5-sandbox-verification'},
        })
        self.assertRegex(order.get('id', ''), r'^order_')


if __name__ == '__main__':
    unittest.main()
