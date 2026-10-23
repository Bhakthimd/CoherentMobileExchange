"""
PyTest Test Suite: Mysuru / K.T. Street Local Marketplace Extensions
Tests:
  1. Store locator OpenStreetMap metadata & live open/closed computation
  2. Pincode serviceability check (Mysuru city vs outside)
  3. Price estimation from matrix with condition deductions
  4. Sell request submission: Luhn IMEI validation & Mysuru pincode guard
  5. Vendor sell inbox & atomic home-pickup claiming
  6. Sell request inspection -> offer acceptance -> payment & AUTO-INVENTORY CREATION
  7. 24-hour "Reserve & Visit" hold with atomic row-locking & cancellation
  8. Store profile & opening hours management
  9. Admin pincodes & price matrix management
"""

import json
import time
import pytest
from datetime import date, timedelta
from app import app
from database import SessionLocal
import models
from models import (
    User, UserRole, Vendor, VendorApprovalStatus,
    InventoryUnit, UnitStatus, ServiceablePincode,
    PriceMatrix, SellRequest, SellRequestStatus, FulfilmentType,
    Reservation, ReservationStatus, StockMovement, utc_now
)
from seed import make_valid_imei
from routes_vendor import validate_imei_luhn


@pytest.fixture(scope="session")
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(scope="session")
def auth_tokens(client):
    """Log in Admin and K.T. Street Store vendors."""
    # 1. Admin
    res_admin = client.post("/api/auth/login", json={
        "login": "admin@coherent.test",
        "password": "Admin@123"
    })
    assert res_admin.status_code == 200, f"Admin login failed: {res_admin.get_data(as_text=True)}"
    admin_token = res_admin.get_json()["token"]

    # 2. Store 1 (Chamundi Mobile Galleria - IST-IND)
    res_s1 = client.post("/api/auth/login", json={
        "login": "IST-IND",
        "password": "Vendor@123"
    })
    assert res_s1.status_code == 200
    s1_token = res_s1.get_json()["token"]
    s1_vendor = res_s1.get_json()["vendor"]

    # 3. Store 2 (Cauvery Phone Junction - APX-DST)
    res_s2 = client.post("/api/auth/login", json={
        "login": "APX-DST",
        "password": "Vendor@123"
    })
    assert res_s2.status_code == 200
    s2_token = res_s2.get_json()["token"]
    s2_vendor = res_s2.get_json()["vendor"]

    return {
        "admin": admin_token,
        "store1": s1_token,
        "store1_id": s1_vendor["id"],
        "store2": s2_token,
        "store2_id": s2_vendor["id"],
    }


# ===========================================================================
# 1. Store Locator & Open/Closed Status
# ===========================================================================

def test_01_store_locator_and_open_status(client):
    res = client.get("/api/stores")
    assert res.status_code == 200
    data = res.json
    assert data["success"] is True
    assert data["count"] >= 5
    assert "K.T. Street, Mysuru" in data["area"]

    # Verify store attributes
    first_store = data["stores"][0]
    assert "store_name" in first_store
    assert "address_line" in first_store
    assert first_store["pincode"] == "570001"
    assert first_store["latitude"] is not None
    assert first_store["longitude"] is not None
    assert "is_open" in first_store
    assert isinstance(first_store["is_open"], bool)
    assert "inventory_count" in first_store
    assert "whatsapp_number" in first_store
    assert "google_maps_url" in first_store

    # Test store search
    res_search = client.get("/api/stores?search=Chamundi")
    assert res_search.status_code == 200
    search_stores = res_search.json["stores"]
    assert len(search_stores) >= 1
    assert "Chamundi" in search_stores[0]["store_name"]

    # Test single store detail with inventory
    store_id = first_store["vendor_id"]
    res_detail = client.get(f"/api/stores/{store_id}")
    assert res_detail.status_code == 200
    detail_data = res_detail.json
    assert detail_data["success"] is True
    assert "inventory" in detail_data["store"]


# ===========================================================================
# 2. Pincode Serviceability Check
# ===========================================================================

