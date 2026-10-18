from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify, send_file, g, abort
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from mysql.connector import pooling, Error
from functools import wraps
import os, datetime, random, smtplib, secrets, hmac, json, re, time
from decimal import Decimal
from io import BytesIO
from email.mime.text import MIMEText
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

# Development convenience only. Production deployments must inject secrets
# through the process environment or an explicitly configured secret provider.
if os.environ.get('FLASK_ENV', 'development').strip().lower() != 'production':
    load_dotenv()

from config import Config
from mysql_setup import create_database, create_tables, seed_data
from tenant_services.middleware.tenant_resolver import resolve_tenant, TenantResolutionError
from tenant_services.file_storage import (
    StorageProviderUnavailable,
    UploadQuotaExceeded,
    UploadValidationError,
    is_private_storage_key,
    read_private_upload,
    save_private_upload,
)
from billing_domain import (
    ALLOWED_PAYMENT_METHODS,
    PLATFORM_SUBSCRIPTION_DOMAIN,
    SCHOOL_FEE_DOMAIN,
    PaymentProviderUnavailable,
    PaymentValidationError,
    json_event,
    parse_amount,
    payload_hash,
    provider_credentials_from_env,
    redact_payment_payload,
    safe_event_id,
    subscription_expiry,
    validate_payment_options,
    validate_school_fee_amount,
    verify_razorpay_payment_signature,
    verify_razorpay_webhook_signature,
    DISPUTE_EVENTS,
    FINAL_WEBHOOK_STATUSES,
    REFUND_EVENTS,
    provider_event_entity,
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config.from_object(Config)
if Config.TRUSTED_PROXY_COUNT:
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=Config.TRUSTED_PROXY_COUNT,
        x_proto=Config.TRUSTED_PROXY_COUNT,
        x_host=Config.TRUSTED_PROXY_COUNT,
    )

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# MySQL Connection Pool
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
db_config = {
    'host': Config.MYSQL_HOST,
    'user': Config.MYSQL_USER,
    'password': Config.MYSQL_PASSWORD,
    'database': Config.MYSQL_DB,
    'port': Config.MYSQL_PORT,
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
    'autocommit': False,
}

# Fail fast with a clear message if MYSQL_PASSWORD is not provided.
if not db_config.get('password'):
    print("MYSQL_PASSWORD is not set. Set it in .env or as an environment variable before starting the app.")
    print("   Example (PowerShell): $env:MYSQL_PASSWORD = 'your_password' ; python app.py")
    raise SystemExit(1)

try:
    connection_pool = pooling.MySQLConnectionPool(
        pool_name="playschool_pool",
        pool_size=5,
        pool_reset_session=True,
        **db_config
    )
    print("MySQL connection pool created successfully.")
except Error as e:
    print(f"MySQL pool error: {e}")
    err_str = str(e).lower()
    # If the database is missing, try to create it and the tables, then retry
    if 'unknown database' in err_str or 'doesn\'t exist' in err_str or ('database' in err_str and 'unknown' in err_str):
        if Config.IS_PRODUCTION:
            print("   Database is missing; automatic production initialization is disabled.")
            connection_pool = None
        else:
            print("   Database not found Ã¢â‚¬â€ attempting to create database and tables...")
            try:
                create_database()
                create_tables()
                seed_data()
                # Retry pool creation
                connection_pool = pooling.MySQLConnectionPool(
                    pool_name="playschool_pool",
                    pool_size=5,
                    pool_reset_session=True,
                    **db_config
                )
                print("Ã¢Å“â€¦ MySQL Connection Pool created successfully after initializing DB!")
            except Exception as e2:
                print(f"Ã¢ÂÅ’ Failed to initialize DB and create pool: {e2}")
                print("   You can also run: python mysql_setup.py")
                connection_pool = None
    else:
        print("   Make sure MySQL is running and run: python mysql_setup.py")
        connection_pool = None

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# DB Helper (MySQL)
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
def get_db():
    """Get a connection from the control (central) pool."""
    if connection_pool is None:
        raise Exception("Database connection pool not available. Run: python mysql_setup.py")
    return connection_pool.get_connection()

def query_db(sql, args=(), one=False, commit=False, use_control=False):
    """Execute a query against tenant DB when available, otherwise control DB.

    Set `use_control=True` to force executing against the central control DB (e.g., schools metadata).
    """
    # Choose connection: control or tenant
    try:
        if not use_control and hasattr(g, 'tenant') and g.tenant:
            # dynamic import to avoid circular at module load
            from tenant_services.tenant_db import get_connection_for_tenant
            conn = get_connection_for_tenant(g.tenant)
        else:
            conn = get_db()

        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, args)
        if commit:
            conn.commit()
            last_id = cursor.lastrowid
            return last_id
        rv = cursor.fetchall()
        return (rv[0] if rv else None) if one else rv
    except Error as e:
        if commit:
            try:
                conn.rollback()
            except Exception:
                pass
        raise e
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# Auth Helpers
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first!', 'warning')
            return redirect(url_for('login'))
        user = current_user()
        if not user or not user.get('is_active') or user.get('role') != session.get('role'):
            session.clear()
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            user = current_user()
            if not user or not user.get('is_active') or user.get('role') != session.get('role'):
                session.clear()
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                flash('Access denied!', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def current_user():
    if 'user_id' not in session:
        return None

    user_id = session['user_id']
    role = session.get('role')

    # Super-admins and school admins are stored centrally.
    if role == 'super_admin':
        return query_db(
            "SELECT * FROM users WHERE id=%s AND role='super_admin'",
            (user_id,),
            one=True,
            use_control=True,
        )

    if role == 'admin':
        sid = session.get('school_id')
        if sid is None:
            return None
        return query_db(
            "SELECT * FROM users WHERE id=%s AND role='admin' AND school_id=%s",
            (user_id, sid),
            one=True,
            use_control=True,
        )

    # Teachers/students are tenant-local accounts.
    return query_db(
        "SELECT * FROM users WHERE id=%s AND school_id=%s",
        (user_id, session.get('school_id')),
        one=True,
    )


def storage_tenant():
    """Return a server-derived storage tenant label; never use browser input."""
    tenant = getattr(g, 'tenant', None)
    if tenant and tenant.get('subdomain'):
        return tenant['subdomain']
    school_id = session.get('school_id')
    if school_id is not None:
        return f'school-{int(school_id)}'
    return 'control'


def save_upload(file_storage, category):
    return save_private_upload(
        file_storage,
        storage_tenant(),
        category,
        app.config['ALLOWED_EXTENSIONS'],
    )


def file_is_authorized(filename):
    """Authorize a private file through its owning application record."""
    user = current_user()
    if not user or not is_private_storage_key(filename):
        return False
    if session.get('role') != 'super_admin' and not is_private_storage_key(filename, storage_tenant()):
        return False

    role = session.get('role')
    user_id = session.get('user_id')
    school_id = session.get('school_id')
    if role == 'super_admin':
        return bool(
            query_db("SELECT id FROM users WHERE id=%s AND profile_pic=%s", (user_id, filename), one=True, use_control=True)
            or query_db("SELECT id FROM payments WHERE screenshot=%s", (filename,), one=True, use_control=True)
            or query_db("SELECT id FROM platform_subscription_payments WHERE receipt_file=%s", (filename,), one=True, use_control=True)
            or query_db("SELECT id FROM student_fee_payments WHERE receipt_file=%s", (filename,), one=True, use_control=True)
        )

    if query_db("SELECT id FROM users WHERE id=%s AND profile_pic=%s", (user_id, filename), one=True):
        return True
    if role == 'teacher':
        return bool(
            query_db("SELECT h.id FROM homework h WHERE h.teacher_id=%s AND h.file_path=%s", (user_id, filename), one=True)
            or query_db(
                "SELECT s.id FROM submissions s JOIN homework h ON h.id=s.homework_id "
                "WHERE h.teacher_id=%s AND s.file_path=%s", (user_id, filename), one=True
            )
        )
    if role == 'student':
        return bool(
            query_db(
                "SELECT h.id FROM homework h JOIN users u ON u.id=h.teacher_id "
                "WHERE h.file_path=%s AND u.school_id=%s AND (h.class_level=%s OR h.class_level='all')",
                (filename, school_id, user.get('class_level')),
                one=True,
            )
            or query_db("SELECT id FROM submissions WHERE student_id=%s AND file_path=%s", (user_id, filename), one=True)
            or query_db("SELECT id FROM student_fee_payments WHERE student_id=%s AND receipt_file=%s", (user_id, filename), one=True)
        )
    if role == 'admin':
        return bool(
            query_db("SELECT id FROM payments WHERE school_id=%s AND screenshot=%s", (school_id, filename), one=True, use_control=True)
            or query_db("SELECT id FROM platform_subscription_payments WHERE school_id=%s AND receipt_file=%s", (school_id, filename), one=True, use_control=True)
            or query_db("SELECT id FROM student_fee_payments WHERE school_id=%s AND receipt_file=%s", (school_id, filename), one=True)
        )
    return False


# Security headers
@app.after_request
def set_security_headers(response):
    response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains; preload'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer-when-downgrade'
    response.headers['Permissions-Policy'] = 'geolocation=()'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Minimal CSP - adjust as needed for your app assets
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https:; "
        "style-src 'self' 'unsafe-inline' https:; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://translate.google.com https://translate.googleapis.com; "
        "frame-src https://translate.google.com https://translate.googleapis.com;"
    )
    return response

def current_school():
    sid = session.get('school_id')
    if sid:
        return query_db("SELECT * FROM schools WHERE id=%s", (sid,), one=True, use_control=True)
    return None

def provisioned_school_for_assignment(school_id):
    """Return an active tenant mapping suitable for a school-admin assignment."""
    try:
        school_id = int(school_id)
    except (TypeError, ValueError):
        return None

    return query_db(
        "SELECT id, name, subdomain, subscription_status, valid_until "
        "FROM schools "
        "WHERE id=%s AND subdomain IS NOT NULL AND subdomain<>'' "
        "AND subscription_status='active'",
        (school_id,),
        one=True,
        use_control=True,
    )

def get_week_number():
    return datetime.date.today().isocalendar()[1]

def letter_grade(marks, total):
    if total == 0: return 'N/A'
    pct = (marks / total) * 100
    if pct >= 90: return 'A+'
    elif pct >= 80: return 'A'
    elif pct >= 70: return 'B+'
    elif pct >= 60: return 'B'
    elif pct >= 50: return 'C'
    else: return 'D'

def send_email(recipient, subject, body):
    """Sends an actual email using SMTP credentials defined in Config."""
    try:
        if not Config.MAIL_USERNAME or not Config.MAIL_PASSWORD:
            return False # Configuration missing
        
        msg = MIMEText(body, 'html')
        msg['Subject'] = subject
        msg['From'] = Config.MAIL_USERNAME
        msg['To'] = recipient
        
        with smtplib.SMTP_SSL(Config.MAIL_SERVER, Config.MAIL_PORT) as server:
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            server.sendmail(Config.MAIL_USERNAME, recipient, msg.as_string())
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def _new_otp():
    return f"{secrets.randbelow(900000) + 100000:06d}"


