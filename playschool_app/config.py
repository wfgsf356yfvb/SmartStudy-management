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
    TENANT_BASE_DOMAIN = os.environ.get(
        'TENANT_BASE_DOMAIN', 'localhost' if not IS_PRODUCTION else ''
    ).strip().lower().rstrip('.')
    TRUSTED_PROXY_COUNT = int(os.environ.get('TRUSTED_PROXY_COUNT', '0'))
    TENANT_ALLOWED_PORTS = tuple(
        int(port.strip()) for port in os.environ.get(
            'TENANT_ALLOWED_PORTS', '80,443' if IS_PRODUCTION else '80,443,5000'
        ).split(',') if port.strip()
    )
    TENANT_CREDENTIAL_PROVIDER = os.environ.get('TENANT_CREDENTIAL_PROVIDER', '').strip().lower()
    ALLOW_LOCAL_TENANT_CREDENTIALS = _as_bool(
        os.environ.get('ALLOW_LOCAL_TENANT_CREDENTIALS'), False
    )
    TENANT_DB_CREDENTIALS_JSON = os.environ.get('TENANT_DB_CREDENTIALS_JSON', '')
    TENANT_DB_CREDENTIALS_FILE = os.environ.get('TENANT_DB_CREDENTIALS_FILE', '')
    PROVISIONING_MYSQL_USER = os.environ.get('PROVISIONING_MYSQL_USER', '')
    PROVISIONING_MYSQL_PASSWORD = os.environ.get('PROVISIONING_MYSQL_PASSWORD', '')
    TENANT_GRANT_MYSQL_USER = os.environ.get('TENANT_GRANT_MYSQL_USER', '')
    TENANT_GRANT_MYSQL_PASSWORD = os.environ.get('TENANT_GRANT_MYSQL_PASSWORD', '')
    TENANT_DB_USER_HOST = os.environ.get('TENANT_DB_USER_HOST', '').strip()
    # Uploads are private application data, never Flask static assets.
    UPLOAD_FOLDER = os.environ.get(
        'PRIVATE_UPLOAD_FOLDER',
        os.path.join(os.path.dirname(__file__), 'instance', 'private_uploads'),
    )
    FILE_STORAGE_PROVIDER = os.environ.get('FILE_STORAGE_PROVIDER', 'local').strip().lower()
    OBJECT_STORAGE_BUCKET = os.environ.get('OBJECT_STORAGE_BUCKET', '').strip()
    FILE_SCANNER_PROVIDER = os.environ.get('FILE_SCANNER_PROVIDER', 'disabled').strip().lower()
    FILE_SCANNER_COMMAND = os.environ.get('FILE_SCANNER_COMMAND', '').strip()
    ALLOW_UNSCANNED_UPLOADS = _as_bool(os.environ.get('ALLOW_UNSCANNED_UPLOADS'), False)
    TENANT_UPLOAD_QUOTA_BYTES = int(os.environ.get('TENANT_UPLOAD_QUOTA_BYTES', 1073741824))
    UPLOAD_RETENTION_DAYS = int(os.environ.get('UPLOAD_RETENTION_DAYS', 365))
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
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '').strip()
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')
    RAZORPAY_WEBHOOK_SECRET = os.environ.get('RAZORPAY_WEBHOOK_SECRET', '')
    PLATFORM_SUBSCRIPTION_GRACE_DAYS = int(os.environ.get('PLATFORM_SUBSCRIPTION_GRACE_DAYS', '7'))
    REQUIRE_HTTPS = _as_bool(os.environ.get('REQUIRE_HTTPS'), IS_PRODUCTION)

    if IS_PRODUCTION:
        if not TENANT_BASE_DOMAIN:
            raise RuntimeError('TENANT_BASE_DOMAIN must be configured in production.')
        if TRUSTED_PROXY_COUNT < 0 or TRUSTED_PROXY_COUNT > 5:
            raise RuntimeError('TRUSTED_PROXY_COUNT must be between 0 and 5.')
        if not TENANT_ALLOWED_PORTS or any(port not in range(1, 65536) for port in TENANT_ALLOWED_PORTS):
            raise RuntimeError('TENANT_ALLOWED_PORTS contains an invalid port.')
        if TENANT_CREDENTIAL_PROVIDER not in ('environment', 'aws', 'protected_file'):
            raise RuntimeError(
                'TENANT_CREDENTIAL_PROVIDER must be explicitly set to environment, aws, or protected_file in production.'
            )
        if TENANT_CREDENTIAL_PROVIDER == 'protected_file' and (
                not TENANT_DB_CREDENTIALS_FILE or TENANT_DB_CREDENTIALS_FILE.endswith('.tenant_secrets.json')):
            raise RuntimeError('Production protected_file credentials require an explicit protected path.')
        if not MYSQL_USER or MYSQL_USER.lower() == 'root':
            raise RuntimeError('MYSQL_USER must be a non-root application account in production.')
        if not MYSQL_PASSWORD:
            raise RuntimeError('MYSQL_PASSWORD must be provided in production.')
        # Only provisioning-capable processes receive provisioning credentials.
        # Web and scheduler must be able to start without the grant secret.
        if PROVISIONING_MYSQL_USER or PROVISIONING_MYSQL_PASSWORD or TENANT_GRANT_MYSQL_USER or TENANT_GRANT_MYSQL_PASSWORD:
            if not PROVISIONING_MYSQL_USER or not PROVISIONING_MYSQL_PASSWORD:
                raise RuntimeError('Provisioning MySQL credentials are required in provisioning-capable production processes.')
            if not TENANT_GRANT_MYSQL_USER or not TENANT_GRANT_MYSQL_PASSWORD:
                raise RuntimeError('TENANT_GRANT_MYSQL_USER and TENANT_GRANT_MYSQL_PASSWORD are required in provisioning-capable production processes.')
            if TENANT_GRANT_MYSQL_USER.lower() == 'root':
                raise RuntimeError('TENANT_GRANT_MYSQL_USER must be non-root in production.')
            if TENANT_GRANT_MYSQL_USER.lower() == PROVISIONING_MYSQL_USER.strip().lower():
                raise RuntimeError('TENANT_GRANT_MYSQL_USER must differ from PROVISIONING_MYSQL_USER.')
        if not TENANT_DB_USER_HOST:
            raise RuntimeError('TENANT_DB_USER_HOST must be configured for tenant database accounts in production.')
        if FILE_STORAGE_PROVIDER not in ('local', 's3'):
            raise RuntimeError('FILE_STORAGE_PROVIDER must be local or s3 in production.')
        normalized_upload_path = os.path.normcase(os.path.abspath(UPLOAD_FOLDER)).replace('\\', '/')
        if '/static/uploads' in normalized_upload_path:
            raise RuntimeError('Production uploads must not use the public static/uploads path.')
        if FILE_STORAGE_PROVIDER == 's3' and not OBJECT_STORAGE_BUCKET:
            raise RuntimeError('OBJECT_STORAGE_BUCKET is required when S3 storage is selected.')
        if FILE_SCANNER_PROVIDER != 'command' or not FILE_SCANNER_COMMAND:
            raise RuntimeError('A configured command malware scanner is required in production.')
        if TENANT_UPLOAD_QUOTA_BYTES <= 0 or UPLOAD_RETENTION_DAYS <= 0:
            raise RuntimeError('Production upload quota and retention values must be positive.')
        if ALLOW_UNSCANNED_UPLOADS:
            raise RuntimeError('ALLOW_UNSCANNED_UPLOADS is forbidden in production.')
