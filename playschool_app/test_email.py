"""Opt-in SMTP smoke test; never runs or sends mail during normal discovery."""

import os
import smtplib
import unittest
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()


@unittest.skipUnless(
    os.environ.get('RUN_SMTP_TEST') == '1',
    'SMTP integration requires RUN_SMTP_TEST=1 plus MAIL_USERNAME/MAIL_PASSWORD',
)
class SMTPIntegrationTest(unittest.TestCase):
    def test_smtp_delivery(self):
        user = os.environ.get('MAIL_USERNAME')
        password = os.environ.get('MAIL_PASSWORD')
        self.assertTrue(user and password, 'MAIL_USERNAME and MAIL_PASSWORD are required')
        message = MIMEText('<p>SmartStudy SMTP smoke test.</p>', 'html')
        message['Subject'] = 'SmartStudy SMTP Test'
        message['From'] = user
        message['To'] = user
        with smtplib.SMTP_SSL(os.environ.get('MAIL_SERVER', 'smtp.gmail.com'), int(os.environ.get('MAIL_PORT', '465'))) as smtp:
            smtp.login(user, password)
            smtp.sendmail(user, [user], message.as_string())


if __name__ == '__main__':
    unittest.main(verbosity=2)
