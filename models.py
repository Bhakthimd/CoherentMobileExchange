from datetime import datetime, timezone, timedelta
import enum
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, Float, Boolean, Date, DateTime,
    ForeignKey, UniqueConstraint, CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import relationship

from database import Base


def utc_now():
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    customer = "customer"
    vendor = "vendor"
    admin = "admin"


class VendorApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    suspended = "suspended"


class ConditionGrade(str, enum.Enum):
    like_new = "like_new"
    good = "good"
    fair = "fair"


class UnitStatus(str, enum.Enum):
    in_stock = "in_stock"
    reserved = "reserved"
    sold = "sold"
    hidden = "hidden"


class SellRequestStatus(str, enum.Enum):
    submitted = "submitted"
    store_confirmed = "store_confirmed"
    inspected = "inspected"
    offer_revised = "offer_revised"
    accepted = "accepted"
    rejected = "rejected"
    paid = "paid"
    cancelled = "cancelled"
    no_show = "no_show"


class FulfilmentType(str, enum.Enum):
    store_visit = "store_visit"
    home_pickup = "home_pickup"


class ReservationStatus(str, enum.Enum):
    active = "active"
    collected = "collected"
    expired = "expired"
    cancelled = "cancelled"


# ---------------------------------------------------------------------------
# Core Entities
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=True, index=True)
    phone = Column(String(20), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    role = Column(
        String(20),
        default=UserRole.customer.value,
        nullable=False,
        server_default="customer"
    )
    created_at = Column(DateTime(timezone=True), default=utc_now)

    # Relationships
    vendor = relationship("Vendor", back_populates="user", uselist=False)
    orders = relationship("Order", back_populates="user")
    auth_sessions = relationship("AuthSession", back_populates="user")

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Vendor(Base):
    __tablename__ = "vendors"

    vendor_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, index=True)
    vendor_name = Column(String(150), nullable=False)
    vendor_code = Column(String(50), unique=True, nullable=False, index=True)
    category = Column(String(100), nullable=True)
    contact_email = Column(String(100), nullable=True)
    contact_phone = Column(String(30), nullable=True)
    location = Column(String(150), nullable=True)
    address = Column(Text, nullable=True)
    gst_number = Column(String(50), nullable=True)
    logo_url = Column(String(255), nullable=True)
    rating = Column(Numeric(3, 2), default=4.80)
    status = Column(String(30), default="Active")
    approval_status = Column(
        String(20),
        default=VendorApprovalStatus.pending.value,
        nullable=False,
        server_default="pending"
    )
    created_at = Column(DateTime(timezone=True), default=utc_now)

    # Mysuru / K.T. Street local store model additions
    store_name = Column(String(150), nullable=True)
    address_line = Column(String(255), nullable=True)
    landmark = Column(String(150), nullable=True)
    area = Column(String(100), default="K.T. Street", nullable=False, server_default="K.T. Street")
    city = Column(String(100), default="Mysuru", nullable=False, server_default="Mysuru")
    pincode = Column(String(10), default="570001", nullable=False, server_default="570001")
    latitude = Column(Float, default=12.3052)
    longitude = Column(Float, default=76.6551)
    whatsapp_number = Column(String(30), nullable=True)
    opening_hours = Column(JSON, nullable=True)
    accepts_walk_in = Column(Boolean, default=True, server_default="true")
    offers_home_pickup = Column(Boolean, default=True, server_default="true")
    offers_doorstep_delivery = Column(Boolean, default=True, server_default="true")
    buyback_enabled = Column(Boolean, default=True, server_default="true")
    store_photos = Column(JSON, nullable=True)
    google_maps_url = Column(String(255), nullable=True)
    is_hand_verified = Column(Boolean, default=True, server_default="true")

    # Relationships
    user = relationship("User", back_populates="vendor")
    variants = relationship("PhoneVariant", back_populates="vendor")
    inventory_units = relationship("InventoryUnit", back_populates="vendor")
    order_items = relationship("OrderItem", back_populates="vendor")
    stock_movements = relationship("StockMovement", back_populates="vendor")
    sell_requests = relationship("SellRequest", back_populates="store", foreign_keys="SellRequest.store_id")
    reservations = relationship("Reservation", back_populates="store", foreign_keys="Reservation.store_id")
    reviews = relationship("StoreReview", back_populates="store", cascade="all, delete-orphan", order_by="desc(StoreReview.created_at)")

    def get_trust_metrics(self):
        """
        Trust rule implementation from Mysuru K.T. Street business plan:
        'Customers only see stores with an average review of at least 4.0 from at least 3 reviews.
        Hand-verified launch partners are shown while they collect their first reviews.'
        """
        revs = self.reviews or []
        count = len(revs)
        if count > 0:
            avg = round(sum(float(r.rating) for r in revs) / count, 1)
        else:
            avg = float(self.rating) if self.rating is not None else 4.8

        is_launch_partner = bool(self.is_hand_verified)
        is_trust_qualified = is_launch_partner or (count >= 3 and avg >= 4.0)

        badge = "Hand-Verified Launch Partner" if is_launch_partner else ("Top Rated Store" if is_trust_qualified else "Collecting Reviews")

        return {
            "review_count": count,
            "average_rating": avg,
            "is_hand_verified": is_launch_partner,
            "is_trust_qualified": is_trust_qualified,
            "trust_badge": badge
        }

    def is_open_now(self, now_dt=None):
        if not self.opening_hours or not isinstance(self.opening_hours, dict):
            return True  # default open if hours not configured

        # IST is UTC+5:30
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        current_dt = now_dt or datetime.now(ist_tz)
        weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        current_day = weekday_names[current_dt.weekday()]

        day_info = self.opening_hours.get(current_day)
        if not day_info:
            return True

        if day_info.get("is_closed") or day_info.get("closed"):
            return False

        open_str = day_info.get("open", "10:00")
        close_str = day_info.get("close", "21:00")
        try:
            open_h, open_m = map(int, open_str.split(":"))
            close_h, close_m = map(int, close_str.split(":"))
            current_time_minutes = current_dt.hour * 60 + current_dt.minute
            open_time_minutes = open_h * 60 + open_m
            close_time_minutes = close_h * 60 + close_m
            return open_time_minutes <= current_time_minutes <= close_time_minutes
        except Exception:
            return True

    def to_dict(self):
        display_name = self.store_name or self.vendor_name
        lat = float(self.latitude) if self.latitude is not None else 12.3052
        lng = float(self.longitude) if self.longitude is not None else 76.6551
        maps_url = self.google_maps_url or f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"

        trust = self.get_trust_metrics()

        return {
            "vendor_id": self.vendor_id,
            "id": self.vendor_id,  # backward compatibility
            "user_id": self.user_id,
            "vendor_name": self.vendor_name,
            "name": display_name,  # backward compatibility
            "store_name": display_name,
            "vendor_code": self.vendor_code,
            "code": self.vendor_code,  # backward compatibility
            "category": self.category,
            "contact_email": self.contact_email,
            "email": self.contact_email,  # backward compatibility
            "contact_phone": self.contact_phone,
            "phone": self.contact_phone,  # backward compatibility
            "location": self.location,
            "address": self.address,
            "address_line": self.address_line or self.address,
            "landmark": self.landmark,
            "area": self.area or "K.T. Street",
            "city": self.city or "Mysuru",
            "pincode": self.pincode or "570001",
            "latitude": lat,
            "longitude": lng,
            "whatsapp_number": self.whatsapp_number or self.contact_phone,
            "opening_hours": self.opening_hours,
            "is_open": self.is_open_now(),
            "accepts_walk_in": bool(self.accepts_walk_in),
            "offers_home_pickup": bool(self.offers_home_pickup),
            "offers_doorstep_delivery": bool(self.offers_doorstep_delivery),
            "buyback_enabled": bool(self.buyback_enabled),
            "store_photos": self.store_photos or [],
            "google_maps_url": maps_url,
            "gst_number": self.gst_number,
            "logo_url": self.logo_url,
            "rating": trust["average_rating"],
            "review_count": trust["review_count"],
            "is_hand_verified": trust["is_hand_verified"],
            "trust_rule_passed": trust["is_trust_qualified"],
            "trust_badge": trust["trust_badge"],
            "status": self.status,
            "approval_status": self.approval_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class StoreReview(Base):
    """Customer ratings and reviews on verified K.T. Street partner stores."""
    __tablename__ = "store_reviews"

    review_id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False, index=True)
    customer_name = Column(String(100), nullable=False)
    customer_phone = Column(String(20), nullable=True)
    rating = Column(Float, nullable=False, default=5.0)  # 1.0 to 5.0
    review_title = Column(String(150), nullable=True)
    review_text = Column(Text, nullable=True)
    device_tag = Column(String(100), nullable=True)  # e.g. "Reserved iPhone 18 Pro", "Sold OnePlus 12"
    is_verified_visit = Column(Boolean, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), default=utc_now)

    store = relationship("Vendor", back_populates="reviews")

    def to_dict(self):
        return {
            "review_id": self.review_id,
            "store_id": self.store_id,
            "customer_name": self.customer_name,
            "rating": round(float(self.rating), 1),
            "review_title": self.review_title or "Verified Store Experience",
            "review_text": self.review_text or "",
            "device_tag": self.device_tag or "K.T. Street Walk-in Customer",
            "is_verified_visit": bool(self.is_verified_visit),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Brand(Base):
    __tablename__ = "brands"

    brand_id = Column(Integer, primary_key=True, autoincrement=True)
    brand_name = Column(String(100), unique=True, nullable=False)
    logo_url = Column(String(255), nullable=True)

    series = relationship("PhoneSeries", back_populates="brand", cascade="all, delete-orphan")

    def to_dict(self):
        bname = self.brand_name.strip()
        slug = bname.lower().replace(" ", "").replace("-", "")
        # High quality official logos / SVGs for mobile brands
        brand_logos = {
            "apple": "https://upload.wikimedia.org/wikipedia/commons/f/fa/Apple_logo_black.svg",
            "samsung": "https://upload.wikimedia.org/wikipedia/commons/2/24/Samsung_Logo.svg",
            "oneplus": "https://upload.wikimedia.org/wikipedia/commons/f/f8/OP_LU_Reg_1L_RGB_red_pos.svg",
            "xiaomi": "https://upload.wikimedia.org/wikipedia/commons/2/29/Xiaomi_logo.svg",
            "vivo": "https://upload.wikimedia.org/wikipedia/commons/e/e5/Vivo_mobile_logo.png",
            "oppo": "https://upload.wikimedia.org/wikipedia/commons/0/02/OPPO_LOGO_2019.svg",
            "realme": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1d/Realme_logo.svg/1024px-Realme_logo.svg.png",
            "google": "https://upload.wikimedia.org/wikipedia/commons/2/2f/Google_2015_logo.svg",
            "googlepixel": "https://upload.wikimedia.org/wikipedia/commons/2/2f/Google_2015_logo.svg",
            "nothing": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c9/Nothing_Logo.svg/1200px-Nothing_Logo.svg.png",
            "motorola": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Motorola_new_logo.svg/1200px-Motorola_new_logo.svg.png"
        }
        logo = self.logo_url or brand_logos.get(slug) or f"https://placehold.co/120x40/png?text={bname}"
        return {
            "brand_id": self.brand_id,
            "brand_name": self.brand_name,
            "logo_url": logo,
        }


class PhoneSeries(Base):
    __tablename__ = "phone_series"

    series_id = Column(Integer, primary_key=True, autoincrement=True)
    brand_id = Column(Integer, ForeignKey("brands.brand_id", ondelete="CASCADE"), nullable=False)
    series_name = Column(String(100), nullable=False)

    __table_args__ = (
        UniqueConstraint("brand_id", "series_name", name="uq_brand_series"),
    )

    brand = relationship("Brand", back_populates="series")
    models = relationship("PhoneModel", back_populates="series", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "series_id": self.series_id,
            "brand_id": self.brand_id,
            "series_name": self.series_name,
        }


class PhoneModel(Base):
    __tablename__ = "phone_models"

    model_id = Column(Integer, primary_key=True, autoincrement=True)
    series_id = Column(Integer, ForeignKey("phone_series.series_id", ondelete="CASCADE"), nullable=False)
    model_name = Column(String(100), nullable=False)
    image_url = Column(String(255), nullable=True)

    series = relationship("PhoneSeries", back_populates="models")
    variants = relationship("PhoneVariant", back_populates="model", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "model_id": self.model_id,
            "series_id": self.series_id,
            "model_name": self.model_name,
            "image_url": self.image_url,
            "brand_name": self.series.brand.brand_name if self.series and self.series.brand else None,
            "series_name": self.series.series_name if self.series else None,
        }


class PhoneVariant(Base):
    __tablename__ = "phone_variants"

    variant_id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, ForeignKey("phone_models.model_id", ondelete="CASCADE"), nullable=False)
    storage_gb = Column(Integer, nullable=False)
    ram_gb = Column(Integer, nullable=False)
    color = Column(String(50), nullable=True)
    battery_capacity = Column(Integer, nullable=True)
    listed_price = Column(Numeric(10, 2), nullable=True)
    rating = Column(Numeric(3, 2), default=4.50)
    stock_quantity = Column(Integer, default=0)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="SET NULL"), nullable=True)

    model = relationship("PhoneModel", back_populates="variants")
    vendor = relationship("Vendor", back_populates="variants")
    inventory_units = relationship("InventoryUnit", back_populates="variant")
    pricing_records = relationship("Pricing", back_populates="variant", cascade="all, delete-orphan")
    images = relationship("MobileImage", back_populates="variant", cascade="all, delete-orphan")

    def to_dict(self):
        brand_name = self.model.series.brand.brand_name if self.model and self.model.series and self.model.series.brand else None
        model_name = self.model.model_name if self.model else None
        image_url = self.model.image_url if self.model else None
        return {
            "variant_id": self.variant_id,
            "model_id": self.model_id,
            "brand_name": brand_name,
            "model_name": model_name,
            "storage_gb": self.storage_gb,
            "storage": f"{self.storage_gb} GB",
            "ram_gb": self.ram_gb,
            "ram": f"{self.ram_gb} GB",
            "color": self.color,
            "battery_capacity": self.battery_capacity,
            "listed_price": float(self.listed_price) if self.listed_price is not None else None,
            "rating": float(self.rating) if self.rating is not None else 4.5,
            "stock_quantity": self.stock_quantity,
            "vendor_id": self.vendor_id,
            "image_url": image_url,
        }


