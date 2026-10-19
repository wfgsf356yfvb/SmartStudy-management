"""Focused tests for server-side account input validation."""

import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


class RegistrationValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = patch.dict(os.environ, {
            'FLASK_ENV': 'development',
            'MYSQL_USER': 'test',
            'MYSQL_PASSWORD': 'test-only',
            'MYSQL_DB': 'test_only',
        }, clear=False)
        cls.env.start()
        import app as app_module
        cls.app_module = app_module

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    def test_email_requires_standard_address_shape(self):
        self.assertTrue(self.app_module._valid_email('person@gmail.com'))
        self.assertTrue(self.app_module._valid_email('teacher@yahoo.com'))
        self.assertFalse(self.app_module._valid_email('person@gmail'))
        self.assertFalse(self.app_module._valid_email('person gmail.com'))

    def test_phone_requires_exactly_ten_ascii_digits(self):
        self.assertTrue(self.app_module._valid_phone('9876543210'))
        self.assertFalse(self.app_module._valid_phone('98765'))
        self.assertFalse(self.app_module._valid_phone('98765432101'))
        self.assertFalse(self.app_module._valid_phone('98765abc10'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
