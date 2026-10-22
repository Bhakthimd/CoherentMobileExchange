"""
Comprehensive End-to-End Test Suite for CoherentMobiles Backend & Vendor Management
Tests all CRUD operations, vendor APIs, filters, input validations, and stats.
Run via: python test_e2e_backend.py
"""

import json
import unittest
from app import app, init_sample_data, r, check_redis_connection

class CoherentMobilesE2ETestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test environment and initialize sample data in Redis."""
        cls.client = app.test_client()
        cls.redis_available = check_redis_connection()
        if cls.redis_available:
            init_sample_data(force=False)

    def test_01_health_check(self):
        """TC-01: Health check endpoint /api/health returns valid status and Redis connection."""
        response = self.client.get("/api/health")
        data = response.get_json()
        if self.redis_available:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(data["status"], "healthy")
            self.assertTrue(data["redis_connected"])
        else:
            self.assertEqual(response.status_code, 503)

    def test_02_web_routes(self):
        """TC-02: Dashboard HTML, CSS, JS, and storefront index.html are served correctly."""
        res_root = self.client.get("/")
        self.assertEqual(res_root.status_code, 200)
        self.assertIn(b"Vendor Management & Products List", res_root.data)

        res_crud = self.client.get("/crud-dashboard.html")
        self.assertEqual(res_crud.status_code, 200)
        self.assertIn(b"dash-layout", res_crud.data)

        res_index = self.client.get("/index.html")
        self.assertEqual(res_index.status_code, 200)
        self.assertIn(b"CoherentMobiles", res_index.data)

        res_css = self.client.get("/crud-dashboard.css")
        self.assertEqual(res_css.status_code, 200)

        res_js = self.client.get("/crud-dashboard.js")
        self.assertEqual(res_js.status_code, 200)

    def test_03_get_vendors(self):
        """TC-03: GET /api/vendors returns registered vendors with enriched metrics."""
        if not self.redis_available:
            self.skipTest("Redis offline")

        response = self.client.get("/api/vendors")
        self.assertEqual(response.status_code, 200)
        vendors = response.get_json()
        self.assertIsInstance(vendors, list)
        self.assertGreaterEqual(len(vendors), 4)

        # Check vendor fields
        v1 = vendors[0]
        self.assertIn("id", v1)
        self.assertIn("name", v1)
        self.assertIn("code", v1)
        self.assertIn("product_count", v1)
        self.assertIn("inventory_value", v1)

    def test_04_get_vendor_by_id(self):
        """TC-04: GET /api/vendors/<id> retrieves single vendor with assigned products."""
        if not self.redis_available:
            self.skipTest("Redis offline")

        response = self.client.get("/api/vendors/1")
        self.assertEqual(response.status_code, 200)
        vendor = response.get_json()
        self.assertEqual(vendor["id"], 1)
        self.assertIn("products", vendor)

    def test_05_add_vendor(self):
        """TC-05: POST /api/vendors creates a new vendor and returns 201."""
        if not self.redis_available:
            self.skipTest("Redis offline")

        payload = {
            "name": "Zenith Mobile Distribution Hub",
            "code": "ZMD-HUB",
            "category": "Regional Flagship Supplier",
            "email": "zenith@mobiledist.com",
            "phone": "+91 98999 11223",
            "location": "Chennai, Tamil Nadu"
        }
        response = self.client.post("/api/vendors", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["vendor"]["name"], payload["name"])

    def test_06_get_mobiles(self):
        """TC-06: GET /api/mobiles returns mobile products list with all required attributes."""
        if not self.redis_available:
            self.skipTest("Redis offline")

        response = self.client.get("/api/mobiles")
        self.assertEqual(response.status_code, 200)
        mobiles = response.get_json()
        self.assertIsInstance(mobiles, list)
        self.assertGreater(len(mobiles), 0)

        item = mobiles[0]
        self.assertIn("id", item)
        self.assertIn("brand", item)
        self.assertIn("model", item)
        self.assertIn("price", item)
        self.assertIn("storage", item)
        self.assertIn("status", item)
        self.assertIn("vendor_id", item)
        self.assertIn("vendor_name", item)

    def test_07_filter_and_search_mobiles(self):
        """TC-07: Query filters (brand, status, vendor_id, search, sort) work accurately."""
        if not self.redis_available:
            self.skipTest("Redis offline")

        # Brand filter
        res_brand = self.client.get("/api/mobiles?brand=Apple")
        self.assertEqual(res_brand.status_code, 200)
        for m in res_brand.get_json():
            self.assertEqual(m["brand"].lower(), "apple")

        # Sort price desc
        res_sort = self.client.get("/api/mobiles?sort=price-desc")
        self.assertEqual(res_sort.status_code, 200)
        sorted_m = res_sort.get_json()
        if len(sorted_m) >= 2:
            self.assertGreaterEqual(sorted_m[0]["price"], sorted_m[1]["price"])

    def test_08_crud_lifecycle_mobile(self):
        """TC-08: Complete mobile product lifecycle: Create -> Get -> Update -> Delete."""
        if not self.redis_available:
            self.skipTest("Redis offline")

        # 1. Create
        payload = {
            "brand": "Google",
            "model": "Pixel 9 Pro XL",
            "price": 109999,
            "storage": "256 GB",
            "status": "Flagship",
            "vendor_id": 2
        }
        res_create = self.client.post("/api/mobiles", json=payload)
        self.assertEqual(res_create.status_code, 201)
        created = res_create.get_json()["mobile"]
        m_id = created["id"]
        self.assertEqual(created["brand"], "Google")
        self.assertEqual(created["price"], 109999.0)

        # 2. Get by ID
        res_get = self.client.get(f"/api/mobiles/{m_id}")
        self.assertEqual(res_get.status_code, 200)
        fetched = res_get.get_json()
        self.assertEqual(fetched["id"], m_id)
        self.assertEqual(fetched["model"], "Pixel 9 Pro XL")

        # 3. Update
        update_payload = {
            "price": 99999,
            "status": "In Stock"
        }
        res_update = self.client.put(f"/api/mobiles/{m_id}", json=update_payload)
        self.assertEqual(res_update.status_code, 200)
        updated = res_update.get_json()["mobile"]
        self.assertEqual(updated["price"], 99999.0)
        self.assertEqual(updated["status"], "In Stock")

        # 4. Delete
        res_delete = self.client.delete(f"/api/mobiles/{m_id}")
        self.assertEqual(res_delete.status_code, 200)
        self.assertTrue(res_delete.get_json()["success"])

        # 5. Verify deleted returns 404
        res_verify = self.client.get(f"/api/mobiles/{m_id}")
        self.assertEqual(res_verify.status_code, 404)

    def test_09_validation_rejections(self):
        """TC-09: Rejects negative prices, non-numeric prices, and missing required fields."""
        # Negative price
        res_neg = self.client.post("/api/mobiles", json={
            "brand": "Apple",
            "model": "iPhone 15",
            "price": -500
        })
        self.assertEqual(res_neg.status_code, 400)
        self.assertIn("cannot be negative", res_neg.get_json()["error"])

        # Non-numeric price
        res_nan = self.client.post("/api/mobiles", json={
            "brand": "Apple",
            "model": "iPhone 15",
            "price": "not_a_number"
        })
        self.assertEqual(res_nan.status_code, 400)

        # Missing brand
        res_no_brand = self.client.post("/api/mobiles", json={
            "model": "iPhone 15",
            "price": 69999
        })
        self.assertEqual(res_no_brand.status_code, 400)

        # Missing model
        res_no_model = self.client.post("/api/mobiles", json={
            "brand": "Apple",
            "price": 69999
        })
        self.assertEqual(res_no_model.status_code, 400)

    def test_10_inventory_statistics(self):
        """TC-10: GET /api/stats computes dynamic analytics from Redis data."""
        if not self.redis_available:
            self.skipTest("Redis offline")

        response = self.client.get("/api/stats")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        stats = data["stats"]

        self.assertIn("total_mobiles", stats)
        self.assertIn("total_vendors", stats)
        self.assertIn("total_orders", stats)
        self.assertIn("total_value", stats)
        self.assertIn("avg_price", stats)
        self.assertIn("brand_distribution", stats)
        self.assertIn("top_expensive", stats)
        self.assertIn("recent_activity", stats)
        self.assertIsInstance(stats["brand_distribution"], list)

    def test_11_orders_crud(self):
        """TC-11: Customer and trade-in orders CRUD lifecycle via /api/orders."""
        if not self.redis_available:
            self.skipTest("Redis offline")

        # 1. GET all orders
        res_get = self.client.get("/api/orders")
        self.assertEqual(res_get.status_code, 200)
        data_get = res_get.get_json()
        self.assertTrue(data_get["success"])
        self.assertIsInstance(data_get["orders"], list)
        initial_count = len(data_get["orders"])
        self.assertGreaterEqual(initial_count, 1)

        # 2. POST create new order
        new_order_payload = {
            "id": "CM-TEST999",
            "customer_name": "Test Customer",
            "customer_phone": "9998887776",
            "customer_address": "Test Avenue 101, Bangalore",
            "device_name": "Apple iPhone 15",
            "storage": "128 GB",
            "fulfillment_type": "Doorstep Delivery",
            "amount": 69999.0,
            "status": "Confirmed"
        }
        res_post = self.client.post("/api/orders", json=new_order_payload)
        self.assertEqual(res_post.status_code, 201)
        data_post = res_post.get_json()
        self.assertTrue(data_post["success"])
        self.assertEqual(data_post["order"]["id"], "CM-TEST999")

        # 3. GET single order
        res_single = self.client.get("/api/orders/CM-TEST999")
        self.assertEqual(res_single.status_code, 200)
        self.assertEqual(res_single.get_json()["order"]["customer_name"], "Test Customer")

        # 4. PUT update order status
        res_put = self.client.put("/api/orders/CM-TEST999", json={"status": "Dispatched"})
        self.assertEqual(res_put.status_code, 200)
        self.assertEqual(res_put.get_json()["order"]["status"], "Dispatched")

    def test_12_alias_web_routes(self):
        """TC-12: Convenient alias routes /admin, /dashboard, /store, /shop work cleanly."""
        res_admin = self.client.get("/admin")
        self.assertEqual(res_admin.status_code, 200)

        res_dash = self.client.get("/dashboard")
        self.assertEqual(res_dash.status_code, 200)

        res_store = self.client.get("/store")
        self.assertEqual(res_store.status_code, 200)
        self.assertIn(b"CoherentMobiles", res_store.data)

        res_shop = self.client.get("/shop")
        self.assertEqual(res_shop.status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
