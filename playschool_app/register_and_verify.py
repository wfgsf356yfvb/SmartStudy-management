import os
import time
import re
import imaplib
import email
from email.header import decode_header
import requests


def read_env(path='.env'):
    env = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


def fetch_latest_otp(mail_user, mail_pass, subject_hint='Account Registration Verification', timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            imap = imaplib.IMAP4_SSL('imap.gmail.com')
            imap.login(mail_user, mail_pass)
            imap.select('INBOX')

            # Try to find by subject first
            status, data = imap.search(None, 'ALL')
            if status != 'OK':
                imap.logout()
                time.sleep(2)
                continue

            ids = data[0].split()
            ids = ids[-20:]  # check last 20
            for msgid in reversed(ids):
                _, msgdata = imap.fetch(msgid, '(RFC822)')
                for part in msgdata:
                    if isinstance(part, tuple):
                        msg = email.message_from_bytes(part[1])
                        subj, enc = decode_header(msg.get('Subject'))[0]
                        if isinstance(subj, bytes):
                            try:
                                subj = subj.decode(enc or 'utf-8')
                            except Exception:
                                subj = subj.decode('utf-8', 'ignore')

                        if subject_hint in (subj or '') or 'confirmation code' in (subj or '').lower() or 'verification code' in (subj or '').lower():
                            # get payload
                            body = ''
                            if msg.is_multipart():
                                for part2 in msg.walk():
                                    ctype = part2.get_content_type()
                                    if ctype == 'text/html' or ctype == 'text/plain':
                                        try:
                                            body = part2.get_payload(decode=True).decode(part2.get_content_charset() or 'utf-8', 'ignore')
                                            break
                                        except Exception:
                                            continue
                            else:
                                body = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8', 'ignore')

                            m = re.search(r"(\d{6})", body)
                            if m:
                                imap.logout()
                                return m.group(1)
            imap.logout()
        except Exception as e:
            # print('IMAP error', e)
            pass
        time.sleep(2)
    return None


def main():
    env = read_env('.env')
    mail_user = env.get('MAIL_USERNAME')
    mail_pass = env.get('MAIL_PASSWORD')
    if not mail_user or not mail_pass:
        print('MAIL_USERNAME or MAIL_PASSWORD missing in .env')
        return

    base = 'http://127.0.0.1:5000'
    sess = requests.Session()

    # Register a new super_admin with the target email
    data = {
        'name': 'Auto Test',
        'email': mail_user,
        'phone': '9999999999',
        'password': 'Testpass123',
        'role': 'super_admin'
    }

    r = sess.post(f'{base}/register', data=data, allow_redirects=False)
    if r.status_code not in (302, 200):
        print('Register request failed', r.status_code)
        print(r.text[:400])
        return

    print('Register requested — waiting for email...')
    code = fetch_latest_otp(mail_user, mail_pass, timeout=45)
    if not code:
        print('Failed to fetch OTP from Gmail')
        return

    print('OTP found:', code)

    # Post to verify
    vr = sess.post(f'{base}/verify-otp', data={'otp': code}, allow_redirects=False)
    print('Verify response code:', vr.status_code)
    if vr.status_code in (302, 200):
        print('OTP verification attempted; check app UI or auth messages.')
    else:
        print('Unexpected verify response:', vr.text[:400])


if __name__ == '__main__':
    main()