class InventoryUnit(Base):
    __tablename__ = "inventory_units"

    unit_id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("phone_variants.variant_id", ondelete="SET NULL"), nullable=True, index=True)
    imei = Column(String(20), unique=True, nullable=False, index=True)
    condition_grade = Column(String(20), nullable=False)  # like_new, good, fair
    battery_health = Column(Integer, nullable=True)  # 0 - 100
    selling_price = Column(Numeric(10, 2), nullable=False)
    mrp = Column(Numeric(10, 2), nullable=True)
    warranty_months = Column(Integer, default=6)
    status = Column(String(20), default=UnitStatus.in_stock.value, nullable=False, index=True)  # in_stock, reserved, sold, hidden
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # soft delete

    __table_args__ = (
        CheckConstraint("battery_health IS NULL OR (battery_health >= 0 AND battery_health <= 100)", name="check_battery_health"),
    )

    vendor = relationship("Vendor", back_populates="inventory_units")
    variant = relationship("PhoneVariant", back_populates="inventory_units")
    images = relationship("UnitImage", back_populates="unit", cascade="all, delete-orphan", order_by="UnitImage.sort_order")
    order_items = relationship("OrderItem", back_populates="unit")
    stock_movements = relationship("StockMovement", back_populates="unit")

    def to_dict(self):
        brand_name = None
        model_name = None
        storage = None
        ram = None
        color = None
        if self.variant:
            storage = f"{self.variant.storage_gb} GB"
            ram = f"{self.variant.ram_gb} GB"
            color = self.variant.color
            if self.variant.model:
                model_name = self.variant.model.model_name
                if self.variant.model.series and self.variant.model.series.brand:
                    brand_name = self.variant.model.series.brand.brand_name

        image_urls = [img.image_url for img in self.images] if self.images else []
        primary_image = image_urls[0] if image_urls else (self.variant.model.image_url if self.variant and self.variant.model else None)

        store_name = (self.vendor.store_name or self.vendor.vendor_name) if self.vendor else None
        store_address = (self.vendor.address_line or self.vendor.address) if self.vendor else None

        return {
            "unit_id": self.unit_id,
            "id": self.unit_id,
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor.vendor_name if self.vendor else None,
            "store_id": self.vendor_id,
            "store_name": store_name,
            "store_address": store_address,
            "store_landmark": self.vendor.landmark if self.vendor else None,
            "store_phone": self.vendor.contact_phone if self.vendor else None,
            "store_whatsapp": self.vendor.whatsapp_number if self.vendor else None,
            "store_is_open": self.vendor.is_open_now() if self.vendor else True,
            "store_directions_url": self.vendor.google_maps_url if self.vendor else None,
            "variant_id": self.variant_id,
            "brand": brand_name,
            "model": model_name,
            "device_name": f"{brand_name} {model_name}" if brand_name and model_name else (model_name or "Unknown Device"),
            "storage": storage,
            "ram": ram,
            "color": color,
            "imei": self.imei,
            "condition_grade": self.condition_grade,
            "grade": self.condition_grade,
            "battery_health": self.battery_health,
            "selling_price": float(self.selling_price) if self.selling_price is not None else 0.0,
            "price": float(self.selling_price) if self.selling_price is not None else 0.0,
            "mrp": float(self.mrp) if self.mrp is not None else None,
            "warranty_months": self.warranty_months,
            "warranty": f"{self.warranty_months} Months" if self.warranty_months else None,
            "status": self.status,
            "notes": self.notes,
            "images": image_urls,
            "image": primary_image,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }


