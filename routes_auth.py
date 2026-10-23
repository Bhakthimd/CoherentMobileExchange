import re
import secrets
from flask import Blueprint, request, jsonify, g, make_response
from database import SessionLocal
import models
from models import User, UserRole, Vendor, VendorApprovalStatus
from auth import (
    hash_password, verify_password,
    create_session, get_session, delete_session,
    check_login_rate_limit, record_failed_login, clear_failed_login,
    get_client_ip, login_required, role_required,
    SESSION_COOKIE_NAME, CSRF_COOKIE_NAME, SESSION_TTL_SECONDS
)

auth_bp = Blueprint("auth", __name__)

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")


def set_auth_cookies(response, token: str, csrf_token: str = None):
    """Attach HttpOnly session cookie and readable CSRF cookie."""
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="Lax",
        secure=False,  # Set True in production with HTTPS
        path="/"
    )
    # Also set legacy 'session' cookie for full browser compatibility
    response.set_cookie(
        "session",
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="Lax",
        secure=False,
        path="/"
    )
    if csrf_token:
        response.set_cookie(
            CSRF_COOKIE_NAME,
            csrf_token,
            max_age=SESSION_TTL_SECONDS,
            httponly=False,  # Readable by frontend JS to set X-CSRF-Token header
            samesite="Lax",
            secure=False,
            path="/"
        )
    return response


def clear_auth_cookies(response):
    response.set_cookie(SESSION_COOKIE_NAME, "", max_age=0, path="/")
    response.set_cookie("session", "", max_age=0, path="/")
    response.set_cookie(CSRF_COOKIE_NAME, "", max_age=0, path="/")
    return response


# ---------------------------------------------------------------------------
# Auth Routes
# ---------------------------------------------------------------------------

@auth_bp.route("/api/auth/register", methods=["POST"])
def register_customer():
    """Customer registration endpoint."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""
    address = (data.get("address") or "").strip()

    if not name:
        return jsonify({"success": False, "error": "Full name is required."}), 400
    if not email or not EMAIL_REGEX.match(email):
        return jsonify({"success": False, "error": "A valid email address is required."}), 400
    if len(password) < 6:
        return jsonify({"success": False, "error": "Password must be at least 6 characters long."}), 400

    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(
            (User.email == email) | ((User.phone == phone) & (User.phone.isnot(None)) & (User.phone != ""))
        ).first()
        if existing_user:
            return jsonify({"success": False, "error": "An account with this email or phone already exists."}), 400

        user = User(
            name=name,
            email=email,
            phone=phone if phone else None,
            password_hash=hash_password(password),
            address=address,
            role=UserRole.customer.value,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        csrf_token = secrets.token_hex(32)
        token = create_session(user.user_id, user.role, email=user.email, name=user.name)

        resp = make_response(jsonify({
            "success": True,
            "message": "Account created successfully.",
            "token": token,
            "csrf_token": csrf_token,
            "user": user.to_dict()
        }), 201)
        return set_auth_cookies(resp, token, csrf_token)
    finally:
        db.close()


@auth_bp.route("/api/auth/vendor/register", methods=["POST"])
def register_vendor():
    """Vendor self-registration endpoint (approval_status=pending)."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""
    vendor_name = (data.get("vendor_name") or data.get("name") or "").strip()
    vendor_code = (data.get("vendor_code") or "").strip().upper()
    category = (data.get("category") or "Multi-Brand Refurbished Specialist").strip()
    location = (data.get("location") or "").strip()
    address = (data.get("address") or location).strip()
    gst_number = (data.get("gst_number") or "").strip()

    if not name or not vendor_name:
        return jsonify({"success": False, "error": "Contact name and business/vendor name are required."}), 400
    if not email or not EMAIL_REGEX.match(email):
        return jsonify({"success": False, "error": "A valid contact email is required."}), 400
    if len(password) < 8:
        return jsonify({"success": False, "error": "Password must be at least 8 characters long."}), 400
    if not vendor_code:
        # Auto-generate a clean vendor code if not provided
        slug = re.sub(r"[^A-Za-z0-9]", "", vendor_name)[:5].upper()
        vendor_code = f"{slug}-{secrets.token_hex(2).upper()}"

    db = SessionLocal()
    try:
        if db.query(User).filter_by(email=email).first():
            return jsonify({"success": False, "error": "An account with this email already exists."}), 400
        if db.query(Vendor).filter_by(vendor_code=vendor_code).first():
            return jsonify({"success": False, "error": f"Vendor store code '{vendor_code}' is already registered."}), 400

        user = User(
            name=name,
            email=email,
            phone=phone if phone else None,
            password_hash=hash_password(password),
            address=address,
            role=UserRole.vendor.value,
        )
        db.add(user)
        db.flush()

        vendor = Vendor(
            user_id=user.user_id,
            vendor_name=vendor_name,
            vendor_code=vendor_code,
            category=category,
            contact_email=email,
            contact_phone=phone,
            location=location,
            address=address,
            gst_number=gst_number,
            status="Active",
            approval_status=VendorApprovalStatus.pending.value,
        )
        db.add(vendor)
        db.commit()
        db.refresh(vendor)
        db.refresh(user)

        # Allow vendor to log in immediately so they see the "pending approval" screen
        csrf_token = secrets.token_hex(32)
        token = create_session(
            user.user_id,
            user.role,
            vendor_id=vendor.vendor_id,
            email=user.email,
            name=vendor.vendor_name
        )

        resp = make_response(jsonify({
            "success": True,
            "message": "Vendor registration submitted successfully! Your account is currently awaiting administrator approval.",
            "token": token,
            "csrf_token": csrf_token,
            "vendor": vendor.to_dict(),
            "user": user.to_dict()
        }), 201)
        return set_auth_cookies(resp, token, csrf_token)
    finally:
        db.close()


