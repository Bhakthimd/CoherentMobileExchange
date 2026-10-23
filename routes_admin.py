from flask import Blueprint, request, jsonify, g
from sqlalchemy import func, desc

from database import SessionLocal
import models
from models import (
    User, UserRole, Vendor, VendorApprovalStatus,
    InventoryUnit, UnitStatus, Order, OrderItem,
    Brand, PhoneModel, PhoneVariant, StockMovement,
    ServiceablePincode, PriceMatrix, SellRequest, SellRequestStatus,
    SellRequestTimeline, Reservation, ReservationStatus, utc_now
)
from auth import login_required, role_required

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/api/admin/vendors", methods=["GET"])
@login_required
@role_required(UserRole.admin.value)
def list_vendors():
    """List all registered vendors with status, metrics, and linked user."""
    status_filter = request.args.get("status")
    db = SessionLocal()
    try:
        query = db.query(Vendor)
        if status_filter:
            query = query.filter(Vendor.approval_status == status_filter)
        vendors = query.order_by(Vendor.vendor_id).all()

        vendor_data = []
        for v in vendors:
            v_dict = v.to_dict()
            v_dict["inventory_count"] = db.query(InventoryUnit).filter(
                InventoryUnit.vendor_id == v.vendor_id,
                InventoryUnit.deleted_at.is_(None)
            ).count()
            v_dict["in_stock_count"] = db.query(InventoryUnit).filter(
                InventoryUnit.vendor_id == v.vendor_id,
                InventoryUnit.status == UnitStatus.in_stock.value,
                InventoryUnit.deleted_at.is_(None)
            ).count()
            v_dict["sold_count"] = db.query(OrderItem).filter(
                OrderItem.vendor_id == v.vendor_id
            ).count()
            vendor_data.append(v_dict)

        return jsonify({
            "success": True,
            "vendors": vendor_data
        }), 200
    finally:
        db.close()


@admin_bp.route("/api/admin/vendors/<int:vendor_id>/status", methods=["PUT"])
@login_required
@role_required(UserRole.admin.value)
def update_vendor_status(vendor_id: int):
    """Approve, reject, or suspend a vendor."""
    data = request.get_json(silent=True) or {}
    new_status = (data.get("approval_status") or data.get("status") or "").strip().lower()

    valid_statuses = [s.value for s in VendorApprovalStatus]
    if new_status not in valid_statuses:
        return jsonify({
            "success": False,
            "error": f"Invalid approval status '{new_status}'. Allowed: {valid_statuses}"
        }), 400

    db = SessionLocal()
    try:
        vendor = db.query(Vendor).filter_by(vendor_id=vendor_id).first()
        if not vendor:
            return jsonify({"success": False, "error": "Vendor not found."}), 404

        vendor.approval_status = new_status
        db.commit()
        db.refresh(vendor)

        return jsonify({
            "success": True,
            "message": f"Vendor '{vendor.vendor_name}' approval status updated to '{new_status}'.",
            "vendor": vendor.to_dict()
        }), 200
    finally:
        db.close()


@admin_bp.route("/api/admin/inventory", methods=["GET"])
@login_required
@role_required(UserRole.admin.value)
def list_all_inventory():
    """List all inventory across all vendors."""
    page = max(1, int(request.args.get("page", 1)))
    per_page = max(1, min(100, int(request.args.get("per_page", 20))))
    vendor_id = request.args.get("vendor_id", type=int)

    db = SessionLocal()
    try:
        query = db.query(InventoryUnit).filter(InventoryUnit.deleted_at.is_(None))
        if vendor_id:
            query = query.filter(InventoryUnit.vendor_id == vendor_id)

        total = query.count()
        units = query.order_by(desc(InventoryUnit.created_at)).offset((page - 1) * per_page).limit(per_page).all()

        return jsonify({
            "success": True,
            "total": total,
            "page": page,
            "per_page": per_page,
            "items": [u.to_dict() for u in units]
        }), 200
    finally:
        db.close()


@admin_bp.route("/api/admin/orders", methods=["GET"])
@login_required
@role_required(UserRole.admin.value)
def list_all_orders():
    """List all orders system-wide."""
    page = max(1, int(request.args.get("page", 1)))
    per_page = max(1, min(100, int(request.args.get("per_page", 20))))

    db = SessionLocal()
    try:
        query = db.query(Order).order_by(desc(Order.created_at))
        total = query.count()
        orders = query.offset((page - 1) * per_page).limit(per_page).all()

        return jsonify({
            "success": True,
            "total": total,
            "page": page,
            "per_page": per_page,
            "orders": [o.to_dict() for o in orders]
        }), 200
    finally:
        db.close()


