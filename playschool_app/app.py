from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify, send_from_directory, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import mysql.connector
from mysql.connector import pooling, Error
from functools import wraps
import os, datetime, random, smtplib, secrets, hmac
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Load environment variables from .env file before importing Config
load_dotenv()

from config import Config
from mysql_setup import create_database, create_tables, seed_data
from tenant_services.middleware.tenant_resolver import resolve_tenant

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config.from_object(Config)

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
    print("Ã¢ÂÅ’ MYSQL_PASSWORD is not set. Set it in .env or as an environment variable before starting the app.")
    print("   Example (PowerShell): $env:MYSQL_PASSWORD = 'your_password' ; python app.py")
    raise SystemExit(1)

try:
    connection_pool = pooling.MySQLConnectionPool(
        pool_name="playschool_pool",
        pool_size=5,
        pool_reset_session=True,
        **db_config
    )
    print("Ã¢Å“â€¦ MySQL Connection Pool created successfully!")
except Error as e:
    print(f"Ã¢Å¡Â Ã¯Â¸Â MySQL Pool Error: {e}")
    err_str = str(e).lower()
    # If the database is missing, try to create it and the tables, then retry
    if 'unknown database' in err_str or 'doesn\'t exist' in err_str or ('database' in err_str and 'unknown' in err_str):
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
            conn = get_connection_for_tenant(g.tenant['subdomain'])
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
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
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
    if 'user_id' in session:
        return query_db("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    return None


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
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https:; style-src 'self' 'unsafe-inline' https:; img-src 'self' data: https:;"
    return response

def current_school():
    sid = session.get('school_id')
    if sid:
        return query_db("SELECT * FROM schools WHERE id=%s", (sid,), one=True, use_control=True)
    return None

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
    if not app.config['CSRF_ENABLED'] or request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return None
    expected = session.get('_csrf_token')
    supplied = request.form.get('_csrf_token') or request.headers.get('X-CSRF-Token')
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        return ('Invalid or missing CSRF token.', 400)

# Subscription Middleware
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
@app.before_request
def resolve_tenant_middleware():
    """Resolve tenant from the request host (subdomain) and set `g.tenant` and session school_id."""
    host = request.host.split(':')[0] if request.host else None
    sch = resolve_tenant(query_db, host)
    if sch:
        g.tenant = sch
        # prefer explicit session school if already set for authenticated user
        if session.get('role') != 'super_admin':
            session_school = session.get('school_id')
            if session_school != sch['id']:
                session['school_id'] = sch['id']
    else:
        g.tenant = None

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
            if sch['subscription_status'] == 'inactive' or (vu and vu < today):
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
        user = query_db("SELECT * FROM users WHERE email=%s AND is_active=1", (email,), one=True)
        if user and check_password_hash(user['password_hash'], password):
            otp = str(random.randint(100000, 999999))
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
                'school_id': user['school_id']
            }
            flash(f"OTP sent to {email}. Check your inbox.", 'success')
            return redirect(url_for('verify_otp'))
        flash('Invalid email or password!', 'danger')
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
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

        role        = request.form['role']
        school_id   = request.form.get('school_id')
        class_level = request.form.get('class_level', None) if role == 'student' else None
        parent_name = request.form.get('parent_name', '').strip()
        parent_phone= request.form.get('parent_phone', '').strip()

        # Only super_admin can theoretically register another admin
        if role == 'admin' and not (session.get('role') == 'super_admin'):
             flash('Permission denied to register as Administrator directly.', 'danger')
             return redirect(url_for('register'))
        
        # Non-super admins must have a school_id
        if not school_id and role != 'super_admin':
            flash('Must select a valid School!', 'danger')
            return redirect(url_for('register'))

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
        otp = str(random.randint(100000, 999999))
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
        
        if entered_otp == session['otp_val']:
            # SUCCESS
            flow = session.get('otp_flow')
            meta = session.get('otp_meta')
            
            if flow == 'login':
                session['user_id'] = meta['user_id']
                session['role']    = meta['role']
                session['name']    = meta['name']
                session['school_id'] = meta.get('school_id')
                session.pop('otp_val', None)
                session.pop('otp_flow', None)
                session.pop('otp_meta', None)
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
            flash('No account found with this email!', 'danger')
            return redirect(url_for('forgot_password'))

        otp = str(random.randint(100000, 999999))
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
                fname = secure_filename(f.filename)
                fname = f"avatar_{session['user_id']}_{int(datetime.datetime.now().timestamp())}_{fname}"
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                profile_pic_name = fname

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
    payments = query_db("SELECT * FROM payments WHERE school_id=%s ORDER BY payment_date DESC", (sid,))
    
    if request.method == 'POST':
        try:
            amount = float(request.form.get('amount', 0))
            notes  = request.form.get('notes', '')
            screenshot_name = None
            
            # Handle file upload
            if 'screenshot' in request.files:
                f = request.files['screenshot']
                if f and f.filename and allowed_file(f.filename):
                    fname = secure_filename(f.filename)
                    fname = f"receipt_{sid}_{int(datetime.datetime.now().timestamp())}_{fname}"
                    f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                    screenshot_name = fname
            
            query_db("INSERT INTO payments (school_id, amount, notes, status, screenshot) VALUES (%s,%s,%s,'pending',%s)", 
                     (sid, amount, notes, screenshot_name), commit=True)
            flash("Transaction submitted! Please wait while Super Admin verifies payment. Ã¢Å“â€¦", "success")
        except ValueError:
            flash("Invalid amount entered.", "danger")
        return redirect(url_for('admin_billing'))
        
    return render_template('billing/admin_billing.html', school=school, payments=payments)

# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
#  ADMIN (PRINCIPAL) ROUTES
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
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
        query_db("DELETE FROM users WHERE id=%s", (uid,), commit=True)
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
        WHERE sfp.school_id=%s
    """
    args = [sid]
    
    if class_filter != 'all':
        sql += " AND u.class_level=%s"
        args.append(class_filter)
    if status_filter != 'all':
        sql += " AND sfp.status=%s"
        args.append(status_filter)
    
    sql += " ORDER BY sfp.payment_date DESC"
    payments = query_db(sql, tuple(args))
    
    stats = {
        'total_collected': query_db("SELECT COALESCE(SUM(amount_paid),0) as c FROM student_fee_payments WHERE school_id=%s AND status='paid'", (sid,), one=True)['c'],
        'pending_amount': query_db("SELECT COALESCE(SUM(amount_paid),0) as c FROM student_fee_payments WHERE school_id=%s AND status='pending'", (sid,), one=True)['c'],
        'overdue_count': query_db("SELECT COUNT(*) as c FROM student_fee_payments WHERE school_id=%s AND status='overdue'", (sid,), one=True)['c'],
        'month_collection': query_db("SELECT COALESCE(SUM(amount_paid),0) as c FROM student_fee_payments WHERE school_id=%s AND status='paid' AND MONTH(payment_date)=MONTH(NOW()) AND YEAR(payment_date)=YEAR(NOW())", (sid,), one=True)['c'],
    }
    
    return render_template('admin/fee_payments.html', payments=payments, stats=stats, 
                           class_filter=class_filter, status_filter=status_filter)

@app.route('/admin/fee-payments/verify/<int:payment_id>', methods=['POST'])
@role_required('admin')
def verify_fee_payment(payment_id):
    sid = session.get('school_id')
    query_db("UPDATE student_fee_payments SET status='paid', verified_by=%s WHERE id=%s AND school_id=%s", 
             (session['user_id'], payment_id, sid), commit=True)
    flash('Payment verified successfully! Ã¢Å“â€¦', 'success')
    return redirect(url_for('admin_fee_payments'))

@app.route('/admin/fee-payments/reject/<int:payment_id>', methods=['POST'])
@role_required('admin')
def reject_fee_payment(payment_id):
    sid = session.get('school_id')
    query_db("UPDATE student_fee_payments SET status='overdue' WHERE id=%s AND school_id=%s", 
             (payment_id, sid), commit=True)
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
                fname = secure_filename(f.filename)
                fname = f"hw_{session['user_id']}_{int(datetime.datetime.now().timestamp())}_{fname}"
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                file_path = fname
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
    hw = query_db("SELECT * FROM homework WHERE id=%s", (hw_id,), one=True)
    if not hw or hw['teacher_id'] != session['user_id']:
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
    sub = query_db("SELECT s.*, h.max_marks FROM submissions s JOIN homework h ON s.homework_id=h.id WHERE s.id=%s", (sub_id,), one=True)
    if sub:
        grade = letter_grade(marks, sub['max_marks'])
        query_db(
            "UPDATE submissions SET marks=%s, grade=%s, feedback=%s, graded_at=NOW() WHERE id=%s",
            (marks, grade, feedback, sub_id), commit=True
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
    hw  = query_db("SELECT h.*, u.name as teacher_name FROM homework h JOIN users u ON h.teacher_id=u.id WHERE h.id=%s", (hw_id,), one=True)
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
                fname = secure_filename(f.filename)
                fname = f"sub_{sid}_{hw_id}_{int(datetime.datetime.now().timestamp())}_{fname}"
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                file_path = fname
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
        SELECT * FROM student_fee_payments WHERE student_id=%s ORDER BY payment_date DESC
    """, (user['id'],))
    
    return render_template('student/fees.html', fees=fees, all_fees=all_fees, user=user, my_payments=my_payments)

