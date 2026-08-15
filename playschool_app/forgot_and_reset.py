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


def fetch_latest_otp(mail_user, mail_pass, timeout=180):
    """Search recent messages from your account or PlaySchool sender and return first 6-digit code found."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            imap = imaplib.IMAP4_SSL('imap.gmail.com')
            imap.login(mail_user, mail_pass)
            imap.select('INBOX')
            status, data = imap.search(None, 'ALL')
            if status != 'OK':
                imap.logout()
                time.sleep(2)
                continue
            ids = data[0].split()
            ids = ids[-60:]
            # First pass: prefer explicit password-reset subjects
            for msgid in reversed(ids):
                _, msgdata = imap.fetch(msgid, '(RFC822)')
                for part in msgdata:
                    if isinstance(part, tuple):
                        msg = email.message_from_bytes(part[1])
                        frm = msg.get('From') or ''
                        subj, enc = decode_header(msg.get('Subject'))[0]
                        if isinstance(subj, bytes):
                            subj = subj.decode(enc or 'utf-8', 'ignore')
                        subj_l = (subj or '').lower()
                        frm_l = (frm or '').lower()
                        # Prefer explicit password-reset subjects
                        if (
                            'password reset' in subj_l or
                            'password reset code' in subj_l or
                            'password reset request' in subj_l or
                            'reset code' in subj_l or
                            'password reset otp' in subj_l
                        ):
                            # get payload
                            body = ''
                            if msg.is_multipart():
                                for p in msg.walk():
                                    ctype = p.get_content_type()
                                    if ctype in ('text/html', 'text/plain'):
                                        try:
                                            body = p.get_payload(decode=True).decode(p.get_content_charset() or 'utf-8', 'ignore')
                                            break
                                        except Exception:
                                            continue
                            else:
                                body = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8', 'ignore')
                            m = re.search(r"(\d{6})", body)
                            if m:
                                imap.logout()
                                return m.group(1)
            # Second pass: fallback to any playschool messages (login codes) if no password-reset found
            for msgid in reversed(ids):
                _, msgdata = imap.fetch(msgid, '(RFC822)')
                for part in msgdata:
                    if isinstance(part, tuple):
                        msg = email.message_from_bytes(part[1])
                        frm = msg.get('From') or ''
                        subj, enc = decode_header(msg.get('Subject'))[0]
                        if isinstance(subj, bytes):
                            subj = subj.decode(enc or 'utf-8', 'ignore')
                        subj_l = (subj or '').lower()
                        frm_l = (frm or '').lower()
                        if mail_user.lower() in frm_l or 'playschool' in subj_l or 'playschool' in frm_l:
                            body = ''
                            if msg.is_multipart():
                                for p in msg.walk():
                                    ctype = p.get_content_type()
                                    if ctype in ('text/html', 'text/plain'):
                                        try:
                                            body = p.get_payload(decode=True).decode(p.get_content_charset() or 'utf-8', 'ignore')
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
        except Exception:
            pass
        time.sleep(2)
    return None


def main():
    env = read_env('.env')
    mail_user = env.get('MAIL_USERNAME')
    mail_pass = env.get('MAIL_PASSWORD')
    if not mail_user or not mail_pass:
        print('MAIL credentials missing in .env')
        return

    base = 'http://127.0.0.1:5000'
    sess = requests.Session()

    # Step 1: request forgot-password
    print('Requesting password reset OTP...')
    r = sess.post(f'{base}/forgot-password', data={'email': mail_user}, allow_redirects=False)
    print('Forgot POST status:', r.status_code)
    if r.status_code not in (302, 200):
        print('Forgot request failed:', r.text[:400])
        return

    # Step 2: wait and fetch OTP from Gmail
    print('Waiting for OTP email...')
    code = fetch_latest_otp(mail_user, mail_pass, timeout=180)
    if not code:
        print('Failed to fetch OTP from Gmail')
        return
    print('OTP found:', code)

    # Step 3: verify OTP
    v = sess.post(f'{base}/verify-otp', data={'otp': code}, allow_redirects=False)
    print('Verify POST status:', v.status_code)
    print('Verify headers:', {k:v.headers.get(k) for k in ('Location','Set-Cookie')})
    print('Session cookies after verify:', sess.cookies.get_dict())
    if v.status_code not in (302, 200):
        print('Verify request failed:', v.text[:400])
        return

    # Step 4: set new password
    new_pw = 'Reset1234'
    print('Fetching reset form (GET) to confirm flow and session)...')
    g = sess.get(f'{base}/reset-password', allow_redirects=True)
    print('GET reset-password status:', g.status_code, 'URL:', g.url)
    if g.status_code == 404:
        print('Reset form not found. Response snippet:', g.text[:400])
        return
    print('Submitting new password...')
    s = sess.post(f'{base}/reset-password', data={'new_password': new_pw, 'confirm_password': new_pw}, allow_redirects=False)
    print('Reset POST status:', s.status_code)
    if s.status_code in (302, 200):
        print('Password reset attempted; check login.')
    else:
        print('Reset failed:', s.text[:400])


if __name__ == '__main__':
    main()
