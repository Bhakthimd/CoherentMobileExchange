r"""
Test Suite for CoherentMobiles Vendor Portal & Stock Management
Covers:
  - Login success (by store code and by email, case-insensitive)
  - Login failure (invalid password, unknown store code/email)
  - Lockout after 5 failures per IP+login (HTTP 429)
  - Token required / invalid token handling (HTTP 401)
  - Vendor sees only its own inventory and correct summary
  - Add product & auto-merge (same brand+model+storage adds units, updates price)
  - Validation of brand/model/storage against ^[A-Za-z0-9][A-Za-z0-9 +\-./()]*$ (including quotes and < >)
  - Cross-store edit/delete blocked with 404
  - Status follows stock (0 = Out of Stock, 1-3 = Low Stock, >=4 = In Stock / Flagship if > 80k)
  - Public availability endpoint grouping and sorting (stores sorted by price, stock > 0)
  - Logout (token invalidated)
  - Password change (validation, min 8 chars, verify new password works)
  - Admin API (/api/mobiles) accepting stock and rejecting invalid values (negative, non-int, > 100000)
"""

import json
import unittest
from app import app, init_sample_data, r, check_redis_connection, VENDOR_DEFAULT_PASSWORD


class VendorPortalTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.redis_available = check_redis_connection()
        if cls.redis_available:
            init_sample_data(force=True)

    def setUp(self):
        if not self.redis_available:
            self.skipTest("Redis is offline")

    def test_01_login_success(self):
        """Vendor can log in with store code or email (case-insensitive) using default password."""
        # 1. Login with store code (uppercase)
        res1 = self.client.post("/api/vendor/login", json={
            "login": "IST-IND",
            "password": VENDOR_DEFAULT_PASSWORD
        })
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        self.assertTrue(data1["success"])
        self.assertIn("token", data1)
        self.assertEqual(data1["vendor"]["code"], "IST-IND")
        self.assertNotIn("password_hash", data1["vendor"])

        # 2. Login with email (lowercase / case-insensitive)
        res2 = self.client.post("/api/vendor/login", json={
            "login": "PARTNER@ISTOREINDIA.COM",
            "password": VENDOR_DEFAULT_PASSWORD
        })
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        self.assertTrue(data2["success"])
        self.assertIn("token", data2)

    def test_02_login_failure_and_lockout(self):
        """Unknown store, wrong password return same error, and locks out after 5 failures (HTTP 429)."""
        test_login = "CR-DIR"
        wrong_pwd = "WrongPassword!999"

        # Clear any existing lockout for clean test
        for k in r.keys(f"vendor_lockout:*{test_login.lower()}*"):
            r.delete(k)

        # 1. Wrong password returns 401 with standard error message
        res_fail = self.client.post("/api/vendor/login", json={
            "login": test_login,
            "password": wrong_pwd
        })
        self.assertEqual(res_fail.status_code, 401)
        err_msg = res_fail.get_json()["error"]
        self.assertIn("Invalid store code/email or password", err_msg)

        # 2. Unknown store returns the exact same 401 error message
        res_unknown = self.client.post("/api/vendor/login", json={
            "login": "NON-EXISTENT-STORE",
            "password": "SomePassword"
        })
        self.assertEqual(res_unknown.status_code, 401)
        self.assertEqual(res_unknown.get_json()["error"], err_msg)

        # 3. Trigger 5 consecutive failures for test_login
        # Failures 1 already happened, do 4 more
        for _ in range(4):
            res = self.client.post("/api/vendor/login", json={
                "login": test_login,
                "password": wrong_pwd
            })
            self.assertEqual(res.status_code, 401)

        # 4. 6th attempt should be blocked with HTTP 429 (Too Many Requests)
        res_lockout = self.client.post("/api/vendor/login", json={
            "login": test_login,
            "password": VENDOR_DEFAULT_PASSWORD  # even with correct password
        })
        self.assertEqual(res_lockout.status_code, 429)
        self.assertIn("locked", res_lockout.get_json()["error"].lower())

        # Cleanup lockout for other tests
        for k in r.keys(f"vendor_lockout:*{test_login.lower()}*"):
            r.delete(k)

    def test_03_token_required_for_vendor_endpoints(self):
        """Vendor endpoints reject missing or invalid tokens with HTTP 401."""
        endpoints = [
            ("GET", "/api/vendor/me"),
            ("GET", "/api/vendor/inventory"),
            ("POST", "/api/vendor/products"),
            ("PUT", "/api/vendor/products/1"),
            ("DELETE", "/api/vendor/products/1"),
            ("POST", "/api/vendor/password"),
            ("POST", "/api/vendor/logout")
        ]
        for method, ep in endpoints:
            # Missing header
            res_no_auth = self.client.open(ep, method=method)
            self.assertEqual(res_no_auth.status_code, 401, f"Failed on missing token for {ep}")

            # Invalid header
            res_bad_auth = self.client.open(ep, method=method, headers={"Authorization": "Bearer badtoken12345"})
            self.assertEqual(res_bad_auth.status_code, 401, f"Failed on bad token for {ep}")

    def test_04_vendor_sees_only_own_inventory(self):
        """Logged-in vendor sees only its own product listings and summary metrics."""
        # Login as iStore India (vendor_id = 3)
        res_login = self.client.post("/api/vendor/login", json={
            "login": "IST-IND",
            "password": VENDOR_DEFAULT_PASSWORD
        })
        token = res_login.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        res_inv = self.client.get("/api/vendor/inventory", headers=headers)
        self.assertEqual(res_inv.status_code, 200)
        data = res_inv.get_json()
        self.assertTrue(data["success"])

        # All listings must belong to vendor 3
        for item in data["listings"]:
            self.assertEqual(item["vendor_id"], 3)
            self.assertIn("stock", item)

        summary = data["summary"]
        self.assertIn("total_units", summary)
        self.assertIn("listings", summary)
        self.assertIn("low_stock_count", summary)
        self.assertIn("out_of_stock_count", summary)
        self.assertIn("inventory_value", summary)
        self.assertEqual(summary["listings"], len(data["listings"]))

    def test_05_add_product_and_merge(self):
        """POST /api/vendor/products creates a new product or merges if brand+model+storage match."""
        res_login = self.client.post("/api/vendor/login", json={
            "login": "APX-DST",
            "password": VENDOR_DEFAULT_PASSWORD
        })
        token = res_login.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Add new unique product
        new_prod_payload = {
            "brand": "Google",
            "model": "Pixel 9 Pro",
            "storage": "256 GB",
            "price": 89999,
            "stock": 10
        }
        res_add = self.client.post("/api/vendor/products", json=new_prod_payload, headers=headers)
        self.assertEqual(res_add.status_code, 201)
        data_add = res_add.get_json()
        self.assertFalse(data_add["merged"])
        prod_id = data_add["product"]["id"]
        self.assertEqual(data_add["product"]["stock"], 10)
        self.assertEqual(data_add["product"]["status"], "Flagship")  # price > 80k

        # 2. Add same brand+model+storage -> must merge stock and update price
        merge_payload = {
            "brand": "Google",
            "model": "Pixel 9 Pro",
            "storage": "256 GB",
            "price": 84999,
            "stock": 5
        }
        res_merge = self.client.post("/api/vendor/products", json=merge_payload, headers=headers)
        self.assertEqual(res_merge.status_code, 200)
        data_merge = res_merge.get_json()
        self.assertTrue(data_merge["merged"])
        self.assertEqual(data_merge["product"]["id"], prod_id)
        self.assertEqual(data_merge["product"]["stock"], 15)  # 10 + 5
        self.assertEqual(data_merge["product"]["price"], 84999.0)

    def test_06_field_validation_quotes_and_brackets(self):
        """Vendor product input rejects quotes, < >, negative prices, and bad chars with HTTP 400."""
        res_login = self.client.post("/api/vendor/login", json={
            "login": "APX-DST",
            "password": VENDOR_DEFAULT_PASSWORD
        })
        token = res_login.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        invalid_payloads = [
            # HTML tags / brackets
            {"brand": "<script>alert(1)</script>", "model": "Pixel", "storage": "128 GB", "price": 50000, "stock": 5},
            {"brand": "Google", "model": "<img src=x onerror=alert()>", "storage": "128 GB", "price": 50000, "stock": 5},
            # Quotes
            {"brand": 'Google"Brand', "model": "Pixel 9", "storage": "128 GB", "price": 50000, "stock": 5},
            {"brand": "Google", "model": "Pixel '9' Pro", "storage": "128 GB", "price": 50000, "stock": 5},
            # Invalid symbols like @ or #
            {"brand": "Google#1", "model": "Pixel", "storage": "128 GB", "price": 50000, "stock": 5},
            # Price <= 0
            {"brand": "Google", "model": "Pixel 9", "storage": "128 GB", "price": 0, "stock": 5},
            {"brand": "Google", "model": "Pixel 9", "storage": "128 GB", "price": -100, "stock": 5},
            # Stock invalid
            {"brand": "Google", "model": "Pixel 9", "storage": "128 GB", "price": 50000, "stock": -1},
            {"brand": "Google", "model": "Pixel 9", "storage": "128 GB", "price": 50000, "stock": 100001},
            {"brand": "Google", "model": "Pixel 9", "storage": "128 GB", "price": 50000, "stock": "five"}
        ]

        for payload in invalid_payloads:
            res = self.client.post("/api/vendor/products", json=payload, headers=headers)
            self.assertEqual(res.status_code, 400, f"Payload should have failed with 400: {payload}")

    def test_07_cross_store_edit_and_delete_blocked(self):
        """Vendor cannot edit or delete products belonging to another vendor (returns 404)."""
        # Login as vendor 2 (Apex Mobile)
        res_login_v2 = self.client.post("/api/vendor/login", json={
            "login": "APX-DST",
            "password": VENDOR_DEFAULT_PASSWORD
        })
        token_v2 = res_login_v2.get_json()["token"]
        headers_v2 = {"Authorization": f"Bearer {token_v2}"}

        # Mobile #1 belongs to vendor 3 (iStore India)
        res_get_m1 = self.client.get("/api/mobiles/1")
        self.assertEqual(res_get_m1.get_json()["vendor_id"], 3)

        # Vendor 2 tries to update Mobile #1 -> 404
        res_put = self.client.put("/api/vendor/products/1", json={"price": 50000, "stock": 10}, headers=headers_v2)
        self.assertEqual(res_put.status_code, 404)

        # Vendor 2 tries to delete Mobile #1 -> 404
        res_del = self.client.delete("/api/vendor/products/1", headers=headers_v2)
        self.assertEqual(res_del.status_code, 404)

    def test_08_status_follows_stock(self):
        """Status follows stock: 0 = Out of Stock, 1-3 = Low Stock, >=4 = In Stock (or Flagship if > 80k)."""
        res_login = self.client.post("/api/vendor/login", json={
            "login": "APX-DST",
            "password": VENDOR_DEFAULT_PASSWORD
        })
        token = res_login.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create product with stock 0
        p0 = self.client.post("/api/vendor/products", json={
            "brand": "Motorola", "model": "Edge 50", "storage": "256 GB", "price": 29999, "stock": 0
        }, headers=headers).get_json()["product"]
        self.assertEqual(p0["status"], "Out of Stock")

        # Update stock to 2 -> Low Stock
        p2 = self.client.put(f"/api/vendor/products/{p0['id']}", json={"stock": 2}, headers=headers).get_json()["product"]
        self.assertEqual(p2["status"], "Low Stock")

        # Update stock to 5 and price 29999 -> In Stock
        p5 = self.client.put(f"/api/vendor/products/{p0['id']}", json={"stock": 5}, headers=headers).get_json()["product"]
        self.assertEqual(p5["status"], "In Stock")

        # Update price to 95000 -> Flagship
        p_flag = self.client.put(f"/api/vendor/products/{p0['id']}", json={"price": 95000}, headers=headers).get_json()["product"]
        self.assertEqual(p_flag["status"], "Flagship")

    def test_09_availability_grouping_and_sorting(self):
        """Public /api/availability groups active store listings, sorts stores by price, excludes stock 0 stores."""
        res = self.client.get("/api/availability")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("phones", data)
        phones = data["phones"]
        self.assertGreater(len(phones), 0)

        # Find a phone with multiple stores (e.g. iPhone 15 128 GB)
        target = next((p for p in phones if p["model"] == "iPhone 15" and "128" in p["storage"]), None)
        self.assertIsNotNone(target)
        self.assertGreater(target["total_stock"], 0)
        self.assertGreaterEqual(target["store_count"], 1)

        # Stores in listing must have stock > 0 and be sorted ascending by price
        stores = target["stores"]
        for s in stores:
            self.assertGreater(s["stock"], 0)
        for i in range(len(stores) - 1):
            self.assertLessEqual(stores[i]["price"], stores[i+1]["price"])

        # Test search query filter
        res_search = self.client.get("/api/availability?search=Samsung")
        self.assertEqual(res_search.status_code, 200)
        search_phones = res_search.get_json()["phones"]
        for sp in search_phones:
            self.assertTrue("samsung" in sp["brand"].lower() or "samsung" in sp["model"].lower())

    def test_10_logout(self):
        """POST /api/vendor/logout invalidates session token."""
        res_login = self.client.post("/api/vendor/login", json={
            "login": "NX-HUB",
            "password": VENDOR_DEFAULT_PASSWORD
        })
        token = res_login.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Verify active
        self.assertEqual(self.client.get("/api/vendor/me", headers=headers).status_code, 200)

        # Logout
        res_logout = self.client.post("/api/vendor/logout", headers=headers)
        self.assertEqual(res_logout.status_code, 200)

        # Token is now invalid
        self.assertEqual(self.client.get("/api/vendor/me", headers=headers).status_code, 401)

    def test_11_password_change(self):
        """Vendor can change password with minimum 8 characters and log in with new password."""
        # Vendor 4 (Nexus)
        res_login = self.client.post("/api/vendor/login", json={
            "login": "NX-HUB",
            "password": VENDOR_DEFAULT_PASSWORD
        })
        token = res_login.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Reject if current password wrong
        res_bad_curr = self.client.post("/api/vendor/password", json={
            "current_password": "WrongPassword!",
            "new_password": "NewSecretPass123"
        }, headers=headers)
        self.assertEqual(res_bad_curr.status_code, 400)

        # 2. Reject if new password < 8 characters
        res_short = self.client.post("/api/vendor/password", json={
            "current_password": VENDOR_DEFAULT_PASSWORD,
            "new_password": "short"
        }, headers=headers)
        self.assertEqual(res_short.status_code, 400)

        # 3. Successful password change
        new_pwd = "NexusVendor2026!"
        res_ok = self.client.post("/api/vendor/password", json={
            "current_password": VENDOR_DEFAULT_PASSWORD,
            "new_password": new_pwd
        }, headers=headers)
        self.assertEqual(res_ok.status_code, 200)

        # 4. Verify login with new password succeeds
        res_new_login = self.client.post("/api/vendor/login", json={
            "login": "NX-HUB",
            "password": new_pwd
        })
        self.assertEqual(res_new_login.status_code, 200)
        self.assertTrue(res_new_login.get_json()["success"])

        # Reset password back to default for clean state
        headers_new = {"Authorization": f"Bearer {res_new_login.get_json()['token']}"}
        self.client.post("/api/vendor/password", json={
            "current_password": new_pwd,
            "new_password": VENDOR_DEFAULT_PASSWORD
        }, headers=headers_new)

    def test_12_admin_api_stock_handling_and_validation(self):
        """Admin /api/mobiles endpoints accept stock and reject non-integer, negative, or > 100000."""
        # 1. Accept valid stock on creation
        res_add = self.client.post("/api/mobiles", json={
            "brand": "Sony",
            "model": "Xperia 1 VI",
            "price": 114999,
            "storage": "256 GB",
            "stock": 25,
            "vendor_id": 1
        })
        self.assertEqual(res_add.status_code, 201)
        m = res_add.get_json()["mobile"]
        self.assertEqual(m["stock"], 25)
        m_id = m["id"]

        # 2. Accept valid stock on update
        res_up = self.client.put(f"/api/mobiles/{m_id}", json={"stock": 18})
        self.assertEqual(res_up.status_code, 200)
        self.assertEqual(res_up.get_json()["mobile"]["stock"], 18)

        # 3. Reject negative stock
        res_neg = self.client.post("/api/mobiles", json={
            "brand": "Sony", "model": "Xperia", "price": 50000, "stock": -5
        })
        self.assertEqual(res_neg.status_code, 400)

        # 4. Reject stock > 100000
        res_over = self.client.post("/api/mobiles", json={
            "brand": "Sony", "model": "Xperia", "price": 50000, "stock": 100005
        })
        self.assertEqual(res_over.status_code, 400)

        # 5. Reject non-integer stock (string, float)
        res_str = self.client.post("/api/mobiles", json={
            "brand": "Sony", "model": "Xperia", "price": 50000, "stock": "twenty"
        })
        self.assertEqual(res_str.status_code, 400)

        res_float = self.client.post("/api/mobiles", json={
            "brand": "Sony", "model": "Xperia", "price": 50000, "stock": 15.5
        })
        self.assertEqual(res_float.status_code, 400)

        # Cleanup created product
        self.client.delete(f"/api/mobiles/{m_id}")


if __name__ == "__main__":
    unittest.main()
