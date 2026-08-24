import os
import json
import re
from datetime import datetime, timezone

AUDIT_FILE = os.environ.get(
    'PROVISION_AUDIT_FILE',
    os.path.join(os.path.dirname(__file__), 'provision_audit.log'),
).strip()

_SENSITIVE_KEY = re.compile(r'(password|passwd|secret|token|api[_-]?key|credential|private[_-]?key)', re.I)
_SENSITIVE_VALUE = re.compile(r'(?i)(password|passwd|secret|token|api[_-]?key|credential)\s*[:=]\s*[^,;\s]+')


def _redact(value, key=''):
    if _SENSITIVE_KEY.search(str(key)):
        return '[redacted]'
    if isinstance(value, dict):
        return {name: _redact(item, name) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _SENSITIVE_VALUE.sub(lambda match: f'{match.group(1)}=[redacted]', value)
    return value


def redact_error(error):
    """Return a bounded, secret-safe operational error string."""
    text = str(error or '')[:1000]
    text = _SENSITIVE_VALUE.sub(lambda match: f'{match.group(1)}=[redacted]', text)
    text = re.sub(r'(?i)(bearer\s+)[^\s,;]+', r'\1[redacted]', text)
    text = re.sub(r'(?i)(mysql://|redis://)[^\s]+', r'\1[redacted]', text)
    return text


def log(event_type, details):
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'event': event_type,
        'details': _redact(details),
    }
    try:
        os.makedirs(os.path.dirname(os.path.abspath(AUDIT_FILE)), exist_ok=True)
        with open(AUDIT_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