@app.route('/student/fees/pay', methods=['POST'])
@role_required('student')
def student_pay_fee():
    user = current_user()
    sid = session.get('school_id')
    
    payment_mode = request.form.get('payment_mode', 'monthly')
    amount = float(request.form.get('amount', 0))
    month_label = request.form.get('month_label', '')
    payment_method = request.form.get('payment_method', 'cash')
    fee_structure_id = request.form.get('fee_structure_id')
    notes = request.form.get('notes', '')
    
    # Handle receipt upload
    receipt_file = None
    if 'receipt_file' in request.files:
        f = request.files['receipt_file']
        if f and f.filename and allowed_file(f.filename):
            fname = secure_filename(f.filename)
            fname = f"fee_receipt_{user['id']}_{int(datetime.datetime.now().timestamp())}_{fname}"
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
            receipt_file = fname
    
    # Generate receipt number
    receipt_no = f"RCP-{user['id']}-{int(datetime.datetime.now().timestamp())}"
    
    query_db("""
        INSERT INTO student_fee_payments 
        (student_id, school_id, fee_structure_id, payment_mode, amount_paid, month_label, 
         payment_method, receipt_no, receipt_file, status, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s)
    """, (user['id'], sid, fee_structure_id or None, payment_mode, amount, month_label,
          payment_method, receipt_no, receipt_file, notes), commit=True)
    
    flash(f'Payment of Ã¢â€šÂ¹{amount} submitted! Receipt: {receipt_no}. Awaiting verification. Ã°Å¸â€™Â°', 'success')
    return redirect(url_for('student_fees'))

