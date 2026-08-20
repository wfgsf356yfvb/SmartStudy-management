import os


def _as_bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


class Config:
    ENVIRONMENT = os.environ.get('FLASK_ENV', 'development').lower()
    IS_PRODUCTION = ENVIRONMENT == 'production'
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if IS_PRODUCTION and (not SECRET_KEY or len(SECRET_KEY) < 32):
        raise RuntimeError('SECRET_KEY must be a random value of at least 32 characters in production.')
    SECRET_KEY = SECRET_KEY or 'development-only-change-me'

    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', '')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'playschool_db')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'mp4', 'docx', 'doc'}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = _as_bool(os.environ.get('SESSION_COOKIE_SECURE'), IS_PRODUCTION)
    PERMANENT_SESSION_LIFETIME = 28800
    CSRF_ENABLED = _as_bool(os.environ.get('CSRF_ENABLED'), True)

    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 465))
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    UPI_ID = os.environ.get('UPI_ID', '')
    UPI_NAME = os.environ.get('UPI_NAME', 'PlaySchool Renewal')

    if IS_PRODUCTION:
        if not MYSQL_USER or MYSQL_USER.lower() == 'root':
            raise RuntimeError('MYSQL_USER must be a non-root application account in production.')
        if not MYSQL_PASSWORD:
            raise RuntimeError('MYSQL_PASSWORD must be provided in production.')
