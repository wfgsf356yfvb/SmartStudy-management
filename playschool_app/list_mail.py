import time
import imaplib
import email
from email.header import decode_header
import os

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


def main():
    env = read_env('.env')
    user = env.get('MAIL_USERNAME')
    pwd = env.get('MAIL_PASSWORD')
    if not user or not pwd:
        print('Missing MAIL credentials in .env')
        return

    imap = imaplib.IMAP4_SSL('imap.gmail.com')
    imap.login(user, pwd)
    imap.select('INBOX')
    status, data = imap.search(None, 'ALL')
    ids = data[0].split()[-40:]
    print('Showing last', len(ids), 'messages:')
    for msgid in reversed(ids):
        _, msgdata = imap.fetch(msgid, '(RFC822)')
        for part in msgdata:
            if isinstance(part, tuple):
                msg = email.message_from_bytes(part[1])
                subj, enc = decode_header(msg.get('Subject'))[0]
                if isinstance(subj, bytes):
                    subj = subj.decode(enc or 'utf-8', 'ignore')
                frm = msg.get('From')
                date = msg.get('Date')
                print('---')
                print('Date:', date)
                print('From:', frm)
                print('Subject:', subj)
                # print body snippet
                body = ''
                if msg.is_multipart():
                    for p in msg.walk():
                        if p.get_content_type() in ('text/html', 'text/plain'):
                            try:
                                body = p.get_payload(decode=True).decode(p.get_content_charset() or 'utf-8', 'ignore')
                                break
                            except Exception:
                                continue
                else:
                    body = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8', 'ignore')
                print('Body snippet:', body[:200].replace('\n',' ').replace('\r',' '))
    imap.logout()

if __name__ == '__main__':
    main()
