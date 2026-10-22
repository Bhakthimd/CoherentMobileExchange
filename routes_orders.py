import secrets
import time
from flask import Blueprint, request, jsonify, g
from sqlalchemy import desc

from database import SessionLocal
import models
from models import (
    Order, OrderItem, InventoryUnit, UnitStatus, StockMovement,
    User, UserRole, Vendor, utc_now
)
from auth import login_required, extract_token_from_request, get_session

orders_bp = Blueprint("orders", __name__)


def generate_order_reference() -> str:
    timestamp = int(time.time())
    suffix = secrets.token_hex(3).upper()
    return f"CM-{timestamp}-{suffix}"


@orders_bp.route("/api/orders", methods=["POST"])
def create_order():
    """
    Checkout endpoint: places an order for a specific inventory unit.
    Uses 'SELECT ... FOR UPDATE' in a database transaction to lock the unit
    and prevent race conditions/double purchasing.
    """
    data = request.get_json(silent=True) or {}
    unit_id = data.get("unit_id")
    customer_name = (data.get("customer_name") or data.get("name") or "").strip()
    customer_email = (data.get("customer_email") or data.get("email") or "").strip().lower()
    customer_phone = (data.get("customer_phone") or data.get("phone") or "").strip()
    delivery_address = (data.get("delivery_address") or data.get("address") or "").strip()
    payment_method = (data.get("payment_method") or "pod").strip()  # pod (Pay on delivery) / mock_upi
    trade_in_credit = max(0.0, float(data.get("trade_in_credit") or 0.0))
    coupon_discount = max(0.0, float(data.get("coupon_discount") or 0.0))

    if not unit_id:
        return jsonify({"success": False, "error": "unit_id is required for checkout."}), 400
    if not customer_name:
        return jsonify({"success": False, "error": "Customer name is required."}), 400
    if not delivery_address:
        return jsonify({"success": False, "error": "Delivery address is required."}), 400

    # Determine user if authenticated
    user_id = None
    token = extract_token_from_request()
    session_data = get_session(token) if token else None
    if session_data:
        user_id = session_data.get("user_id")

    db = SessionLocal()
    try:
        # Atomic transaction with row locking
        # SELECT ... FOR UPDATE locks the specific inventory unit row
        unit = db.query(InventoryUnit).filter(
            InventoryUnit.unit_id == unit_id
        ).with_for_update().first()

        # Check availability
        if not unit or unit.deleted_at is not None or unit.status != UnitStatus.in_stock.value:
            db.rollback()
            return jsonify({
                "success": False,
                "error": "This device has just been reserved or purchased by another customer. Please select another unit."
            }), 409

        # Calculate amounts
        selling_price = float(unit.selling_price)
        total_amount = max(0.0, selling_price - trade_in_credit - coupon_discount)

        # Mark unit as sold (or reserved)
        unit.status = UnitStatus.sold.value
        unit.updated_at = utc_now()

        # If user not logged in, link to existing customer by email if exists
        if not user_id and customer_email:
            existing_user = db.query(User).filter_by(email=customer_email).first()
            if existing_user:
                user_id = existing_user.user_id

        order_ref = generate_order_reference()

        # Create Order
        order = Order(
            user_id=user_id,
            order_reference=order_ref,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            subtotal=selling_price,
            trade_in_credit=trade_in_credit,
            coupon_discount=coupon_discount,
            total_amount=total_amount,
            delivery_address=delivery_address,
            order_status="placed",
            payment_method=payment_method,
            payment_status="pending" if payment_method == "pod" else "paid",
            created_at=utc_now(),
            updated_at=utc_now()
        )
        db.add(order)
        db.flush()

        # Create OrderItem linked to unit and vendor
        order_item = OrderItem(
            order_id=order.order_id,
            unit_id=unit.unit_id,
            variant_id=unit.variant_id,
            vendor_id=unit.vendor_id,
            quantity=1,
            price=selling_price,
            item_status="confirmed"
        )
        db.add(order_item)

        # Record stock movement audit trail
        movement = StockMovement(
            unit_id=unit.unit_id,
            vendor_id=unit.vendor_id,
            action="sold",
            actor_user_id=user_id,
            old_value={"status": "in_stock", "price": selling_price},
            new_value={"status": "sold", "order_reference": order_ref, "price": selling_price},
            created_at=utc_now()
        )
        db.add(movement)

        # Commit entire transaction atomically
        db.commit()
        db.refresh(order)

        return jsonify({
            "success": True,
            "message": "Order placed successfully! Your refurbished device has been reserved.",
            "order": order.to_dict()
        }), 201

    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "error": f"Failed to complete checkout: {str(e)}"}), 500
    finally:
        db.close()


@orders_bp.route("/api/orders", methods=["GET"])
@orders_bp.route("/api/customer/orders", methods=["GET"])
def get_orders():
    """Retrieve orders: user's own orders if logged in, or all orders if admin."""
    token = extract_token_from_request()
    session_data = get_session(token) if token else None

    db = SessionLocal()
    try:
        if session_data:
            user = db.query(User).filter_by(user_id=session_data["user_id"]).first()
            if user and user.role == UserRole.admin.value:
                orders = db.query(Order).order_by(desc(Order.created_at)).all()
                return jsonify({"success": True, "orders": [o.to_dict() for o in orders]}), 200
            elif user:
                orders = db.query(Order).filter_by(user_id=user.user_id).order_by(desc(Order.created_at)).all()
                return jsonify({"success": True, "orders": [o.to_dict() for o in orders]}), 200

        # Guest order lookup by email or phone
        email = request.args.get("email", "").strip().lower()
        phone = request.args.get("phone", "").strip()
        if email or phone:
            query = db.query(Order)
            if email:
                query = query.filter(Order.customer_email.ilike(email))
            if phone:
                query = query.filter(Order.customer_phone == phone)
            orders = query.order_by(desc(Order.created_at)).all()
            return jsonify({"success": True, "orders": [o.to_dict() for o in orders]}), 200

        return jsonify({"success": False, "error": "Authentication or customer lookup parameters required."}), 401
    finally:
        db.close()


@orders_bp.route("/api/orders/<string:order_ref>", methods=["GET"])
def get_order_by_ref(order_ref: str):
    """Retrieve single order details by reference number or ID."""
    db = SessionLocal()
    try:
        if order_ref.isdigit():
            order = db.query(Order).filter((Order.order_id == int(order_ref)) | (Order.order_reference == order_ref)).first()
        else:
            order = db.query(Order).filter_by(order_reference=order_ref).first()

        if not order:
            return jsonify({"success": False, "error": "Order not found."}), 404

        return jsonify({"success": True, "order": order.to_dict()}), 200
    finally:
        db.close()
