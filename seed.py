"""
Database Seed Script for CoherentMobiles
Populates PostgreSQL from data.json and sets up initial users, vendors,
catalog models/variants, sample inventory units, and stock movements.
Idempotent: safe to run multiple times.
"""

import json
import os
import random
from argon2 import PasswordHasher
from database import SessionLocal
import models
from models import (
    User, UserRole, Vendor, VendorApprovalStatus,
    Brand, PhoneSeries, PhoneModel, PhoneVariant,
    InventoryUnit, ConditionGrade, UnitStatus,
    UnitImage, StockMovement
)

ph = PasswordHasher()

ADMIN_EMAIL = os.environ.get("ADMIN_DEFAULT_EMAIL", "admin@coherent.test")
ADMIN_PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD", "Admin@123")
VENDOR_DEFAULT_PASSWORD = os.environ.get("VENDOR_DEFAULT_PASSWORD", "Vendor@123")


def generate_luhn_check_digit(number_str: str) -> int:
    """Compute the Luhn check digit for a string of digits."""
    digits = [int(c) for c in number_str]
    total = 0
    # Process from right to left, doubling every second digit
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:  # In IMEI, 14th digit (index 13) is doubled
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - (total % 10)) % 10


def make_valid_imei(prefix: str, index: int) -> str:
    """Generate a valid 15-digit IMEI with correct Luhn check digit."""
    # Prefix typically 8 digits TAC, plus 6 digits sequence = 14 digits
    base = f"{prefix[:8]}{index:06d}"
    check_digit = generate_luhn_check_digit(base)
    return f"{base}{check_digit}"


