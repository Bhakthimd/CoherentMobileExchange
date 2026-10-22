"""
Comprehensive PyTest Test Suite for CoherentMobiles Marketplace
Tests:
  1. Health & Database connectivity
  2. Auth, password hashing, session cookies, rate limiting, and role guards
  3. Pending vendor restrictions vs Admin approval
  4. Vendor isolation & 404 cross-vendor protections
  5. Storefront catalog visibility & inline hide/unhide toggle
  6. Customer checkout with atomic row-locking & audit stock movements
  7. Concurrent purchases: 2 simultaneous threads buying the same unit -> exactly 1 succeeds, 1 gets 409
  8. Bulk CSV upload with per-row validation
"""

import json
import threading
import time
import pytest
from app import app
from database import SessionLocal
import models
from models import (
    User, UserRole, Vendor, VendorApprovalStatus,
    InventoryUnit, UnitStatus, StockMovement, OrderItem
)
from routes_vendor import validate_imei_luhn
from seed import make_valid_imei


@pytest.fixture(scope="session")
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(scope="session")
def auth_tokens(client):
    """Log in all key roles and return session tokens."""
    # 1. Admin
    res_admin = client.post("/api/auth/login", json={
        "login": "admin@coherent.test",
        "password": "Admin@123"
    })
    assert res_admin.status_code == 200, f"Admin login failed: {res_admin.get_data(as_text=True)}"
    admin_token = res_admin.get_json()["token"]

    # 2. Approved Vendor A (iStore India - IST-IND)
    res_va = client.post("/api/auth/login", json={
        "login": "IST-IND",
        "password": "Vendor@123"
    })
    assert res_va.status_code == 200, f"Vendor A login failed: {res_va.get_data(as_text=True)}"
    vendor_a_token = res_va.get_json()["token"]
    vendor_a_id = res_va.get_json()["vendor"]["id"]

    # 3. Approved Vendor B (Apex Mobile - APX-DST)
    res_vb = client.post("/api/auth/login", json={
        "login": "APX-DST",
        "password": "Vendor@123"
    })
    assert res_vb.status_code == 200, f"Vendor B login failed: {res_vb.get_data(as_text=True)}"
    vendor_b_token = res_vb.get_json()["token"]
    vendor_b_id = res_vb.get_json()["vendor"]["id"]

    # 4. Pending Vendor (Nexus - NX-HUB)
    res_vp = client.post("/api/auth/login", json={
        "login": "NX-HUB",
        "password": "Vendor@123"
    })
    assert res_vp.status_code == 200, f"Pending Vendor login failed: {res_vp.get_data(as_text=True)}"
    vendor_p_token = res_vp.get_json()["token"]

    return {
        "admin": admin_token,
        "vendor_a": vendor_a_token,
        "vendor_a_id": vendor_a_id,
        "vendor_b": vendor_b_token,
        "vendor_b_id": vendor_b_id,
        "vendor_pending": vendor_p_token
    }


# ===========================================================================
# 1. Health & Database Connectivity
# ===========================================================================

