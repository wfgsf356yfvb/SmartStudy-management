"""Opt-in Flask reset-flow integration test requiring a live application DB."""

import os
import unittest


@unittest.skipUnless(
    os.environ.get('RUN_FLASK_INTEGRATION') == '1',
    'Flask reset integration requires RUN_FLASK_INTEGRATION=1 and live MySQL configuration',
)
class ResetFlowIntegrationTest(unittest.TestCase):
    def test_reset_password_flow(self):
        from app import app

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['otp_flow'] = 'forgot'
                session['forgot_verified'] = True
                session['otp_meta'] = {'email': os.environ['TEST_RESET_EMAIL']}
            response = client.get('/reset-password')
            self.assertEqual(response.status_code, 200)
            response = client.post('/reset-password', data={
                'new_password': os.environ['TEST_RESET_PASSWORD'],
                'confirm_password': os.environ['TEST_RESET_PASSWORD'],
            }, follow_redirects=False)
            self.assertIn(response.status_code, (302, 303))


if __name__ == '__main__':
    unittest.main(verbosity=2)