class UnitImage(Base):
    __tablename__ = "unit_images"

    image_id = Column(Integer, primary_key=True, autoincrement=True)
    unit_id = Column(Integer, ForeignKey("inventory_units.unit_id", ondelete="CASCADE"), nullable=False, index=True)
    image_url = Column(String(255), nullable=False)
    sort_order = Column(Integer, default=0)

    unit = relationship("InventoryUnit", back_populates="images")

    def to_dict(self):
        return {
            "image_id": self.image_id,
            "unit_id": self.unit_id,
            "image_url": self.image_url,
            "sort_order": self.sort_order,
        }


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, index=True)
    order_reference = Column(String(50), unique=True, nullable=False, index=True)
    customer_name = Column(String(100), nullable=True)
    customer_email = Column(String(150), nullable=True)
    customer_phone = Column(String(20), nullable=True)
    subtotal = Column(Numeric(10, 2), default=0.0)
    trade_in_credit = Column(Numeric(10, 2), default=0.0)
    coupon_discount = Column(Numeric(10, 2), default=0.0)
    total_amount = Column(Numeric(10, 2), default=0.0)
    delivery_address = Column(Text, nullable=True)
    order_status = Column(String(50), default="placed")  # placed, confirmed, processing, shipped, delivered, cancelled
    payment_method = Column(String(50), default="pod")  # pod (pay on delivery), mock_upi, card
    payment_status = Column(String(50), default="pending")  # pending, paid, refunded, failed
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "order_id": self.order_id,
            "order_reference": self.order_reference,
            "user_id": self.user_id,
            "customer_name": self.customer_name or (self.user.name if self.user else None),
            "customer_email": self.customer_email or (self.user.email if self.user else None),
            "customer_phone": self.customer_phone or (self.user.phone if self.user else None),
            "subtotal": float(self.subtotal) if self.subtotal is not None else 0.0,
            "trade_in_credit": float(self.trade_in_credit) if self.trade_in_credit is not None else 0.0,
            "coupon_discount": float(self.coupon_discount) if self.coupon_discount is not None else 0.0,
            "total_amount": float(self.total_amount) if self.total_amount is not None else 0.0,
            "delivery_address": self.delivery_address,
            "order_status": self.order_status,
            "payment_method": self.payment_method,
            "payment_status": self.payment_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "items": [item.to_dict() for item in self.items] if self.items else [],
        }


