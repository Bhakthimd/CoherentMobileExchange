# CoherentMobiles — Refurbished Mobile Marketplace Platform

CoherentMobiles is an end-to-end Cashify-style refurbished smartphone marketplace connecting certified vendors with customers. Features include IMEI-level unit inventory tracking, condition grading (Like New, Good, Fair), battery health certification, vendor scoped dashboards, concurrent purchase prevention via PostgreSQL `SELECT ... FOR UPDATE` row locking, and admin partner approvals.

---

## 🛠️ Architecture & Tech Stack

- **Backend API**: Flask 3.x, SQLAlchemy 2.x, Alembic migrations against **PostgreSQL** (the single source of truth for all business data).
- **Session & Rate Limiting**: Redis 7.x (RESP2 compatible) managing HttpOnly session cookies, CSRF protection, and rate limiting (5 failed logins / min / IP).
- **Security & Passwords**: Argon2 password hashing (`argon2-cffi`), session token authentication with Bearer header & HttpOnly cookies.
- **Vendor Portal**: Clean responsive vendor pages under `/vendor/` (`dashboard.html`, `inventory.html`, `device-form.html`, `bulk-upload.html`, `orders.html`, `login.html`, `register.html`).
- **Storefront & Checkout**: High-performance customer SPA (`index.html`) backed by `/api/catalog` with real-time stock decrements and concurrency locking.
- **Audit Trail**: Every inventory addition, price edit, status hide/unhide, reservation, sale, and soft-delete creates immutable records in `stock_movements`.

---

## 🚀 Quickstart Guide

### Option 1: Run with Docker Compose (Recommended)

1. Copy the environment configuration:
   ```bash
   cp .env.example .env
   ```
2. Start all services (PostgreSQL, Redis, Flask App):
   ```bash
   docker compose up --build
   ```
3. The platform is immediately live:
   - **Customer Storefront**: [http://localhost:5000/](http://localhost:5000/)
   - **Vendor Portal**: [http://localhost:5000/vendor/login.html](http://localhost:5000/vendor/login.html)
   - **Admin Portal**: [http://localhost:5000/crud-dashboard.html](http://localhost:5000/crud-dashboard.html)

---

### Option 2: Run Locally (Native Windows / Linux / macOS)

1. Ensure PostgreSQL is running on `localhost:5432` with database `coherentmobiles`, and Redis on `localhost:6379`.
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run database migrations:
   ```bash
   alembic upgrade head
   ```
4. Seed the database with initial catalog, vendors, and sample certified units:
   ```bash
   python seed.py
   ```
5. Start the Flask application:
   ```bash
   python app.py
   ```

---

## 🔑 Demo Logins & Credentials

| Role | Email / Store Code | Password | Status & Permissions |
| :--- | :--- | :--- | :--- |
| **System Admin** | `admin@coherent.test` | `Admin@123` | Full administrative oversight, vendor approvals/suspensions |
| **Vendor A** (iStore India) | `IST-IND` / `partner@istoreindia.com` | `Vendor@123` | **Approved** • Premium Flagship Specialist (Can add/edit/sell inventory) |
| **Vendor B** (Apex Mobiles) | `APX-DST` / `contact@apexmobiles.in` | `Vendor@123` | **Approved** • Multi-Brand Wholesaler |
| **Vendor C** (Coherent Retail) | `CR-DIR` / `retail@coherentmobiles.com` | `Vendor@123` | **Approved** • Direct Retail Partner |
| **Vendor D** (Nexus Gadgets) | `NX-HUB` / `sales@nexusgadgets.in` | `Vendor@123` | **Pending Approval** • Cannot publish units until admin approves |

---

## 🧪 Automated Test Suite

Run the full end-to-end pytest suite verifying auth guards, vendor isolation, concurrent purchase locking, bulk CSV upload, and catalog visibility:

```bash
python -m pytest test_marketplace_e2e.py -v
```

### Verified Test Cases:
- `test_01_health_check`: Validates PostgreSQL & Redis connectivity.
- `test_02_customer_registration_and_login`: Customer registration, role verification, and admin route denial.
- `test_03_unauthenticated_guards`: 401 Unauthorized for unauthenticated protected endpoints.
- `test_04_pending_vendor_cannot_add_inventory`: Pending vendors are blocked (403) from listing devices.
- `test_05_vendor_a_creates_unit_and_vendor_b_gets_404`: Strict vendor scoping; Vendor B receives **404 Not Found** when attempting to read, update, or soft-delete Vendor A's units.
- `test_06_storefront_visibility_and_hide_toggle`: Units immediately appear on `/api/catalog`, vanish when toggled to `hidden`, and reappear when set to `in_stock`.
- `test_07_customer_checkout_and_vendor_order_fulfillment`: Checkout marks unit `sold`, removes it from the catalog, displays it in Vendor A's orders, and records audit trail in `stock_movements`.
- `test_08_concurrent_purchase_race_condition`: Two simultaneous threads attempt to purchase the exact same unit. PostgreSQL row locking (`SELECT ... FOR UPDATE`) guarantees **exactly ONE succeeds (201)** and the other receives a **409 Conflict**.
- `test_09_bulk_csv_upload`: CSV batch ingestion with per-row 15-digit Luhn algorithm checks and error reporting.

---

## 📱 Vendor Portal Features (`/vendor/`)

1. **Dashboard (`dashboard.html`)**: Real-time KPI stat cards (In Stock, Reserved, Sold This Month, Revenue), low-stock brand warnings, and recent customer orders.
2. **Inventory (`inventory.html`)**: Searchable, filterable table by brand, status, and condition grade. Inline status toggle (`in_stock` / `hidden`), quick editing, and soft-delete with confirmation.
3. **Add Device (`device-form.html`)**: Cascading dropdowns (Brand → Model → Storage/RAM/Color), real-time client-side and server-side 15-digit IMEI Luhn algorithm validation, battery health (0-100), warranty, and drag-and-drop multi-image uploads.
4. **Bulk CSV Upload (`bulk-upload.html`)**: Ingest hundreds of handsets with downloadable sample CSV template, client-side table preview, and row-by-row error report.
5. **Orders (`orders.html`)**: Vendor order fulfillment tracking with status transitions: `confirmed` → `packed` → `shipped` → `delivered`.

---

## 🛡️ Security Best Practices

- `vendor_id` is **always derived from the authenticated session**, never accepted from the request body or URL.
- CORS restricted to configured domains with credentials enabled.
- Rate limiting on login attempts (5 failed attempts per minute per IP via Redis).
- Passwords hashed with Argon2 (`argon2-cffi`).
- `.env` excluded from version control and git history.