# File serving
@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

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
@app.route('/init-db')
def init_db():
    try:
        # Just verify connection and seed defaults
        schools = query_db("SELECT COUNT(*) as c FROM schools", one=True, use_control=True)
        users_count = query_db("SELECT COUNT(*) as c FROM users", one=True)
        
        if schools['c'] == 0:
            query_db("INSERT INTO schools (name, address, subscription_status, valid_until) VALUES (%s,%s,'active', DATE_ADD(NOW(), INTERVAL 1 YEAR))",
                     ('Default School', 'Main Campus'), commit=True, use_control=True)
        
        if users_count['c'] == 0:
            pw_admin = generate_password_hash('admin123')
            pw_super = generate_password_hash('superadmin123')
            pw_teacher = generate_password_hash('teacher123')
            pw_nursery = generate_password_hash('nursery123')
            pw_lkg = generate_password_hash('lkg123')
            pw_ukg = generate_password_hash('ukg123')
            query_db("INSERT INTO users (name,email,phone,password_hash,role,school_id) VALUES (%s,%s,%s,%s,%s,NULL)",
                     ('Super Admin', 'superadmin@playschool.com', '0000000000', pw_super, 'super_admin'), commit=True)
            query_db("INSERT INTO users (name,email,phone,password_hash,role,school_id) VALUES (%s,%s,%s,%s,%s,%s)",
                     ('School Admin', 'admin@playschool.com', '9999999999', pw_admin, 'admin', 1), commit=True)
            query_db("INSERT INTO users (name,email,phone,password_hash,role,school_id,class_level) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                     ('Teacher Demo', 'teacher@playschool.com', '1111111111', pw_teacher, 'teacher', 1, None), commit=True)
            query_db("INSERT INTO users (name,email,phone,password_hash,role,school_id,class_level) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                     ('Nursery Class', 'nursery@playschool.com', '1111111112', pw_nursery, 'student', 1, 'nursery'), commit=True)
            query_db("INSERT INTO users (name,email,phone,password_hash,role,school_id,class_level) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                     ('LKG Class', 'lkg@playschool.com', '1111111113', pw_lkg, 'student', 1, 'lkg'), commit=True)
            query_db("INSERT INTO users (name,email,phone,password_hash,role,school_id,class_level) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                     ('UKG Class', 'ukg@playschool.com', '1111111114', pw_ukg, 'student', 1, 'ukg'), commit=True)

        return '<h2 style="font-family:sans-serif;color:green">Ã¢Å“â€¦ MySQL Database verified! <a href="/login">Login now</a></h2>'
    except Exception as e:
        return f'<h2 style="color:red">Ã¢ÂÅ’ Error: {e}<br><br>Run: python mysql_setup.py first!</h2>'


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
    records  = query_db("SELECT * FROM attendance WHERE date=%s", (selected_date,))
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
    uid = session['user_id']
    records = query_db("SELECT a.*, u.name as teacher_name FROM attendance a JOIN users u ON a.teacher_id=u.id WHERE a.student_id=%s ORDER BY a.date DESC LIMIT 30", (uid,))
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
def admin_teacher_attendance():
    today = datetime.date.today().strftime('%Y-%m-%d')
    selected_date = request.args.get('date', today)
    
    if request.method == 'POST':
        admin_id  = session['user_id']
        mark_date = request.form.get('mark_date', today)
        
        for key in request.form.keys():
            if key.startswith('status_'):
                tid = int(key.replace('status_', ''))
                status = request.form[key]
                remark = request.form.get(f'remark_{tid}', '')
                
                query_db("""
                    INSERT INTO attendance (student_id, teacher_id, date, status, remark)
                    VALUES (%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE 
                    status=VALUES(status), remark=VALUES(remark), teacher_id=VALUES(teacher_id)
                """, (tid, admin_id, mark_date, status, remark), commit=True)
        
        flash('Teacher attendance recorded successfully!', 'success')
        return redirect(url_for('admin_teacher_attendance', date=mark_date))

    teachers = query_db("SELECT * FROM users WHERE role='teacher' AND school_id=%s ORDER BY name", (session.get('school_id'),))
    records  = query_db("SELECT * FROM attendance WHERE date=%s", (selected_date,))
    rec_map  = {r['student_id']: r for r in records}
    
    return render_template('admin/teacher_attendance.html', 
                           teachers=teachers, rec_map=rec_map, 
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

@app.route('/super-admin/schools', methods=['GET', 'POST'])
@role_required('super_admin')
def super_admin_schools():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        addr = request.form.get('address', '').strip()
        if name:
            query_db("INSERT INTO schools (name, address) VALUES (%s, %s)", (name, addr), commit=True, use_control=True)
            flash(f'School "{name}" created successfully! Ã°Å¸ÂÂ«', 'success')
        else:
            flash('School name is required.', 'danger')
        return redirect(url_for('super_admin_schools'))

    schools = query_db("""
        SELECT s.*, 
               (SELECT COUNT(*) FROM users WHERE school_id=s.id AND role='student') as student_count,
               (SELECT COUNT(*) FROM users WHERE school_id=s.id AND role='teacher') as teacher_count,
               (SELECT name FROM users WHERE school_id=s.id AND role='admin' LIMIT 1) as admin_name
        FROM schools s
        ORDER BY s.created_at DESC
    """)
    # This listing needs control DB
    schools = query_db("""
        SELECT s.*, 
               (SELECT COUNT(*) FROM users WHERE school_id=s.id AND role='student') as student_count,
               (SELECT COUNT(*) FROM users WHERE school_id=s.id AND role='teacher') as teacher_count,
               (SELECT name FROM users WHERE school_id=s.id AND role='admin' LIMIT 1) as admin_name
        FROM schools s
        ORDER BY s.created_at DESC
    """, use_control=True)
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

    name = request.form.get('name')
    subdomain = request.form.get('subdomain')
    address = request.form.get('address', '')
    use_aws = bool(request.form.get('use_aws'))

    job_id = create_job({'name': name, 'subdomain': subdomain})
    # Enqueue Celery task
    provision_task.apply_async(args=(job_id, name, subdomain, address, use_aws))

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

    job = get_job(job_id)
    if not job:
        flash('Job not found', 'danger')
        return redirect(url_for('super_admin_provision_jobs'))
    data = job.get('result') or job.get('result', {})
    # attempt to extract name/subdomain
    name = data.get('name') if isinstance(data, dict) else None
    subdomain = data.get('subdomain') if isinstance(data, dict) else None
    if not name or not subdomain:
        # fallback: read from job metadata if present
        meta = job.get('result') or {}
        name = meta.get('name') or 'restored'
        subdomain = meta.get('subdomain') or 'retry'
    new_job = create_job({'name': name, 'subdomain': subdomain})
    provision_task.apply_async(args=(new_job, name, subdomain, '', False))
    flash('Retry enqueued', 'success')
    return redirect(url_for('super_admin_provision_jobs'))

@app.route('/super-admin/admins/create', methods=['GET', 'POST'])
@role_required('super_admin')
def super_admin_create_admin():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        passw = request.form.get('password')
        school_id = request.form.get('school_id')
        
        pw_hash = generate_password_hash(passw)
        try:
            query_db("INSERT INTO users (name, email, phone, password_hash, role, school_id) VALUES (%s,%s,%s,%s,'admin',%s)",
                    (name, email, phone, pw_hash, school_id), commit=True)
            flash(f"Admin created successfully for the school! Ã¢Å“Â¨", "success")
        except Exception as e:
            flash(f"Error creating admin: {e}", "danger")
        return redirect(url_for('super_admin_dashboard'))
    
    schools = query_db("SELECT * FROM schools", use_control=True)
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
    admin = query_db("SELECT * FROM users WHERE id=%s AND role='admin'", (admin_id,), one=True)
    if not admin:
        flash('Admin not found!', 'danger')
        return redirect(url_for('super_admin_admins'))
        
    if request.method == 'POST':
        name      = request.form.get('name')
        email     = request.form.get('email')
        phone     = request.form.get('phone')
        passw     = request.form.get('password', '').strip()
        school_id = request.form.get('school_id')
        
        if passw:
            pw_hash = generate_password_hash(passw)
            query_db("UPDATE users SET name=%s, email=%s, phone=%s, password_hash=%s, school_id=%s WHERE id=%s",
                     (name, email, phone, pw_hash, school_id, admin_id), commit=True)
        else:
            query_db("UPDATE users SET name=%s, email=%s, phone=%s, school_id=%s WHERE id=%s",
                     (name, email, phone, school_id, admin_id), commit=True)
                     
        flash("School Admin profile updated successfully!", "success")
        return redirect(url_for('super_admin_admins'))
        
    schools = query_db("SELECT * FROM schools", use_control=True)
    return render_template('super_admin/edit_admin.html', admin=admin, schools=schools)

@app.route('/super-admin/admins/delete/<int:admin_id>', methods=['POST'])
@role_required('super_admin')
def super_admin_delete_admin(admin_id):
    query_db("DELETE FROM users WHERE id=%s AND role='admin'", (admin_id,), commit=True)
    flash("School Admin removed successfully.", "success")
    return redirect(url_for('super_admin_admins'))


@app.route('/super-admin/payments')
@role_required('super_admin')
def super_admin_payments():
    payments = query_db("""
        SELECT p.*, s.name as school_name 
        FROM payments p JOIN schools s ON p.school_id=s.id 
        ORDER BY p.payment_date DESC
    """, use_control=True)
    return render_template('super_admin/payments.html', payments=payments)

@app.route('/super-admin/payments/approve/<int:pid>', methods=['POST'])
@role_required('super_admin')
def super_admin_approve_payment(pid):
    pay = query_db("SELECT * FROM payments WHERE id=%s", (pid,), one=True, use_control=True)
    if not pay:
        flash("Payment request not found.", "danger")
        return redirect(url_for('super_admin_payments'))
    
    if pay['status'] == 'approved':
        flash("Payment already approved earlier.", "warning")
        return redirect(url_for('super_admin_payments'))
        
    months_to_add = pay['months'] if pay['months'] else 12
    
    # 1. Update payment log
    query_db("UPDATE payments SET status='approved' WHERE id=%s", (pid,), commit=True, use_control=True)
    
    # 2. Fetch current school data
    sch = query_db("SELECT valid_until FROM schools WHERE id=%s", (pay['school_id'],), one=True, use_control=True)
    
    # 3. Date calculation
    from datetime import datetime, timedelta
    
    base_date = datetime.now()
    if sch['valid_until']:
        try:
            if isinstance(sch['valid_until'], str):
                parsed_vu = datetime.strptime(sch['valid_until'], '%Y-%m-%d')
            else:
                parsed_vu = datetime.combine(sch['valid_until'], datetime.min.time())
            if parsed_vu > base_date:
                base_date = parsed_vu
        except:
            pass
            
    new_expiry = base_date + timedelta(days=30 * months_to_add)
    expiry_str = new_expiry.strftime('%Y-%m-%d')
    
    # 4. Update school table
    query_db("UPDATE schools SET valid_until=%s, subscription_status='active' WHERE id=%s",
             (expiry_str, pay['school_id']), commit=True, use_control=True)
             
    flash(f"Payment approved! School extended to {expiry_str} Ã°Å¸â€™Â¸Ã¢Å“â€¦", "success")
    return redirect(url_for('super_admin_payments'))

# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
#  FEE STRUCTURE ROUTES
# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

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
