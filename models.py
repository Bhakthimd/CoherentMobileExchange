from datetime import datetime, timezone
import enum
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, Boolean, Date, DateTime,
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

    # Relationships
    user = relationship("User", back_populates="vendor")
    variants = relationship("PhoneVariant", back_populates="vendor")
    inventory_units = relationship("InventoryUnit", back_populates="vendor")
    order_items = relationship("OrderItem", back_populates="vendor")
    stock_movements = relationship("StockMovement", back_populates="vendor")

    def to_dict(self):
        return {
            "vendor_id": self.vendor_id,
            "id": self.vendor_id,  # backward compatibility
            "user_id": self.user_id,
            "vendor_name": self.vendor_name,
            "name": self.vendor_name,  # backward compatibility
            "vendor_code": self.vendor_code,
            "code": self.vendor_code,  # backward compatibility
            "category": self.category,
            "contact_email": self.contact_email,
            "email": self.contact_email,  # backward compatibility
            "contact_phone": self.contact_phone,
            "phone": self.contact_phone,  # backward compatibility
            "location": self.location,
            "address": self.address,
            "gst_number": self.gst_number,
            "logo_url": self.logo_url,
            "rating": float(self.rating) if self.rating is not None else 4.8,
            "status": self.status,
            "approval_status": self.approval_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Brand(Base):
    __tablename__ = "brands"

    brand_id = Column(Integer, primary_key=True, autoincrement=True)
    brand_name = Column(String(100), unique=True, nullable=False)

    series = relationship("PhoneSeries", back_populates="brand", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "brand_id": self.brand_id,
            "brand_name": self.brand_name,
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

        return {
            "unit_id": self.unit_id,
            "id": self.unit_id,
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor.vendor_name if self.vendor else None,
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
