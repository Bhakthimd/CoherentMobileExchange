from flask import Blueprint, request, jsonify
from sqlalchemy import or_, desc, asc

from database import SessionLocal
import models
from models import (
    Brand, PhoneSeries, PhoneModel, PhoneVariant,
    InventoryUnit, ConditionGrade, UnitStatus,
    Vendor, VendorApprovalStatus
)

catalog_bp = Blueprint("catalog", __name__)


@catalog_bp.route("/api/catalog", methods=["GET"])
def get_catalog():
    """
    Public catalog endpoint: returns only status=in_stock units from approved vendors.
    Supports filtering by brand, price range, storage, condition grade, search term, and sorting.
    """
    search = request.args.get("search", "").strip()
    brand_filter = request.args.get("brand", "").strip()
    grade_filter = request.args.get("grade", "").strip()
    storage_filter = request.args.get("storage", "").strip()
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    sort_by = request.args.get("sort", "newest").strip().lower()
    page = max(1, int(request.args.get("page", 1)))
    per_page = max(1, min(100, int(request.args.get("per_page", 12))))

    db = SessionLocal()
    try:
        query = db.query(InventoryUnit).join(InventoryUnit.vendor).join(InventoryUnit.variant).join(PhoneVariant.model).join(PhoneModel.series).join(PhoneSeries.brand).filter(
            InventoryUnit.status == UnitStatus.in_stock.value,
            InventoryUnit.deleted_at.is_(None),
            Vendor.approval_status == VendorApprovalStatus.approved.value
        )

        if brand_filter:
            query = query.filter(Brand.brand_name.ilike(brand_filter))
        if grade_filter:
            query = query.filter(InventoryUnit.condition_grade == grade_filter)
        if storage_filter:
            try:
                st_gb = int(storage_filter.split()[0])
                query = query.filter(PhoneVariant.storage_gb == st_gb)
            except Exception:
                pass
        if min_price is not None:
            query = query.filter(InventoryUnit.selling_price >= min_price)
        if max_price is not None:
            query = query.filter(InventoryUnit.selling_price <= max_price)
        if search:
            query = query.filter(
                or_(
                    Brand.brand_name.ilike(f"%{search}%"),
                    PhoneModel.model_name.ilike(f"%{search}%"),
                    InventoryUnit.notes.ilike(f"%{search}%")
                )
            )

        # Sorting
        if sort_by == "price_asc":
            query = query.order_by(asc(InventoryUnit.selling_price))
        elif sort_by == "price_desc":
            query = query.order_by(desc(InventoryUnit.selling_price))
        elif sort_by == "rating":
            query = query.order_by(desc(PhoneVariant.rating), desc(InventoryUnit.selling_price))
        else:  # newest
            query = query.order_by(desc(InventoryUnit.created_at))

        total = query.count()
        units = query.offset((page - 1) * per_page).limit(per_page).all()

        return jsonify({
            "success": True,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page if total > 0 else 1,
            "items": [u.to_dict() for u in units]
        }), 200
    finally:
        db.close()


@catalog_bp.route("/api/catalog/<int:unit_id>", methods=["GET"])
def get_catalog_unit(unit_id: int):
    """Retrieve details for a single in-stock device."""
    db = SessionLocal()
    try:
        unit = db.query(InventoryUnit).join(InventoryUnit.vendor).filter(
            InventoryUnit.unit_id == unit_id,
            InventoryUnit.status == UnitStatus.in_stock.value,
            InventoryUnit.deleted_at.is_(None),
            Vendor.approval_status == VendorApprovalStatus.approved.value
        ).first()

        if not unit:
            return jsonify({"success": False, "error": "This device is no longer available or was not found."}), 404

        return jsonify({
            "success": True,
            "unit": unit.to_dict()
        }), 200
    finally:
        db.close()


@catalog_bp.route("/api/brands", methods=["GET"])
def get_brands():
    """List all phone brands with in-stock unit counts."""
    db = SessionLocal()
    try:
        brands = db.query(Brand).order_by(Brand.brand_name).all()
        return jsonify({
            "success": True,
            "brands": [b.to_dict() for b in brands]
        }), 200
    finally:
        db.close()


@catalog_bp.route("/api/models", methods=["GET"])
def get_models():
    """List models, optionally filtered by brand_id or brand name."""
    brand_param = request.args.get("brand", "").strip()
    db = SessionLocal()
    try:
        query = db.query(PhoneModel).join(PhoneModel.series).join(PhoneSeries.brand)
        if brand_param:
            if brand_param.isdigit():
                query = query.filter(Brand.brand_id == int(brand_param))
            else:
                query = query.filter(Brand.brand_name.ilike(brand_param))
        models_list = query.order_by(PhoneModel.model_name).all()
        return jsonify({
            "success": True,
            "models": [m.to_dict() for m in models_list]
        }), 200
    finally:
        db.close()


@catalog_bp.route("/api/variants", methods=["GET"])
def get_variants():
    """List variants for a given model_id."""
    model_id = request.args.get("model_id", type=int)
    if not model_id:
        return jsonify({"success": False, "error": "model_id is required"}), 400

    db = SessionLocal()
    try:
        variants = db.query(PhoneVariant).filter_by(model_id=model_id).order_by(PhoneVariant.storage_gb).all()
        return jsonify({
            "success": True,
            "variants": [v.to_dict() for v in variants]
        }), 200
    finally:
        db.close()


@catalog_bp.route("/api/availability", methods=["GET"])
def get_availability():
    """
    Backwards compatible availability endpoint.
    Groups in-stock inventory units by model and vendor with price and condition comparisons.
    """
    db = SessionLocal()
    try:
        units = db.query(InventoryUnit).join(InventoryUnit.vendor).join(InventoryUnit.variant).join(PhoneVariant.model).join(PhoneModel.series).join(PhoneSeries.brand).filter(
            InventoryUnit.status == UnitStatus.in_stock.value,
            InventoryUnit.deleted_at.is_(None),
            Vendor.approval_status == VendorApprovalStatus.approved.value
        ).all()

        grouped = {}
        for u in units:
            m_name = u.variant.model.model_name if u.variant and u.variant.model else "Device"
            b_name = u.variant.model.series.brand.brand_name if u.variant and u.variant.model and u.variant.model.series else ""
            key = f"{b_name} {m_name}".strip()
            if key not in grouped:
                grouped[key] = {
                    "brand": b_name,
                    "model": m_name,
                    "image": u.variant.model.image_url if u.variant and u.variant.model else None,
                    "stores": []
                }
            grouped[key]["stores"].append({
                "unit_id": u.unit_id,
                "vendor_name": u.vendor.vendor_name,
                "vendor_code": u.vendor.vendor_code,
                "price": float(u.selling_price),
                "grade": u.condition_grade,
                "battery_health": u.battery_health,
                "warranty": f"{u.warranty_months} Months"
            })

        # Sort stores in each model by lowest price
        for k in grouped:
            grouped[k]["stores"].sort(key=lambda x: x["price"])

        return jsonify({
            "success": True,
            "availability": list(grouped.values())
        }), 200
    finally:
        db.close()