@admin_bp.route("/api/admin/stats", methods=["GET"])
@login_required
@role_required(UserRole.admin.value)
def admin_stats():
    """System-wide summary metrics."""
    db = SessionLocal()
    try:
        total_vendors = db.query(Vendor).count()
        pending_vendors = db.query(Vendor).filter_by(approval_status=VendorApprovalStatus.pending.value).count()
        total_units = db.query(InventoryUnit).filter(InventoryUnit.deleted_at.is_(None)).count()
        in_stock_units = db.query(InventoryUnit).filter(
            InventoryUnit.status == UnitStatus.in_stock.value,
            InventoryUnit.deleted_at.is_(None)
        ).count()
        total_orders = db.query(Order).count()
        gmv_sum = db.query(func.sum(Order.total_amount)).scalar()

        return jsonify({
            "success": True,
            "stats": {
                "total_vendors": total_vendors,
                "pending_vendors": pending_vendors,
                "total_inventory_units": total_units,
                "in_stock_units": in_stock_units,
                "total_orders": total_orders,
                "total_gmv": float(gmv_sum or 0.0)
            }
        }), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Admin Pincodes Management
# ---------------------------------------------------------------------------

@admin_bp.route("/api/admin/pincodes", methods=["GET"])
@login_required
@role_required(UserRole.admin.value)
def admin_list_pincodes():
    """List all serviceable pincodes for Mysuru."""
    db = SessionLocal()
    try:
        pins = db.query(ServiceablePincode).order_by(ServiceablePincode.pincode.asc()).all()
        return jsonify({
            "success": True,
            "count": len(pins),
            "pincodes": [p.to_dict() for p in pins]
        }), 200
    finally:
        db.close()


