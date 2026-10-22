import json
import os
import re
import secrets
from datetime import datetime, timezone
from functools import wraps
from flask import request, jsonify, g, make_response
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
import redis

from database import SessionLocal
import models
from models import User, UserRole, Vendor, VendorApprovalStatus

# ---------------------------------------------------------------------------
# Configuration & Hasher
# ---------------------------------------------------------------------------

ph = PasswordHasher()

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)

SESSION_COOKIE_NAME = "cm_session"
CSRF_COOKIE_NAME = "cm_csrf"
SESSION_TTL_SECONDS = 86400 * 7  # 7 days
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_WINDOW = 60  # seconds

# In-memory fallbacks if Redis is offline
_in_memory_sessions = {}
_in_memory_rate_limits = {}

def get_redis_client():
    try:
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True,
            protocol=2,
            socket_timeout=2,
            socket_connect_timeout=2
        )
        client.ping()
        return client
    except Exception:
        return None

r_client = get_redis_client()


# ---------------------------------------------------------------------------
# Password Helpers
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(hashed: str, password: str) -> bool:
    if not hashed:
        return False
    try:
        if hashed.startswith("$argon2"):
            return ph.verify(hashed, password)
        # Fallback for werkzeug pbkdf2 or scrypt hashes
        from werkzeug.security import check_password_hash
        return check_password_hash(hashed, password)
    except (VerifyMismatchError, VerificationError, Exception):
        return False


# ---------------------------------------------------------------------------
# Session Helpers
# ---------------------------------------------------------------------------

def create_session(user_id: int, role: str, vendor_id: int = None, email: str = None, name: str = None) -> str:
    token = secrets.token_hex(32)
    session_data = {
        "user_id": user_id,
        "role": role,
        "vendor_id": vendor_id,
        "email": email,
        "name": name,
        "csrf_token": secrets.token_hex(32),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    client = get_redis_client()
    if client:
        client.set(f"session:{token}", json.dumps(session_data), ex=SESSION_TTL_SECONDS)
    else:
        _in_memory_sessions[token] = session_data
    return token


def get_session(token: str) -> dict:
    if not token:
        return None
    client = get_redis_client()
    if client:
        raw = client.get(f"session:{token}")
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                return None
    return _in_memory_sessions.get(token)


def delete_session(token: str):
    if not token:
        return
    client = get_redis_client()
    if client:
        client.delete(f"session:{token}")
    _in_memory_sessions.pop(token, None)


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------

def get_client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


def check_login_rate_limit(ip: str) -> bool:
    """Returns True if within rate limit, False if rate limited (blocked)."""
    key = f"rate_limit:login:{ip}"
    client = get_redis_client()
    if client:
        count = client.get(key)
        if count and int(count) >= MAX_LOGIN_ATTEMPTS:
            return False
        return True
    else:
        now = datetime.now(timezone.utc).timestamp()
        history = _in_memory_rate_limits.get(ip, [])
        history = [t for t in history if now - t < LOGIN_LOCKOUT_WINDOW]
        _in_memory_rate_limits[ip] = history
        return len(history) < MAX_LOGIN_ATTEMPTS


def record_failed_login(ip: str):
    key = f"rate_limit:login:{ip}"
    client = get_redis_client()
    if client:
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, LOGIN_LOCKOUT_WINDOW)
        pipe.execute()
    else:
        now = datetime.now(timezone.utc).timestamp()
        history = _in_memory_rate_limits.get(ip, [])
        history.append(now)
        _in_memory_rate_limits[ip] = history


def clear_failed_login(ip: str):
    key = f"rate_limit:login:{ip}"
    client = get_redis_client()
    if client:
        client.delete(key)
    _in_memory_rate_limits.pop(ip, None)


# ---------------------------------------------------------------------------
# Authentication Decorators
# ---------------------------------------------------------------------------

def extract_token_from_request() -> str:
    # 1. Bearer Token in Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    # 2. Session cookie
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie:
        return cookie
    # 3. Fallback cookie 'session'
    return request.cookies.get("session")


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = extract_token_from_request()
        session_data = get_session(token)
        if not session_data:
            return jsonify({"success": False, "error": "Authentication required. Please log in."}), 401

        db = SessionLocal()
        try:
            user = db.query(User).filter_by(user_id=session_data["user_id"]).first()
            if not user:
                return jsonify({"success": False, "error": "User account not found."}), 401

            g.current_user = user
            g.user = user
            g.session_data = session_data
            g.session_token = token

            # If user is a vendor, load vendor record
            g.vendor = None
            if user.role == UserRole.vendor.value or session_data.get("vendor_id"):
                vendor = db.query(Vendor).filter_by(user_id=user.user_id).first()
                if not vendor and session_data.get("vendor_id"):
                    vendor = db.query(Vendor).filter_by(vendor_id=session_data["vendor_id"]).first()
                g.vendor = vendor

            return f(*args, **kwargs)
        finally:
            db.close()
    return decorated_function


def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if g.user.role not in allowed_roles:
                return jsonify({
                    "success": False,
                    "error": f"Forbidden: This action requires role in {allowed_roles}."
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def approved_vendor_required(f):
    """Requires vendor role AND vendor approval_status == 'approved'."""
    @wraps(f)
    @role_required(UserRole.vendor.value)
    def decorated_function(*args, **kwargs):
        if not g.vendor:
            return jsonify({
                "success": False,
                "error": "No vendor profile associated with this account."
            }), 403

        if g.vendor.approval_status != VendorApprovalStatus.approved.value:
            return jsonify({
                "success": False,
                "error": f"Vendor account is {g.vendor.approval_status}. Pending administrator approval before inventory operations are allowed.",
                "approval_status": g.vendor.approval_status
            }), 403
        return f(*args, **kwargs)
    return decorated_function
