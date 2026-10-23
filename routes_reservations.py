"""
24-Hour "Reserve & Visit" Reservation System
CoherentMobiles - Mysuru / K.T. Street Hub
"""

import secrets
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request
from database import SessionLocal
import models
from models import (
    Reservation, ReservationStatus, InventoryUnit, UnitStatus,
    Vendor, StockMovement, utc_now
)

reservations_bp = Blueprint("reservations", __name__, url_prefix="/api")


def release_expired_reservations(db) -> int:
    """
    Finds active reservations that have passed their 24-hour expiration window
    and atomically releases the held inventory units back to 'in_stock'.
    """
    now = utc_now()
    expired = db.query(Reservation).filter(
        Reservation.status == ReservationStatus.active.value,
        Reservation.expires_at <= now
    ).all()

    count = 0
    for res in expired:
        res.status = ReservationStatus.expired.value
        if res.unit and res.unit.status == UnitStatus.reserved.value:
            res.unit.status = UnitStatus.in_stock.value
            movement = StockMovement(
                unit_id=res.unit.unit_id,
                vendor_id=res.store_id,
                action="reservation_expired",
                actor_user_id=None,
                old_value={"status": UnitStatus.reserved.value},
                new_value={
                    "status": UnitStatus.in_stock.value,
                    "reason": f"Reservation {res.reservation_reference} 24-hour hold expired."
                }
            )
            db.add(movement)
            count += 1

    if count > 0:
        db.commit()
    return count


@reservations_bp.route("/reservations", methods=["POST"])
def create_reservation():
    """
    Hold a device for 24 hours to visit and inspect at a K.T. Street store.
    Uses atomic SELECT ... FOR UPDATE to avoid double-booking races.
    """
    data = request.get_json(silent=True) or {}
    unit_id = data.get("unit_id")
    customer_name = (data.get("customer_name") or data.get("name") or "").strip()
    customer_phone = (data.get("customer_phone") or data.get("phone") or "").strip()
    customer_email = (data.get("customer_email") or data.get("email") or "").strip()
    notes = (data.get("notes") or "").strip()

    if not unit_id or not customer_name or not customer_phone:
        return jsonify({
            "success": False,
            "error": "unit_id, customer_name, and customer_phone are required to hold a device."
        }), 400

    db = SessionLocal()
    try:
        # Check and release any past-due reservations first
        release_expired_reservations(db)

        # Atomic lock on the inventory unit
        unit = db.query(InventoryUnit).filter(
            InventoryUnit.unit_id == unit_id,
            InventoryUnit.deleted_at.is_(None)
        ).with_for_update().first()

        if not unit:
            return jsonify({"success": False, "error": f"Device with ID {unit_id} not found."}), 404

        if unit.status != UnitStatus.in_stock.value:
            return jsonify({
                "success": False,
                "error": f"Device is currently '{unit.status}' and unavailable for reservation."
            }), 409

        # Generate reservation reference & 24h expiration
        ref = f"RES-MYS-{secrets.randbelow(89999) + 10000}"
        now = utc_now()
        expires = now + timedelta(hours=24)

        # Mark unit as reserved
        old_status = unit.status
        unit.status = UnitStatus.reserved.value

        reservation = Reservation(
            reservation_reference=ref,
            unit_id=unit.unit_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=customer_email or None,
            store_id=unit.vendor_id,
            reserved_at=now,
            expires_at=expires,
            status=ReservationStatus.active.value,
            notes=notes or None
        )
        db.add(reservation)

        # Audit movement
        movement = StockMovement(
            unit_id=unit.unit_id,
            vendor_id=unit.vendor_id,
            action="reserved",
            actor_user_id=None,
            old_value={"status": old_status},
            new_value={
                "status": UnitStatus.reserved.value,
                "reservation_reference": ref,
                "expires_at": expires.isoformat()
            }
        )
        db.add(movement)
        db.commit()
        db.refresh(reservation)

        store = unit.vendor
        store_name = store.store_name or store.vendor_name if store else "K.T. Street Store"
        store_address = store.address_line or store.address if store else "K.T. Street, Mysuru"

        return jsonify({
            "success": True,
            "message": f"Device successfully held for 24 hours at {store_name}!",
            "reservation_reference": reservation.reservation_reference,
            "reservation": reservation.to_dict(),
            "store": {
                "name": store_name,
                "address": store_address,
                "phone": store.contact_phone if store else None,
                "whatsapp": store.whatsapp_number if store else None,
                "directions_url": store.google_maps_url if store else None
            },
            "expires_at": expires.isoformat(),
            "instructions": f"Visit {store_name} on K.T. Street within 24 hours. Show reservation code '{ref}' to test and purchase your device."
        }), 201
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()


@reservations_bp.route("/reservations/<string:reference>", methods=["GET"])
def get_reservation(reference: str):
    """
    Look up a reservation by reference code.
    """
    db = SessionLocal()
    try:
        release_expired_reservations(db)
        res = db.query(Reservation).filter_by(reservation_reference=reference).first()
        if not res:
            return jsonify({"success": False, "error": f"Reservation '{reference}' not found."}), 404

        return jsonify({
            "success": True,
            "reservation": res.to_dict()
        }), 200
    finally:
        db.close()


@reservations_bp.route("/reservations/<string:reference>/cancel", methods=["POST"])
def cancel_reservation(reference: str):
    """
    Customer cancels their reservation hold. Unit is returned to in_stock.
    """
    db = SessionLocal()
    try:
        res = db.query(Reservation).filter_by(reservation_reference=reference).with_for_update().first()
        if not res:
            return jsonify({"success": False, "error": f"Reservation '{reference}' not found."}), 404

        if res.status != ReservationStatus.active.value:
            return jsonify({
                "success": False,
                "error": f"Cannot cancel reservation in '{res.status}' status."
            }), 400

        res.status = ReservationStatus.cancelled.value
        if res.unit:
            unit = db.query(InventoryUnit).filter_by(unit_id=res.unit_id).with_for_update().first()
            if unit and unit.status == UnitStatus.reserved.value:
                unit.status = UnitStatus.in_stock.value

            movement = StockMovement(
                unit_id=res.unit_id,
                vendor_id=res.store_id,
                action="unreserved",
                actor_user_id=None,
                old_value={"status": UnitStatus.reserved.value},
                new_value={
                    "status": UnitStatus.in_stock.value,
                    "reason": f"Customer cancelled reservation {reference}"
                }
            )
            db.add(movement)

        db.commit()
        db.refresh(res)

        return jsonify({
            "success": True,
            "message": "Reservation hold cancelled successfully.",
            "reservation": res.to_dict()
        }), 200
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()
