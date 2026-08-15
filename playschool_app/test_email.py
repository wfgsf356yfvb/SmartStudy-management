from dotenv import load_dotenv
import os, smtplib
from email.mime.text import MIMEText

load_dotenv()
user = os.environ.get('MAIL_USERNAME')
pwd = os.environ.get('MAIL_PASSWORD')
recipient = user

if not user or not pwd:
    print('ERROR: MAIL_USERNAME or MAIL_PASSWORD not set in .env')
    raise SystemExit(1)

msg = MIMEText("<p>Test OTP delivery from PlaySchool — ignore.</p>", 'html')
msg['Subject'] = "PlaySchool - SMTP Test"
msg['From'] = user
msg['To'] = recipient

try:
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(user, pwd)
        s.sendmail(user, recipient, msg.as_string())
    print('✅ Test email sent — check your Gmail inbox (and Spam).')
except Exception as e:
    print('❌ SMTP error:', e)
    raise
