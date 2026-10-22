import csv
import io
import os
import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g, send_file, Response
from werkzeug.utils import secure_filename
from sqlalchemy import func, extract

from database import SessionLocal
import models
from models import (
    User, UserRole, Vendor, VendorApprovalStatus,
    Brand, PhoneSeries, PhoneModel, PhoneVariant,
    InventoryUnit, ConditionGrade, UnitStatus,
    UnitImage, Order, OrderItem, StockMovement, utc_now
)
from auth import login_required, role_required, approved_vendor_required

vendor_bp = Blueprint("vendor", __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_IMAGES_PER_UNIT = 6

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_imei_luhn(imei: str) -> bool:
    """Validate 15-digit IMEI with Luhn checksum."""
    if not imei or not isinstance(imei, str):
        return False
    imei = imei.strip()
    if len(imei) != 15 or not imei.isdigit():
        return False
    digits = [int(c) for c in imei]
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def record_stock_movement(db, unit_id: int, vendor_id: int, action: str, actor_user_id: int, old_val: dict, new_val: dict):
    movement = StockMovement(
        unit_id=unit_id,
        vendor_id=vendor_id,
        action=action,
        actor_user_id=actor_user_id,
        old_value=old_val,
        new_value=new_val,
        created_at=utc_now()
    )
    db.add(movement)


# ---------------------------------------------------------------------------
# Vendor Inventory Management
# ---------------------------------------------------------------------------

@vendor_bp.route("/api/vendor/inventory", methods=["GET"])
@login_required
@role_required(UserRole.vendor.value)
def get_vendor_inventory():
    """List inventory units for the authenticated vendor with filters and pagination."""
    vendor_id = g.vendor.vendor_id
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()
    brand_filter = request.args.get("brand", "").strip()
    grade_filter = request.args.get("grade", "").strip()
    page = max(1, int(request.args.get("page", 1)))
    per_page = max(1, min(100, int(request.args.get("per_page", 15))))

    db = SessionLocal()
    try:
        query = db.query(InventoryUnit).join(InventoryUnit.variant).join(PhoneVariant.model).join(PhoneModel.series).join(PhoneSeries.brand).filter(
            InventoryUnit.vendor_id == vendor_id,
            InventoryUnit.deleted_at.is_(None)
        )

        if status_filter:
            query = query.filter(InventoryUnit.status == status_filter)
        if grade_filter:
            query = query.filter(InventoryUnit.condition_grade == grade_filter)
        if brand_filter:
            query = query.filter(Brand.brand_name.ilike(brand_filter))
        if search:
            query = query.filter(
                (InventoryUnit.imei.ilike(f"%{search}%")) |
                (PhoneModel.model_name.ilike(f"%{search}%")) |
                (Brand.brand_name.ilike(f"%{search}%"))
            )

        total = query.count()
        units = query.order_by(InventoryUnit.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

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


@vendor_bp.route("/api/vendor/inventory", methods=["POST"])
@approved_vendor_required
def add_inventory_unit():
    """Add a single inventory unit with optional multi-image upload."""
    vendor_id = g.vendor.vendor_id
    actor_id = g.user.user_id

    # Handle JSON or multipart/form-data
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict()

    brand_name = (data.get("brand") or "").strip()
    model_name = (data.get("model") or "").strip()
    storage_val = data.get("storage_gb") or data.get("storage") or 128
    ram_val = data.get("ram_gb") or data.get("ram") or 8
    color = (data.get("color") or "Standard").strip()
    imei = (data.get("imei") or "").strip()
    condition_grade = (data.get("condition_grade") or data.get("grade") or "good").strip().lower()
    battery_health = data.get("battery_health")
    selling_price = data.get("selling_price") or data.get("price")
    mrp = data.get("mrp")
    warranty_months = data.get("warranty_months") or 6
    status = (data.get("status") or UnitStatus.in_stock.value).strip()
    notes = (data.get("notes") or "").strip()

    # Validations
    if not brand_name or not model_name:
        return jsonify({"success": False, "error": "Brand and Model name are required."}), 400
    if not imei:
        return jsonify({"success": False, "error": "IMEI number is required."}), 400
    if not validate_imei_luhn(imei):
        return jsonify({"success": False, "error": "Invalid 15-digit IMEI number (failed Luhn checksum verification)."}), 400

    try:
        storage_gb = int(str(storage_val).split()[0])
        ram_gb = int(str(ram_val).split()[0])
    except Exception:
        return jsonify({"success": False, "error": "Storage and RAM must be numeric GB values."}), 400

    try:
        selling_price = float(selling_price)
        if selling_price <= 0:
            return jsonify({"success": False, "error": "Selling price must be greater than 0."}), 400
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Selling price must be a valid number."}), 400

    mrp_val = None
    if mrp:
        try:
            mrp_val = float(mrp)
        except (TypeError, ValueError):
            pass

    battery_val = None
    if battery_health is not None and str(battery_health).strip() != "":
        try:
            battery_val = int(battery_health)
            if battery_val < 0 or battery_val > 100:
                return jsonify({"success": False, "error": "Battery health must be between 0 and 100."}), 400
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Battery health must be an integer."}), 400

    if condition_grade not in ("like_new", "good", "fair"):
        condition_grade = "good"

    if status not in ("in_stock", "reserved", "sold", "hidden"):
        status = "in_stock"

    db = SessionLocal()
    try:
        # Check IMEI uniqueness
        existing_imei = db.query(InventoryUnit).filter_by(imei=imei).first()
        if existing_imei:
            return jsonify({"success": False, "error": f"An inventory unit with IMEI '{imei}' already exists."}), 400

        # Resolve or create Brand
        brand = db.query(Brand).filter(Brand.brand_name.ilike(brand_name)).first()
        if not brand:
            brand = Brand(brand_name=brand_name)
            db.add(brand)
            db.flush()

        # Resolve or create PhoneSeries
        series_name = f"{brand.brand_name} {model_name.split()[0]} Series"
        series = db.query(PhoneSeries).filter_by(brand_id=brand.brand_id, series_name=series_name).first()
        if not series:
            series = PhoneSeries(brand_id=brand.brand_id, series_name=series_name)
            db.add(series)
            db.flush()

        # Resolve or create PhoneModel
        model = db.query(PhoneModel).filter_by(series_id=series.series_id, model_name=model_name).first()
        if not model:
            model = PhoneModel(
                series_id=series.series_id,
                model_name=model_name,
                image_url=f"/images/{model_name.lower().replace(' ', '')}.jpg"
            )
            db.add(model)
            db.flush()

        # Resolve or create PhoneVariant
        variant = db.query(PhoneVariant).filter_by(
            model_id=model.model_id,
            storage_gb=storage_gb,
            ram_gb=ram_gb,
            color=color
        ).first()
        if not variant:
            variant = PhoneVariant(
                model_id=model.model_id,
                storage_gb=storage_gb,
                ram_gb=ram_gb,
                color=color,
                battery_capacity=4500,
                listed_price=selling_price,
                stock_quantity=1
            )
            db.add(variant)
            db.flush()
        else:
            variant.stock_quantity = (variant.stock_quantity or 0) + 1

        # Create InventoryUnit
        unit = InventoryUnit(
            vendor_id=vendor_id,
            variant_id=variant.variant_id,
            imei=imei,
            condition_grade=condition_grade,
            battery_health=battery_val,
            selling_price=selling_price,
            mrp=mrp_val or round(selling_price * 1.15, -1),
            warranty_months=int(warranty_months),
            status=status,
            notes=notes
        )
        db.add(unit)
        db.flush()

        # Handle uploaded images
        uploaded_files = request.files.getlist("images")
        if not uploaded_files and "image" in request.files:
            uploaded_files = [request.files["image"]]

        valid_files = [f for f in uploaded_files if f and f.filename and allowed_file(f.filename)]
        for s_order, file in enumerate(valid_files[:MAX_IMAGES_PER_UNIT]):
            ext = file.filename.rsplit(".", 1)[1].lower()
            unique_fname = f"{uuid.uuid4().hex}.{ext}"
            file_path = os.path.join(UPLOAD_FOLDER, unique_fname)
            file.save(file_path)
            unit_img = UnitImage(
                unit_id=unit.unit_id,
                image_url=f"/uploads/{unique_fname}",
                sort_order=s_order
            )
            db.add(unit_img)

        # Audit movement
        record_stock_movement(
            db=db,
            unit_id=unit.unit_id,
            vendor_id=vendor_id,
            action="added",
            actor_user_id=actor_id,
            old_val=None,
            new_val={
                "imei": unit.imei,
                "price": float(unit.selling_price),
                "status": unit.status,
                "grade": unit.condition_grade
            }
        )

        db.commit()
        db.refresh(unit)

        return jsonify({
            "success": True,
            "message": "Inventory unit registered successfully.",
            "unit": unit.to_dict()
        }), 201
    finally:
        db.close()


@vendor_bp.route("/api/vendor/inventory/<int:unit_id>", methods=["PUT"])
@approved_vendor_required
def update_inventory_unit(unit_id: int):
    """Update price, status, condition, or notes of a vendor's unit. Cross-vendor access returns 404."""
    vendor_id = g.vendor.vendor_id
    actor_id = g.user.user_id
    data = request.get_json(silent=True) or {}

    db = SessionLocal()
    try:
        unit = db.query(InventoryUnit).filter(
            InventoryUnit.unit_id == unit_id,
            InventoryUnit.vendor_id == vendor_id,
            InventoryUnit.deleted_at.is_(None)
        ).first()

        if not unit:
            return jsonify({"success": False, "error": "Inventory unit not found or access denied."}), 404

        old_values = {
            "price": float(unit.selling_price),
            "status": unit.status,
            "condition_grade": unit.condition_grade,
            "battery_health": unit.battery_health
        }

        # Update price
        if "price" in data or "selling_price" in data:
            val = data.get("selling_price") if "selling_price" in data else data.get("price")
            try:
                new_price = float(val)
                if new_price > 0:
                    unit.selling_price = new_price
            except (TypeError, ValueError):
                pass

        if "mrp" in data:
            try:
                unit.mrp = float(data["mrp"])
            except (TypeError, ValueError):
                pass

        if "status" in data:
            st = str(data["status"]).strip().lower()
            if st in ("in_stock", "reserved", "sold", "hidden"):
                unit.status = st

        if "condition_grade" in data or "grade" in data:
            gr = (data.get("condition_grade") or data.get("grade")).strip().lower()
            if gr in ("like_new", "good", "fair"):
                unit.condition_grade = gr

        if "battery_health" in data:
            try:
                bh = int(data["battery_health"])
                if 0 <= bh <= 100:
                    unit.battery_health = bh
            except (TypeError, ValueError):
                pass

        if "warranty_months" in data:
            try:
                unit.warranty_months = int(data["warranty_months"])
            except (TypeError, ValueError):
                pass

        if "notes" in data:
            unit.notes = str(data["notes"]).strip()

        unit.updated_at = utc_now()

        new_values = {
            "price": float(unit.selling_price),
            "status": unit.status,
            "condition_grade": unit.condition_grade,
            "battery_health": unit.battery_health
        }

        record_stock_movement(
            db=db,
            unit_id=unit.unit_id,
            vendor_id=vendor_id,
            action="edited",
            actor_user_id=actor_id,
            old_val=old_values,
            new_val=new_values
        )

        db.commit()
        db.refresh(unit)

        return jsonify({
            "success": True,
            "message": "Unit updated successfully.",
            "unit": unit.to_dict()
        }), 200
    finally:
        db.close()


@vendor_bp.route("/api/vendor/inventory/<int:unit_id>", methods=["DELETE"])
@approved_vendor_required
def delete_inventory_unit(unit_id: int):
    """Soft delete an inventory unit. Cross-vendor access returns 404."""
    vendor_id = g.vendor.vendor_id
    actor_id = g.user.user_id

    db = SessionLocal()
    try:
        unit = db.query(InventoryUnit).filter(
            InventoryUnit.unit_id == unit_id,
            InventoryUnit.vendor_id == vendor_id,
            InventoryUnit.deleted_at.is_(None)
        ).first()

        if not unit:
            return jsonify({"success": False, "error": "Inventory unit not found or access denied."}), 404

        unit.deleted_at = utc_now()
        unit.status = UnitStatus.hidden.value

        record_stock_movement(
            db=db,
            unit_id=unit.unit_id,
            vendor_id=vendor_id,
            action="deleted",
            actor_user_id=actor_id,
            old_val={"status": unit.status, "deleted_at": None},
            new_val={"status": "hidden", "deleted_at": unit.deleted_at.isoformat()}
        )

        db.commit()
        return jsonify({"success": True, "message": "Inventory unit deleted successfully."}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Bulk CSV Upload & Template
# ---------------------------------------------------------------------------

@vendor_bp.route("/api/vendor/inventory/template.csv", methods=["GET"])
def download_csv_template():
    """Download standard CSV template for bulk inventory upload."""
    header = "brand,model,storage_gb,ram_gb,color,imei,condition_grade,battery_health,selling_price,mrp,warranty_months,notes\n"
    sample1 = "Apple,iPhone 15 Pro,256,8,Natural Titanium,358742110000010,like_new,98,94999,129999,12,Original box with cable\n"
    sample2 = "Samsung,Galaxy S24 Ultra,512,12,Titanium Gray,864209040000020,good,92,89999,119999,6,Minor scuffs on edge\n"
    csv_content = header + sample1 + sample2
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=inventory_template.csv"}
    )


@vendor_bp.route("/api/vendor/inventory/bulk", methods=["POST"])
@approved_vendor_required
def bulk_csv_upload():
    """Upload CSV to import multiple inventory units with per-row validation and error report."""
    vendor_id = g.vendor.vendor_id
    actor_id = g.user.user_id

    csv_file = request.files.get("file")
    csv_text = None

    if csv_file:
        try:
            csv_text = csv_file.read().decode("utf-8-sig")
        except Exception:
            return jsonify({"success": False, "error": "Failed to decode CSV file. Please upload a valid UTF-8 CSV."}), 400
    else:
        csv_text = request.data.decode("utf-8", errors="ignore")

    if not csv_text or not csv_text.strip():
        return jsonify({"success": False, "error": "No CSV content provided."}), 400

    db = SessionLocal()
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        errors = []
        created_count = 0
        batch_imeis = set()

        for row_num, row in enumerate(reader, start=2):
            brand_name = (row.get("brand") or "").strip()
            model_name = (row.get("model") or "").strip()
            imei = (row.get("imei") or "").strip()
            grade = (row.get("condition_grade") or row.get("grade") or "good").strip().lower()
            price_str = (row.get("selling_price") or row.get("price") or "").strip()

            if not brand_name or not model_name:
                errors.append({"row": row_num, "imei": imei, "error": "Missing brand or model name."})
                continue
            if not imei:
                errors.append({"row": row_num, "imei": "", "error": "Missing IMEI."})
                continue
            if not validate_imei_luhn(imei):
                errors.append({"row": row_num, "imei": imei, "error": "Invalid 15-digit IMEI or failed Luhn check."})
                continue
            if imei in batch_imeis:
                errors.append({"row": row_num, "imei": imei, "error": f"Duplicate IMEI '{imei}' within upload batch."})
                continue
            if db.query(InventoryUnit).filter_by(imei=imei).first():
                errors.append({"row": row_num, "imei": imei, "error": f"IMEI '{imei}' is already registered in the system."})
                continue

            try:
                price = float(price_str)
                if price <= 0:
                    errors.append({"row": row_num, "imei": imei, "error": "Selling price must be > 0."})
                    continue
            except Exception:
                errors.append({"row": row_num, "imei": imei, "error": f"Invalid price format '{price_str}'."})
                continue

            storage_gb = 128
            try:
                storage_gb = int(str(row.get("storage_gb") or "128").split()[0])
            except Exception:
                pass

            ram_gb = 8
            try:
                ram_gb = int(str(row.get("ram_gb") or "8").split()[0])
            except Exception:
                pass

            battery_health = None
            if row.get("battery_health"):
                try:
                    bh = int(row.get("battery_health"))
                    if 0 <= bh <= 100:
                        battery_health = bh
                except Exception:
                    pass

            mrp_val = round(price * 1.15, -1)
            if row.get("mrp"):
                try:
                    mrp_val = float(row.get("mrp"))
                except Exception:
                    pass

            warranty_months = 6
            if row.get("warranty_months"):
                try:
                    warranty_months = int(row.get("warranty_months"))
                except Exception:
                    pass

            # Resolve hierarchy
            brand = db.query(Brand).filter(Brand.brand_name.ilike(brand_name)).first()
            if not brand:
                brand = Brand(brand_name=brand_name)
                db.add(brand)
                db.flush()

            series_name = f"{brand.brand_name} {model_name.split()[0]} Series"
            series = db.query(PhoneSeries).filter_by(brand_id=brand.brand_id, series_name=series_name).first()
            if not series:
                series = PhoneSeries(brand_id=brand.brand_id, series_name=series_name)
                db.add(series)
                db.flush()

            model = db.query(PhoneModel).filter_by(series_id=series.series_id, model_name=model_name).first()
            if not model:
                model = PhoneModel(
                    series_id=series.series_id,
                    model_name=model_name,
                    image_url=f"/images/{model_name.lower().replace(' ', '')}.jpg"
                )
                db.add(model)
                db.flush()

            color = (row.get("color") or "Standard").strip()
            variant = db.query(PhoneVariant).filter_by(
                model_id=model.model_id,
                storage_gb=storage_gb,
                color=color
            ).first()
            if not variant:
                variant = PhoneVariant(
                    model_id=model.model_id,
                    storage_gb=storage_gb,
                    ram_gb=ram_gb,
                    color=color,
                    listed_price=price,
                    stock_quantity=1
                )
                db.add(variant)
                db.flush()

            unit = InventoryUnit(
                vendor_id=vendor_id,
                variant_id=variant.variant_id,
                imei=imei,
                condition_grade=grade if grade in ("like_new", "good", "fair") else "good",
                battery_health=battery_health,
                selling_price=price,
                mrp=mrp_val,
                warranty_months=warranty_months,
                status=UnitStatus.in_stock.value,
                notes=(row.get("notes") or "").strip()
            )
            db.add(unit)
            db.flush()

            batch_imeis.add(imei)
            created_count += 1

            record_stock_movement(
                db=db,
                unit_id=unit.unit_id,
                vendor_id=vendor_id,
                action="added",
                actor_user_id=actor_id,
                old_val=None,
                new_val={"imei": imei, "price": price, "source": "bulk_csv"}
            )

        db.commit()
        return jsonify({
            "success": True,
            "created_count": created_count,
            "failed_count": len(errors),
            "errors": errors
        }), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Vendor Dashboard Stats
# ---------------------------------------------------------------------------

@vendor_bp.route("/api/vendor/stats", methods=["GET"])
@login_required
@role_required(UserRole.vendor.value)
def get_vendor_stats():
    """Calculates vendor-specific operational and inventory metrics."""
    vendor_id = g.vendor.vendor_id
    now = utc_now()
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    db = SessionLocal()
    try:
        # Stock status counts
        in_stock_count = db.query(InventoryUnit).filter(
            InventoryUnit.vendor_id == vendor_id,
            InventoryUnit.status == UnitStatus.in_stock.value,
            InventoryUnit.deleted_at.is_(None)
        ).count()

        reserved_count = db.query(InventoryUnit).filter(
            InventoryUnit.vendor_id == vendor_id,
            InventoryUnit.status == UnitStatus.reserved.value,
            InventoryUnit.deleted_at.is_(None)
        ).count()

        # Sold this month from OrderItems
        sold_items_query = db.query(OrderItem).join(OrderItem.order).filter(
            OrderItem.vendor_id == vendor_id,
            Order.created_at >= month_start,
            OrderItem.item_status.in_(["confirmed", "packed", "shipped", "delivered"])
        )
        sold_this_month = sold_items_query.count()
        revenue_sum = sold_items_query.with_entities(func.sum(OrderItem.price)).scalar()
        revenue_this_month = float(revenue_sum or 0.0)

        # By brand distribution
        brand_counts = db.query(Brand.brand_name, func.count(InventoryUnit.unit_id)).join(
            PhoneSeries, Brand.brand_id == PhoneSeries.brand_id
        ).join(
            PhoneModel, PhoneSeries.series_id == PhoneModel.series_id
        ).join(
            PhoneVariant, PhoneModel.model_id == PhoneVariant.model_id
        ).join(
            InventoryUnit, PhoneVariant.variant_id == InventoryUnit.variant_id
        ).filter(
            InventoryUnit.vendor_id == vendor_id,
            InventoryUnit.status == UnitStatus.in_stock.value,
            InventoryUnit.deleted_at.is_(None)
        ).group_by(Brand.brand_name).all()

        by_brand = {b_name: cnt for b_name, cnt in brand_counts}

        # Low stock brands (< 3 units)
        low_stock_brands = [b for b, cnt in by_brand.items() if cnt < 3]

        return jsonify({
            "success": True,
            "stats": {
                "in_stock": in_stock_count,
                "reserved": reserved_count,
                "sold_this_month": sold_this_month,
                "revenue_this_month": revenue_this_month,
                "by_brand": by_brand,
                "low_stock_brands": low_stock_brands
            }
        }), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Vendor Orders Management
# ---------------------------------------------------------------------------

@vendor_bp.route("/api/vendor/orders", methods=["GET"])
@login_required
@role_required(UserRole.vendor.value)
def get_vendor_orders():
    """List orders containing units sold by this vendor."""
    vendor_id = g.vendor.vendor_id
    db = SessionLocal()
    try:
        items = db.query(OrderItem).join(OrderItem.order).filter(
            OrderItem.vendor_id == vendor_id
        ).order_by(Order.created_at.desc()).all()

        return jsonify({
            "success": True,
            "orders": [item.to_dict() for item in items]
        }), 200
    finally:
        db.close()


@vendor_bp.route("/api/vendor/orders/<int:order_item_id>/status", methods=["PUT"])
@login_required
@role_required(UserRole.vendor.value)
def update_order_item_status(order_item_id: int):
    """Update order fulfillment status: confirmed -> packed -> shipped -> delivered. Cross-vendor returns 404."""
    vendor_id = g.vendor.vendor_id
    data = request.get_json(silent=True) or {}
    new_status = (data.get("status") or "").strip().lower()

    valid_statuses = ("confirmed", "packed", "shipped", "delivered", "cancelled")
    if new_status not in valid_statuses:
        return jsonify({"success": False, "error": f"Invalid status '{new_status}'. Allowed: {valid_statuses}"}), 400

    db = SessionLocal()
    try:
        item = db.query(OrderItem).filter(
            OrderItem.order_item_id == order_item_id,
            OrderItem.vendor_id == vendor_id
        ).first()

        if not item:
            return jsonify({"success": False, "error": "Order item not found or unauthorized access."}), 404

        item.item_status = new_status
        db.commit()
        db.refresh(item)

        return jsonify({
            "success": True,
            "message": f"Order item status updated to '{new_status}'.",
            "item": item.to_dict()
        }), 200
    finally:
        db.close()