class OrderItem(Base):
    __tablename__ = "order_items"

    order_item_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False, index=True)
    unit_id = Column(Integer, ForeignKey("inventory_units.unit_id", ondelete="SET NULL"), nullable=True, index=True)
    variant_id = Column(Integer, ForeignKey("phone_variants.variant_id", ondelete="SET NULL"), nullable=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="SET NULL"), nullable=True, index=True)
    quantity = Column(Integer, default=1)
    price = Column(Numeric(10, 2), nullable=False)
    item_status = Column(String(50), default="confirmed")  # confirmed, packed, shipped, delivered, cancelled

    order = relationship("Order", back_populates="items")
    unit = relationship("InventoryUnit", back_populates="order_items")
    variant = relationship("PhoneVariant")
    vendor = relationship("Vendor", back_populates="order_items")

    def to_dict(self):
        device_name = None
        brand_name = None
        model_name = None
        imei = None
        condition_grade = None
        image = None

        if self.unit:
            imei = self.unit.imei
            condition_grade = self.unit.condition_grade
            if self.unit.images:
                image = self.unit.images[0].image_url
            if self.unit.variant:
                if self.unit.variant.model:
                    model_name = self.unit.variant.model.model_name
                    if not image:
                        image = self.unit.variant.model.image_url
                    if self.unit.variant.model.series and self.unit.variant.model.series.brand:
                        brand_name = self.unit.variant.model.series.brand.brand_name
        elif self.variant and self.variant.model:
            model_name = self.variant.model.model_name
            image = self.variant.model.image_url
            if self.variant.model.series and self.variant.model.series.brand:
                brand_name = self.variant.model.series.brand.brand_name

        if brand_name and model_name:
            device_name = f"{brand_name} {model_name}"
        else:
            device_name = model_name or "Mobile Device"

        return {
            "order_item_id": self.order_item_id,
            "order_id": self.order_id,
            "order_reference": self.order.order_reference if self.order else None,
            "unit_id": self.unit_id,
            "variant_id": self.variant_id,
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor.vendor_name if self.vendor else None,
            "device_name": device_name,
            "brand": brand_name,
            "model": model_name,
            "imei": imei,
            "condition_grade": condition_grade,
            "image": image,
            "quantity": self.quantity,
            "price": float(self.price) if self.price is not None else 0.0,
            "item_status": self.item_status,
            "created_at": self.order.created_at.isoformat() if self.order and self.order.created_at else None,
            "delivery_address": self.order.delivery_address if self.order else None,
            "customer_name": self.order.customer_name if self.order else None,
            "customer_phone": self.order.customer_phone if self.order else None,
        }


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    unit_id = Column(Integer, ForeignKey("inventory_units.unit_id", ondelete="SET NULL"), nullable=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(50), nullable=False)  # added, edited, reserved, sold, hidden, unhidden, deleted
    actor_user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    unit = relationship("InventoryUnit", back_populates="stock_movements")
    vendor = relationship("Vendor", back_populates="stock_movements")
    actor = relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "unit_id": self.unit_id,
            "vendor_id": self.vendor_id,
            "action": self.action,
            "actor_user_id": self.actor_user_id,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# Auxiliary Tables (Existing Storefront & Valuation Flow)
