"""
Store Locator, Store Profiles, and Serviceable Pincodes API
CoherentMobiles - Mysuru / K.T. Street Hub
"""

from flask import Blueprint, jsonify, request
from sqlalchemy import func, or_
from database import SessionLocal
import models
from models import (
    Vendor, VendorApprovalStatus, InventoryUnit, UnitStatus,
    ServiceablePincode, User, UserRole, utc_now
)
from auth import login_required, role_required

stores_bp = Blueprint("stores", __name__, url_prefix="/api")


@stores_bp.route("/stores", methods=["GET"])
def list_stores():
    """
    Returns list of verified partner stores on K.T. Street, Mysuru
    with live open/closed status, inventory count, and coordinates.
    """
    search_q = request.args.get("search", "").strip().lower()
    service_filter = request.args.get("service", "").strip().lower()
    open_only = request.args.get("open_only", "").lower() in ("true", "1", "yes")

    db = SessionLocal()
    try:
        # Retrieve approved stores
        query = db.query(Vendor).filter(
            Vendor.approval_status == VendorApprovalStatus.approved.value
        ).order_by(Vendor.vendor_id.asc())

        if search_q:
            query = query.filter(
                or_(
                    func.lower(Vendor.vendor_name).contains(search_q),
                    func.lower(Vendor.store_name).contains(search_q),
                    func.lower(Vendor.address).contains(search_q),
                    func.lower(Vendor.landmark).contains(search_q)
                )
            )

        if service_filter == "walk_in":
            query = query.filter(Vendor.accepts_walk_in.is_(True))
        elif service_filter == "home_pickup":
            query = query.filter(Vendor.offers_home_pickup.is_(True))
        elif service_filter == "doorstep_delivery":
            query = query.filter(Vendor.offers_doorstep_delivery.is_(True))
        elif service_filter == "buyback":
            query = query.filter(Vendor.buyback_enabled.is_(True))

        stores = query.all()
        results = []

        for store in stores:
            store_data = store.to_dict()
            # Count in-stock units
            in_stock_count = db.query(InventoryUnit).filter(
                InventoryUnit.vendor_id == store.vendor_id,
                InventoryUnit.status == UnitStatus.in_stock.value,
                InventoryUnit.deleted_at.is_(None)
            ).count()
            store_data["inventory_count"] = in_stock_count

            if open_only and not store_data.get("is_open"):
                continue

            results.append(store_data)

        return jsonify({
            "success": True,
            "count": len(results),
            "area": "K.T. Street, Mysuru (PIN 570001)",
            "center": {"lat": 12.3060, "lng": 76.6548},
            "stores": results
        }), 200
    finally:
        db.close()


@stores_bp.route("/stores/<int:store_id>", methods=["GET"])
def get_store_detail(store_id: int):
    """
    Returns single store profile with opening hours table and in-stock devices.
    """
    db = SessionLocal()
    try:
        store = db.query(Vendor).filter(
            Vendor.vendor_id == store_id,
            Vendor.approval_status == VendorApprovalStatus.approved.value
        ).first()

        if not store:
            return jsonify({"success": False, "error": f"Store with ID {store_id} not found or not approved."}), 404

        store_data = store.to_dict()

        # Fetch in-stock devices at this store
        units = db.query(InventoryUnit).filter(
            InventoryUnit.vendor_id == store.vendor_id,
            InventoryUnit.status == UnitStatus.in_stock.value,
            InventoryUnit.deleted_at.is_(None)
        ).all()

        store_data["inventory"] = [u.to_dict() for u in units]
        store_data["inventory_count"] = len(units)

        return jsonify({"success": True, "store": store_data}), 200
    finally:
        db.close()


@stores_bp.route("/pincodes/check", methods=["GET"])
def check_pincode():
    """
    Validates if a customer's pincode is serviceable for home pickup in Mysuru.
    """
    pincode = request.args.get("pincode", "").strip()
    if not pincode:
        return jsonify({
            "serviceable": False,
            "error": "Pincode is required."
        }), 400

    db = SessionLocal()
    try:
        record = db.query(ServiceablePincode).filter_by(pincode=pincode, is_active=True).first()
        if record:
            return jsonify({
                "serviceable": True,
                "pincode": record.pincode,
                "area_name": record.area_name,
                "city": record.city,
                "message": f"Great! Home pickup is available in {record.area_name}, {record.city}."
            }), 200
        else:
            return jsonify({
                "serviceable": False,
                "pincode": pincode,
                "message": "Home pickup is currently limited to Mysuru city limits (PIN 570001 - 570024). You are welcome to visit our partner stores on K.T. Street for instant cash evaluation!"
            }), 200
    finally:
        db.close()


@stores_bp.route("/stores/lead", methods=["POST"])
def submit_store_lead():
    """
    'Become a Partner Store' form on K.T. Street.
    Creates a pending vendor lead for administrator review.
    """
    data = request.get_json(silent=True) or {}
    shop_name = (data.get("store_name") or data.get("shop_name") or "").strip()
    owner_name = (data.get("owner_name") or data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip().lower()
    address = (data.get("address") or "").strip()

    if not shop_name or not phone:
        return jsonify({"success": False, "error": "Store name and contact phone are required."}), 400

    db = SessionLocal()
    try:
        # Generate vendor code
        import secrets
        code_prefix = "".join(filter(str.isalnum, shop_name[:3])).upper() or "KTS"
        code = f"{code_prefix}-{secrets.randbelow(899) + 100}"

        vendor = Vendor(
            vendor_name=shop_name,
            store_name=shop_name,
            vendor_code=code,
            category="Partner Mobile Store",
            contact_email=email or f"lead.{code.lower()}@coherent.test",
            contact_phone=phone,
            location="K.T. Street, Mysuru",
            address=address or "K.T. Street, Mysuru - 570001",
            address_line=address or "K.T. Street, Mysuru - 570001",
            landmark=data.get("landmark", "K.T. Street"),
            area="K.T. Street",
            city="Mysuru",
            pincode="570001",
            latitude=12.3060,
            longitude=76.6548,
            whatsapp_number=phone,
            status="Pending Review",
            approval_status=VendorApprovalStatus.pending.value
        )
        db.add(vendor)
        db.commit()
        db.refresh(vendor)

        return jsonify({
            "success": True,
            "message": "Thank you! Your partnership request for K.T. Street has been submitted. Our team will contact you within 24 hours.",
            "lead_id": vendor.vendor_id,
            "vendor_code": vendor.vendor_code
        }), 201
    finally:
        db.close()