def test_02_pincode_serviceability(client):
    # Serviceable Mysuru pincodes
    res_kts = client.get("/api/pincodes/check?pincode=570001")
    assert res_kts.status_code == 200
    assert res_kts.json["serviceable"] is True
    assert "K.T. Street" in res_kts.json["area_name"]

    res_gok = client.get("/api/pincodes/check?pincode=570006")
    assert res_gok.status_code == 200
    assert res_gok.json["serviceable"] is True
    assert "Gokulam" in res_gok.json["area_name"]

    # Non-serviceable pincode (Bengaluru / Mumbai)
    res_blr = client.get("/api/pincodes/check?pincode=560001")
    assert res_blr.status_code == 200
    assert res_blr.json["serviceable"] is False
    assert "Mysuru city limits" in res_blr.json["message"]


# ===========================================================================
# 3. Price Estimation from Matrix
# ===========================================================================

def test_03_price_estimation(client):
    # Flawless iPhone 15 128GB
    res_est = client.post("/api/estimate", json={
        "brand": "Apple",
        "model": "iPhone 15",
        "storage_gb": 128,
        "condition_answers": {
            "screen": "flawless",
            "body": "flawless",
            "battery": "above_85",
            "accessories": ["box", "charger"]
        }
    })
    assert res_est.status_code == 200
    data = res_est.json
    assert data["success"] is True
    assert data["estimated_max_price"] >= 40000
    assert data["estimated_min_price"] < data["estimated_max_price"]

    # Cracked screen should deduct value
    res_cracked = client.post("/api/estimate", json={
        "brand": "Apple",
        "model": "iPhone 15",
        "storage_gb": 128,
        "condition_answers": {
            "screen": "cracked",
            "body": "flawless",
            "battery": "above_85",
            "accessories": ["box", "charger"]
        }
    })
    assert res_cracked.status_code == 200
    assert res_cracked.json["estimated_max_price"] < data["estimated_max_price"]
    assert "screen" in res_cracked.json["deductions"]


# ===========================================================================
# 4. Sell Request Submission with Luhn IMEI & Pincode Guard
# ===========================================================================

def test_04_sell_request_submission_validation(client, auth_tokens):
    # 1. Invalid Luhn IMEI should be rejected
    res_bad_imei = client.post("/api/sell/requests", json={
        "brand": "Apple",
        "model": "iPhone 14",
        "storage_gb": 128,
        "imei": "123456789012345",  # invalid Luhn
        "customer_name": "Deepak M",
        "customer_phone": "9845012345",
        "fulfilment_type": "store_visit",
        "store_id": auth_tokens["store1_id"]
    })
    assert res_bad_imei.status_code == 400
    assert "invalid imei" in res_bad_imei.json["error"].lower()

    # 2. Home pickup outside Mysuru city limits should be rejected
    valid_imei = make_valid_imei("35874288", int(time.time()) % 100000)
    res_bad_pin = client.post("/api/sell/requests", json={
        "brand": "Apple",
        "model": "iPhone 14",
        "storage_gb": 128,
        "imei": valid_imei,
        "customer_name": "Deepak M",
        "customer_phone": "9845012345",
        "fulfilment_type": "home_pickup",
        "pincode": "560001",  # outside Mysuru!
        "customer_address": "MG Road, Bengaluru"
    })
    assert res_bad_pin.status_code == 400
    assert "outside our mysuru city limits" in res_bad_pin.json["error"].lower()

    # 3. Valid Store Visit on K.T. Street succeeds
    res_valid_store = client.post("/api/sell/requests", json={
        "brand": "Apple",
        "model": "iPhone 14",
        "storage_gb": 128,
        "imei": valid_imei,
        "customer_name": "Deepak M",
        "customer_phone": "9845012345",
        "fulfilment_type": "store_visit",
        "store_id": auth_tokens["store1_id"],
        "slot_date": str(date.today()),
        "slot_time": "02:30 PM",
        "condition_answers": {"screen": "flawless", "body": "good", "battery": "above_85"}
    })
    assert res_valid_store.status_code == 201
    sr = res_valid_store.json["sell_request"]
    assert sr["request_reference"].startswith("SELL-MYS-")
    assert sr["status"] == "submitted"
    assert len(sr["timeline"]) >= 1


# ===========================================================================
# 5. Vendor Sell Inbox & Atomic Claiming
# ===========================================================================

