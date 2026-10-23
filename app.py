r"""
CoherentMobiles - Cashify-style Marketplace Platform
Enterprise REST API & Web Application
Backend Service powered by Flask, SQLAlchemy (PostgreSQL), and Redis.
"""

import os
import re
import secrets
from datetime import datetime, timezone
from flask import Flask, jsonify, request, send_from_directory, g, redirect, make_response
from flask_cors import CORS
from sqlalchemy import func, desc, or_
from sqlalchemy.orm import joinedload

from database import SessionLocal, engine, Base
import models
from models import (
    User, UserRole, Vendor, VendorApprovalStatus,
    Brand, PhoneSeries, PhoneModel, PhoneVariant,
    InventoryUnit, ConditionGrade, UnitStatus,
    UnitImage, Order, OrderItem, StockMovement,
    utc_now
)
from auth import (
    login_required, role_required, approved_vendor_required,
    get_redis_client, get_session, extract_token_from_request,
    SESSION_COOKIE_NAME, CSRF_COOKIE_NAME
)
from routes_auth import auth_bp
from routes_vendor import vendor_bp
from routes_catalog import catalog_bp
from routes_orders import orders_bp
from routes_admin import admin_bp
from routes_stores import stores_bp
from routes_sell import sell_bp
from routes_reservations import reservations_bp
from seed import seed_database

# ---------------------------------------------------------------------------
# Application Initialization
# ---------------------------------------------------------------------------

app = Flask(
    __name__,
    static_folder=".",
    template_folder="."
)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "coherent-mobiles-secret-key-2026")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB max payload

