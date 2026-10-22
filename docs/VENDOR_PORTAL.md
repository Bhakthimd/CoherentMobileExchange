# CoherentMobiles - Vendor Portal & Stock Management Documentation

The Vendor Portal enables certified smartphone retail partners and distributors to log in from the storefront UI, manage live inventory, adjust stock units with real-time status recalculation, update selling prices, and prevent duplicate listings through intelligent stock merging. Customers can view total available stock across all stores, see store-level breakdown with units remaining, and purchase at the lowest in-stock store price.

---

## 1. Vendor Store Logins

Every store can log in using either their **Store Code** or **Store Email** (case-insensitive) with the default vendor password.

| Store ID | Store Name | Store Code | Store Email | Location | Category | Default Password |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | Coherent Retail Direct | `CR-DIR` | `retail@coherentmobiles.com` | Mumbai, Maharashtra | Direct Retail Partner | `Vendor@123` |
| **2** | Apex Mobile Distributors | `APX-DST` | `contact@apexmobiles.in` | Bengaluru, Karnataka | Multi-Brand Authorized Wholesaler | `Vendor@123` |
| **3** | iStore India Authorized | `IST-IND` | `partner@istoreindia.com` | New Delhi, NCR | Premium Flagship Specialist | `Vendor@123` |
| **4** | Nexus Gadgets Hub | `NX-HUB` | `sales@nexusgadgets.in` | Hyderabad, Telangana | Regional Inventory Supplier | `Vendor@123` |

> **Environment Configuration**: The default seed password is controlled by the environment variable `VENDOR_DEFAULT_PASSWORD` (default: `Vendor@123`).

---

## 2. API Endpoints Table

### Vendor Authentication & Management Endpoints

| Method | Endpoint | Auth Required | Description | Request Payload / Params | Response Codes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/vendor/login` | No | Vendor authentication. Returns random token with 8h TTL stored in `vsession:<token>`. Rate-limited to 5 failures per IP+login for 5 mins. | `{"login": "<code> or <email>", "password": "<pwd>"}` | `200` (OK with token & vendor info), `400` (Missing fields), `401` (Invalid credentials), `429` (Locked out) |
| `POST` | `/api/vendor/logout` | `Bearer <token>` | Invalidates active session token from Redis. | None | `200` (Logged out), `401` (Unauthorized) |
| `GET` | `/api/vendor/me` | `Bearer <token>` | Returns logged-in vendor profile and inventory summary. | None | `200` (Profile & summary), `401` (Unauthorized) |
| `GET` | `/api/vendor/inventory` | `Bearer <token>` | Returns own store listings and summary (`total_units`, `listings`, `low_stock_count`, `out_of_stock_count`, `inventory_value`). | None | `200` (Listings & summary), `401` (Unauthorized) |
| `POST` | `/api/vendor/products` | `Bearer <token>` | Adds product or merges stock if brand+model+storage match an existing listing. | `{"brand": str, "model": str, "storage": str, "price": float, "stock": int}` | `200` (Merged existing), `201` (Created new), `400` (Validation error), `401` (Unauthorized) |
| `PUT` | `/api/vendor/products/<id>` | `Bearer <token>` | Updates price and/or stock of vendor-owned listing. Recalculates stock status. Returns 404 for cross-store listings. | `{"price": float, "stock": int}` (at least one) | `200` (Updated), `400` (Invalid value), `404` (Not found/unowned) |
| `DELETE` | `/api/vendor/products/<id>` | `Bearer <token>` | Deletes vendor-owned mobile listing. Returns 404 for cross-store listings. | None | `200` (Deleted), `404` (Not found/unowned) |
| `POST` | `/api/vendor/password` | `Bearer <token>` | Updates store password. Requires minimum 8 characters. | `{"current_password": str, "new_password": str}` | `200` (Success), `400` (Wrong current pwd or < 8 chars) |

### Public & Customer Availability Endpoints

| Method | Endpoint | Auth Required | Description | Request Payload / Params | Response Codes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/availability` | No | Returns active store listings grouped by `brand + model + storage`. Includes only stores with `stock > 0`, sorted ascending by price. | `?search=<query>` (optional) | `200` (`{phones: [{brand, model, storage, image, total_stock, store_count, min_price, stores}]}`) |
| `GET` | `/api/mobiles` | No | Lists all mobile records. Supports filtering by brand, status, vendor_id, search, sort. | Query params: `brand`, `vendor_id`, `status`, `search`, `sort` | `200` |
| `POST` | `/api/mobiles` | No (Admin) | Creates product listing. Accepts integer `stock` (0 to 100,000). Status follows stock. | `{"brand", "model", "price", "storage", "stock", "vendor_id"}` | `201`, `400` (Invalid stock/price) |
| `PUT` | `/api/mobiles/<id>` | No (Admin) | Updates product listing. Accepts integer `stock`. Status follows stock. | `{"price", "stock", "brand", "model", "storage", "status"}` | `200`, `400` (Invalid stock/price), `404` |
| `GET` | `/api/vendors` | No | Lists all registered vendors with `total_units` and `inventory_value = sum(price * stock)`. | None | `200` |
| `POST` | `/api/reset` | No | Resets Redis back to initial seed data from `data.json`. | None | `200` |

---

## 3. Stock Status Rules

Mobile product status follows stock level:
- `0` units: `"Out of Stock"`
- `1` to `3` units: `"Low Stock"`
- `4+` units: `"Flagship"` if selling price > ₹80,000, otherwise `"In Stock"`

---

## 4. Input Validation Rules

- **Brand, Model, Storage**: Validated against regex `^[A-Za-z0-9][A-Za-z0-9 +\-./()]*$`.
  - Brand max length: 60 characters
  - Model max length: 100 characters
  - Storage max length: 20 characters
  - HTML tags (`<`, `>`), single quotes, double quotes, and invalid symbols are rejected with HTTP 400.
- **Price**: Must be a number greater than 0 (`price > 0`).
- **Stock**: Must be an integer between 0 and 100,000 (`0 <= stock <= 100000`). Floats and non-numeric values are rejected with HTTP 400.

---

## 5. Security & Authentication Model

- Passwords are encrypted using standard `werkzeug.security` (`generate_password_hash` / `check_password_hash`).
- `password_hash` is never included in any API response.
- Sessions are maintained using high-entropy random tokens stored in Redis key `vsession:<token>` pointing to `vendor_id` with an 8-hour TTL.
- Bruteforce protection: 5 consecutive failed login attempts for any IP + login combination triggers a 5-minute lockout returning HTTP 429.
- Unknown store logins and incorrect passwords return identical 401 error responses to prevent account enumeration.

---

## 6. Known Limits

1. **Placing an order does not reduce stock yet**: Ordering phones through the checkout flow records orders in Redis, but inventory decrement / reservation is planned for the next fulfillment service milestone.
2. **The admin dashboard and /api/reset are still unauthenticated**: The administrative CRUD dashboard at `/crud-dashboard.html` and the inventory reset endpoint `/api/reset` remain open for demonstration and test convenience.
3. **PostgreSQL schema is unchanged**: Dynamic inventory operations, vendor sessions, and lockout counters are powered directly by Redis key-value/hash structures; PostgreSQL relational tables remain as originally defined.
