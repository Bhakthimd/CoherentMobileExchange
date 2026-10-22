from flask import Blueprint, request, jsonify, g
from sqlalchemy import func, desc

from database import SessionLocal
import models
from models import (
    User, UserRole, Vendor, VendorApprovalStatus,
    InventoryUnit, UnitStatus, Order, OrderItem,
    Brand, PhoneModel, PhoneVariant, StockMovement
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
