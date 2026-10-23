"""
Database Seed Script for CoherentMobiles
Populates PostgreSQL from data.json and sets up initial users, vendors,
catalog models/variants, sample inventory units, and stock movements.
Idempotent: safe to run multiple times.
"""

import json
import os
import random
from datetime import datetime, timezone, timedelta, date
from argon2 import PasswordHasher
from database import SessionLocal
import models
from models import (
    User, UserRole, Vendor, VendorApprovalStatus,
    Brand, PhoneSeries, PhoneModel, PhoneVariant,
    InventoryUnit, ConditionGrade, UnitStatus,
    UnitImage, StockMovement, ServiceablePincode,
    PriceMatrix, SellRequest, SellRequestTimeline,
    Reservation, ReservationStatus, SellRequestStatus,
    FulfilmentType, utc_now
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

        # 3. Seed 5 K.T. Street Stores (+1 Pending Vendor)
        default_hours = {
            "monday": {"open": "10:00", "close": "21:00", "is_closed": False},
            "tuesday": {"open": "10:00", "close": "21:00", "is_closed": False},
            "wednesday": {"open": "10:00", "close": "21:00", "is_closed": False},
            "thursday": {"open": "10:00", "close": "21:00", "is_closed": False},
            "friday": {"open": "10:00", "close": "21:00", "is_closed": False},
            "saturday": {"open": "10:00", "close": "21:30", "is_closed": False},
            "sunday": {"open": "11:00", "close": "19:00", "is_closed": False},
        }

        sunday_closed_hours = dict(default_hours)
        sunday_closed_hours["sunday"] = {"open": "00:00", "close": "00:00", "is_closed": True}

        stores_metadata = [
            {
                "id": 1,
                "code": "IST-IND",
                "name": "Chamundi Mobile Galleria",
                "email": "istore@coherent.test",
                "phone": "+91 821 242 1001",
                "whatsapp": "+91 98450 11001",
                "address": "42 K.T. Street, Mandi Mohalla, Mysuru - 570001",
                "landmark": "Near D. Banumaiah Circle",
                "lat": 12.3052,
                "lng": 76.6551,
                "rating": 4.9,
                "approved": True,
                "hours": default_hours,
            },
            {
                "id": 2,
                "code": "APX-DST",
                "name": "Cauvery Phone Junction",
                "email": "apex@coherent.test",
                "phone": "+91 821 242 1002",
                "whatsapp": "+91 98450 11002",
                "address": "78 K.T. Street, Mandi Mohalla, Mysuru - 570001",
                "landmark": "Opp. Clock Tower Lane",
                "lat": 12.3058,
                "lng": 76.6548,
                "rating": 4.8,
                "approved": True,
                "hours": default_hours,
            },
            {
                "id": 3,
                "code": "GRN-TEL",
                "name": "Heritage Gadgets & Exchange",
                "email": "green@coherent.test",
                "phone": "+91 821 242 1003",
                "whatsapp": "+91 98450 11003",
                "address": "115 K.T. Street, Mandi Mohalla, Mysuru - 570001",
                "landmark": "Cross Road 2",
                "lat": 12.3065,
                "lng": 76.6545,
                "rating": 4.7,
                "approved": True,
                "hours": sunday_closed_hours,
            },
            {
                "id": 4,
                "code": "MMP-KTS",
                "name": "Mysuru Mobile Point",
                "email": "mysuru.point@coherent.test",
                "phone": "+91 821 242 1004",
                "whatsapp": "+91 98450 11004",
                "address": "152 K.T. Street, Mandi Mohalla, Mysuru - 570001",
                "landmark": "Near Central Market Gate",
                "lat": 12.3071,
                "lng": 76.6542,
                "rating": 4.85,
                "approved": True,
                "hours": default_hours,
            },
            {
                "id": 5,
                "code": "KRS-KTS",
                "name": "K.T. Street Refurb Studio",
                "email": "refurb.studio@coherent.test",
                "phone": "+91 821 242 1005",
                "whatsapp": "+91 98450 11005",
                "address": "204 K.T. Street, Mandi Mohalla, Mysuru - 570001",
                "landmark": "North End Corner",
                "lat": 12.3079,
                "lng": 76.6539,
                "rating": 4.95,
                "approved": True,
                "hours": default_hours,
            },
            {
                "id": 6,
                "code": "NX-HUB",
                "name": "Nexus Hub K.T. Street",
                "email": "nexus@coherent.test",
                "phone": "+91 821 242 1006",
                "whatsapp": "+91 98450 11006",
                "address": "260 K.T. Street, Mandi Mohalla, Mysuru - 570001",
                "landmark": "Near Irwin Road Junction",
                "lat": 12.3085,
                "lng": 76.6535,
                "rating": 4.5,
                "approved": False,
                "hours": default_hours,
            },
        ]

        vendor_map = {}  # code/id -> Vendor
        for idx, sdata in enumerate(stores_metadata):
            vcode = sdata["code"]
            vname = sdata["name"]
            vemail = sdata["email"]
            vphone = sdata["phone"]
            is_approved = sdata["approved"]
            approval_status = (
                VendorApprovalStatus.approved.value
                if is_approved
                else VendorApprovalStatus.pending.value
            )

            vendor_user = session.query(User).filter_by(email=vemail).first()
            if not vendor_user:
                vendor_user = User(
                    name=vname,
                    email=vemail,
                    phone=vphone,
                    password_hash=ph.hash(VENDOR_DEFAULT_PASSWORD),
                    address=sdata["address"],
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
                vendor_user.name = vname
                vendor_user.address = sdata["address"]
                if not vendor_user.password_hash or not vendor_user.password_hash.startswith("$argon2"):
                    vendor_user.password_hash = ph.hash(VENDOR_DEFAULT_PASSWORD)
                session.flush()

            vendor = session.query(Vendor).filter_by(vendor_code=vcode).first()
            if not vendor:
                vendor = Vendor(
                    user_id=vendor_user.user_id,
                    vendor_name=vname,
                    store_name=vname,
                    vendor_code=vcode,
                    category="Certified Refurb Store",
                    contact_email=vemail,
                    contact_phone=vphone,
                    location="K.T. Street, Mysuru",
                    address=sdata["address"],
                    address_line=sdata["address"],
                    landmark=sdata["landmark"],
                    area="K.T. Street",
                    city="Mysuru",
                    pincode="570001",
                    latitude=sdata["lat"],
                    longitude=sdata["lng"],
                    whatsapp_number=sdata["whatsapp"],
                    opening_hours=sdata["hours"],
                    accepts_walk_in=True,
                    offers_home_pickup=True,
                    offers_doorstep_delivery=True,
                    buyback_enabled=True,
                    store_photos=[
                        f"/images/stores/store_{idx + 1}_front.jpg",
                        f"/images/stores/store_{idx + 1}_inside.jpg"
                    ],
                    google_maps_url=f"https://www.google.com/maps/dir/?api=1&destination={sdata['lat']},{sdata['lng']}",
                    gst_number=f"29AABCU{1000 + idx}D1Z5",
                    logo_url=f"/images/vendors/{vcode.lower()}.png",
                    rating=sdata["rating"],
                    status="Active" if is_approved else "Pending Verification",
                    approval_status=approval_status,
                )
                session.add(vendor)
                session.flush()
            else:
                vendor.user_id = vendor_user.user_id
                vendor.store_name = vname
                vendor.vendor_name = vname
                vendor.address = sdata["address"]
                vendor.address_line = sdata["address"]
                vendor.landmark = sdata["landmark"]
                vendor.area = "K.T. Street"
                vendor.city = "Mysuru"
                vendor.pincode = "570001"
                vendor.latitude = sdata["lat"]
                vendor.longitude = sdata["lng"]
                vendor.whatsapp_number = sdata["whatsapp"]
                vendor.opening_hours = sdata["hours"]
                vendor.accepts_walk_in = True
                vendor.offers_home_pickup = True
                vendor.offers_doorstep_delivery = True
                vendor.buyback_enabled = True
                vendor.google_maps_url = f"https://www.google.com/maps/dir/?api=1&destination={sdata['lat']},{sdata['lng']}"
                vendor.approval_status = approval_status
                session.flush()

            vendor_map[sdata["id"]] = vendor
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

        # 5. Seed Serviceable Mysuru Pincodes
        mysuru_pincodes = [
            ("570001", "K.T. Street, Mandi Mohalla, Mysuru City"),
            ("570002", "Lashkar Mohalla, Doora"),
            ("570004", "Vontikoppal, Yadavagiri"),
            ("570005", "Jayalakshmipuram, Gokulam 1st Stage"),
            ("570006", "Gokulam 2nd & 3rd Stage"),
            ("570008", "Kuvempunagar, Jayanagar"),
            ("570009", "Saraswathipuram, Tonachikoppal"),
            ("570010", "Nazarbad, Ittigegud"),
            ("570012", "Siddhartha Layout, Alanahalli"),
            ("570017", "Hebbal 1st & 2nd Stage"),
            ("570020", "Vijayanagar 1st, 2nd, 3rd Stage"),
            ("570024", "Alanahalli, Chamundi Foothills"),
        ]
        for pin, area in mysuru_pincodes:
            existing_pin = session.query(ServiceablePincode).filter_by(pincode=pin).first()
            if not existing_pin:
                session.add(ServiceablePincode(
                    pincode=pin,
                    area_name=area,
                    city="Mysuru",
                    is_active=True
                ))
            else:
                existing_pin.area_name = area
                existing_pin.is_active = True
        session.flush()

        # 6. Seed Price Matrix for Instant Valuations
        matrix_data = [
            ("Apple", "iPhone 15", 128, 46000),
            ("Apple", "iPhone 15", 256, 53000),
            ("Apple", "iPhone 14", 128, 36000),
            ("Apple", "iPhone 14", 256, 41000),
            ("Apple", "iPhone 13", 128, 28000),
            ("Apple", "iPhone 12", 128, 21000),
            ("Samsung", "Galaxy S23 Ultra", 256, 55000),
            ("Samsung", "Galaxy S23", 128, 34000),
            ("Samsung", "Galaxy S22", 128, 24000),
            ("OnePlus", "12", 256, 38000),
            ("OnePlus", "11", 128, 27000),
            ("Google", "Pixel 8", 128, 32000),
            ("Google", "Pixel 7", 128, 22000),
            ("Xiaomi", "13 Pro", 256, 29000),
        ]
        for brand_m, model_m, storage_m, base_p in matrix_data:
            existing_pm = session.query(PriceMatrix).filter_by(
                brand=brand_m, model=model_m, storage_gb=storage_m
            ).first()
            if not existing_pm:
                session.add(PriceMatrix(
                    brand=brand_m,
                    model=model_m,
                    storage_gb=storage_m,
                    base_price=base_p,
                    screen_scratch_pct=10.0,
                    screen_cracked_pct=35.0,
                    body_dent_pct=12.0,
                    battery_low_pct=15.0,
                    camera_fault_pct=20.0,
                    speaker_fault_pct=10.0,
                    accessories_deduction=1000.0,
                    is_active=True
                ))
            else:
                existing_pm.base_price = base_p
                existing_pm.is_active = True
        session.flush()

        # 7. Seed Sample Sell Request & Timeline
        sample_store = vendor_map.get(1)
        if sample_store:
            existing_sr = session.query(SellRequest).filter_by(request_reference="SELL-MYS-001").first()
            if not existing_sr:
                sr_imei = make_valid_imei("35874299", 88812)
                sr = SellRequest(
                    request_reference="SELL-MYS-001",
                    customer_name="Praveen Kumar",
                    customer_phone="+919880123456",
                    customer_email="praveen.mysuru@example.com",
                    customer_address="14, Gokulam 3rd Stage, Mysuru",
                    pincode="570006",
                    store_id=sample_store.vendor_id,
                    brand="Apple",
                    model="iPhone 13",
                    storage_gb=128,
                    imei=sr_imei,
                    condition_answers={
                        "screen": "flawless",
                        "body": "minor_scratches",
                        "battery": "above_85",
                        "camera": "working",
                        "speaker": "working",
                        "accessories": ["box", "charger"]
                    },
                    estimated_min_price=24500,
                    estimated_max_price=27000,
                    final_offer_price=26000,
                    final_offer_notes="Flawless screen, 89% battery health. Accepted offer.",
                    fulfilment_type=FulfilmentType.store_visit.value,
                    slot_date=date.today(),
                    slot_time="11:30 AM",
                    status=SellRequestStatus.paid.value,
                    payout_method="upi",
                    payout_reference="UPI/2026/MYS/9880123456",
                    paid_at=utc_now(),
                )
                session.add(sr)
                session.flush()

                # Add timeline steps
                tl1 = SellRequestTimeline(
                    request_id=sr.request_id,
                    from_status=None,
                    to_status=SellRequestStatus.submitted.value,
                    actor_role="customer",
                    notes="Sell request submitted for store visit at Chamundi Mobile Galleria."
                )
                tl2 = SellRequestTimeline(
                    request_id=sr.request_id,
                    from_status=SellRequestStatus.submitted.value,
                    to_status=SellRequestStatus.store_confirmed.value,
                    actor_role="vendor",
                    notes="Store confirmed the appointment slot."
                )
                tl3 = SellRequestTimeline(
                    request_id=sr.request_id,
                    from_status=SellRequestStatus.store_confirmed.value,
                    to_status=SellRequestStatus.inspected.value,
                    actor_role="vendor",
                    notes="15-point physical diagnostics completed. Screen perfect, minor body scuffs."
                )
                tl4 = SellRequestTimeline(
                    request_id=sr.request_id,
                    from_status=SellRequestStatus.inspected.value,
                    to_status=SellRequestStatus.offer_revised.value,
                    actor_role="vendor",
                    notes="Final offer set to Rs. 26,000."
                )
                tl5 = SellRequestTimeline(
                    request_id=sr.request_id,
                    from_status=SellRequestStatus.offer_revised.value,
                    to_status=SellRequestStatus.accepted.value,
                    actor_role="customer",
                    notes="Customer accepted final offer."
                )
                tl6 = SellRequestTimeline(
                    request_id=sr.request_id,
                    from_status=SellRequestStatus.accepted.value,
                    to_status=SellRequestStatus.paid.value,
                    actor_role="vendor",
                    notes="Instant payout executed via UPI ref: UPI/2026/MYS/9880123456"
                )
                session.add_all([tl1, tl2, tl3, tl4, tl5, tl6])

        # 8. Seed Sample Unassigned Home Pickup for Vendor Claim Testing
        existing_pickup = session.query(SellRequest).filter_by(request_reference="SELL-MYS-002").first()
        if not existing_pickup:
            pu_imei = make_valid_imei("86420904", 77712)
            pu = SellRequest(
                request_reference="SELL-MYS-002",
                customer_name="Sunita Rao",
                customer_phone="+919844556677",
                customer_email="sunita.rao@example.com",
                customer_address="72, Saraswathipuram 5th Main, Mysuru",
                pincode="570009",
                store_id=None,  # Unassigned - available for any K.T. Street store to claim!
                brand="Samsung",
                model="Galaxy S23",
                storage_gb=128,
                imei=pu_imei,
                condition_answers={
                    "screen": "minor_scratches",
                    "body": "good",
                    "battery": "above_85",
                    "camera": "working",
                    "speaker": "working",
                    "accessories": ["box"]
                },
                estimated_min_price=29000,
                estimated_max_price=32000,
                fulfilment_type=FulfilmentType.home_pickup.value,
                slot_date=date.today() + timedelta(days=1),
                slot_time="03:00 PM",
                status=SellRequestStatus.submitted.value,
            )
            session.add(pu)
            session.flush()
            tl_pu = SellRequestTimeline(
                request_id=pu.request_id,
                from_status=None,
                to_status=SellRequestStatus.submitted.value,
                actor_role="customer",
                notes="Home pickup requested in Saraswathipuram (570009). Available for store claiming."
            )
            session.add(tl_pu)

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