def _otp_rate_limited():
    last_sent = float(session.get('otp_last_sent_at') or 0)
    return bool(last_sent and time.time() - last_sent < 60)

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# Context Processor
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
@app.context_processor
def inject_user():
    return dict(current_user=current_user(), current_school=current_school(), csrf_token=csrf_token)

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
def csrf_token():
    """Return a per-session token for all unsafe browser requests."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return session['_csrf_token']


@app.before_request
def csrf_protect():
    if request.endpoint == 'platform_razorpay_webhook':
        return None
    if not app.config['CSRF_ENABLED'] or request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return None
    expected = session.get('_csrf_token')
    supplied = request.form.get('_csrf_token') or request.headers.get('X-CSRF-Token')
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        return ('Invalid or missing CSRF token.', 400)


@app.before_request
def block_legacy_public_uploads():
    """Prevent old files under the historical static upload tree being public."""
    if request.path.startswith('/static/uploads/'):
        return ('Not found', 404)


@app.before_request
def enforce_production_https():
    # Let Flask produce its normal 404 for unknown/development-only paths.
    # HTTPS enforcement still applies to every registered application route.
    if request.url_rule is None:
        return None
    if Config.REQUIRE_HTTPS and not request.is_secure:
        return ('HTTPS is required.', 400)

# Subscription Middleware
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
@app.before_request
def resolve_tenant_middleware():
    """Resolve tenant from the request host (subdomain) and set `g.tenant` and session school_id."""
    try:
        sch = resolve_tenant(
            query_db,
            request.host,
            Config.TENANT_BASE_DOMAIN,
            allowed_ports=Config.TENANT_ALLOWED_PORTS,
        )
    except TenantResolutionError:
        g.tenant = None
        return ('Tenant host is not authorized.', 404)
    if sch:
        if session.get('role') == 'super_admin':
            g.tenant = None
            return ('Super Admin must use the control host.', 403)
        g.tenant = sch
        if session.get('role') != 'super_admin':
            bound_tenant = session.get('tenant_subdomain')
            if bound_tenant and bound_tenant != sch.get('subdomain'):
                session.clear()
                return ('Tenant session is not valid for this host.', 403)
            session['tenant_subdomain'] = sch['subdomain']
        # Never let the request hostname overwrite an authenticated user's school.
        # The authenticated session must remain bound to the tenant selected at login.
        if session.get('role') != 'super_admin' and session.get('user_id') is not None:
            session_school = session.get('school_id')
            if session_school is not None and session_school != sch['id']:
                session.clear()
                return ('Tenant session is not valid for this host.', 403)
    else:
        if session.get('tenant_subdomain') and session.get('role') != 'super_admin':
            session.clear()
            return ('Tenant context is required.', 404)
        g.tenant = None
        if session.get('role') in {'admin', 'teacher', 'student'} and request.endpoint not in {'logout'}:
            return ('Tenant context is required.', 404)

@app.before_request
def check_school_subscription():
    exempt = ['login', 'logout', 'static', 'index', 'verify_otp', 'school_expired', 
              'admin_billing', 'admin_billing_renew', 'register', 'forgot_password', 'test']
    if not request.endpoint or request.endpoint in exempt or request.path.startswith('/static'):
        return

    if session.get('role') == 'super_admin':
        return

    sid = session.get('school_id')
    if sid:
        sch = query_db("SELECT valid_until, subscription_status FROM schools WHERE id=%s", (sid,), one=True, use_control=True)
        if sch:
            today = datetime.datetime.now().strftime('%Y-%m-%d')
            vu = str(sch['valid_until']) if sch['valid_until'] else None
            
            # Force lock if expired or disabled
            if sch['subscription_status'] == 'inactive':
                return redirect(url_for('school_expired'))
            if vu and vu < today:
                try:
                    grace_until = (datetime.datetime.strptime(vu, '%Y-%m-%d') + datetime.timedelta(
                        days=Config.PLATFORM_SUBSCRIPTION_GRACE_DAYS
                    )).strftime('%Y-%m-%d')
                except (TypeError, ValueError):
                    grace_until = today
                if today > grace_until:
                    return redirect(url_for('school_expired'))

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# INDEX
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# AUTH
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email'].strip()
        password = request.form['password']
        if g.tenant:
            # School admins are centrally managed; teacher/student accounts are tenant-local.
            admin_user = query_db(
                "SELECT * FROM users "
                "WHERE email=%s AND is_active=1 AND role='admin' AND school_id=%s",
                (email, g.tenant['id']),
                one=True,
                use_control=True,
            )

            user = admin_user or query_db(
                "SELECT * FROM users "
                "WHERE email=%s AND is_active=1 AND school_id=%s",
                (email, g.tenant['id']),
                one=True,
            )
        else:
            user = query_db(
                "SELECT * FROM users WHERE email=%s AND is_active=1 AND role='super_admin'",
                (email,),
                one=True,
                use_control=True,
            )
        if user and check_password_hash(user['password_hash'], password):
            if _otp_rate_limited():
                flash('Please wait before requesting another verification code.', 'warning')
                return redirect(url_for('login'))
            otp = _new_otp()
            # Send OTP only if SMTP is configured. Do NOT reveal OTP in the UI.
            mail_sent = send_email(
                email,
                "Ã°Å¸â€Â Playschool App - Login Verification Code",
                f"<h2>Hello, {user['name']}</h2><p>Your temporary code is: <b style='font-size:24px;'>{otp}</b></p><p>Thank you!</p>"
            )
            if not mail_sent:
                flash('SMTP not configured or failed to send email. OTP is sent only to the account email (Gmail). Please set `MAIL_USERNAME` and `MAIL_PASSWORD` in .env.', 'danger')
                return redirect(url_for('login'))

            # Persist OTP/session only after email was sent
            session['otp_val']  = otp
            session['otp_flow'] = 'login'
            session['otp_meta'] = {
                'user_id': user['id'],
                'role': user['role'],
                'name': user['name'],
                'school_id': user['school_id'],
                'tenant_subdomain': g.tenant.get('subdomain') if g.tenant else None,
            }
            session['otp_created_at'] = time.time()
            session['otp_attempts'] = 0
            session['otp_last_sent_at'] = time.time()
            flash(f"OTP sent to {email}. Check your inbox.", 'success')
            return redirect(url_for('verify_otp'))
        flash('Invalid email or password!', 'danger')
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if not g.tenant:
        return ('Tenant registration is required.', 404)
    if request.method == 'POST':
        name        = request.form['name'].strip()
        email       = request.form['email'].strip()
        phone       = request.form.get('phone', '').strip()
        if not phone.isdigit() or len(phone) != 10:
            flash('Phone number must be exactly 10 digits!', 'danger')
            return redirect(url_for('register'))
        password    = request.form['password']
        
        # Enforce Strong Password check Backend
        if len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            flash('Password must be minimum 8 characters and contain at least one letter and one number! Ã°Å¸â€Â', 'danger')
            return redirect(url_for('register'))

        submitted_role = request.form.get('role', 'student').strip().lower()
        if session.get('role') == 'admin':
            if submitted_role not in {'student', 'teacher'}:
                flash('School Admin may create only student or teacher accounts.', 'danger')
                return redirect(url_for('register'))
            role = submitted_role
        else:
            if submitted_role != 'student':
                flash('Public registration is limited to student accounts.', 'danger')
                return redirect(url_for('register'))
            role = 'student'
        school_id   = g.tenant['id']
        class_level = request.form.get('class_level', None) if role == 'student' else None
        parent_name = request.form.get('parent_name', '').strip()
        parent_phone= request.form.get('parent_phone', '').strip()

        # Only super_admin can theoretically register another admin
        existing = query_db("SELECT id FROM users WHERE email=%s", (email,), one=True)
        if existing:
            flash('Email already registered!', 'danger')
            return redirect(url_for('register'))
        existing_phone = query_db("SELECT id FROM users WHERE phone=%s", (phone,), one=True)
        if existing_phone:
            flash('Phone number already registered!', 'danger')
            return redirect(url_for('register'))
        pw_hash = generate_password_hash(password)
        
        # Send registration OTP via email; require SMTP
        if _otp_rate_limited():
            flash('Please wait before requesting another verification code.', 'warning')
            return redirect(url_for('register'))
        otp = _new_otp()
        mail_sent = send_email(
            email,
            "Ã°Å¸Å¡â‚¬ Account Registration Verification",
            f"<h2>Welcome to Playschool, {name}!</h2><p>Your confirmation code is: <b style='font-size:24px;'>{otp}</b></p>"
        )
        if not mail_sent:
            flash('SMTP not configured or failed to send email. Registration OTP must be delivered to your email (Gmail). Please set `MAIL_USERNAME` and `MAIL_PASSWORD` in .env.', 'danger')
            return redirect(url_for('register'))

        session['otp_val']  = otp
        session['otp_flow'] = 'register'
        session['otp_meta'] = {
            'name': name, 'email': email, 'phone': phone,
            'pw_hash': pw_hash, 'role': role,
            'school_id': school_id,
            'class_level': class_level, 'parent_name': parent_name,
            'parent_phone': parent_phone
        }
        session['otp_created_at'] = time.time()
        session['otp_attempts'] = 0
        session['otp_last_sent_at'] = time.time()
        flash(f"Registration OTP sent to {email}. Check your inbox.", 'success')
        return redirect(url_for('verify_otp'))
    
    # Pass Schools list for Registration Dropdown
    schools = query_db("SELECT * FROM schools", use_control=True)
    return render_template('auth/register.html', schools=schools)

@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if 'otp_val' not in session or 'otp_flow' not in session:
        flash('Session expired or invalid flow.', 'warning')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        entered_otp = request.form.get('otp', '').strip()
        created_at = float(session.get('otp_created_at') or 0)
        attempts = int(session.get('otp_attempts') or 0)
        if time.time() - created_at > 300 or attempts >= 5:
            session.pop('otp_val', None)
            session.pop('otp_flow', None)
            session.pop('otp_meta', None)
            session.pop('otp_created_at', None)
            session.pop('otp_attempts', None)
            flash('Verification code expired. Please request a new code.', 'warning')
            return redirect(url_for('login'))
        session['otp_attempts'] = attempts + 1
        if hmac.compare_digest(entered_otp, str(session['otp_val'])):
            # SUCCESS
            flow = session.get('otp_flow')
            meta = session.get('otp_meta')
            
            if flow == 'login':
                session['user_id'] = meta['user_id']
                session['role']    = meta['role']
                session['name']    = meta['name']
                session['school_id'] = meta.get('school_id')
                session['tenant_subdomain'] = meta.get('tenant_subdomain')
                session.pop('otp_val', None)
                session.pop('otp_flow', None)
                session.pop('otp_meta', None)
                session.pop('otp_created_at', None)
                session.pop('otp_attempts', None)
                flash(f"OTP Verified! Welcome back {meta['name']}! Ã°Å¸Å½â€°", 'success')
                return redirect(url_for('dashboard'))
                
            elif flow == 'register':
                # Actually commit user into DB now
                query_db(
                    "INSERT INTO users (name,email,phone,password_hash,role,school_id,class_level,parent_name,parent_phone) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (meta['name'], meta['email'], meta['phone'], meta['pw_hash'], meta['role'], meta['school_id'], meta['class_level'], meta['parent_name'], meta['parent_phone']),
                    commit=True
                )
                session.pop('otp_val', None)
                session.pop('otp_flow', None)
                session.pop('otp_meta', None)
                session.pop('otp_created_at', None)
                session.pop('otp_attempts', None)
                flash('Account secured and created successfully! Log in now.', 'success')
                return redirect(url_for('login'))
            elif flow == 'forgot':
                # Keep the forgot-password state active until the user resets the password
                session.pop('otp_val', None)
                session['otp_flow'] = 'forgot'
                session['forgot_verified'] = True
                session['otp_meta'] = meta or session.get('otp_meta', {})
                flash('OTP verified. Please set your new password.', 'success')
                return redirect(url_for('reset_password'))
        else:
            flash('Incorrect OTP code! Please try again.', 'danger')

    return render_template('auth/otp_verify.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'info')
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    # Simplified flow: user provides email -> send OTP to email -> user verifies OTP -> set new password
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            flash('Please enter your account email!', 'danger')
            return redirect(url_for('forgot_password'))

        user = query_db("SELECT * FROM users WHERE email=%s", (email,), one=True)
        if not user:
            flash('If an account exists, a reset code will be sent to its email address.', 'info')
            return redirect(url_for('forgot_password'))

        if _otp_rate_limited():
            flash('Please wait before requesting another verification code.', 'warning')
            return redirect(url_for('forgot_password'))
        otp = _new_otp()
        mail_sent = send_email(
            email,
            "Ã°Å¸â€Â Playschool App - Password Reset Code",
            f"<h2>Password reset request</h2><p>Your password reset code is: <b style='font-size:24px;'>{otp}</b></p>"
        )
        if not mail_sent:
            flash('SMTP not configured or failed to send email. Password reset OTP must be delivered to your email. Please set `MAIL_USERNAME` and `MAIL_PASSWORD` in .env.', 'danger')
            return redirect(url_for('forgot_password'))

        session['otp_val'] = otp
        session['otp_flow'] = 'forgot'
        session['forgot_verified'] = False
        session['otp_meta'] = {'email': email}
        session['otp_created_at'] = time.time()
        session['otp_attempts'] = 0
        session['otp_last_sent_at'] = time.time()
        flash(f'Password reset OTP sent to {email}. Check your inbox.', 'success')
        return redirect(url_for('verify_otp'))

    return render_template('auth/forgot_password.html')


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    # Only accessible after OTP 'forgot' verification
    if session.get('otp_flow') != 'forgot' or not session.get('forgot_verified'):
        flash('Invalid or expired reset flow. Request a new OTP.', 'warning')
        return redirect(url_for('forgot_password'))

    meta = session.get('otp_meta') or {}
    email = meta.get('email') or session.get('reset_email')
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        if new_password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('reset_password'))
        # Strength check: min 8, at least one letter and one number
        if len(new_password) < 8 or not any(c.isalpha() for c in new_password) or not any(c.isdigit() for c in new_password):
            flash('Password must be minimum 8 characters and contain at least one letter and one number! Ã°Å¸â€Â', 'danger')
            return redirect(url_for('reset_password'))

        pw_hash = generate_password_hash(new_password)
        query_db('UPDATE users SET password_hash=%s WHERE email=%s', (pw_hash, email), commit=True)

        # Clear session OTP state
        session.pop('otp_val', None)
        session.pop('otp_flow', None)
        session.pop('otp_meta', None)
        session.pop('forgot_verified', None)
        session.pop('reset_email', None)
        session.pop('otp_created_at', None)
        session.pop('otp_attempts', None)

        flash('Password reset successfully! Please login with your new password.', 'success')
        return redirect(url_for('login'))

    if email:
        session['reset_email'] = email
    return render_template('auth/reset_password.html', email=email)

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# DASHBOARD (role-based redirect)
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
@app.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role')
    if role == 'super_admin':
        return redirect(url_for('super_admin_dashboard'))
    elif role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif role == 'teacher':
        return redirect(url_for('teacher_dashboard'))
    else:
        return redirect(url_for('student_dashboard'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = current_user()
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        new_password = request.form.get('password', '').strip()
        
        # Image Upload logic
        profile_pic_name = user['profile_pic']
        if 'profile_pic' in request.files:
            f = request.files['profile_pic']
            if f and f.filename and allowed_file(f.filename):
                try:
                    profile_pic_name = save_upload(f, 'profile')
                except (UploadValidationError, UploadQuotaExceeded, StorageProviderUnavailable) as exc:
                    flash(str(exc), 'danger')
                    return redirect(url_for('profile'))

        if new_password:
            pw_hash = generate_password_hash(new_password)
            query_db("UPDATE users SET phone=%s, password_hash=%s, profile_pic=%s WHERE id=%s", 
                     (phone, pw_hash, profile_pic_name, session['user_id']), commit=True)
            flash('Profile, password and picture saved! Ã¢Å“Â¨', 'success')
        else:
            query_db("UPDATE users SET phone=%s, profile_pic=%s WHERE id=%s", 
                     (phone, profile_pic_name, session['user_id']), commit=True)
            flash('Profile details updated successfully! Ã¢Å“â€¦', 'success')
            
        return redirect(url_for('profile'))
        
    return render_template('profile.html', user=user)

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
#  BILLING & EXPIRY ROUTES
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
@app.route('/school-expired')
def school_expired():
    sid = session.get('school_id')
    if not sid: return redirect(url_for('index'))
    
    sch = query_db("SELECT * FROM schools WHERE id=%s", (sid,), one=True, use_control=True)
    if sch:
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        vu = str(sch['valid_until']) if sch['valid_until'] else None
        if sch['subscription_status'] != 'inactive' and (not vu or vu >= today):
            return redirect(url_for('dashboard'))
            
    return render_template('billing/expired.html', school=sch)

@app.route('/admin/billing', methods=['GET', 'POST'])
@role_required('admin')
def admin_billing():
    sid = session.get('school_id')
    school = query_db("SELECT * FROM schools WHERE id=%s", (sid,), one=True, use_control=True)
    plans = query_db("SELECT * FROM platform_subscription_plans WHERE is_active=1 ORDER BY amount, duration_days", use_control=True)
    payments = query_db("SELECT * FROM platform_subscription_payments WHERE school_id=%s ORDER BY created_at DESC", (sid,), use_control=True)
    
    if request.method == 'POST':
        try:
            amount = parse_amount(request.form.get('amount', 0))
            months = int(request.form.get('months', '12'))
            if months not in (1, 3, 6, 12):
                raise PaymentValidationError('Unsupported subscription duration.')
            notes  = request.form.get('notes', '').strip()[:2000]
            screenshot_name = None
            
            # Handle file upload
            if 'screenshot' in request.files:
                f = request.files['screenshot']
                if f and f.filename and allowed_file(f.filename):
                    try:
                        screenshot_name = save_upload(f, 'payment')
                    except (UploadValidationError, UploadQuotaExceeded, StorageProviderUnavailable) as exc:
                        flash(str(exc), 'danger')
                        return redirect(url_for('admin_billing'))
            
            invoice_no = f"PS-{sid}-{secrets.token_hex(8).upper()}"
            query_db(
                "INSERT INTO platform_subscription_payments "
                "(school_id, amount, duration_days, status, provider, idempotency_key, invoice_no, receipt_file, notes) "
                "VALUES (%s,%s,%s,'pending','manual_upi',%s,%s,%s,%s)",
                (sid, amount, months * 30, f"manual:{invoice_no}", invoice_no, screenshot_name, notes),
                commit=True, use_control=True,
            )
            flash("Transaction submitted! Please wait while Super Admin verifies payment. Ã¢Å“â€¦", "success")
        except (ValueError, PaymentValidationError):
            flash("Invalid amount entered.", "danger")
        except Exception:
            flash("Platform subscription payment could not be recorded.", "danger")
        return redirect(url_for('admin_billing'))
        
    return render_template('billing/admin_billing.html', school=school, payments=payments, plans=plans)

# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
#  ADMIN (PRINCIPAL) ROUTES
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
def _json_or_form():
    return request.get_json(silent=True) or request.form.to_dict()


def _razorpay_credentials():
    return provider_credentials_from_env(
        Config.ENVIRONMENT,
        Config.RAZORPAY_KEY_ID,
        Config.RAZORPAY_KEY_SECRET,
        Config.RAZORPAY_WEBHOOK_SECRET,
    )


def _activate_platform_subscription(payment_id, expected_school_id=None):
    """Atomically settle one platform payment and extend only its school."""
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT p.*, s.valid_until FROM platform_subscription_payments p "
            "JOIN schools s ON s.id=p.school_id WHERE p.id=%s FOR UPDATE",
            (payment_id,),
        )
        payment = cur.fetchone()
        if not payment or (expected_school_id is not None and payment['school_id'] != expected_school_id):
            raise PaymentValidationError('Platform payment was not found for this school.')
        if payment['status'] == 'paid':
            conn.commit()
            return False, payment
        duration_days = int(payment.get('duration_days') or 30)
        if payment.get('plan_id'):
            cur.execute("SELECT duration_days FROM platform_subscription_plans WHERE id=%s", (payment['plan_id'],))
            plan = cur.fetchone()
            if not plan:
                raise PaymentValidationError('Platform subscription plan is unavailable.')
            duration_days = int(plan['duration_days'])
        expiry = subscription_expiry(payment['valid_until'], duration_days)
        cur.execute(
            "UPDATE platform_subscription_payments SET status='paid', paid_at=UTC_TIMESTAMP() WHERE id=%s AND status<>'paid'",
            (payment_id,),
        )
        cur.execute(
            "UPDATE schools SET valid_until=%s, subscription_status='active' WHERE id=%s",
            (expiry, payment['school_id']),
        )
        conn.commit()
        payment['status'] = 'paid'
        payment['new_expiry'] = expiry
        return True, payment
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


@app.route('/platform/billing/order', methods=['POST'])
@role_required('admin')
def platform_subscription_order():
    """Create a platform-only Razorpay order."""
    data = _json_or_form()
    idempotency_key = request.headers.get('Idempotency-Key', '').strip()
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{8,160}', idempotency_key):
        return jsonify({'error': 'A valid Idempotency-Key is required.'}), 400
    try:
        credentials = _razorpay_credentials()
        plan_id = int(data.get('plan_id', 0))
        plan = query_db("SELECT * FROM platform_subscription_plans WHERE id=%s AND is_active=1",
                        (plan_id,), one=True, use_control=True)
        if not plan:
            raise PaymentValidationError('Subscription plan is unavailable.')
        sid = session.get('school_id')
        existing = query_db(
            "SELECT provider_order_id, amount, currency, invoice_no FROM platform_subscription_payments "
            "WHERE idempotency_key=%s AND school_id=%s",
            (idempotency_key, sid), one=True, use_control=True,
        )
        if existing and existing.get('provider_order_id'):
            return jsonify({'key_id': credentials['key_id'], 'order_id': existing['provider_order_id'],
                            'amount': int(parse_amount(existing['amount']) * 100),
                            'currency': existing['currency'], 'invoice_no': existing['invoice_no'],
                            'idempotent': True})
        invoice_no = f"PS-{sid}-{secrets.token_hex(8).upper()}"
        try:
            import razorpay
            client = razorpay.Client(auth=(credentials['key_id'], credentials['key_secret']))
            order = client.order.create(data={
                'amount': int(parse_amount(plan['amount']) * 100),
                'currency': plan['currency'],
                'receipt': invoice_no,
                'notes': {'domain': PLATFORM_SUBSCRIPTION_DOMAIN, 'school_id': str(sid)},
            })
        except ImportError as exc:
            raise PaymentProviderUnavailable('Razorpay client dependency is unavailable.') from exc
        order_id = order.get('id')
        if not isinstance(order_id, str) or not order_id:
            raise PaymentProviderUnavailable('Razorpay did not return an order identity.')
        query_db("INSERT INTO platform_subscription_payments "
                  "(school_id,plan_id,amount,duration_days,currency,status,provider,provider_order_id,idempotency_key,invoice_no) "
                  "VALUES (%s,%s,%s,%s,%s,'pending','razorpay',%s,%s,%s)",
                  (sid, plan['id'], plan['amount'], plan['duration_days'], plan['currency'], order_id, idempotency_key, invoice_no),
                  commit=True, use_control=True)
        return jsonify({'key_id': credentials['key_id'], 'order_id': order_id,
                        'amount': int(parse_amount(plan['amount']) * 100),
                        'currency': plan['currency'], 'invoice_no': invoice_no})
    except (PaymentValidationError, PaymentProviderUnavailable) as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception:
        return jsonify({'error': 'Platform payment order could not be created.'}), 503


@app.route('/platform/billing/verify', methods=['POST'])
@role_required('admin')
def platform_subscription_verify():
    data = _json_or_form()
    try:
        credentials = _razorpay_credentials()
        order_id = str(data.get('razorpay_order_id', '')).strip()
        payment_id = str(data.get('razorpay_payment_id', '')).strip()
        signature = str(data.get('razorpay_signature', '')).strip()
        payment = query_db("SELECT id FROM platform_subscription_payments WHERE provider_order_id=%s "
                           "AND school_id=%s AND provider='razorpay'",
                           (order_id, session.get('school_id')), one=True, use_control=True)
        if not payment or not verify_razorpay_payment_signature(order_id, payment_id, signature, credentials['key_secret']):
            raise PaymentValidationError('Payment verification failed.')
        query_db("UPDATE platform_subscription_payments SET provider_payment_id=%s WHERE id=%s "
                  "AND (provider_payment_id IS NULL OR provider_payment_id=%s)",
                  (payment_id, payment['id'], payment_id), commit=True, use_control=True)
        changed, settled = _activate_platform_subscription(payment['id'], session.get('school_id'))
        return jsonify({'status': 'paid', 'idempotent': not changed,
                        'invoice_no': settled['invoice_no'], 'expiry': str(settled.get('new_expiry') or '')})
    except (PaymentValidationError, PaymentProviderUnavailable) as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception:
        return jsonify({'error': 'Payment verification failed.'}), 400


@app.route('/webhooks/razorpay/platform', methods=['POST'])
def platform_razorpay_webhook():
    """Verify and idempotently apply platform-only Razorpay callbacks."""
    raw_body = request.get_data(cache=True)
    try:
        if getattr(g, 'tenant', None):
            return jsonify({'error': 'Webhook must use the control host.'}), 404
        credentials = _razorpay_credentials()
        if not verify_razorpay_webhook_signature(raw_body, request.headers.get('X-Razorpay-Signature', ''), credentials['webhook_secret']):
            return jsonify({'error': 'Invalid webhook signature.'}), 400
        event = json_event(raw_body)
        event_id = safe_event_id(event, request.headers.get('X-Razorpay-Event-Id'))
        event_type = str(event.get('event', ''))[:120]
        try:
            query_db("INSERT INTO platform_payment_events (event_id,event_type,payload_sha256,status) "
                     "VALUES (%s,%s,%s,'received')",
                     (event_id, event_type, payload_hash(raw_body)), commit=True, use_control=True)
        except Exception as exc:
            if 'duplicate' in str(exc).lower() or '1062' in str(exc):
                prior = query_db("SELECT status FROM platform_payment_events WHERE event_id=%s",
                                 (event_id,), one=True, use_control=True)
                if prior and prior.get('status') in FINAL_WEBHOOK_STATUSES:
                    return jsonify({'status': 'duplicate'}), 200
            else:
                raise
        entity = provider_event_entity(event, event_type)
        order_id, payment_id, amount = entity.get('order_id'), entity.get('id'), entity.get('amount')
        payment = None
        if event_type in REFUND_EVENTS or event_type in DISPUTE_EVENTS:
            payment = query_db("SELECT id,amount,school_id FROM platform_subscription_payments "
                               "WHERE provider_payment_id=%s AND provider='razorpay'",
                               (entity.get('payment_id'),), one=True, use_control=True)
        else:
            payment = query_db("SELECT id,amount,school_id FROM platform_subscription_payments "
                               "WHERE provider_order_id=%s AND provider='razorpay'",
                               (order_id,), one=True, use_control=True)
        if event_type in REFUND_EVENTS and payment and entity.get('id'):
            query_db("UPDATE platform_subscription_payments SET status='refunded', provider_refund_id=%s, "
                     "reconciliation_status='provider_refund' WHERE id=%s",
                     (entity.get('id'), payment['id']), commit=True, use_control=True)
            query_db("UPDATE platform_payment_events SET status='processed', processed_at=UTC_TIMESTAMP() WHERE event_id=%s",
                     (event_id,), commit=True, use_control=True)
            return jsonify({'status': 'processed'}), 200
        if event_type in DISPUTE_EVENTS and payment and entity.get('id'):
            query_db("UPDATE platform_subscription_payments SET status='disputed', provider_dispute_id=%s, "
                     "reconciliation_status='provider_dispute' WHERE id=%s",
                     (entity.get('id'), payment['id']), commit=True, use_control=True)
            query_db("UPDATE platform_payment_events SET status='processed', processed_at=UTC_TIMESTAMP() WHERE event_id=%s",
                     (event_id,), commit=True, use_control=True)
            return jsonify({'status': 'processed'}), 200
        if event_type not in ('payment.captured', 'order.paid') or not payment or not payment_id:
            query_db("UPDATE platform_payment_events SET status='ignored', processed_at=UTC_TIMESTAMP() WHERE event_id=%s",
                     (event_id,), commit=True, use_control=True)
            return jsonify({'status': 'ignored'}), 202
        if int(amount or -1) != int(parse_amount(payment['amount']) * 100):
            query_db("UPDATE platform_payment_events SET status='rejected', processed_at=UTC_TIMESTAMP() WHERE event_id=%s",
                     (event_id,), commit=True, use_control=True)
            return jsonify({'error': 'Webhook amount mismatch.'}), 400
        query_db("UPDATE platform_subscription_payments SET provider_payment_id=%s, reconciliation_status='provider_confirmed' "
                  "WHERE id=%s AND (provider_payment_id IS NULL OR provider_payment_id=%s)",
                  (payment_id, payment['id'], payment_id), commit=True, use_control=True)
        _activate_platform_subscription(payment['id'], payment['school_id'])
        query_db("UPDATE platform_payment_events SET status='processed', processed_at=UTC_TIMESTAMP() WHERE event_id=%s",
                 (event_id,), commit=True, use_control=True)
        return jsonify({'status': 'processed'}), 200
    except (PaymentValidationError, PaymentProviderUnavailable):
        return jsonify({'error': 'Webhook rejected.'}), 400
    except Exception:
        return jsonify({'error': 'Webhook processing failed.'}), 503


@app.route('/admin/dashboard')
@role_required('admin')
def admin_dashboard():
    sid = session.get('school_id')
    today = datetime.date.today().strftime('%Y-%m-%d')
    
    stats = {
        'total_students': query_db("SELECT COUNT(*) as c FROM users WHERE role='student' AND school_id=%s", (sid,), one=True)['c'],
        'total_teachers': query_db("SELECT COUNT(*) as c FROM users WHERE role='teacher' AND school_id=%s", (sid,), one=True)['c'],
        'active_students': query_db("SELECT COUNT(*) as c FROM users WHERE role='student' AND school_id=%s AND is_active=1", (sid,), one=True)['c'],
        'active_teachers': query_db("SELECT COUNT(*) as c FROM users WHERE role='teacher' AND school_id=%s AND is_active=1", (sid,), one=True)['c'],
        'inactive_students': query_db("SELECT COUNT(*) as c FROM users WHERE role='student' AND school_id=%s AND is_active=0", (sid,), one=True)['c'],
        'inactive_teachers': query_db("SELECT COUNT(*) as c FROM users WHERE role='teacher' AND school_id=%s AND is_active=0", (sid,), one=True)['c'],
        'total_homework': query_db("SELECT COUNT(*) as c FROM homework h JOIN users u ON h.teacher_id=u.id WHERE u.school_id=%s", (sid,), one=True)['c'],
        'total_submissions': query_db("SELECT COUNT(*) as c FROM submissions s JOIN users u ON s.student_id=u.id WHERE u.school_id=%s", (sid,), one=True)['c'],
        'nursery_count': query_db("SELECT COUNT(*) as c FROM users WHERE role='student' AND class_level='nursery' AND school_id=%s", (sid,), one=True)['c'],
        'lkg_count':     query_db("SELECT COUNT(*) as c FROM users WHERE role='student' AND class_level='lkg' AND school_id=%s", (sid,), one=True)['c'],
        'ukg_count':     query_db("SELECT COUNT(*) as c FROM users WHERE role='student' AND class_level='ukg' AND school_id=%s", (sid,), one=True)['c'],
        'today_present': query_db("SELECT COUNT(*) as c FROM attendance a JOIN users u ON a.student_id=u.id WHERE a.date=%s AND a.status='present' AND u.school_id=%s", (today, sid), one=True)['c'],
        'today_absent': query_db("SELECT COUNT(*) as c FROM attendance a JOIN users u ON a.student_id=u.id WHERE a.date=%s AND a.status='absent' AND u.school_id=%s", (today, sid), one=True)['c'],
        'pending_fees': query_db("SELECT COUNT(*) as c FROM student_fee_payments WHERE school_id=%s AND status='pending'", (sid,), one=True)['c'],
        'collected_fees': query_db("SELECT COALESCE(SUM(amount_paid),0) as c FROM student_fee_payments WHERE school_id=%s AND status='paid'", (sid,), one=True)['c'],
    }
    recent_hw = query_db("""
        SELECT h.*, u.name as teacher_name 
        FROM homework h JOIN users u ON h.teacher_id=u.id 
        WHERE u.school_id=%s
        ORDER BY h.created_at DESC LIMIT 5
    """, (sid,))
    top_students = query_db("""
        SELECT u.name, u.class_level,
               ROUND(AVG(s.marks/h.max_marks*100),1) as avg_pct,
               COUNT(s.id) as total_subs
        FROM submissions s
        JOIN users u ON s.student_id=u.id
        JOIN homework h ON s.homework_id=h.id
        WHERE s.marks IS NOT NULL AND u.school_id=%s
        GROUP BY u.id, u.name, u.class_level
        ORDER BY avg_pct DESC LIMIT 5
    """, (sid,))
    announcements = query_db("""
        SELECT a.* FROM announcements a JOIN users u ON a.author_id=u.id 
        WHERE u.school_id=%s ORDER BY a.created_at DESC LIMIT 3
    """, (sid,))
    
    # Subscription info
    school = query_db("SELECT * FROM schools WHERE id=%s", (sid,), one=True, use_control=True)
    
    return render_template('admin/dashboard.html', stats=stats, recent_hw=recent_hw,
                           top_students=top_students, announcements=announcements, school=school)

@app.route('/admin/users')
@role_required('admin')
def admin_users():
    sid = session.get('school_id')
    role_filter = request.args.get('role', 'all')
    class_filter = request.args.get('class', 'all')
    sql = "SELECT * FROM users WHERE school_id=%s"
    args = [sid]
    if role_filter != 'all':
        sql += " AND role=%s"; args.append(role_filter)
    if class_filter != 'all':
        sql += " AND class_level=%s"; args.append(class_filter)
    sql += " ORDER BY created_at DESC"
    users = query_db(sql, tuple(args))
    return render_template('admin/users.html', users=users, role_filter=role_filter, class_filter=class_filter)

@app.route('/admin/user/toggle/<int:uid>', methods=['POST'])
@role_required('admin')
def toggle_user(uid):
    sid = session.get('school_id')
    user = query_db("SELECT * FROM users WHERE id=%s AND school_id=%s", (uid, sid), one=True)
    if user and user['role'] != 'admin':
        new_status = 0 if user['is_active'] else 1
        query_db("UPDATE users SET is_active=%s WHERE id=%s", (new_status, uid), commit=True)
        flash(f"User {'activated' if new_status else 'deactivated'} successfully!", 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/delete/<int:uid>', methods=['POST'])
@role_required('admin')
def delete_user(uid):
    sid = session.get('school_id')
    user = query_db("SELECT * FROM users WHERE id=%s AND school_id=%s", (uid, sid), one=True)
    if user and user['role'] != 'admin':
        query_db("DELETE FROM users WHERE id=%s AND school_id=%s", (uid, sid), commit=True)
        flash('User deleted!', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/reports')
@role_required('admin')
def admin_reports():
    sid = session.get('school_id')
    class_stats = query_db("""
        SELECT u.class_level,
               COUNT(DISTINCT u.id) as students,
               COUNT(DISTINCT h.id) as homeworks,
               COUNT(DISTINCT s.id) as submissions,
               ROUND(AVG(s.marks/h.max_marks*100), 1) as avg_pct
        FROM users u
        LEFT JOIN submissions s ON s.student_id=u.id
        LEFT JOIN homework h ON s.homework_id=h.id
        WHERE u.role='student' AND u.school_id=%s
        GROUP BY u.class_level
    """, (sid,))
    student_progress = query_db("""
        SELECT u.name, u.class_level, u.parent_name,
               COUNT(s.id) as total_hw,
               SUM(CASE WHEN s.marks IS NOT NULL THEN 1 ELSE 0 END) as graded,
               ROUND(AVG(s.marks/h.max_marks*100), 1) as avg_pct
        FROM users u
        LEFT JOIN submissions s ON s.student_id=u.id
        LEFT JOIN homework h ON s.homework_id=h.id
        WHERE u.role='student' AND u.school_id=%s
        GROUP BY u.id, u.name, u.class_level, u.parent_name
        ORDER BY avg_pct DESC
    """, (sid,))
    return render_template('admin/reports.html', class_stats=class_stats, student_progress=student_progress)

@app.route('/admin/announcement', methods=['GET', 'POST'])
@role_required('admin')
def admin_announcement():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        target_role = request.form.get('target_role', 'all')
        target_class = request.form.get('target_class', 'all')
        query_db(
            "INSERT INTO announcements (author_id,title,content,target_role,target_class) VALUES (%s,%s,%s,%s,%s)",
            (session['user_id'], title, content, target_role, target_class), commit=True
        )
        flash('Announcement posted! Ã°Å¸â€œÂ¢', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/announcement.html')

# Ã¢â€â‚¬Ã¢â€â‚¬ Admin Fee Payments Management Ã¢â€â‚¬Ã¢â€â‚¬
@app.route('/admin/fee-payments')
@role_required('admin')
def admin_fee_payments():
    sid = session.get('school_id')
    class_filter = request.args.get('class', 'all')
    status_filter = request.args.get('status', 'all')
    
    sql = """
        SELECT sfp.*, u.name as student_name, u.class_level, u.parent_name, u.parent_phone
        FROM student_fee_payments sfp 
        JOIN users u ON sfp.student_id=u.id 
        WHERE sfp.school_id=%s AND sfp.payment_domain=%s
    """
    args = [sid, SCHOOL_FEE_DOMAIN]
    
    if class_filter != 'all':
        sql += " AND u.class_level=%s"
        args.append(class_filter)
    if status_filter != 'all':
        sql += " AND sfp.status=%s"
        args.append(status_filter)
    
    sql += " ORDER BY sfp.payment_date DESC"
    payments = query_db(sql, tuple(args))
    
    stats = {
        'total_collected': query_db("SELECT COALESCE(SUM(amount_paid),0) as c FROM student_fee_payments WHERE school_id=%s AND payment_domain=%s AND status='paid'", (sid, SCHOOL_FEE_DOMAIN), one=True)['c'],
        'pending_amount': query_db("SELECT COALESCE(SUM(amount_paid),0) as c FROM student_fee_payments WHERE school_id=%s AND payment_domain=%s AND status='pending'", (sid, SCHOOL_FEE_DOMAIN), one=True)['c'],
        'overdue_count': query_db("SELECT COUNT(*) as c FROM student_fee_payments WHERE school_id=%s AND payment_domain=%s AND status='overdue'", (sid, SCHOOL_FEE_DOMAIN), one=True)['c'],
        'month_collection': query_db("SELECT COALESCE(SUM(amount_paid),0) as c FROM student_fee_payments WHERE school_id=%s AND payment_domain=%s AND status='paid' AND MONTH(payment_date)=MONTH(NOW()) AND YEAR(payment_date)=YEAR(NOW())", (sid, SCHOOL_FEE_DOMAIN), one=True)['c'],
    }
    
    return render_template('admin/fee_payments.html', payments=payments, stats=stats, 
                           class_filter=class_filter, status_filter=status_filter)

@app.route('/admin/fee-payments/verify/<int:payment_id>', methods=['POST'])
@role_required('admin')
def verify_fee_payment(payment_id):
    sid = session.get('school_id')
    query_db("UPDATE student_fee_payments SET status='paid', verified_by=%s WHERE id=%s AND school_id=%s AND payment_domain=%s",
             (session['user_id'], payment_id, sid, SCHOOL_FEE_DOMAIN), commit=True)
    flash('Payment verified successfully! Ã¢Å“â€¦', 'success')
    return redirect(url_for('admin_fee_payments'))

@app.route('/admin/fee-payments/reject/<int:payment_id>', methods=['POST'])
@role_required('admin')
def reject_fee_payment(payment_id):
    sid = session.get('school_id')
    query_db("UPDATE student_fee_payments SET status='overdue' WHERE id=%s AND school_id=%s AND payment_domain=%s",
             (payment_id, sid, SCHOOL_FEE_DOMAIN), commit=True)
    flash('Payment rejected/marked overdue.', 'warning')
    return redirect(url_for('admin_fee_payments'))

# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
#  TEACHER ROUTES
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
@app.route('/teacher/dashboard')
@role_required('teacher')
def teacher_dashboard():
    tid = session['user_id']
    sid = session.get('school_id')
    stats = {
        'my_homework': query_db("SELECT COUNT(*) as c FROM homework WHERE teacher_id=%s", (tid,), one=True)['c'],
        'pending_grade': query_db("""
            SELECT COUNT(*) as c FROM submissions s
            JOIN homework h ON s.homework_id=h.id
            WHERE h.teacher_id=%s AND s.marks IS NULL
        """, (tid,), one=True)['c'],
        'students_nursery': query_db("SELECT COUNT(*) as c FROM users WHERE role='student' AND class_level='nursery' AND school_id=%s", (sid,), one=True)['c'],
        'students_lkg':     query_db("SELECT COUNT(*) as c FROM users WHERE role='student' AND class_level='lkg' AND school_id=%s", (sid,), one=True)['c'],
        'students_ukg':     query_db("SELECT COUNT(*) as c FROM users WHERE role='student' AND class_level='ukg' AND school_id=%s", (sid,), one=True)['c'],
    }
    recent_hw = query_db("""
        SELECT h.*, COUNT(s.id) as sub_count
        FROM homework h LEFT JOIN submissions s ON s.homework_id=h.id
        WHERE h.teacher_id=%s GROUP BY h.id ORDER BY h.created_at DESC LIMIT 5
    """, (tid,))
    announcements = query_db("""
        SELECT a.* FROM announcements a JOIN users u ON a.author_id=u.id 
        WHERE target_role IN ('all','teacher') AND (u.school_id=%s OR u.role='super_admin')
        ORDER BY a.created_at DESC LIMIT 3
    """, (sid,))
    return render_template('teacher/dashboard.html', stats=stats, recent_hw=recent_hw, announcements=announcements)

@app.route('/teacher/homework')
@role_required('teacher')
def teacher_homework():
    tid = session['user_id']
    homeworks = query_db("""
        SELECT h.*, COUNT(s.id) as sub_count,
               SUM(CASE WHEN s.marks IS NOT NULL THEN 1 ELSE 0 END) as graded_count
        FROM homework h LEFT JOIN submissions s ON s.homework_id=h.id
        WHERE h.teacher_id=%s GROUP BY h.id ORDER BY h.created_at DESC
    """, (tid,))
    return render_template('teacher/homework.html', homeworks=homeworks)

@app.route('/teacher/homework/create', methods=['GET', 'POST'])
@role_required('teacher')
def create_homework():
    if request.method == 'POST':
        title       = request.form['title']
        description = request.form.get('description', '')
        class_level = request.form['class_level']
        hw_type     = request.form['homework_type']
        due_date    = request.form['due_date']
        max_marks   = int(request.form.get('max_marks', 10))
        file_path   = None
        if 'file' in request.files:
            f = request.files['file']
            if f and f.filename and allowed_file(f.filename):
                try:
                    file_path = save_upload(f, 'homework')
                except (UploadValidationError, UploadQuotaExceeded, StorageProviderUnavailable) as exc:
                    flash(str(exc), 'danger')
                    return redirect(url_for('create_homework'))
        query_db(
            "INSERT INTO homework (teacher_id,class_level,title,description,file_path,homework_type,due_date,max_marks) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (session['user_id'], class_level, title, description, file_path, hw_type, due_date, max_marks),
            commit=True
        )
        flash('Homework assigned successfully! Ã°Å¸â€œÂ', 'success')
        return redirect(url_for('teacher_homework'))
    return render_template('teacher/create_homework.html')

@app.route('/teacher/homework/<int:hw_id>/submissions')
@role_required('teacher')
def hw_submissions(hw_id):
    hw = query_db("SELECT * FROM homework WHERE id=%s AND teacher_id=%s", (hw_id, session['user_id']), one=True)
    if not hw:
        flash('Access denied!', 'danger')
        return redirect(url_for('teacher_homework'))
    sid = session.get('school_id')
    students = query_db("""
        SELECT u.id, u.name, u.class_level, u.parent_name, u.parent_phone,
               s.id as sub_id, s.file_path as sub_file, s.submitted_at,
               s.marks, s.grade, s.feedback, s.remarks
        FROM users u
        LEFT JOIN submissions s ON s.student_id=u.id AND s.homework_id=%s
        WHERE u.role='student' AND u.school_id=%s AND (u.class_level=%s OR %s='all')
        ORDER BY u.name
    """, (hw_id, sid, hw['class_level'], hw['class_level']))
    return render_template('teacher/submissions.html', hw=hw, students=students)

@app.route('/teacher/grade/<int:sub_id>', methods=['POST'])
@role_required('teacher')
def grade_submission(sub_id):
    marks    = int(request.form['marks'])
    feedback = request.form.get('feedback', '')
    sub = query_db("SELECT s.*, h.max_marks FROM submissions s JOIN homework h ON s.homework_id=h.id WHERE s.id=%s AND h.teacher_id=%s", (sub_id, session['user_id']), one=True)
    if sub:
        grade = letter_grade(marks, sub['max_marks'])
        query_db(
            "UPDATE submissions s JOIN homework h ON s.homework_id=h.id SET s.marks=%s, s.grade=%s, s.feedback=%s, s.graded_at=NOW() WHERE s.id=%s AND h.teacher_id=%s",
            (marks, grade, feedback, sub_id, session['user_id']), commit=True
        )
        flash('Graded successfully! Ã¢Â­Â', 'success')
    return redirect(request.referrer or url_for('teacher_homework'))

@app.route('/teacher/progress')
@role_required('teacher')
def teacher_progress():
    sid = session.get('school_id')
    class_filter = request.args.get('class', 'all')
    sql = """
        SELECT u.id, u.name, u.class_level, u.parent_name, u.parent_phone,
               COUNT(s.id) as total_hw,
               SUM(CASE WHEN s.marks IS NOT NULL THEN 1 ELSE 0 END) as graded,
               ROUND(AVG(s.marks/h.max_marks*100), 1) as avg_pct
        FROM users u
        LEFT JOIN submissions s ON s.student_id=u.id
        LEFT JOIN homework h ON s.homework_id=h.id
        WHERE u.role='student' AND u.school_id=%s
    """
    args = [sid]
    if class_filter != 'all':
        sql += " AND u.class_level=%s"
        args.append(class_filter)
    sql += " GROUP BY u.id, u.name, u.class_level, u.parent_name, u.parent_phone ORDER BY avg_pct DESC"
    students = query_db(sql, tuple(args))
    return render_template('teacher/progress.html', students=students, class_filter=class_filter)

@app.route('/teacher/progress/weekly', methods=['GET', 'POST'])
@role_required('teacher')
def weekly_report():
    if request.method == 'POST':
        student_id = int(request.form['student_id'])
        marks      = float(request.form['marks_obtained'])
        total      = float(request.form.get('total_marks', 100))
        remarks    = request.form.get('remarks', '')
        week       = get_week_number()
        year       = datetime.date.today().year
        student = query_db(
            "SELECT id FROM users WHERE id=%s AND role='student' AND school_id=%s",
            (student_id, session.get('school_id')),
            one=True,
        )
        if not student:
            flash('Student is not part of this tenant.', 'danger')
            return redirect(url_for('weekly_report'))
        grade      = letter_grade(marks, total)
        # MySQL: INSERT ... ON DUPLICATE KEY UPDATE
        query_db("""
            INSERT INTO weekly_progress (student_id,teacher_id,week_number,year,marks_obtained,total_marks,grade,teacher_remarks)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE 
            marks_obtained=VALUES(marks_obtained), total_marks=VALUES(total_marks), 
            grade=VALUES(grade), teacher_remarks=VALUES(teacher_remarks)
        """, (student_id, session['user_id'], week, year, marks, total, grade, remarks), commit=True)
        flash('Weekly progress saved! Ã°Å¸â€œÅ ', 'success')
        return redirect(url_for('weekly_report'))
    students = query_db("SELECT * FROM users WHERE role='student' AND school_id=%s ORDER BY class_level, name", (session.get('school_id'),))
    weekly   = query_db("""
        SELECT wp.*, u.name as student_name, u.class_level
        FROM weekly_progress wp JOIN users u ON wp.student_id=u.id
        WHERE wp.teacher_id=%s AND wp.week_number=%s AND wp.year=%s
        ORDER BY u.class_level, u.name
    """, (session['user_id'], get_week_number(), datetime.date.today().year))
    return render_template('teacher/weekly_report.html', students=students, weekly=weekly,
                           current_week=get_week_number())

# Ã¢â€â‚¬Ã¢â€â‚¬ Teacher Announcements Ã¢â€â‚¬Ã¢â€â‚¬
@app.route('/teacher/announcement', methods=['GET', 'POST'])
@role_required('teacher')
def teacher_announcement():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        target_class = request.form.get('target_class', 'all')
        ann_type = request.form.get('announcement_type', 'general')
        query_db(
            "INSERT INTO announcements (author_id,title,content,target_role,target_class,announcement_type) VALUES (%s,%s,%s,'student',%s,%s)",
            (session['user_id'], title, content, target_class, ann_type), commit=True
        )
        flash('Announcement posted! Ã°Å¸â€œÂ¢', 'success')
        return redirect(url_for('teacher_announcement'))
    
    announcements = query_db("""
        SELECT * FROM announcements WHERE author_id=%s ORDER BY created_at DESC LIMIT 20
    """, (session['user_id'],))
    return render_template('teacher/announcement.html', announcements=announcements)

# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
#  STUDENT ROUTES
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
@app.route('/student/dashboard')
@role_required('student')
def student_dashboard():
    sid  = session['user_id']
    user = current_user()
    school_id = session.get('school_id')
    cl = user['class_level']
    
    stats = {
        'pending_hw': query_db("""
            SELECT COUNT(*) as c FROM homework h
            JOIN users ut ON h.teacher_id=ut.id
            WHERE (h.class_level=%s OR h.class_level='all')
            AND ut.school_id=%s
            AND h.id NOT IN (SELECT homework_id FROM submissions WHERE student_id=%s)
            AND h.due_date >= CURDATE()
        """, (cl, school_id, sid), one=True)['c'],
        'submitted_hw': query_db("SELECT COUNT(*) as c FROM submissions WHERE student_id=%s", (sid,), one=True)['c'],
        'graded_hw': query_db("SELECT COUNT(*) as c FROM submissions WHERE student_id=%s AND marks IS NOT NULL", (sid,), one=True)['c'],
        'avg_marks': query_db("""
            SELECT ROUND(AVG(s.marks/h.max_marks*100),1) as a
            FROM submissions s JOIN homework h ON s.homework_id=h.id
            WHERE s.student_id=%s AND s.marks IS NOT NULL
        """, (sid,), one=True)['a'] or 0,
        'game_stars': query_db("SELECT COALESCE(SUM(stars),0) as s FROM game_scores WHERE student_id=%s", (sid,), one=True)['s'],
    }
    recent_grades = query_db("""
        SELECT h.title, s.marks, h.max_marks, s.grade, s.feedback, s.graded_at
        FROM submissions s JOIN homework h ON s.homework_id=h.id
        WHERE s.student_id=%s AND s.marks IS NOT NULL
        ORDER BY s.graded_at DESC LIMIT 4
    """, (sid,))
    pending_hw = query_db("""
        SELECT h.*, u.name as teacher_name
        FROM homework h JOIN users u ON h.teacher_id=u.id
        WHERE (h.class_level=%s OR h.class_level='all')
        AND u.school_id=%s
        AND h.id NOT IN (SELECT homework_id FROM submissions WHERE student_id=%s)
        AND h.due_date >= CURDATE()
        ORDER BY h.due_date ASC LIMIT 3
    """, (cl, school_id, sid))
    announcements = query_db("""
        SELECT a.* FROM announcements a JOIN users u ON a.author_id=u.id 
        WHERE a.target_role IN ('all','student') 
        AND (a.target_class='all' OR a.target_class=%s)
        AND (u.school_id=%s OR u.role='super_admin')
        ORDER BY a.created_at DESC LIMIT 3
    """, (cl, school_id))
    return render_template('student/dashboard.html', stats=stats, recent_grades=recent_grades,
                           pending_hw=pending_hw, announcements=announcements)

@app.route('/student/homework')
@role_required('student')
def student_homework():
    sid  = session['user_id']
    user = current_user()
    tab  = request.args.get('tab', 'pending')
    school_id = session.get('school_id')
    cl = user['class_level']
    
    pending = query_db("""
        SELECT h.*, u.name as teacher_name
        FROM homework h JOIN users u ON h.teacher_id=u.id
        WHERE (h.class_level=%s OR h.class_level='all')
        AND u.school_id=%s
        AND h.id NOT IN (SELECT homework_id FROM submissions WHERE student_id=%s)
        ORDER BY h.due_date ASC
    """, (cl, school_id, sid))
    submitted = query_db("""
        SELECT h.*, u.name as teacher_name, s.submitted_at, s.marks, s.grade, s.feedback, s.file_path as sub_file, s.id as sub_id
        FROM submissions s JOIN homework h ON s.homework_id=h.id JOIN users u ON h.teacher_id=u.id
        WHERE s.student_id=%s ORDER BY s.submitted_at DESC
    """, (sid,))
    return render_template(
        'student/homework.html',
        pending=pending,
        submitted=submitted,
        tab=tab,
        now=datetime.date.today()
    )

@app.route('/student/homework/<int:hw_id>/submit', methods=['GET', 'POST'])
@role_required('student')
def submit_homework(hw_id):
    sid = session['user_id']
    user = current_user()
    hw  = query_db("SELECT h.*, u.name as teacher_name FROM homework h JOIN users u ON h.teacher_id=u.id WHERE h.id=%s AND u.school_id=%s AND (h.class_level=%s OR h.class_level='all')", (hw_id, session.get('school_id'), user.get('class_level')), one=True)
    if not hw:
        flash('Homework not found!', 'danger')
        return redirect(url_for('student_homework'))
    already = query_db("SELECT id FROM submissions WHERE homework_id=%s AND student_id=%s", (hw_id, sid), one=True)
    if already:
        flash('Already submitted!', 'info')
        return redirect(url_for('student_homework'))
    if request.method == 'POST':
        remarks   = request.form.get('remarks', '')
        file_path = None
        if 'file' in request.files:
            f = request.files['file']
            if f and f.filename and allowed_file(f.filename):
                try:
                    file_path = save_upload(f, 'submission')
                except (UploadValidationError, UploadQuotaExceeded, StorageProviderUnavailable) as exc:
                    flash(str(exc), 'danger')
                    return redirect(url_for('submit_homework', hw_id=hw_id))
        query_db(
            "INSERT INTO submissions (homework_id,student_id,file_path,remarks) VALUES (%s,%s,%s,%s)",
            (hw_id, sid, file_path, remarks), commit=True
        )
        flash('Homework submitted successfully! Great job! Ã°Å¸Å’Å¸', 'success')
        return redirect(url_for('student_homework'))
    return render_template('student/submit_homework.html', hw=hw)

@app.route('/student/games')
@role_required('student')
def student_games():
    sid = session['user_id']
    user = current_user()
    scores = query_db("""
        SELECT game_name, MAX(score) as best_score, SUM(stars) as total_stars, COUNT(*) as plays,
               MAX(level) as max_level
        FROM game_scores WHERE student_id=%s GROUP BY game_name
    """, (sid,))
    total_stars = query_db("SELECT COALESCE(SUM(stars),0) as s FROM game_scores WHERE student_id=%s", (sid,), one=True)['s']
    
    # Get game progress (current levels)
    progress = query_db("SELECT * FROM game_progress WHERE student_id=%s", (sid,))
    progress_map = {p['game_name']: p for p in progress}
    
    return render_template('student/games.html', scores=scores, total_stars=total_stars,
                           class_level=user.get('class_level', 'nursery'), progress_map=progress_map)

@app.route('/student/game/score', methods=['POST'])
@role_required('student')
def save_game_score():
    data = request.get_json()
    game_name = data.get('game_name', '')
    score     = int(data.get('score', 0))
    stars     = int(data.get('stars', 0))
    level     = int(data.get('level', 1))
    student_id = session['user_id']
    
    # Save score
    query_db(
        "INSERT INTO game_scores (student_id, game_name, score, stars, level) VALUES (%s,%s,%s,%s,%s)",
        (student_id, game_name, score, stars, level), commit=True
    )
    
    # Update game progress
    query_db("""
        INSERT INTO game_progress (student_id, game_name, current_level, max_level_reached, total_stars)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
            current_level = GREATEST(current_level, VALUES(current_level)),
            max_level_reached = GREATEST(max_level_reached, VALUES(max_level_reached)),
            total_stars = total_stars + VALUES(total_stars)
    """, (student_id, game_name, level, level, stars), commit=True)
    
    return jsonify({'status': 'ok', 'level': level})

@app.route('/student/game/progress')
@role_required('student')
def get_game_progress():
    sid = session['user_id']
    progress = query_db("SELECT * FROM game_progress WHERE student_id=%s", (sid,))
    result = {}
    for p in progress:
        result[p['game_name']] = {
            'current_level': p['current_level'],
            'max_level_reached': p['max_level_reached'],
            'total_stars': p['total_stars']
        }
    return jsonify(result)

@app.route('/student/progress')
@role_required('student')
def student_progress():
    sid = session['user_id']
    grades = query_db("""
        SELECT h.title, h.homework_type, h.class_level, s.marks, h.max_marks,
               s.grade, s.feedback, s.graded_at
        FROM submissions s JOIN homework h ON s.homework_id=h.id
        WHERE s.student_id=%s AND s.marks IS NOT NULL
        ORDER BY s.graded_at DESC
    """, (sid,))
    weekly = query_db("""
        SELECT wp.*, u.name as teacher_name
        FROM weekly_progress wp JOIN users u ON wp.teacher_id=u.id
        WHERE wp.student_id=%s ORDER BY wp.year DESC, wp.week_number DESC LIMIT 12
    """, (sid,))
    overall_avg = query_db("""
        SELECT ROUND(AVG(s.marks/h.max_marks*100),1) as avg
        FROM submissions s JOIN homework h ON s.homework_id=h.id
        WHERE s.student_id=%s AND s.marks IS NOT NULL
    """, (sid,), one=True)['avg'] or 0
    game_stats = query_db("""
        SELECT game_name, MAX(score) as best, SUM(stars) as stars
        FROM game_scores WHERE student_id=%s GROUP BY game_name
    """, (sid,))
    return render_template('student/progress.html', grades=grades, weekly=weekly,
                           overall_avg=overall_avg, game_stats=game_stats)

# Ã¢â€â‚¬Ã¢â€â‚¬ Smart Study Route Ã¢â€â‚¬Ã¢â€â‚¬
@app.route('/student/smart-study')
@role_required('student')
def student_smart_study():
    sid = session['user_id']
    weekly = query_db("""
        SELECT wp.*, u.name as teacher_name
        FROM weekly_progress wp JOIN users u ON wp.teacher_id=u.id
        WHERE wp.student_id=%s ORDER BY wp.year DESC, wp.week_number DESC LIMIT 20
    """, (sid,))
    overall_avg = query_db("""
        SELECT ROUND(AVG(s.marks/h.max_marks*100),1) as avg
        FROM submissions s JOIN homework h ON s.homework_id=h.id
        WHERE s.student_id=%s AND s.marks IS NOT NULL
    """, (sid,), one=True)['avg'] or 0
    game_stats = query_db("""
        SELECT game_name, MAX(score) as best, SUM(stars) as stars
        FROM game_scores WHERE student_id=%s GROUP BY game_name
    """, (sid,))
    return render_template('student/smart_study.html', weekly=weekly,
                           overall_avg=overall_avg, game_stats=game_stats)

# Ã¢â€â‚¬Ã¢â€â‚¬ Student Fee Payment Ã¢â€â‚¬Ã¢â€â‚¬
@app.route('/student/fees')
@role_required('student')
def student_fees():
    user = current_user()
    sid = session.get('school_id')
    if not sid and user:
        sid = user.get('school_id')
        if sid:
            session['school_id'] = sid

    if not user or not sid:
        flash('Session error. Please login again.', 'danger')
        return redirect(url_for('login'))

    fees = query_db("""
        SELECT * FROM fee_structures
        WHERE school_id=%s AND class_level=%s AND is_active=1
        ORDER BY CASE fee_type WHEN 'full' THEN 1 WHEN 'half' THEN 2 WHEN 'quarterly' THEN 3 ELSE 4 END
    """, (sid, user['class_level']))
    all_fees = query_db("""
        SELECT * FROM fee_structures WHERE school_id=%s AND is_active=1
        ORDER BY class_level, CASE fee_type WHEN 'full' THEN 1 WHEN 'half' THEN 2 WHEN 'quarterly' THEN 3 ELSE 4 END
    """, (sid,))
    
    # Get payment history
    my_payments = query_db("""
        SELECT * FROM student_fee_payments WHERE student_id=%s AND payment_domain=%s ORDER BY payment_date DESC
    """, (user['id'], SCHOOL_FEE_DOMAIN))
    school_payment_config = query_db(
        "SELECT provider, upi_id, display_name, is_active FROM school_payment_config WHERE school_id=%s",
        (sid,), one=True, use_control=True,
    )
    
    return render_template('student/fees.html', fees=fees, all_fees=all_fees, user=user,
                           my_payments=my_payments, school_payment_config=school_payment_config)

@app.route('/student/fees/pay', methods=['POST'])
@role_required('student')
def student_pay_fee():
    user = current_user()
    sid = session.get('school_id')
    
    payment_mode = request.form.get('payment_mode', 'monthly')
    month_label = request.form.get('month_label', '')
    payment_method = request.form.get('payment_method', 'cash')
    fee_structure_id = request.form.get('fee_structure_id')
    notes = request.form.get('notes', '')

    try:
        payment_mode, payment_method = validate_payment_options(payment_mode, payment_method)
        fee_id = int(fee_structure_id) if fee_structure_id else 0
        fee = query_db("SELECT id,total_amount FROM fee_structures WHERE id=%s AND school_id=%s AND is_active=1",
                       (fee_id, sid), one=True)
        if not fee:
            raise PaymentValidationError('Select an active fee structure for this school.')
        paid = query_db(
            "SELECT COALESCE(SUM(amount_paid),0) AS paid FROM student_fee_payments "
            "WHERE student_id=%s AND school_id=%s AND fee_structure_id=%s AND payment_domain=%s "
            "AND status IN ('pending','paid')",
            (user['id'], sid, fee_id, SCHOOL_FEE_DOMAIN), one=True,
        )
        remaining = max(Decimal(str(fee['total_amount'])) - Decimal(str(paid['paid'] or 0)), Decimal('0.00'))
        amount = validate_school_fee_amount(request.form.get('amount', 0), remaining)
        _, payment_method = validate_payment_options(payment_mode, payment_method)
        if payment_method == 'upi':
            config = query_db("SELECT is_active, provider FROM school_payment_config WHERE school_id=%s",
                              (sid,), one=True, use_control=True)
            if not config or not config['is_active'] or config['provider'] != 'manual_upi':
                raise PaymentValidationError('School UPI payment configuration is unavailable.')
    except (PaymentValidationError, ValueError, TypeError):
        flash('Invalid fee payment, fee plan, or remaining amount.', 'danger')
        return redirect(url_for('student_fees'))
    
    # Handle receipt upload
    receipt_file = None
    if 'receipt_file' in request.files:
        f = request.files['receipt_file']
        if f and f.filename and allowed_file(f.filename):
            try:
                receipt_file = save_upload(f, 'fee-receipt')
            except (UploadValidationError, UploadQuotaExceeded, StorageProviderUnavailable) as exc:
                flash(str(exc), 'danger')
                return redirect(url_for('student_fees'))
    
    # Generate receipt number
    receipt_no = f"FEE-{sid}-{secrets.token_hex(8).upper()}"
    
    query_db("""
        INSERT INTO student_fee_payments 
        (student_id, school_id, fee_structure_id, payment_mode, amount_paid, month_label,
         payment_method, receipt_no, receipt_file, payment_domain, status, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s)
    """, (user['id'], sid, fee_id or None, payment_mode, amount, month_label,
          payment_method, receipt_no, receipt_file, SCHOOL_FEE_DOMAIN, notes), commit=True)
    
    flash(f'Payment of Ã¢â€šÂ¹{amount} submitted! Receipt: {receipt_no}. Awaiting verification. Ã°Å¸â€™Â°', 'success')
    return redirect(url_for('student_fees'))

# Private file serving. Legacy/static upload paths are never served here.
@app.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    if not file_is_authorized(filename):
        abort(404)
    try:
        contents, mime_type = read_private_upload(filename)
    except (FileNotFoundError, UploadValidationError, StorageProviderUnavailable):
        abort(404)
    return send_file(
        BytesIO(contents),
        mimetype=mime_type,
        download_name=filename.rsplit('/', 1)[-1],
    )

if not Config.IS_PRODUCTION:
    @app.route('/test')
    def test():
        return "<h2 style='font-family:sans-serif;color:green'>Ã¢Å“â€¦ Flask is working! MySQL Connected!</h2>"


# Static informational pages
@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/privacy')
def privacy():
    return render_template('privacy.html')


@app.route('/terms')
def terms():
    return render_template('terms.html')


@app.route('/case-studies')
def case_studies():
    return render_template('case_studies.html')


@app.route('/platform-docs')
def platform_docs():
    return render_template('platform_docs.html')


@app.route('/integration-apis')
def integration_apis():
    return render_template('integration_apis.html')

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# DB Init route (MySQL version)
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
## Database initialization is intentionally not exposed through Flask.


# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
#  ATTENDANCE ROUTES
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
@app.route('/teacher/attendance', methods=['GET', 'POST'])
@role_required('teacher')
def teacher_attendance():
    today = datetime.date.today().strftime('%Y-%m-%d')
    selected_date = request.args.get('date', today)
    class_level   = request.args.get('class', 'nursery')
    
    if request.method == 'POST':
        teacher_id = session['user_id']
        mark_date  = request.form.get('mark_date', today)
        post_class = request.form.get('class_level', class_level)
        
        for key in request.form.keys():
            if key.startswith('status_'):
                sid = int(key.replace('status_', ''))
                status = request.form[key]
                remark = request.form.get(f'remark_{sid}', '')
                student = query_db(
                    "SELECT id FROM users WHERE id=%s AND role='student' AND class_level=%s AND school_id=%s",
                    (sid, post_class, session.get('school_id')),
                    one=True,
                )
                if not student:
                    continue
                
                # MySQL: INSERT ... ON DUPLICATE KEY UPDATE
                query_db("""
                    INSERT INTO attendance (student_id, teacher_id, date, status, remark)
                    VALUES (%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE 
                    status=VALUES(status), remark=VALUES(remark), teacher_id=VALUES(teacher_id)
                """, (sid, teacher_id, mark_date, status, remark), commit=True)
        
        flash('Daily attendance saved successfully!', 'success')
        return redirect(url_for('teacher_attendance', date=mark_date, **{'class': post_class}))

    students = query_db("SELECT * FROM users WHERE role='student' AND class_level=%s AND school_id=%s ORDER BY name", (class_level, session.get('school_id')))
    records  = query_db(
        "SELECT a.* FROM attendance a JOIN users u ON a.student_id=u.id "
        "WHERE a.date=%s AND a.teacher_id=%s AND u.school_id=%s",
        (selected_date, session['user_id'], session.get('school_id')),
    )
    rec_map  = {r['student_id']: r for r in records}
    
    return render_template('teacher/attendance.html', 
                           students=students, rec_map=rec_map, 
                           selected_date=selected_date, class_level=class_level)

@app.route('/student/attendance')
@role_required('student')
def student_attendance():
    sid = session['user_id']
    records = query_db("SELECT a.*, u.name as teacher_name FROM attendance a JOIN users u ON a.teacher_id=u.id WHERE a.student_id=%s ORDER BY a.date DESC LIMIT 30", (sid,))
    
    total = len(records)
    present = sum(1 for r in records if r['status'] == 'present')
    late = sum(1 for r in records if r['status'] == 'late')
    
    stats = {
        'total': total,
        'present': present,
        'late': late,
        'absent': total - present - late,
        'pct': round(((present + 0.5 * late) / total * 100), 1) if total > 0 else 0
    }
    return render_template('student/attendance.html', records=records, stats=stats)

@app.route('/teacher/my-attendance')
@role_required('teacher')
def my_attendance_view():
    records = query_db(
        "SELECT a.*, u.name as student_name FROM attendance a JOIN users u ON a.student_id=u.id "
        "WHERE a.teacher_id=%s AND u.school_id=%s ORDER BY a.date DESC LIMIT 30",
        (session['user_id'], session.get('school_id')),
    )
    total = len(records)
    present = sum(1 for r in records if r['status'] == 'present')
    late = sum(1 for r in records if r['status'] == 'late')
    stats = {
        'total': total, 'present': present, 'late': late, 'absent': total - present - late,
        'pct': round(((present + 0.5 * late) / total * 100), 1) if total > 0 else 0
    }
    return render_template('student/attendance.html', records=records, stats=stats)

@app.route('/admin/attendance', methods=['GET', 'POST'])
@role_required('admin')
def admin_student_attendance():
    today = datetime.date.today().strftime('%Y-%m-%d')
    selected_date = request.args.get('date', today)
    
    if request.method == 'POST':
        admin_id  = session['user_id']
        mark_date = request.form.get('mark_date', today)
        
        for key in request.form.keys():
            if key.startswith('status_'):
                student_id = int(key.replace('status_', ''))
                status = request.form[key]
                remark = request.form.get(f'remark_{student_id}', '')
                if status not in {'present', 'absent', 'late'}:
                    continue
                student = query_db(
                    "SELECT id FROM users WHERE id=%s AND role='student' AND school_id=%s",
                    (student_id, session.get('school_id')),
                    one=True,
                )
                if not student:
                    continue
                
                query_db("""
                    INSERT INTO attendance (student_id, teacher_id, date, status, remark)
                    VALUES (%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE 
                    status=VALUES(status), remark=VALUES(remark), teacher_id=VALUES(teacher_id)
                """, (student_id, admin_id, mark_date, status, remark), commit=True)
        
        flash('Student attendance recorded successfully!', 'success')
        return redirect(url_for('admin_student_attendance', date=mark_date))

    students = query_db("SELECT * FROM users WHERE role='student' AND school_id=%s ORDER BY name", (session.get('school_id'),))
    records  = query_db(
        "SELECT a.* FROM attendance a JOIN users u ON a.student_id=u.id "
        "WHERE a.date=%s AND u.school_id=%s",
        (selected_date, session.get('school_id')),
    )
    rec_map  = {r['student_id']: r for r in records}
    
    return render_template('admin/teacher_attendance.html', 
                           students=students, rec_map=rec_map,
                           selected_date=selected_date)

# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
#  SUPER ADMIN ROUTES
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
@app.route('/super-admin/dashboard')
@role_required('super_admin')
def super_admin_dashboard():
    stats = {
        'total_schools': query_db("SELECT COUNT(*) as c FROM schools", one=True, use_control=True)['c'],
        'total_students': query_db("SELECT COUNT(*) as c FROM users WHERE role='student'", one=True)['c'],
        'total_teachers': query_db("SELECT COUNT(*) as c FROM users WHERE role='teacher'", one=True)['c'],
        'total_admins': query_db("SELECT COUNT(*) as c FROM users WHERE role='admin'", one=True)['c'],
    }
    recent_schools = query_db("SELECT * FROM schools ORDER BY created_at DESC LIMIT 5", use_control=True)
    
    return render_template('super_admin/dashboard.html', stats=stats, recent_schools=recent_schools)

@app.route('/super-admin/schools')
@role_required('super_admin')
def super_admin_schools():
    schools = query_db(
        """
        SELECT s.*,
               (SELECT COUNT(*) FROM users
                WHERE school_id=s.id AND role='student') AS student_count,
               (SELECT COUNT(*) FROM users
                WHERE school_id=s.id AND role='teacher') AS teacher_count,
               (SELECT name FROM users
                WHERE school_id=s.id AND role='admin' LIMIT 1) AS admin_name
        FROM schools s
        ORDER BY s.created_at DESC
        """,
        use_control=True,
    )
    return render_template('super_admin/schools.html', schools=schools)

@app.route('/super-admin/provision', methods=['GET'])
@role_required('super_admin')
def super_admin_provision():
    return render_template('super_admin/provision_tenant.html', result=None)


@app.route('/super-admin/provision/start', methods=['POST'])
@role_required('super_admin')
def super_admin_provision_start():
    from flask import request, jsonify
    from scripts.provision_tasks import provision_task
    from scripts.provision_jobs import create_job
    from tenant_services.job_context import make_tenant_job_ref

    name = request.form.get('name')
    subdomain = request.form.get('subdomain')
    address = request.form.get('address', '')
    # Provider selection is process configuration, never a browser option.
    use_aws = os.environ.get('TENANT_CREDENTIAL_PROVIDER', '').strip().lower() == 'aws'

    job_id = create_job({'name': name, 'subdomain': subdomain, 'tenant_ref': make_tenant_job_ref(subdomain, 'pending')})
    # Enqueue Celery task
    provision_task.apply_async(args=(job_id, name, subdomain, address, use_aws, make_tenant_job_ref(subdomain, job_id)))

    return jsonify({'job_id': job_id}), 202


@app.route('/super-admin/provision/status/<job_id>', methods=['GET'])
@role_required('super_admin')
def super_admin_provision_status(job_id):
    from flask import jsonify
    from scripts.provision_jobs import get_job
    job = get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)


@app.route('/super-admin/provision/jobs', methods=['GET'])
@role_required('super_admin')
def super_admin_provision_jobs():
    from scripts.provision_jobs import _read_jobs
    jobs = _read_jobs()
    return render_template('super_admin/provision_jobs.html', jobs=jobs)


@app.route('/super-admin/provision/retry/<job_id>', methods=['POST'])
@role_required('super_admin')
def super_admin_provision_retry(job_id):
    from flask import redirect, url_for, flash
    from scripts.provision_jobs import get_job, create_job
    from scripts.provision_tasks import provision_task
    from tenant_services.job_context import make_tenant_job_ref

    job = get_job(job_id)
    if not job:
        flash('Job not found', 'danger')
        return redirect(url_for('super_admin_provision_jobs'))
    if job.get('status') not in ('failed', 'error'):
        flash('Only failed provisioning jobs can be retried', 'warning')
        return redirect(url_for('super_admin_provision_jobs'))
    data = job.get('input') or {}
    # attempt to extract name/subdomain
    name = data.get('name') if isinstance(data, dict) else None
    subdomain = data.get('subdomain') if isinstance(data, dict) else None
    if not name or not subdomain:
        # fallback: read from job metadata if present
        meta = job.get('result') or {}
        name = meta.get('name') or 'restored'
        subdomain = meta.get('subdomain') or 'retry'
    new_job = create_job({'name': name, 'subdomain': subdomain, 'tenant_ref': make_tenant_job_ref(subdomain, 'pending')})
    provision_task.apply_async(args=(new_job, name, subdomain, '', False, make_tenant_job_ref(subdomain, new_job)))
    flash('Retry enqueued', 'success')
    return redirect(url_for('super_admin_provision_jobs'))

@app.route('/super-admin/admins/create', methods=['GET', 'POST'])
@role_required('super_admin')
def super_admin_create_admin():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        passw = request.form.get('password', '')
        school_id = request.form.get('school_id')

        school = provisioned_school_for_assignment(school_id)
        if not school:
            flash('Select an active, provisioned tenant school.', 'danger')
            return redirect(url_for('super_admin_create_admin'))

        if not passw:
            flash('Admin password is required.', 'danger')
            return redirect(url_for('super_admin_create_admin'))

        pw_hash = generate_password_hash(passw)
        try:
            query_db(
                "INSERT INTO users "
                "(name, email, phone, password_hash, role, school_id) "
                "VALUES (%s,%s,%s,%s,'admin',%s)",
                (name, email, phone, pw_hash, school['id']),
                commit=True,
                use_control=True,
            )
            flash('Admin created successfully for the school!', 'success')
        except Exception as e:
            flash(f'Error creating admin: {e}', 'danger')

        return redirect(url_for('super_admin_dashboard'))

    schools = query_db(
        "SELECT * FROM schools "
        "WHERE subdomain IS NOT NULL AND subdomain<>'' "
        "AND subscription_status='active' "
        "ORDER BY created_at DESC",
        use_control=True,
    )
    return render_template('super_admin/create_admin.html', schools=schools)

@app.route('/super-admin/admins')
@role_required('super_admin')
def super_admin_admins():
    admins = query_db("""
        SELECT u.*, s.name as school_name 
        FROM users u LEFT JOIN schools s ON u.school_id=s.id 
        WHERE u.role='admin'
        ORDER BY u.created_at DESC
    """, use_control=True)
    return render_template('super_admin/admins.html', admins=admins)

@app.route('/super-admin/admins/edit/<int:admin_id>', methods=['GET', 'POST'])
@role_required('super_admin')
def super_admin_edit_admin(admin_id):
    admin = query_db(
        "SELECT * FROM users WHERE id=%s AND role='admin'",
        (admin_id,),
        one=True,
        use_control=True,
    )
    if not admin:
        flash('Admin not found!', 'danger')
        return redirect(url_for('super_admin_admins'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        passw = request.form.get('password', '').strip()
        school_id = request.form.get('school_id')

        school = provisioned_school_for_assignment(school_id)
        if not school:
            flash('Select an active, provisioned tenant school.', 'danger')
            return redirect(
                url_for('super_admin_edit_admin', admin_id=admin_id)
            )

        if passw:
            pw_hash = generate_password_hash(passw)
            query_db(
                "UPDATE users SET name=%s, email=%s, phone=%s, "
                "password_hash=%s, school_id=%s WHERE id=%s",
                (name, email, phone, pw_hash, school['id'], admin_id),
                commit=True,
                use_control=True,
            )
        else:
            query_db(
                "UPDATE users SET name=%s, email=%s, phone=%s, school_id=%s "
                "WHERE id=%s",
                (name, email, phone, school['id'], admin_id),
                commit=True,
                use_control=True,
            )

        flash('School Admin profile updated successfully!', 'success')
        return redirect(url_for('super_admin_admins'))

    schools = query_db(
        "SELECT * FROM schools "
        "WHERE subdomain IS NOT NULL AND subdomain<>'' "
        "AND subscription_status='active' "
        "ORDER BY created_at DESC",
        use_control=True,
    )
    return render_template(
        'super_admin/edit_admin.html',
        admin=admin,
        schools=schools,
    )

@app.route('/super-admin/admins/delete/<int:admin_id>', methods=['POST'])
@role_required('super_admin')
def super_admin_delete_admin(admin_id):
    query_db("DELETE FROM users WHERE id=%s AND role='admin'", (admin_id,), commit=True, use_control=True)
    flash("School Admin removed successfully.", "success")
    return redirect(url_for('super_admin_admins'))


@app.route('/super-admin/payments')
@role_required('super_admin')
def super_admin_payments():
    payments = query_db("""
        SELECT p.*, s.name as school_name
        FROM platform_subscription_payments p JOIN schools s ON p.school_id=s.id
        ORDER BY p.created_at DESC
    """, use_control=True)
    return render_template('super_admin/payments.html', payments=payments)

@app.route('/super-admin/payments/approve/<int:pid>', methods=['POST'])
@role_required('super_admin')
def super_admin_approve_payment(pid):
    pay = query_db("SELECT * FROM platform_subscription_payments WHERE id=%s", (pid,), one=True, use_control=True)
    if not pay:
        flash("Payment request not found.", "danger")
        return redirect(url_for('super_admin_payments'))
    
    if pay['status'] == 'paid':
        flash("Payment already approved earlier.", "warning")
        return redirect(url_for('super_admin_payments'))
    try:
        _, settled = _activate_platform_subscription(pid, pay['school_id'])
        flash(f"Payment approved! School extended to {settled.get('new_expiry')} Ã°Å¸â€™Â¸Ã¢Å“â€¦", "success")
    except PaymentValidationError:
        flash("Platform payment could not be settled.", "danger")
    return redirect(url_for('super_admin_payments'))

# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
#  FEE STRUCTURE ROUTES
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

@app.route('/admin/fee-payment-config', methods=['GET', 'POST'])
@role_required('admin')
def admin_fee_payment_config():
    sid = session.get('school_id')
    if request.method == 'POST':
        provider = request.form.get('provider', 'manual_upi').strip().lower()
        upi_id = request.form.get('upi_id', '').strip()
        display_name = request.form.get('display_name', '').strip()[:160]
        active = 1 if request.form.get('is_active') == '1' else 0
        if provider != 'manual_upi' or active and not re.fullmatch(r'[A-Za-z0-9._-]{2,160}@[A-Za-z0-9._-]{2,80}', upi_id):
            flash('Only a valid school-owned manual UPI configuration can be enabled.', 'danger')
            return redirect(url_for('admin_fee_payment_config'))
        query_db(
            "INSERT INTO school_payment_config (school_id,provider,upi_id,display_name,is_active) "
            "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE provider=VALUES(provider), "
            "upi_id=VALUES(upi_id), display_name=VALUES(display_name), is_active=VALUES(is_active)",
            (sid, provider, upi_id or None, display_name or None, active), commit=True, use_control=True,
        )
        flash('School fee payment configuration saved.', 'success')
        return redirect(url_for('admin_fee_payment_config'))
    config = query_db("SELECT * FROM school_payment_config WHERE school_id=%s", (sid,), one=True, use_control=True)
    return render_template('admin/fee_payment_config.html', payment_config=config)


@app.route('/admin/fees', methods=['GET', 'POST'])
@role_required('admin')
def admin_fees():
    sid = session.get('school_id')
    if not sid:
        user = current_user()
        if user:
            sid = user.get('school_id')
            session['school_id'] = sid

    def safe_float(val):
        try:
            return float(val) if val and str(val).strip() else 0.0
        except (ValueError, TypeError):
            return 0.0

    if request.method == 'POST':
        class_level   = request.form.get('class_level', '').strip()
        fee_type      = request.form.get('fee_type', '').strip()
        label         = request.form.get('label', '').strip()
        total_amount  = safe_float(request.form.get('total_amount'))
        admission_fee = safe_float(request.form.get('admission_fee'))
        tuition_fee   = safe_float(request.form.get('tuition_fee'))
        activity_fee  = safe_float(request.form.get('activity_fee'))
        transport_fee = safe_float(request.form.get('transport_fee'))
        misc_fee      = safe_float(request.form.get('misc_fee'))
        due_date      = request.form.get('due_date', '').strip()
        description   = request.form.get('description', '').strip()

        if not class_level or not fee_type or not label or total_amount <= 0:
            flash('Class level, Fee type, Label aur Total amount required hain!', 'danger')
            return redirect(url_for('admin_fees'))

        if not sid:
            flash('School ID not found. Please logout and login again.', 'danger')
            return redirect(url_for('admin_fees'))

        try:
            query_db("""
                INSERT INTO fee_structures (school_id, class_level, fee_type, label, total_amount,
                    admission_fee, tuition_fee, activity_fee, transport_fee, misc_fee, due_date, description)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    label=VALUES(label), total_amount=VALUES(total_amount),
                    admission_fee=VALUES(admission_fee), tuition_fee=VALUES(tuition_fee),
                    activity_fee=VALUES(activity_fee), transport_fee=VALUES(transport_fee),
                    misc_fee=VALUES(misc_fee), due_date=VALUES(due_date), description=VALUES(description)
            """, (sid, class_level, fee_type, label, total_amount,
                  admission_fee, tuition_fee, activity_fee, transport_fee, misc_fee,
                  due_date, description), commit=True)
            flash('Fee structure saved successfully!', 'success')
        except Exception as e:
            flash(f'Error saving fee: {e}', 'danger')
        return redirect(url_for('admin_fees'))

    fees = query_db("SELECT * FROM fee_structures WHERE school_id=%s ORDER BY class_level, fee_type", (sid,)) if sid else []
    return render_template('admin/fees.html', fees=fees)


@app.route('/admin/fees/delete/<int:fid>', methods=['POST'])
@role_required('admin')
def delete_fee(fid):
    sid = session.get('school_id')
    query_db("DELETE FROM fee_structures WHERE id=%s AND school_id=%s", (fid, sid), commit=True)
    flash('Fee entry deleted!', 'success')
    return redirect(url_for('admin_fees'))


if __name__ == '__main__':
    # Disable the reloader to avoid duplicate startup logs and duplicate DB connection attempts.
    app.run(debug=not app.config['IS_PRODUCTION'], use_reloader=False, host='0.0.0.0', port=5000)