# ---------------------------------------------------------------------------

class Pricing(Base):
    __tablename__ = "pricing"

    pricing_id = Column(Integer, primary_key=True, autoincrement=True)
    variant_id = Column(Integer, ForeignKey("phone_variants.variant_id", ondelete="CASCADE"), nullable=False)
    market_price = Column(Numeric(10, 2), nullable=True)
    original_price = Column(Numeric(10, 2), nullable=True)
    discount = Column(Numeric(10, 2), default=0.0)
    current_price = Column(Numeric(10, 2), nullable=True)
    effective_date = Column(Date, nullable=True)

    variant = relationship("PhoneVariant", back_populates="pricing_records")


class MobileImage(Base):
    __tablename__ = "mobile_images"

    image_id = Column(Integer, primary_key=True, autoincrement=True)
    variant_id = Column(Integer, ForeignKey("phone_variants.variant_id", ondelete="CASCADE"), nullable=False)
    image_url = Column(String(255), nullable=False)
    image_type = Column(String(50), nullable=True)

    variant = relationship("PhoneVariant", back_populates="images")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    session_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True)
    login_method = Column(String(50), nullable=True)
    otp_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="auth_sessions")


class PhoneEvaluation(Base):
    __tablename__ = "phone_evaluations"

    evaluation_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    variant_id = Column(Integer, nullable=True)
    imei_id = Column(Integer, nullable=True)
    feature_score = Column(Integer, nullable=True)
    condition_score = Column(Integer, nullable=True)
    performance_score = Column(Integer, nullable=True)
    overall_score = Column(Integer, nullable=True)
    evaluation_date = Column(DateTime(timezone=True), default=utc_now)