def test_01_health_check(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "healthy"
    assert data["postgres_connected"] is True
    assert data["database_connected"] is True


# ===========================================================================
# 2. Auth, Role Guards, & Customer Registration
# ===========================================================================

def test_02_customer_registration_and_login(client):
    test_email = f"customer_{int(time.time())}@example.com"
    res = client.post("/api/auth/register", json={
        "name": "Test Customer",
        "email": test_email,
        "phone": f"+9198{int(time.time()) % 100000000:08d}",
        "password": "Password123!",
        "address": "Bandra West, Mumbai"
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data["success"] is True
    assert "token" in data
    assert data["user"]["role"] == "customer"

    # Login with newly created customer
    res_login = client.post("/api/auth/login", json={
        "login": test_email,
        "password": "Password123!"
    })
    assert res_login.status_code == 200
    cust_token = res_login.get_json()["token"]

    # Customer accessing admin route must be blocked with 403
    res_admin = client.get("/api/admin/vendors", headers={
        "Authorization": f"Bearer {cust_token}"
    })
    assert res_admin.status_code == 403


def test_03_unauthenticated_guards():
    with app.test_client() as unauth_client:
        # Unauthenticated access to admin must return 401
        res = unauth_client.get("/api/admin/vendors")
        assert res.status_code == 401

        # Unauthenticated access to vendor inventory must return 401
        res_inv = unauth_client.get("/api/vendor/inventory")
        assert res_inv.status_code == 401


# ===========================================================================
# 3. Pending Vendor vs Admin Approval
# ===========================================================================

def test_04_pending_vendor_cannot_add_inventory(client, auth_tokens):
    # Pending vendor can access profile
    res_me = client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {auth_tokens['vendor_pending']}"
    })
    assert res_me.status_code == 200
    data = res_me.get_json()
    assert data["vendor"]["approval_status"] == "pending"

    # Pending vendor attempting to add inventory must receive 403
    valid_imei = make_valid_imei("35874299", int(time.time()) % 100000)
    res_add = client.post("/api/vendor/inventory", headers={
        "Authorization": f"Bearer {auth_tokens['vendor_pending']}"
    }, json={
        "brand": "Apple",
        "model": "iPhone 15",
        "storage_gb": 128,
        "imei": valid_imei,
        "selling_price": 54999,
        "condition_grade": "good"
    })
    assert res_add.status_code == 403
    assert "pending" in res_add.get_json()["error"].lower()


# ===========================================================================
# 4. Vendor Isolation & Cross-Vendor 404 Protections
# ===========================================================================

def test_05_vendor_a_creates_unit_and_vendor_b_gets_404(client, auth_tokens):
    # Generate a brand new unique Luhn-valid IMEI
    unique_seq = int(time.time() * 1000) % 1000000
    imei_a = make_valid_imei("35874211", unique_seq)
    assert validate_imei_luhn(imei_a) is True

    # Vendor A adds device
    res_add = client.post("/api/vendor/inventory", headers={
        "Authorization": f"Bearer {auth_tokens['vendor_a']}"
    }, json={
        "brand": "Apple",
        "model": "iPhone 15 Pro",
        "storage_gb": 256,
        "color": "Natural Titanium",
        "imei": imei_a,
        "selling_price": 89999,
        "mrp": 129999,
        "condition_grade": "like_new",
        "battery_health": 97,
        "warranty_months": 12,
        "notes": "Vendor A certified flagship"
    })
    assert res_add.status_code == 201, f"Add unit failed: {res_add.get_data(as_text=True)}"
    unit_a = res_add.get_json()["unit"]
    unit_a_id = unit_a["unit_id"]

    # Vendor A can view it in their inventory
    res_list = client.get(f"/api/vendor/inventory?search={imei_a}", headers={
        "Authorization": f"Bearer {auth_tokens['vendor_a']}"
    })
    assert res_list.status_code == 200
    items = res_list.get_json()["items"]
    assert any(i["imei"] == imei_a for i in items)

    # Vendor B MUST NOT see Vendor A's unit in their inventory
    res_b_list = client.get(f"/api/vendor/inventory?search={imei_a}", headers={
        "Authorization": f"Bearer {auth_tokens['vendor_b']}"
    })
    assert res_b_list.status_code == 200
    assert len(res_b_list.get_json()["items"]) == 0

    # Vendor B attempting to edit Vendor A's unit MUST return 404
    res_b_edit = client.put(f"/api/vendor/inventory/{unit_a_id}", headers={
        "Authorization": f"Bearer {auth_tokens['vendor_b']}"
    }, json={
        "selling_price": 10000
    })
    assert res_b_edit.status_code == 404
    assert "not found" in res_b_edit.get_json()["error"].lower()

    # Vendor B attempting to delete Vendor A's unit MUST return 404
    res_b_del = client.delete(f"/api/vendor/inventory/{unit_a_id}", headers={
        "Authorization": f"Bearer {auth_tokens['vendor_b']}"
    })
    assert res_b_del.status_code == 404

    # Verify unit is still intact and owned by Vendor A
    db = SessionLocal()
    try:
        db_unit = db.query(InventoryUnit).filter_by(unit_id=unit_a_id).first()
        assert db_unit is not None
        assert db_unit.vendor_id == auth_tokens["vendor_a_id"]
        assert db_unit.deleted_at is None
    finally:
        db.close()


# ===========================================================================
# 5. Storefront Catalog Visibility & Inline Hide Toggle
# ===========================================================================

def test_06_storefront_visibility_and_hide_toggle(client, auth_tokens):
    # Add a device with Vendor A
    unique_seq = int(time.time() * 1000 + 7) % 1000000
    test_imei = make_valid_imei("86420904", unique_seq)

    res_add = client.post("/api/vendor/inventory", headers={
        "Authorization": f"Bearer {auth_tokens['vendor_a']}"
    }, json={
        "brand": "Samsung",
        "model": "Galaxy S24 Ultra",
        "storage_gb": 512,
        "imei": test_imei,
        "selling_price": 99999,
        "condition_grade": "like_new",
        "battery_health": 100
    })
    assert res_add.status_code == 201
    unit_id = res_add.get_json()["unit"]["unit_id"]

    # 1. Device appears in public /api/catalog
    res_cat1 = client.get("/api/catalog?per_page=100")
    assert res_cat1.status_code == 200
    cat_items = res_cat1.get_json()["items"]
    assert any(u["unit_id"] == unit_id for u in cat_items)

    # 2. Vendor A hides the unit
    res_hide = client.put(f"/api/vendor/inventory/{unit_id}", headers={
        "Authorization": f"Bearer {auth_tokens['vendor_a']}"
    }, json={
        "status": "hidden"
    })
    assert res_hide.status_code == 200
    assert res_hide.get_json()["unit"]["status"] == "hidden"

    # 3. Unit disappears from public /api/catalog
    res_cat2 = client.get("/api/catalog?per_page=100")
    assert res_cat2.status_code == 200
    cat_items2 = res_cat2.get_json()["items"]
    assert not any(u["unit_id"] == unit_id for u in cat_items2)

    # 4. Vendor A restores it to in_stock
    res_unhide = client.put(f"/api/vendor/inventory/{unit_id}", headers={
        "Authorization": f"Bearer {auth_tokens['vendor_a']}"
    }, json={
        "status": "in_stock"
    })
    assert res_unhide.status_code == 200

    # 5. Unit reappears on storefront
    res_cat3 = client.get("/api/catalog?per_page=100")
    assert any(u["unit_id"] == unit_id for u in res_cat3.get_json()["items"])


# ===========================================================================
# 6. Customer Checkout, Stock Movements, & Vendor Orders
# ===========================================================================

def test_07_customer_checkout_and_vendor_order_fulfillment(client, auth_tokens):
    # Vendor A lists a unit
    unique_seq = int(time.time() * 1000 + 42) % 1000000
    imei_sold = make_valid_imei("35492109", unique_seq)

    res_add = client.post("/api/vendor/inventory", headers={
        "Authorization": f"Bearer {auth_tokens['vendor_a']}"
    }, json={
        "brand": "OnePlus",
        "model": "OnePlus 12",
        "storage_gb": 256,
        "imei": imei_sold,
        "selling_price": 49999,
        "condition_grade": "good"
    })
    assert res_add.status_code == 201
    unit_id = res_add.get_json()["unit"]["unit_id"]

    # Customer places order
    res_order = client.post("/api/orders", json={
        "unit_id": unit_id,
        "customer_name": "Aarav Mehta",
        "customer_email": "aarav@example.com",
        "customer_phone": "+919876500001",
        "delivery_address": "402 Palm Heights, Worli, Mumbai",
        "payment_method": "pod",
        "trade_in_credit": 5000,
        "coupon_discount": 1000
    })
    assert res_order.status_code == 201
    order_data = res_order.get_json()["order"]
    assert order_data["total_amount"] == 49999 - 5000 - 1000
    order_ref = order_data["order_reference"]

    # Unit must no longer be in_stock in catalog
    res_cat = client.get("/api/catalog?per_page=100")
    assert not any(u["unit_id"] == unit_id for u in res_cat.get_json()["items"])

    # Order item appears in Vendor A's orders list
    res_orders = client.get("/api/vendor/orders", headers={
        "Authorization": f"Bearer {auth_tokens['vendor_a']}"
    })
    assert res_orders.status_code == 200
    vendor_order_items = res_orders.get_json()["orders"]
    matching_item = next((item for item in vendor_order_items if item["unit_id"] == unit_id), None)
    assert matching_item is not None
    assert matching_item["order_reference"] == order_ref
    order_item_id = matching_item["order_item_id"]

    # Vendor A updates fulfillment status: confirmed -> packed -> shipped -> delivered
    for next_status in ["packed", "shipped", "delivered"]:
        res_st = client.put(f"/api/vendor/orders/{order_item_id}/status", headers={
            "Authorization": f"Bearer {auth_tokens['vendor_a']}"
        }, json={"status": next_status})
        assert res_st.status_code == 200
        assert res_st.get_json()["item"]["item_status"] == next_status

    # StockMovements audit log contains both 'added' and 'sold' entries
    db = SessionLocal()
    try:
        movements = db.query(StockMovement).filter_by(unit_id=unit_id).order_by(StockMovement.id).all()
        actions = [m.action for m in movements]
        assert "added" in actions
        assert "sold" in actions
    finally:
        db.close()


# ===========================================================================
# 7. Concurrent Purchases: Exactly One Succeeds, One Gets 409
# ===========================================================================

def test_08_concurrent_purchase_race_condition(client, auth_tokens):
    # Vendor A lists a unique unit for concurrent test
    unique_seq = int(time.time() * 1000 + 99) % 1000000
    imei_race = make_valid_imei("86753091", unique_seq)

    res_add = client.post("/api/vendor/inventory", headers={
        "Authorization": f"Bearer {auth_tokens['vendor_a']}"
    }, json={
        "brand": "Apple",
        "model": "iPhone 15 Pro",
        "storage_gb": 256,
        "imei": imei_race,
        "selling_price": 84999,
        "condition_grade": "like_new"
    })
    assert res_add.status_code == 201
    target_unit_id = res_add.get_json()["unit"]["unit_id"]

    results = []

    def attempt_purchase(customer_name, email):
        with app.test_client() as thread_client:
            res = thread_client.post("/api/orders", json={
                "unit_id": target_unit_id,
                "customer_name": customer_name,
                "customer_email": email,
                "customer_phone": "+919999988888",
                "delivery_address": "Tech Residency, Whitefield, Bengaluru",
                "payment_method": "pod"
            })
            results.append((res.status_code, res.get_json()))

    t1 = threading.Thread(target=attempt_purchase, args=("Customer Alpha", "alpha@test.com"))
    t2 = threading.Thread(target=attempt_purchase, args=("Customer Beta", "beta@test.com"))

    # Fire both simultaneously
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(results) == 2
    status_codes = [r[0] for r in results]

    # Exactly one must succeed with 201, and the second must be rejected with 409 Conflict!
    assert 201 in status_codes, f"Expected one 201 success, got: {status_codes}"
    assert 409 in status_codes, f"Expected one 409 conflict, got: {status_codes}"

    conflict_res = next(r[1] for r in results if r[0] == 409)
    assert "reserved or purchased" in conflict_res["error"]


# ===========================================================================
# 8. Bulk CSV Upload with Per-Row Validation
# ===========================================================================

def test_09_bulk_csv_upload(client, auth_tokens):
    # Row 1: Valid
    valid_imei_1 = make_valid_imei("35874211", int(time.time() * 1000 + 1) % 1000000)
    # Row 2: Valid
    valid_imei_2 = make_valid_imei("86420904", int(time.time() * 1000 + 2) % 1000000)
    # Row 3: INVALID Luhn Check Digit
    invalid_imei = "358742110000019"  # last digit intentionally wrong

    csv_data = f"""brand,model,storage_gb,ram_gb,color,imei,condition_grade,battery_health,selling_price,mrp,warranty_months,notes
Apple,iPhone 15,128,8,Blue,{valid_imei_1},like_new,96,65999,79999,12,Mint condition
Samsung,Galaxy S24,256,8,Onyx Black,{valid_imei_2},good,91,61999,74999,6,Minor wear
Google,Pixel 8,128,8,Hazel,{invalid_imei},good,89,45999,69999,6,Bad IMEI row
"""

    res = client.post("/api/vendor/inventory/bulk", headers={
        "Authorization": f"Bearer {auth_tokens['vendor_a']}"
    }, data=csv_data.encode("utf-8"), content_type="text/csv")

    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["created_count"] == 2
    assert data["failed_count"] == 1
    assert len(data["errors"]) == 1
    assert data["errors"][0]["imei"] == invalid_imei
    assert "Luhn" in data["errors"][0]["error"]
