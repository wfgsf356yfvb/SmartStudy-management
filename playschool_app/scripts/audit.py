import os
import json
from datetime import datetime

AUDIT_FILE = os.path.join(os.path.dirname(__file__), 'provision_audit.log')


def log(event_type, details):
    entry = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'event': event_type,
        'details': details
    }
    try:
        with open(AUDIT_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