class Estimation(Base):
    __tablename__ = "estimations"

    estimation_id = Column(Integer, primary_key=True, autoincrement=True)
    variant_id = Column(Integer, nullable=True)
    expected_selling_price = Column(Numeric(10, 2), nullable=True)
    estimated_repair_cost = Column(Numeric(10, 2), nullable=True)
    estimated_resale_price = Column(Numeric(10, 2), nullable=True)
    estimation_date = Column(DateTime(timezone=True), default=utc_now)
    exchange_id = Column(Integer, nullable=True)


class ExchangeDetail(Base):
    __tablename__ = "exchange_details"

    exchange_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True)
    old_variant_id = Column(Integer, nullable=True)
    new_variant_id = Column(Integer, nullable=True)
    evaluation_id = Column(Integer, nullable=True)
    exchange_credit = Column(Numeric(10, 2), nullable=True)
    exchange_status = Column(String(50), nullable=True)
    credited_at = Column(DateTime(timezone=True), default=utc_now)


class IMEIDetail(Base):
    __tablename__ = "imei_details"

    imei_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True)
    variant_id = Column(Integer, nullable=True)
    imei_number = Column(String(20), unique=True, nullable=True)
    validation_status = Column(String(50), nullable=True)
    device_eligibility = Column(String(50), nullable=True)
    validation_source = Column(String(100), nullable=True)
    validated_at = Column(DateTime(timezone=True), default=utc_now)