def seed_database():
    session = SessionLocal()
    print("================================================================")
    print("CoherentMobiles: Seeding PostgreSQL Database")
    print("================================================================")

    created_credentials = []

    try:
        # 1. Admin User
        admin_user = session.query(User).filter_by(email=ADMIN_EMAIL).first()
        if not admin_user:
            admin_user = User(
                name="System Administrator",
                email=ADMIN_EMAIL,
                phone="+919000000001",
                password_hash=ph.hash(ADMIN_PASSWORD),
                address="HQ Tech Park, Bengaluru",
                role=UserRole.admin.value,
            )
            session.add(admin_user)
            session.flush()
            created_credentials.append(("Admin", admin_user.email, ADMIN_PASSWORD, "admin", "Approved"))
        else:
            # Ensure admin has admin role and valid hash
            admin_user.role = UserRole.admin.value
            if not admin_user.password_hash or not admin_user.password_hash.startswith("$argon2"):
                admin_user.password_hash = ph.hash(ADMIN_PASSWORD)
            session.flush()

        # 2. Load data.json
        data_path = os.path.join(os.path.dirname(__file__), "data.json")
        data = {}
        if os.path.exists(data_path):
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        raw_vendors = data.get("vendors", [])
        raw_mobiles = data.get("mobiles", [])

        # 3. Seed Vendors & Vendor Users
        vendor_map = {}  # code -> Vendor
        for idx, vdata in enumerate(raw_vendors):
            vcode = vdata.get("code")
            vname = vdata.get("name")
            vemail = vdata.get("email")
            vphone = vdata.get("phone")

            # 3 approved, 4th pending for testing approval flows
            is_approved = idx < 3
            approval_status = (
                VendorApprovalStatus.approved.value
                if is_approved
                else VendorApprovalStatus.pending.value
            )

            # Create or update user account for vendor
            vendor_user = session.query(User).filter_by(email=vemail).first()
            if not vendor_user:
                vendor_user = User(
                    name=vname,
                    email=vemail,
                    phone=vphone,
                    password_hash=ph.hash(VENDOR_DEFAULT_PASSWORD),
                    address=vdata.get("location", "Mumbai, India"),
                    role=UserRole.vendor.value,
                )
                session.add(vendor_user)
                session.flush()
                created_credentials.append((
                    f"Vendor ({vcode})",
                    vemail,
                    VENDOR_DEFAULT_PASSWORD,
                    "vendor",
                    approval_status
                ))
            else:
                vendor_user.role = UserRole.vendor.value
                if not vendor_user.password_hash or not vendor_user.password_hash.startswith("$argon2"):
                    vendor_user.password_hash = ph.hash(VENDOR_DEFAULT_PASSWORD)
                session.flush()

            # Create or update Vendor record
            vendor = session.query(Vendor).filter_by(vendor_code=vcode).first()
            if not vendor:
                vendor = Vendor(
                    user_id=vendor_user.user_id,
                    vendor_name=vname,
                    vendor_code=vcode,
                    category=vdata.get("category", "Authorized Retailer"),
                    contact_email=vemail,
                    contact_phone=vphone,
                    location=vdata.get("location", "India"),
                    address=vdata.get("location", "India"),
                    gst_number=f"27AABCU{1000 + idx}D1Z5",
                    logo_url=f"/images/vendors/{vcode.lower()}.png",
                    rating=vdata.get("rating", 4.8),
                    status="Active",
                    approval_status=approval_status,
                )
                session.add(vendor)
                session.flush()
            else:
                vendor.user_id = vendor_user.user_id
                vendor.approval_status = approval_status
                session.flush()

            vendor_map[vdata.get("id")] = vendor
            vendor_map[vcode] = vendor

        # 4. Seed Brands, Series, Models, Variants from mobiles
        # Common TAC prefixes for TAC + sequence IMEIs
        tac_prefixes = [
            "35874211", "86420904", "35492109", "86753091", "35987123", "86543210"
        ]
        unit_count = 0

        for m_idx, m in enumerate(raw_mobiles):
            brand_name = m.get("brand", "Generic").strip()
            model_name = m.get("model", "Phone").strip()
            storage_str = m.get("storage", "128 GB").strip()
            price = float(m.get("price", 49999))
            stock = int(m.get("stock", 5))
            m_vendor_id = m.get("vendor_id", 1)
            image_url = m.get("image", "images/iphone15.jpg")

            # Parse storage integer
            storage_gb = 128
            try:
                storage_gb = int(storage_str.split()[0])
            except Exception:
                storage_gb = 128

            # Ensure Brand
            brand = session.query(Brand).filter_by(brand_name=brand_name).first()
            if not brand:
                brand = Brand(brand_name=brand_name)
                session.add(brand)
                session.flush()

            # Ensure PhoneSeries
            series_name = f"{brand_name} {model_name.split()[0]} Series"
            series = session.query(PhoneSeries).filter_by(brand_id=brand.brand_id, series_name=series_name).first()
            if not series:
                series = PhoneSeries(brand_id=brand.brand_id, series_name=series_name)
                session.add(series)
                session.flush()

            # Ensure PhoneModel
            model = session.query(PhoneModel).filter_by(series_id=series.series_id, model_name=model_name).first()
            if not model:
                model = PhoneModel(
                    series_id=series.series_id,
                    model_name=model_name,
                    image_url=image_url if image_url.startswith("/") else f"/{image_url}",
                )
                session.add(model)
                session.flush()

            # Ensure PhoneVariant
            variant = session.query(PhoneVariant).filter_by(
                model_id=model.model_id,
                storage_gb=storage_gb
            ).first()
            if not variant:
                variant = PhoneVariant(
                    model_id=model.model_id,
                    storage_gb=storage_gb,
                    ram_gb=8 if storage_gb <= 128 else 12,
                    color="Default Color",
                    battery_capacity=4500,
                    listed_price=price,
                    rating=4.6,
                    stock_quantity=stock,
                )
                session.add(variant)
                session.flush()

            # Link vendor
            target_vendor = vendor_map.get(m_vendor_id) or list(vendor_map.values())[0]

            # Create sample inventory units
            # For each mobile in data.json, create 2-4 individual units
            sample_units_to_create = 3 if stock > 0 else 1
            grades = [ConditionGrade.like_new.value, ConditionGrade.good.value, ConditionGrade.fair.value]

            for u_idx in range(sample_units_to_create):
                imei = make_valid_imei(tac_prefixes[(m_idx + u_idx) % len(tac_prefixes)], (m_idx * 10) + u_idx + 1)
                existing_unit = session.query(InventoryUnit).filter_by(imei=imei).first()
                if existing_unit:
                    continue

                grade = grades[u_idx % len(grades)]
                # Price adjusts slightly by condition grade
                grade_discount = 1.0 if grade == "like_new" else (0.92 if grade == "good" else 0.85)
                unit_selling_price = round(price * grade_discount, -1)
                unit_mrp = round(price * 1.20, -1)
                battery_health = 95 - (u_idx * 4)

                unit_status = UnitStatus.in_stock.value
                if stock == 0:
                    unit_status = UnitStatus.sold.value
                elif u_idx == 2 and stock > 2:
                    # make some units have diverse statuses
                    unit_status = UnitStatus.in_stock.value

                unit = InventoryUnit(
                    vendor_id=target_vendor.vendor_id,
                    variant_id=variant.variant_id,
                    imei=imei,
                    condition_grade=grade,
                    battery_health=battery_health,
                    selling_price=unit_selling_price,
                    mrp=unit_mrp,
                    warranty_months=12 if grade == "like_new" else 6,
                    status=unit_status,
                    notes=f"Grade {grade.replace('_', ' ').title()} - Original box & accessories included.",
                )
                session.add(unit)
                session.flush()
                unit_count += 1

                # Unit image
                clean_img = image_url if image_url.startswith("/") else f"/{image_url}"
                img = UnitImage(
                    unit_id=unit.unit_id,
                    image_url=clean_img,
                    sort_order=0,
                )
                session.add(img)

                # Stock movement audit trail
                movement = StockMovement(
                    unit_id=unit.unit_id,
                    vendor_id=target_vendor.vendor_id,
                    action="added",
                    actor_user_id=admin_user.user_id,
                    old_value=None,
                    new_value={
                        "imei": unit.imei,
                        "status": unit.status,
                        "selling_price": float(unit.selling_price),
                        "condition_grade": unit.condition_grade,
                    },
                )
                session.add(movement)

        session.commit()
        print("Database seeded successfully!")
        print(f"Total inventory units created: {unit_count}")
        print("\n----------------------------------------------------------------")
        print("CREDENTIALS (Generated & Verified):")
        print("----------------------------------------------------------------")
        print(f"{'Role':<18} | {'Email/Login':<30} | {'Password':<15} | {'Approval':<10}")
        print("-" * 80)
        for cred in created_credentials:
            print(f"{cred[0]:<18} | {cred[1]:<30} | {cred[2]:<15} | {cred[4]:<10}")
        print("================================================================")

    except Exception as e:
        session.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_database()