def test_05_vendor_sell_inbox_and_claiming(client, auth_tokens):
    # Customer submits a home pickup in Saraswathipuram (570009)
    imei_pu = make_valid_imei("86420955", int(time.time() * 10) % 100000)
    res_pu = client.post("/api/sell/requests", json={
        "brand": "Samsung",
        "model": "Galaxy S23",
        "storage_gb": 128,
        "imei": imei_pu,
        "customer_name": "Kavitha Shastry",
        "customer_phone": "9845099887",
        "fulfilment_type": "home_pickup",
        "pincode": "570009",
        "customer_address": "84 Saraswathipuram 4th Cross, Mysuru",
        "condition_answers": {"screen": "flawless", "body": "flawless", "battery": "above_85"}
    })
    assert res_pu.status_code == 201
    req_id = res_pu.json["sell_request"]["request_id"]
    ref_code = res_pu.json["sell_request"]["request_reference"]

    # Store 1 checks inbox
    res_inbox = client.get("/api/vendor/sell-requests?tab=pool", headers={
        "Authorization": f"Bearer {auth_tokens['store1']}"
    })
    assert res_inbox.status_code == 200
    pool_ids = [r["request_id"] for r in res_inbox.json["requests"]]
    assert req_id in pool_ids

    # Store 1 claims this home pickup
    res_claim1 = client.post(f"/api/vendor/sell-requests/{req_id}/claim", headers={
        "Authorization": f"Bearer {auth_tokens['store1']}"
    })
    assert res_claim1.status_code == 200
    assert res_claim1.json["sell_request"]["status"] == "store_confirmed"

    # Store 2 attempts to claim the same already-claimed pickup -> must receive 409 Conflict
    res_claim2 = client.post(f"/api/vendor/sell-requests/{req_id}/claim", headers={
        "Authorization": f"Bearer {auth_tokens['store2']}"
    })
    assert res_claim2.status_code == 409
    assert "already been claimed" in res_claim2.json["error"].lower()


# ===========================================================================
# 6. Inspection -> Customer Acceptance -> Payout & AUTO-INVENTORY
# ===========================================================================

def test_06_inspection_payout_and_auto_inventory(client, auth_tokens):
    # Customer submits store visit request
    unique_imei = make_valid_imei("35987111", int(time.time() * 5) % 100000)
    res_sub = client.post("/api/sell/requests", json={
        "brand": "OnePlus",
        "model": "11",
        "storage_gb": 128,
        "imei": unique_imei,
        "customer_name": "Girish Rao",
        "customer_phone": "9880011223",
        "fulfilment_type": "store_visit",
        "store_id": auth_tokens["store1_id"],
        "condition_answers": {"screen": "minor_scratches", "body": "flawless", "battery": "above_85"}
    })
    assert res_sub.status_code == 201
    req_id = res_sub.json["sell_request"]["request_id"]
    ref = res_sub.json["sell_request"]["request_reference"]

    # Store 1 completes 15-point inspection and sets final offer
    res_inspect = client.put(f"/api/vendor/sell-requests/{req_id}/status", headers={
        "Authorization": f"Bearer {auth_tokens['store1']}"
    }, json={
        "status": "offer_revised",
        "final_offer_price": 25500,
        "final_offer_notes": "Screen has faint hair scratch, 91% battery health. Excellent condition."
    })
    assert res_inspect.status_code == 200
    assert res_inspect.json["sell_request"]["status"] == "offer_revised"
    assert res_inspect.json["sell_request"]["final_offer_price"] == 25500

    # Customer accepts final offer
    res_accept = client.post(f"/api/sell/requests/{ref}/accept")
    assert res_accept.status_code == 200
    assert res_accept.json["sell_request"]["status"] == "accepted"

    # Store marks paid with UPI reference -> TRIGGERS AUTO INVENTORY CREATION
    res_pay = client.post(f"/api/vendor/sell-requests/{req_id}/pay", headers={
        "Authorization": f"Bearer {auth_tokens['store1']}"
    }, json={
        "payout_method": "upi",
        "payout_reference": f"UPI/2026/MYS/{int(time.time())}",
        "resale_price": 31999
    })
    assert res_pay.status_code == 200
    data_pay = res_pay.json
    assert data_pay["success"] is True
    assert data_pay["sell_request"]["status"] == "paid"

    # Verify device was automatically created in store 1 inventory
    created_unit = data_pay["created_unit"]
    assert created_unit["imei"] == unique_imei
    assert created_unit["vendor_id"] == auth_tokens["store1_id"]
    assert created_unit["status"] == "in_stock"
    assert created_unit["selling_price"] == 31999

    # Verify it now appears in public catalog
    res_cat = client.get(f"/api/catalog/{created_unit['unit_id']}")
    assert res_cat.status_code == 200
    assert res_cat.json["unit"]["imei"] == unique_imei


