"""Opt-in HTTP login smoke test with no embedded credentials."""

import os
import unittest

import requests


@unittest.skipUnless(
    os.environ.get('RUN_HTTP_TEST') == '1',
    'HTTP integration requires RUN_HTTP_TEST=1, a running Flask server, and test credentials',
)
class LoginIntegrationTest(unittest.TestCase):
    def test_login_endpoint(self):
        email = os.environ.get('TEST_LOGIN_EMAIL')
        password = os.environ.get('TEST_LOGIN_PASSWORD')
        self.assertTrue(email and password, 'TEST_LOGIN_EMAIL and TEST_LOGIN_PASSWORD are required')
        response = requests.post(
            os.environ.get('TEST_LOGIN_URL', 'http://127.0.0.1:5000/login'),
            data={'email': email, 'password': password},
            allow_redirects=False,
            timeout=10,
        )
        self.assertIn(response.status_code, (200, 302, 303))


if __name__ == '__main__':
    unittest.main(verbosity=2)