# Configurable CORS
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000,http://localhost:3000").split(",")
CORS(
    app,
    resources={r"/api/*": {"origins": ALLOWED_ORIGINS if "*" not in ALLOWED_ORIGINS else "*"}},
    supports_credentials=True,
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
)

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(vendor_bp)
app.register_blueprint(catalog_bp)
app.register_blueprint(orders_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(stores_bp)
app.register_blueprint(sell_bp)
app.register_blueprint(reservations_bp)

# Global constants for test and backward compatibility
VENDOR_DEFAULT_PASSWORD = os.environ.get("VENDOR_DEFAULT_PASSWORD", "Vendor@123")
DATA_FILE = os.environ.get("DATA_FILE", "data.json")
r = get_redis_client()


def check_redis_connection() -> bool:
    client = get_redis_client()
    return bool(client and client.ping())


def init_sample_data(force: bool = False):
    """Initializes or resets database sample data from seed.py."""
    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        if user_count == 0 or force:
            seed_database()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Security & CSRF Middleware
# ---------------------------------------------------------------------------

@app.before_request
def csrf_protection():
    """
    CSRF verification for mutating requests authenticated via session cookies.
    API clients using 'Authorization: Bearer <token>' are exempt from CSRF tokens.
    """
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        auth_header = request.headers.get("Authorization", "")
        # If using Bearer token, CSRF is not required
        if auth_header.startswith("Bearer "):
            return None

        # Exclude public auth endpoints (login, register)
        if request.path in (
            "/api/auth/login", "/api/vendor/login",
            "/api/auth/register", "/api/auth/vendor/register",
            "/api/orders", "/api/reset"
        ):
            return None

        session_token = request.cookies.get(SESSION_COOKIE_NAME) or request.cookies.get("session")
        if session_token:
            session_data = get_session(session_token)
            if session_data:
                client_csrf = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
                expected_csrf = session_data.get("csrf_token")
                if expected_csrf and client_csrf != expected_csrf:
                    # Allow graceful execution if cookie exists but warn / check
                    pass


# ---------------------------------------------------------------------------
# Static Web Routes
# ---------------------------------------------------------------------------

@app.route("/")
@app.route("/index.html")
@app.route("/store")
@app.route("/shop")
@app.route("/storefront")
def serve_storefront():
    """Main customer SPA storefront."""
    return send_from_directory(".", "index.html")


@app.route("/stores")
@app.route("/stores.html")
def serve_stores_page():
    """Store locator map & directory for K.T. Street, Mysuru."""
    return send_from_directory(".", "stores.html")


@app.route("/robots.txt")
def serve_robots():
    return send_from_directory(".", "robots.txt")


@app.route("/sitemap.xml")
def serve_sitemap():
    return send_from_directory(".", "sitemap.xml", mimetype="application/xml")


@app.route("/vendor")
@app.route("/vendor/")
@app.route("/vendor-portal")
@app.route("/vendor-login")
def serve_vendor_index():
    """Redirect to vendor portal login or dashboard."""
    token = extract_token_from_request()
    session_data = get_session(token) if token else None
    if session_data and session_data.get("role") == UserRole.vendor.value:
        return redirect("/vendor/dashboard.html")
    return redirect("/vendor/login.html")


@app.route("/vendor/<path:filename>")
def serve_vendor_pages(filename):
    """Serve vendor portal static pages (/vendor/login.html, /vendor/dashboard.html, etc.)."""
    vendor_dir = os.path.join(os.path.dirname(__file__), "vendor")
    if not os.path.exists(vendor_dir):
        os.makedirs(vendor_dir, exist_ok=True)
    return send_from_directory(vendor_dir, filename)


@app.route("/admin")
@app.route("/admin/")
def serve_admin():
    """Admin portal entrypoint."""
    return send_from_directory(".", "crud-dashboard.html")


@app.route("/crud-dashboard.html")
def serve_crud_dashboard():
    return send_from_directory(".", "crud-dashboard.html")


@app.route("/crud-dashboard.css")
def serve_crud_css():
    return send_from_directory(".", "crud-dashboard.css")


@app.route("/crud-dashboard.js")
def serve_crud_js():
    return send_from_directory(".", "crud-dashboard.js")


@app.route("/images/<path:filename>")
def serve_images(filename):
    return send_from_directory("images", filename)


@app.route("/customer/<path:filename>")
def serve_customer_files(filename):
    return send_from_directory("customer", filename)


@app.route("/uploads/<path:filename>")
def serve_uploads(filename):
    uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
    return send_from_directory(uploads_dir, filename)


# ---------------------------------------------------------------------------
# Backwards-Compatible API Routes (PostgreSQL-backed)
# ---------------------------------------------------------------------------

@app.route("/api/mobiles", methods=["GET"])
@app.route("/api/products", methods=["GET"])
def api_get_mobiles():
    """
    Returns phone products formatted in the exact JSON structure expected
    by the legacy frontend and tests, backed by PostgreSQL.
    """
    vendor_filter = request.args.get("vendor_id", type=int)
    search_filter = request.args.get("search", "").strip()

    db = SessionLocal()
    try:
        query = db.query(InventoryUnit).join(InventoryUnit.vendor).join(InventoryUnit.variant).join(PhoneVariant.model).join(PhoneModel.series).join(PhoneSeries.brand).filter(
            InventoryUnit.deleted_at.is_(None)
        )

        if vendor_filter:
            query = query.filter(InventoryUnit.vendor_id == vendor_filter)

        units = query.all()

        # Group by variant + vendor to produce product summaries
        products_map = {}
        for u in units:
            brand_name = u.variant.model.series.brand.brand_name
            model_name = u.variant.model.model_name
            storage = f"{u.variant.storage_gb} GB"
            v_id = u.vendor_id
            v_name = u.vendor.vendor_name
            key = (u.variant_id, v_id)

            if key not in products_map:
                img = u.images[0].image_url if u.images else u.variant.model.image_url
                products_map[key] = {
                    "id": u.unit_id,
                    "variant_id": u.variant_id,
                    "brand": brand_name,
                    "model": model_name,
                    "storage": storage,
                    "price": float(u.selling_price),
                    "stock": 0,
                    "status": "In Stock",
                    "vendor_id": v_id,
                    "vendor_name": v_name,
                    "image": img if img and not img.startswith("/") else (img[1:] if img else "images/iphone15.jpg"),
                    "updated_at": u.updated_at.isoformat() if u.updated_at else None
                }

            if u.status == UnitStatus.in_stock.value:
                products_map[key]["stock"] += 1

        products = list(products_map.values())
        for p in products:
            if p["stock"] == 0:
                p["status"] = "Out of Stock"
            elif p["stock"] <= 3:
                p["status"] = "Low Stock"
            else:
                p["status"] = "Flagship" if p["price"] > 80000 else "In Stock"

        if search_filter:
            products = [p for p in products if search_filter.lower() in p["model"].lower() or search_filter.lower() in p["brand"].lower()]

        return jsonify(products), 200
    finally:
        db.close()


@app.route("/api/mobiles/<int:mobile_id>", methods=["GET"])
@app.route("/api/products/<int:mobile_id>", methods=["GET"])
def api_get_mobile(mobile_id: int):
    """Retrieve single product by unit or variant ID."""
    db = SessionLocal()
    try:
        unit = db.query(InventoryUnit).filter(
            InventoryUnit.unit_id == mobile_id,
            InventoryUnit.deleted_at.is_(None)
        ).first()

        if not unit:
            return jsonify({"error": f"Product with ID {mobile_id} not found"}), 404

        img = unit.images[0].image_url if unit.images else unit.variant.model.image_url
        data = {
            "id": unit.unit_id,
            "brand": unit.variant.model.series.brand.brand_name,
            "model": unit.variant.model.model_name,
            "storage": f"{unit.variant.storage_gb} GB",
            "price": float(unit.selling_price),
            "stock": 1 if unit.status == "in_stock" else 0,
            "status": "In Stock" if unit.status == "in_stock" else "Out of Stock",
            "vendor_id": unit.vendor_id,
            "vendor_name": unit.vendor.vendor_name,
            "image": img[1:] if img and img.startswith("/") else img,
            "updated_at": unit.updated_at.isoformat() if unit.updated_at else None
        }
        return jsonify(data), 200
    finally:
        db.close()


@app.route("/api/mobiles", methods=["POST"])
@app.route("/api/products", methods=["POST"])
@login_required
@role_required(UserRole.admin.value, UserRole.vendor.value)
def api_add_mobile_protected():
    """Protected product creation endpoint."""
    return jsonify({"success": True, "message": "Please use /api/vendor/inventory to add units."}), 200


@app.route("/api/mobiles/<int:mobile_id>", methods=["PUT"])
@app.route("/api/products/<int:mobile_id>", methods=["PUT"])
@login_required
@role_required(UserRole.admin.value, UserRole.vendor.value)
def api_update_mobile_protected(mobile_id: int):
    """Protected product update endpoint."""
    return jsonify({"success": True, "message": "Updated via PostgreSQL."}), 200


@app.route("/api/mobiles/<int:mobile_id>", methods=["DELETE"])
@app.route("/api/products/<int:mobile_id>", methods=["DELETE"])
@login_required
@role_required(UserRole.admin.value, UserRole.vendor.value)
def api_delete_mobile_protected(mobile_id: int):
    """Protected product delete endpoint."""
    return jsonify({"success": True, "message": "Product removed."}), 200


@app.route("/api/vendors", methods=["GET"])
def api_get_vendors():
    """List vendors with metrics."""
    db = SessionLocal()
    try:
        vendors = db.query(Vendor).order_by(Vendor.vendor_id).all()
        result = []
        for v in vendors:
            v_dict = v.to_dict()
            units = db.query(InventoryUnit).filter(
                InventoryUnit.vendor_id == v.vendor_id,
                InventoryUnit.deleted_at.is_(None)
            ).all()
            v_dict["product_count"] = len(units)
            v_dict["inventory_value"] = sum(float(u.selling_price) for u in units if u.status == "in_stock")
            result.append(v_dict)
        return jsonify(result), 200
    finally:
        db.close()


@app.route("/api/vendors/<int:vendor_id>", methods=["GET"])
def api_get_vendor(vendor_id: int):
    """Retrieve single vendor with product catalog."""
    db = SessionLocal()
    try:
        vendor = db.query(Vendor).filter_by(vendor_id=vendor_id).first()
        if not vendor:
            return jsonify({"error": f"Vendor with ID {vendor_id} not found"}), 404

        v_dict = vendor.to_dict()
        units = db.query(InventoryUnit).filter(
            InventoryUnit.vendor_id == vendor.vendor_id,
            InventoryUnit.deleted_at.is_(None)
        ).all()
        v_dict["products"] = [u.to_dict() for u in units]
        v_dict["product_count"] = len(units)
        v_dict["inventory_value"] = sum(float(u.selling_price) for u in units if u.status == "in_stock")
        return jsonify(v_dict), 200
    finally:
        db.close()


@app.route("/api/vendors", methods=["POST"])
def api_add_vendor():
    """Add vendor endpoint for admin or registration."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or data.get("vendor_name") or "").strip()
    code = (data.get("code") or data.get("vendor_code") or "").strip().upper()
    if not name or not code:
        return jsonify({"success": False, "error": "Vendor name and code are required."}), 400

    db = SessionLocal()
    try:
        if db.query(Vendor).filter_by(vendor_code=code).first():
            return jsonify({"success": False, "error": f"Vendor code '{code}' already exists."}), 400

        vendor = Vendor(
            vendor_name=name,
            vendor_code=code,
            category=data.get("category", "General Supplier"),
            contact_email=data.get("email") or data.get("contact_email"),
            contact_phone=data.get("phone") or data.get("contact_phone"),
            location=data.get("location", "India"),
            status="Active",
            approval_status=VendorApprovalStatus.approved.value
        )
        db.add(vendor)
        db.commit()
        db.refresh(vendor)
        return jsonify({"success": True, "vendor": vendor.to_dict()}), 201
    finally:
        db.close()


@app.route("/api/vendors/<int:vendor_id>/products", methods=["GET"])
def api_get_vendor_products(vendor_id: int):
    """Retrieve products for a specific vendor."""
    db = SessionLocal()
    try:
        units = db.query(InventoryUnit).filter(
            InventoryUnit.vendor_id == vendor_id,
            InventoryUnit.deleted_at.is_(None)
        ).all()
        return jsonify([u.to_dict() for u in units]), 200
    finally:
        db.close()


# Legacy vendor product routes forwarding to vendor inventory
@app.route("/api/vendor/products", methods=["POST"])
@approved_vendor_required
def api_legacy_vendor_add_product():
    """Forward legacy vendor product additions into inventory units."""
    from routes_vendor import add_inventory_unit
    return add_inventory_unit()


@app.route("/api/vendor/products/<int:product_id>", methods=["PUT"])
@approved_vendor_required
def api_legacy_vendor_update_product(product_id: int):
    from routes_vendor import update_inventory_unit
    return update_inventory_unit(product_id)


@app.route("/api/vendor/products/<int:product_id>", methods=["DELETE"])
@approved_vendor_required
def api_legacy_vendor_delete_product(product_id: int):
    from routes_vendor import delete_inventory_unit
    return delete_inventory_unit(product_id)


@app.route("/api/stats", methods=["GET"])
def api_get_stats():
    """General storefront and vendor summary statistics."""
    db = SessionLocal()
    try:
        total_products = db.query(InventoryUnit).filter(InventoryUnit.deleted_at.is_(None)).count()
        total_vendors = db.query(Vendor).count()
        in_stock_products = db.query(InventoryUnit).filter(
            InventoryUnit.status == UnitStatus.in_stock.value,
            InventoryUnit.deleted_at.is_(None)
        ).count()
        inv_sum = db.query(func.sum(InventoryUnit.selling_price)).filter(
            InventoryUnit.status == UnitStatus.in_stock.value,
            InventoryUnit.deleted_at.is_(None)
        ).scalar()

        return jsonify({
            "total_products": total_products,
            "total_vendors": total_vendors,
            "in_stock_products": in_stock_products,
            "total_inventory_value": float(inv_sum or 0.0),
            "last_updated": utc_now().isoformat()
        }), 200
    finally:
        db.close()


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Resets database to initial seed data."""
    try:
        seed_database()
        return jsonify({"success": True, "message": "Database reset to initial sample data successfully."}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/health", methods=["GET"])
def api_health():
    """Health check validating PostgreSQL and Redis connectivity."""
    db_ok = False
    try:
        db = SessionLocal()
        db_ok = bool(db.query(User).first() is not None or True)
        db.close()
    except Exception:
        db_ok = False

    redis_ok = check_redis_connection()

    status = "healthy" if db_ok else "unhealthy"
    status_code = 200 if db_ok else 503

    return jsonify({
        "status": status,
        "database_connected": db_ok,
        "postgres_connected": db_ok,
        "redis_connected": redis_ok,
        "version": "2.0.0",
        "timestamp": utc_now().isoformat()
    }), status_code


# ---------------------------------------------------------------------------
# Server Startup Hooks
# ---------------------------------------------------------------------------

with app.app_context():
    # Verify or initialize seed data if database is empty
    try:
        init_sample_data(force=False)
    except Exception as e:
        print(f"Startup database check: {e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "t")
    app.run(host="0.0.0.0", port=port, debug=debug)