# ===========================================================================
# 7. 24-Hour "Reserve & Visit" Hold & Cancellation
# ===========================================================================

def test_07_reservation_hold_and_release(client):
    # Find an in-stock unit
    res_cat = client.get("/api/catalog?per_page=1")
    assert res_cat.status_code == 200
    assert len(res_cat.json["items"]) > 0
    target_unit = res_cat.json["items"][0]
    unit_id = target_unit["unit_id"]

    # Customer holds the device for 24 hours
    res_hold = client.post("/api/reservations", json={
        "unit_id": unit_id,
        "customer_name": "Ananya Sharma",
        "customer_phone": "9845112233",
        "customer_email": "ananya@example.com"
    })
    assert res_hold.status_code == 201
    hold_data = res_hold.json
    assert hold_data["success"] is True
    res_ref = hold_data["reservation_reference"]
    assert res_ref.startswith("RES-MYS-")

    # Unit must now be marked as 'reserved' and unavailable in catalog
    res_check = client.get(f"/api/catalog/{unit_id}")
    assert res_check.status_code == 404  # Not in public catalog while reserved

    # Another customer attempting to hold the same device receives 409 Conflict
    res_race = client.post("/api/reservations", json={
        "unit_id": unit_id,
        "customer_name": "Another Buyer",
        "customer_phone": "9845999999"
    })
    assert res_race.status_code == 409

    # Customer cancels hold
    res_cancel = client.post(f"/api/reservations/{res_ref}/cancel")
    assert res_cancel.status_code == 200
    assert res_cancel.json["reservation"]["status"] == "cancelled"

    # Unit must return to public catalog as 'in_stock'
    res_restored = client.get(f"/api/catalog/{unit_id}")
    assert res_restored.status_code == 200
    assert res_restored.json["unit"]["status"] == "in_stock"


# ===========================================================================
# 8. Store Profile & Opening Hours Management
# ===========================================================================

def test_08_store_profile_management(client, auth_tokens):
    # Retrieve store profile
    res_prof = client.get("/api/vendor/store-profile", headers={
        "Authorization": f"Bearer {auth_tokens['store1']}"
    })
    assert res_prof.status_code == 200
    store = res_prof.json["store"]
    assert "Chamundi" in store["store_name"]

    # Update hours and service options
    updated_hours = dict(store.get("opening_hours") or {})
    updated_hours["sunday"] = {"open": "11:00", "close": "18:00", "is_closed": False}

    res_up = client.put("/api/vendor/store-profile", headers={
        "Authorization": f"Bearer {auth_tokens['store1']}"
    }, json={
        "landmark": "Near D. Banumaiah Circle, Mysuru City",
        "whatsapp_number": "+91 98450 11001",
        "accepts_walk_in": True,
        "offers_home_pickup": True,
        "opening_hours": updated_hours
    })
    assert res_up.status_code == 200
    assert res_up.json["store"]["landmark"] == "Near D. Banumaiah Circle, Mysuru City"


# ===========================================================================
# 9. Admin Pincodes & Price Matrix Management
# ===========================================================================

def test_09_admin_pincodes_and_price_matrix(client, auth_tokens):
    # 1. Admin lists pincodes
    res_pins = client.get("/api/admin/pincodes", headers={
        "Authorization": f"Bearer {auth_tokens['admin']}"
    })
    assert res_pins.status_code == 200
    assert res_pins.json["count"] >= 12

    # 2. Admin adds a new Mysuru pincode (e.g. 570025)
    res_add_pin = client.post("/api/admin/pincodes", headers={
        "Authorization": f"Bearer {auth_tokens['admin']}"
    }, json={
        "pincode": "570025",
        "area_name": "Bogadi 2nd Stage",
        "city": "Mysuru"
    })
    assert res_add_pin.status_code in (200, 201)

    # Verify newly added pincode is now serviceable
    res_check = client.get("/api/pincodes/check?pincode=570025")
    assert res_check.status_code == 200
    assert res_check.json["serviceable"] is True

    # 3. Admin updates price matrix
    res_matrix = client.get("/api/admin/price-matrix", headers={
        "Authorization": f"Bearer {auth_tokens['admin']}"
    })
    assert res_matrix.status_code == 200
    assert res_matrix.json["count"] >= 10