@admin_bp.route("/api/admin/pincodes", methods=["POST"])
@login_required
@role_required(UserRole.admin.value)
def admin_add_pincode():
    """Add a new serviceable pincode in Mysuru."""
    data = request.get_json(silent=True) or {}
    pincode = (data.get("pincode") or "").strip()
    area_name = (data.get("area_name") or "").strip()
    city = (data.get("city") or "Mysuru").strip()

    if not pincode or not area_name:
        return jsonify({"success": False, "error": "Pincode and area name are required."}), 400

    db = SessionLocal()
    try:
        existing = db.query(ServiceablePincode).filter_by(pincode=pincode).first()
        if existing:
            existing.area_name = area_name
            existing.is_active = True
            db.commit()
            db.refresh(existing)
            return jsonify({"success": True, "pincode": existing.to_dict()}), 200

        record = ServiceablePincode(
            pincode=pincode,
            area_name=area_name,
            city=city,
            is_active=True
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        return jsonify({"success": True, "pincode": record.to_dict()}), 201
    finally:
        db.close()


@admin_bp.route("/api/admin/pincodes/<int:pincode_id>", methods=["PUT"])
@login_required
@role_required(UserRole.admin.value)
def admin_update_pincode(pincode_id: int):
    """Toggle active status or update area name for a pincode."""
    data = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        record = db.query(ServiceablePincode).filter_by(id=pincode_id).first()
        if not record:
            return jsonify({"success": False, "error": "Pincode record not found."}), 404

        if "area_name" in data:
            record.area_name = data["area_name"].strip()
        if "is_active" in data:
            record.is_active = bool(data["is_active"])

        db.commit()
        db.refresh(record)
        return jsonify({"success": True, "pincode": record.to_dict()}), 200
    finally:
        db.close()


@admin_bp.route("/api/admin/pincodes/<int:pincode_id>", methods=["DELETE"])
@login_required
@role_required(UserRole.admin.value)
def admin_delete_pincode(pincode_id: int):
    """Delete or deactivate a pincode."""
    db = SessionLocal()
    try:
        record = db.query(ServiceablePincode).filter_by(id=pincode_id).first()
        if not record:
            return jsonify({"success": False, "error": "Pincode record not found."}), 404

        db.delete(record)
        db.commit()
        return jsonify({"success": True, "message": "Pincode removed."}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Admin Price Matrix Management
# ---------------------------------------------------------------------------

@admin_bp.route("/api/admin/price-matrix", methods=["GET"])
@login_required
@role_required(UserRole.admin.value)
def admin_list_price_matrix():
    """List price matrix rules."""
    db = SessionLocal()
    try:
        rules = db.query(PriceMatrix).order_by(PriceMatrix.brand.asc(), PriceMatrix.model.asc()).all()
        return jsonify({
            "success": True,
            "count": len(rules),
            "price_matrix": [r.to_dict() for r in rules]
        }), 200
    finally:
        db.close()


@admin_bp.route("/api/admin/price-matrix", methods=["POST"])
@login_required
@role_required(UserRole.admin.value)
def admin_add_or_update_price_matrix():
    """Create or update a valuation price matrix entry."""
    data = request.get_json(silent=True) or {}
    brand = (data.get("brand") or "").strip()
    model = (data.get("model") or "").strip()
    storage_gb = int(data.get("storage_gb") or 128)
    base_price = float(data.get("base_price") or 0.0)

    if not brand or not model or base_price <= 0:
        return jsonify({"success": False, "error": "Brand, model, and valid base price are required."}), 400

    db = SessionLocal()
    try:
        rule = db.query(PriceMatrix).filter_by(brand=brand, model=model, storage_gb=storage_gb).first()
        if not rule:
            rule = PriceMatrix(
                brand=brand,
                model=model,
                storage_gb=storage_gb,
                base_price=base_price,
                screen_scratch_pct=float(data.get("screen_scratch_pct", 10.0)),
                screen_cracked_pct=float(data.get("screen_cracked_pct", 35.0)),
                body_dent_pct=float(data.get("body_dent_pct", 12.0)),
                battery_low_pct=float(data.get("battery_low_pct", 15.0)),
                camera_fault_pct=float(data.get("camera_fault_pct", 20.0)),
                speaker_fault_pct=float(data.get("speaker_fault_pct", 10.0)),
                accessories_deduction=float(data.get("accessories_deduction", 1000.0)),
                is_active=bool(data.get("is_active", True))
            )
            db.add(rule)
        else:
            rule.base_price = base_price
            if "screen_scratch_pct" in data:
                rule.screen_scratch_pct = float(data["screen_scratch_pct"])
            if "screen_cracked_pct" in data:
                rule.screen_cracked_pct = float(data["screen_cracked_pct"])
            if "body_dent_pct" in data:
                rule.body_dent_pct = float(data["body_dent_pct"])
            if "battery_low_pct" in data:
                rule.battery_low_pct = float(data["battery_low_pct"])
            if "camera_fault_pct" in data:
                rule.camera_fault_pct = float(data["camera_fault_pct"])
            if "speaker_fault_pct" in data:
                rule.speaker_fault_pct = float(data["speaker_fault_pct"])
            if "accessories_deduction" in data:
                rule.accessories_deduction = float(data["accessories_deduction"])
            if "is_active" in data:
                rule.is_active = bool(data["is_active"])

        db.commit()
        db.refresh(rule)
        return jsonify({"success": True, "rule": rule.to_dict()}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Admin Sell Requests & Conversion Analytics
# ---------------------------------------------------------------------------

@admin_bp.route("/api/admin/sell-requests", methods=["GET"])
@login_required
@role_required(UserRole.admin.value)
def admin_list_sell_requests():
    """List all customer sell requests with funnel and conversion stats."""
    db = SessionLocal()
    try:
        requests_list = db.query(SellRequest).order_by(SellRequest.created_at.desc()).all()

        total = len(requests_list)
        paid_count = sum(1 for r in requests_list if r.status == SellRequestStatus.paid.value)
        inspected_count = sum(1 for r in requests_list if r.status in (
            SellRequestStatus.inspected.value, SellRequestStatus.offer_revised.value,
            SellRequestStatus.accepted.value, SellRequestStatus.paid.value
        ))
        total_payout_amount = sum(float(r.final_offer_price or 0.0) for r in requests_list if r.status == SellRequestStatus.paid.value)

        conversion_rate = (paid_count / total * 100.0) if total > 0 else 0.0

        return jsonify({
            "success": True,
            "metrics": {
                "total_requests": total,
                "inspected_count": inspected_count,
                "paid_count": paid_count,
                "conversion_rate_pct": round(conversion_rate, 1),
                "total_payout_amount": total_payout_amount
            },
            "requests": [r.to_dict() for r in requests_list]
        }), 200
    finally:
        db.close()