class MobileCondition(Base):
    __tablename__ = "mobile_condition"

    condition_id = Column(Integer, primary_key=True, autoincrement=True)
    evaluation_id = Column(Integer, nullable=True)
    screen_condition = Column(String(100), nullable=True)
    body_condition = Column(String(100), nullable=True)
    battery_health = Column(Integer, nullable=True)
    camera_condition = Column(String(100), nullable=True)
    speaker_condition = Column(String(100), nullable=True)
    charging_condition = Column(String(100), nullable=True)
    overall_condition = Column(String(100), nullable=True)


class Valuation(Base):
    __tablename__ = "valuations"

    valuation_id = Column(Integer, primary_key=True, autoincrement=True)
    evaluation_id = Column(Integer, nullable=True)
    original_value = Column(Numeric(10, 2), nullable=True)
    depreciation = Column(Numeric(10, 2), nullable=True)
    repair_cost = Column(Numeric(10, 2), nullable=True)
    resale_value = Column(Numeric(10, 2), nullable=True)
    final_valuation = Column(Numeric(10, 2), nullable=True)
    valuation_date = Column(DateTime(timezone=True), default=utc_now)
    imei_id = Column(Integer, nullable=True)


class Feedback(Base):
    __tablename__ = "feedback"

    feedback_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    evaluation_id = Column(Integer, nullable=True)
    rating = Column(Integer, nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class Appointment(Base):
    __tablename__ = "appointments"

    appointment_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    order_id = Column(Integer, nullable=True)
    appointment_date = Column(Date, nullable=True)
    appointment_time = Column(String(20), nullable=True)
    location = Column(String(100), nullable=True)
    verification_method = Column(String(50), nullable=True)
    reference_number = Column(String(50), unique=True, nullable=True)
    status = Column(String(50), default="Scheduled")
    created_at = Column(DateTime(timezone=True), default=utc_now)


# ---------------------------------------------------------------------------
# Mysuru / K.T. Street Local Marketplace Extensions
# ---------------------------------------------------------------------------

class ServiceablePincode(Base):
    __tablename__ = "serviceable_pincodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pincode = Column(String(10), unique=True, nullable=False, index=True)
    area_name = Column(String(150), nullable=False)
    city = Column(String(100), default="Mysuru", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "pincode": self.pincode,
            "area_name": self.area_name,
            "city": self.city,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PriceMatrix(Base):
    __tablename__ = "price_matrix"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand = Column(String(100), nullable=False, index=True)
    model = Column(String(100), nullable=False, index=True)
    storage_gb = Column(Integer, nullable=False)
    base_price = Column(Numeric(10, 2), nullable=False)
    screen_scratch_pct = Column(Numeric(5, 2), default=10.0)
    screen_cracked_pct = Column(Numeric(5, 2), default=35.0)
    body_dent_pct = Column(Numeric(5, 2), default=12.0)
    battery_low_pct = Column(Numeric(5, 2), default=15.0)
    camera_fault_pct = Column(Numeric(5, 2), default=20.0)
    speaker_fault_pct = Column(Numeric(5, 2), default=10.0)
    accessories_deduction = Column(Numeric(10, 2), default=1000.0)
    is_active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("brand", "model", "storage_gb", name="uq_price_matrix_variant"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "brand": self.brand,
            "model": self.model,
            "storage_gb": self.storage_gb,
            "base_price": float(self.base_price) if self.base_price is not None else 0.0,
            "screen_scratch_pct": float(self.screen_scratch_pct or 10.0),
            "screen_cracked_pct": float(self.screen_cracked_pct or 35.0),
            "body_dent_pct": float(self.body_dent_pct or 12.0),
            "battery_low_pct": float(self.battery_low_pct or 15.0),
            "camera_fault_pct": float(self.camera_fault_pct or 20.0),
            "speaker_fault_pct": float(self.speaker_fault_pct or 10.0),
            "accessories_deduction": float(self.accessories_deduction or 1000.0),
            "is_active": self.is_active,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SellRequest(Base):
    __tablename__ = "sell_requests"

    request_id = Column(Integer, primary_key=True, autoincrement=True)
    request_reference = Column(String(50), unique=True, nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name = Column(String(100), nullable=False)
    customer_phone = Column(String(20), nullable=False, index=True)
    customer_email = Column(String(150), nullable=True)
    customer_address = Column(Text, nullable=True)
    pincode = Column(String(10), nullable=True, index=True)

    store_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="SET NULL"), nullable=True, index=True)

    brand = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    storage_gb = Column(Integer, nullable=True)
    imei = Column(String(20), nullable=False, index=True)
    condition_answers = Column(JSON, nullable=True)

    estimated_min_price = Column(Numeric(10, 2), nullable=False)
    estimated_max_price = Column(Numeric(10, 2), nullable=False)
    final_offer_price = Column(Numeric(10, 2), nullable=True)
    final_offer_notes = Column(Text, nullable=True)

    fulfilment_type = Column(String(30), default=FulfilmentType.store_visit.value, nullable=False)
    slot_date = Column(Date, nullable=True)
    slot_time = Column(String(30), nullable=True)

    status = Column(String(30), default=SellRequestStatus.submitted.value, nullable=False, index=True)
    payout_method = Column(String(30), nullable=True)  # cash, upi
    payout_reference = Column(String(100), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)

    created_unit_id = Column(Integer, ForeignKey("inventory_units.unit_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    customer = relationship("User", foreign_keys=[customer_id])
    store = relationship("Vendor", back_populates="sell_requests", foreign_keys=[store_id])
    created_unit = relationship("InventoryUnit", foreign_keys=[created_unit_id])
    timeline = relationship("SellRequestTimeline", back_populates="sell_request", cascade="all, delete-orphan", order_by="SellRequestTimeline.created_at.asc()")

    def to_dict(self):
        return {
            "request_id": self.request_id,
            "request_reference": self.request_reference,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "customer_email": self.customer_email,
            "customer_address": self.customer_address,
            "pincode": self.pincode,
            "store_id": self.store_id,
            "store_name": self.store.store_name if self.store else None,
            "store_address": self.store.address_line or self.store.address if self.store else None,
            "store_phone": self.store.contact_phone if self.store else None,
            "brand": self.brand,
            "model": self.model,
            "storage_gb": self.storage_gb,
            "storage": f"{self.storage_gb} GB" if self.storage_gb else None,
            "imei": self.imei,
            "condition_answers": self.condition_answers or {},
            "estimated_min_price": float(self.estimated_min_price) if self.estimated_min_price is not None else 0.0,
            "estimated_max_price": float(self.estimated_max_price) if self.estimated_max_price is not None else 0.0,
            "final_offer_price": float(self.final_offer_price) if self.final_offer_price is not None else None,
            "final_offer_notes": self.final_offer_notes,
            "fulfilment_type": self.fulfilment_type,
            "slot_date": self.slot_date.isoformat() if self.slot_date else None,
            "slot_time": self.slot_time,
            "status": self.status,
            "payout_method": self.payout_method,
            "payout_reference": self.payout_reference,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "created_unit_id": self.created_unit_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "timeline": [t.to_dict() for t in self.timeline] if self.timeline else [],
        }


class SellRequestTimeline(Base):
    __tablename__ = "sell_request_timelines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, ForeignKey("sell_requests.request_id", ondelete="CASCADE"), nullable=False, index=True)
    from_status = Column(String(30), nullable=True)
    to_status = Column(String(30), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    actor_role = Column(String(30), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    sell_request = relationship("SellRequest", back_populates="timeline")

    def to_dict(self):
        return {
            "id": self.id,
            "request_id": self.request_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "actor_user_id": self.actor_user_id,
            "actor_role": self.actor_role,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Reservation(Base):
    __tablename__ = "reservations"

    reservation_id = Column(Integer, primary_key=True, autoincrement=True)
    reservation_reference = Column(String(50), unique=True, nullable=False, index=True)
    unit_id = Column(Integer, ForeignKey("inventory_units.unit_id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name = Column(String(100), nullable=False)
    customer_phone = Column(String(20), nullable=False)
    customer_email = Column(String(150), nullable=True)
    store_id = Column(Integer, ForeignKey("vendors.vendor_id", ondelete="CASCADE"), nullable=False, index=True)
    reserved_at = Column(DateTime(timezone=True), default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(30), default=ReservationStatus.active.value, nullable=False, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    unit = relationship("InventoryUnit")
    customer = relationship("User")
    store = relationship("Vendor", back_populates="reservations", foreign_keys=[store_id])

    def is_expired(self):
        if not self.expires_at:
            return False
        # Normalize timezone awareness
        now = utc_now()
        exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
        return now > exp

    def to_dict(self):
        return {
            "reservation_id": self.reservation_id,
            "reservation_reference": self.reservation_reference,
            "unit_id": self.unit_id,
            "unit": self.unit.to_dict() if self.unit else None,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "customer_email": self.customer_email,
            "store_id": self.store_id,
            "store_name": self.store.store_name if self.store else None,
            "store_address": self.store.address_line or self.store.address if self.store else None,
            "store_phone": self.store.contact_phone if self.store else None,
            "reserved_at": self.reserved_at.isoformat() if self.reserved_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "status": self.status,
            "is_expired": self.is_expired(),
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