@auth_bp.route("/api/auth/login", methods=["POST"])
@auth_bp.route("/api/vendor/login", methods=["POST"])
def login():
    """Unified login for customers, vendors, and admins."""
    ip = get_client_ip()
    if not check_login_rate_limit(ip):
        return jsonify({
            "success": False,
            "error": "Too many failed login attempts. Please wait a minute and try again."
        }), 429

    data = request.get_json(silent=True) or {}
    login_id = (data.get("login") or data.get("email") or data.get("username") or "").strip()
    password = data.get("password") or ""

    if not login_id or not password:
        return jsonify({"success": False, "error": "Login ID and password are required."}), 400

    db = SessionLocal()
    try:
        user = None
        vendor = None

        # 1. Try finding by email (case-insensitive)
        user = db.query(User).filter(User.email.ilike(login_id)).first()

        # 2. If not found, try finding by vendor_code (case-insensitive)
        if not user:
            vendor = db.query(Vendor).filter(Vendor.vendor_code.ilike(login_id)).first()
            if vendor and vendor.user_id:
                user = db.query(User).filter_by(user_id=vendor.user_id).first()

        # 3. If still not found, try phone
        if not user:
            user = db.query(User).filter_by(phone=login_id).first()

        # Verify password
        if not user or not verify_password(user.password_hash, password):
            record_failed_login(ip)
            return jsonify({
                "success": False,
                "error": "Invalid store code/email or password."
            }), 401

        # Clear failed login record on success
        clear_failed_login(ip)

        # Retrieve linked vendor if user is a vendor
        if not vendor and user.role == UserRole.vendor.value:
            vendor = db.query(Vendor).filter_by(user_id=user.user_id).first()
            if not vendor:
                vendor = db.query(Vendor).filter(
                    (Vendor.contact_email.ilike(user.email)) |
                    (Vendor.store_name.ilike(user.name))
                ).first()

        vendor_id = vendor.vendor_id if vendor else None
        csrf_token = secrets.token_hex(32)
        token = create_session(
            user_id=user.user_id,
            role=user.role,
            vendor_id=vendor_id,
            email=user.email,
            name=user.name
        )

        resp_data = {
            "success": True,
            "message": "Login successful.",
            "token": token,
            "csrf_token": csrf_token,
            "user": user.to_dict(),
        }
        if vendor:
            resp_data["vendor"] = vendor.to_dict()

        resp = make_response(jsonify(resp_data), 200)
        return set_auth_cookies(resp, token, csrf_token)
    finally:
        db.close()


@auth_bp.route("/api/auth/logout", methods=["POST"])
@auth_bp.route("/api/vendor/logout", methods=["POST"])
def logout():
    """Logout and clear session."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not token:
        token = request.cookies.get(SESSION_COOKIE_NAME) or request.cookies.get("session")
    if token:
        delete_session(token)

    resp = make_response(jsonify({"success": True, "message": "Logged out successfully."}), 200)
    return clear_auth_cookies(resp)


@auth_bp.route("/api/auth/me", methods=["GET"])
@login_required
def get_current_user_profile():
    """Returns profile of currently logged-in user and linked vendor if applicable."""
    resp = {
        "success": True,
        "user": g.user.to_dict(),
        "role": g.user.role
    }
    if g.vendor:
        resp["vendor"] = g.vendor.to_dict()
    return jsonify(resp), 200


@auth_bp.route("/api/vendor/me", methods=["GET"])
@login_required
def get_vendor_profile():
    """Vendor-specific me endpoint for vendor dashboard."""
    if not g.vendor:
        return jsonify({"success": False, "error": "No vendor account associated with this login."}), 404
    return jsonify({
        "success": True,
        "vendor": g.vendor.to_dict(),
        "user": g.user.to_dict()
    }), 200


@auth_bp.route("/api/vendor/password", methods=["POST"])
@login_required
def change_vendor_password():
    """Change vendor account password."""
    data = request.get_json(silent=True) or {}
    current_pwd = data.get("current_password") or ""
    new_pwd = data.get("new_password") or ""

    if len(new_pwd) < 8:
        return jsonify({"success": False, "error": "New password must be at least 8 characters long."}), 400

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(user_id=g.user.user_id).first()
        if not user or not verify_password(user.password_hash, current_pwd):
            return jsonify({"success": False, "error": "Current password is incorrect."}), 400

        user.password_hash = hash_password(new_pwd)
        db.commit()
        return jsonify({"success": True, "message": "Password updated successfully."}), 200
    finally:
        db.close()
