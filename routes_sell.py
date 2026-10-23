"""
Sell Flow & Trade-in Valuation API
CoherentMobiles - Mysuru / K.T. Street Hub
"""

import secrets
from datetime import datetime, date, timezone
from flask import Blueprint, jsonify, request
from sqlalchemy import func
from database import SessionLocal
import models
from models import (
    SellRequest, SellRequestTimeline, SellRequestStatus, FulfilmentType,
    ServiceablePincode, PriceMatrix, Vendor, VendorApprovalStatus,
    InventoryUnit, UnitStatus, StockMovement, utc_now
)
from routes_vendor import validate_imei_luhn

sell_bp = Blueprint("sell", __name__, url_prefix="/api")


def calculate_valuation(brand: str, model: str, storage_gb: int, condition: dict, db):
    """
    Computes an estimated price range based on database PriceMatrix and condition answers.
    """
    pm = db.query(PriceMatrix).filter(
        func.lower(PriceMatrix.brand) == brand.lower(),
        func.lower(PriceMatrix.model) == model.lower(),
        PriceMatrix.storage_gb == storage_gb,
        PriceMatrix.is_active.is_(True)
    ).first()

    if not pm:
        # Fallback to model match regardless of storage, or default base price
        pm = db.query(PriceMatrix).filter(
            func.lower(PriceMatrix.brand) == brand.lower(),
            func.lower(PriceMatrix.model) == model.lower(),
            PriceMatrix.is_active.is_(True)
        ).first()

    base_price = float(pm.base_price) if pm else 25000.0
    screen_scratch_pct = float(pm.screen_scratch_pct if pm else 10.0) / 100.0
    screen_cracked_pct = float(pm.screen_cracked_pct if pm else 35.0) / 100.0
    body_dent_pct = float(pm.body_dent_pct if pm else 12.0) / 100.0
    battery_low_pct = float(pm.battery_low_pct if pm else 15.0) / 100.0
    camera_fault_pct = float(pm.camera_fault_pct if pm else 20.0) / 100.0
    speaker_fault_pct = float(pm.speaker_fault_pct if pm else 10.0) / 100.0
    accessories_deduction = float(pm.accessories_deduction if pm else 1000.0)

    deductions = {}
    total_pct_deduction = 0.0

    # Screen
    screen_ans = condition.get("screen", "flawless").lower()
    if screen_ans in ("scratched", "minor_scratches"):
        total_pct_deduction += screen_scratch_pct
        deductions["screen"] = f"-{int(screen_scratch_pct * 100)}% for screen scratches"
    elif screen_ans in ("cracked", "broken"):
        total_pct_deduction += screen_cracked_pct
        deductions["screen"] = f"-{int(screen_cracked_pct * 100)}% for cracked screen"

    # Body
    body_ans = condition.get("body", "flawless").lower()
    if body_ans in ("dented", "heavy_wear"):
        total_pct_deduction += body_dent_pct
        deductions["body"] = f"-{int(body_dent_pct * 100)}% for body dents/wear"
    elif body_ans in ("good", "minor_wear"):
        total_pct_deduction += 0.05
        deductions["body"] = "-5% for minor cosmetic signs"

    # Battery
    battery_ans = condition.get("battery", "above_85").lower()
    if battery_ans in ("below_85", "service", "poor"):
        total_pct_deduction += battery_low_pct
        deductions["battery"] = f"-{int(battery_low_pct * 100)}% for depleted battery"

    # Camera
    camera_ans = condition.get("camera", "working").lower()
    if camera_ans in ("faulty", "not_working", "cracked"):
        total_pct_deduction += camera_fault_pct
        deductions["camera"] = f"-{int(camera_fault_pct * 100)}% for camera defect"

    # Speaker
    speaker_ans = condition.get("speaker", "working").lower()
    if speaker_ans in ("faulty", "not_working"):
        total_pct_deduction += speaker_fault_pct
        deductions["speaker"] = f"-{int(speaker_fault_pct * 100)}% for speaker defect"

    # Max deduction capped at 75%
    total_pct_deduction = min(0.75, total_pct_deduction)

    price_after_pct = base_price * (1.0 - total_pct_deduction)

    # Accessories
    acc_list = condition.get("accessories") or []
    if "box" not in acc_list or "charger" not in acc_list:
        price_after_pct = max(3000.0, price_after_pct - accessories_deduction)
        deductions["accessories"] = f"-Rs. {int(accessories_deduction)} for missing original box/charger"

    max_estimate = round(price_after_pct, -1)
    min_estimate = round(max_estimate * 0.90, -1)

    return {
        "base_price": base_price,
        "estimated_min_price": min_estimate,
        "estimated_max_price": max_estimate,
        "deductions": deductions
    }


@sell_bp.route("/estimate", methods=["POST"])
def get_price_estimate():
    """
    Returns instant price range estimation before booking sell appointment.
    """
    data = request.get_json(silent=True) or {}
    brand = (data.get("brand") or "").strip()
    model = (data.get("model") or "").strip()
    storage_gb = int(data.get("storage_gb") or data.get("storage") or 128)
    condition = data.get("condition_answers") or data.get("condition") or {}

    if not brand or not model:
        return jsonify({"success": False, "error": "Brand and model are required for valuation."}), 400

    db = SessionLocal()
    try:
        val = calculate_valuation(brand, model, storage_gb, condition, db)
        return jsonify({
            "success": True,
            "brand": brand,
            "model": model,
            "storage_gb": storage_gb,
            "currency": "INR",
            "estimated_min_price": val["estimated_min_price"],
            "estimated_max_price": val["estimated_max_price"],
            "base_price": val["base_price"],
            "deductions": val["deductions"],
            "disclaimer": "This is an instant preliminary estimate. The final offer will be confirmed by the K.T. Street partner store after physical inspection."
        }), 200
    finally:
        db.close()


@sell_bp.route("/sell/requests", methods=["POST"])
def create_sell_request():
    """
    Submit customer phone sell request with Luhn IMEI validation and Mysuru pincode verification.
    """
    data = request.get_json(silent=True) or {}

    brand = (data.get("brand") or "").strip()
    model = (data.get("model") or "").strip()
    storage_gb = int(data.get("storage_gb") or 128)
    imei = (data.get("imei") or "").strip().replace(" ", "").replace("-", "")
    customer_name = (data.get("customer_name") or data.get("name") or "").strip()
    customer_phone = (data.get("customer_phone") or data.get("phone") or "").strip()
    customer_email = (data.get("customer_email") or data.get("email") or "").strip().lower()
    customer_address = (data.get("customer_address") or data.get("address") or "").strip()
    pincode = (data.get("pincode") or "").strip()
    fulfilment_type = (data.get("fulfilment_type") or FulfilmentType.store_visit.value).strip()
    store_id = data.get("store_id")
    slot_date_str = data.get("slot_date")
    slot_time = data.get("slot_time", "11:00 AM")
    condition = data.get("condition_answers") or {}

    # 1. Basic validation
    if not brand or not model or not customer_name or not customer_phone or not imei:
        return jsonify({
            "success": False,
            "error": "Brand, model, IMEI, customer name, and customer phone are required."
        }), 400

    # 2. Luhn IMEI validation
    if not validate_imei_luhn(imei):
        return jsonify({
            "success": False,
            "error": f"Invalid IMEI '{imei}'. IMEI must be a valid 15-digit number passing the Luhn checksum."
        }), 400

    db = SessionLocal()
    try:
        # 3. Fulfillment validation
        target_store = None
        if fulfilment_type == FulfilmentType.home_pickup.value:
            if not pincode:
                return jsonify({"success": False, "error": "Pincode is required for home pickup."}), 400

            # Verify pincode is serviceable in Mysuru
            serviceable = db.query(ServiceablePincode).filter_by(pincode=pincode, is_active=True).first()
            if not serviceable:
                return jsonify({
                    "success": False,
                    "error": f"Pincode {pincode} is outside our Mysuru city limits. Home pickup is only available in Mysuru (PIN 570001 - 570024). Please select 'Store Visit' to visit a partner store on K.T. Street!"
                }), 400
        else:
            fulfilment_type = FulfilmentType.store_visit.value
            if not store_id:
                # Default to first approved store if not picked
                first_store = db.query(Vendor).filter_by(approval_status=VendorApprovalStatus.approved.value).first()
                if first_store:
                    store_id = first_store.vendor_id
            target_store = db.query(Vendor).filter_by(
                vendor_id=store_id,
                approval_status=VendorApprovalStatus.approved.value
            ).first()
            if not target_store:
                return jsonify({"success": False, "error": f"Selected store ID {store_id} not found or not approved."}), 400

        # Parse date
        parsed_date = date.today()
        if slot_date_str:
            try:
                parsed_date = datetime.strptime(slot_date_str, "%Y-%m-%d").date()
            except ValueError:
                parsed_date = date.today()

        # Calculate valuation range
        val = calculate_valuation(brand, model, storage_gb, condition, db)

        # Generate unique reference
        ref = f"SELL-MYS-{secrets.randbelow(89999) + 10000}"

        sell_req = SellRequest(
            request_reference=ref,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=customer_email or None,
            customer_address=customer_address or None,
            pincode=pincode or None,
            store_id=store_id if fulfilment_type == FulfilmentType.store_visit.value else None,
            brand=brand,
            model=model,
            storage_gb=storage_gb,
            imei=imei,
            condition_answers=condition,
            estimated_min_price=val["estimated_min_price"],
            estimated_max_price=val["estimated_max_price"],
            fulfilment_type=fulfilment_type,
            slot_date=parsed_date,
            slot_time=slot_time,
            status=SellRequestStatus.submitted.value
        )
        db.add(sell_req)
        db.flush()

        # Initial timeline event
        action_note = (
            f"Store visit booked at {target_store.store_name} on K.T. Street for {parsed_date} at {slot_time}."
            if fulfilment_type == FulfilmentType.store_visit.value
            else f"Home pickup requested for address in Mysuru ({pincode}) on {parsed_date} at {slot_time}."
        )
        timeline_entry = SellRequestTimeline(
            request_id=sell_req.request_id,
            from_status=None,
            to_status=SellRequestStatus.submitted.value,
            actor_role="customer",
            notes=action_note
        )
        db.add(timeline_entry)
        db.commit()
        db.refresh(sell_req)

        return jsonify({
            "success": True,
            "message": "Sell request submitted successfully! Bring your device to the store or prepare for home pickup.",
            "request_reference": sell_req.request_reference,
            "sell_request": sell_req.to_dict()
        }), 201
    finally:
        db.close()


@sell_bp.route("/sell/requests/<string:reference>", methods=["GET"])
def get_sell_request(reference: str):
    """
    Customer tracking endpoint: returns sell request status timeline and store details.
    """
    db = SessionLocal()
    try:
        sr = db.query(SellRequest).filter_by(request_reference=reference).first()
        if not sr:
            return jsonify({"success": False, "error": f"Sell request '{reference}' not found."}), 404

        return jsonify({
            "success": True,
            "sell_request": sr.to_dict()
        }), 200
    finally:
        db.close()


@sell_bp.route("/sell/requests/<string:reference>/accept", methods=["POST"])
def accept_final_offer(reference: str):
    """
    Customer accepts final revised offer from the store inspection.
    """
    db = SessionLocal()
    try:
        sr = db.query(SellRequest).filter_by(request_reference=reference).first()
        if not sr:
            return jsonify({"success": False, "error": f"Sell request '{reference}' not found."}), 404

        if sr.status not in (SellRequestStatus.inspected.value, SellRequestStatus.offer_revised.value):
            return jsonify({
                "success": False,
                "error": f"Cannot accept offer in current status '{sr.status}'."
            }), 400

        old_status = sr.status
        sr.status = SellRequestStatus.accepted.value

        tl = SellRequestTimeline(
            request_id=sr.request_id,
            from_status=old_status,
            to_status=SellRequestStatus.accepted.value,
            actor_role="customer",
            notes=f"Customer accepted offer of Rs. {float(sr.final_offer_price or sr.estimated_max_price):,.2f}."
        )
        db.add(tl)
        db.commit()
        db.refresh(sr)

        return jsonify({
            "success": True,
            "message": "Offer accepted! The store will now disburse your instant cash or UPI payout.",
            "sell_request": sr.to_dict()
        }), 200
    finally:
        db.close()


@sell_bp.route("/sell/requests/<string:reference>/reject", methods=["POST"])
def reject_final_offer(reference: str):
    """
    Customer rejects final offer. Device will be returned with zero fee.
    """
    db = SessionLocal()
    try:
        sr = db.query(SellRequest).filter_by(request_reference=reference).first()
        if not sr:
            return jsonify({"success": False, "error": f"Sell request '{reference}' not found."}), 404

        old_status = sr.status
        sr.status = SellRequestStatus.rejected.value

        tl = SellRequestTimeline(
            request_id=sr.request_id,
            from_status=old_status,
            to_status=SellRequestStatus.rejected.value,
            actor_role="customer",
            notes="Customer declined revised offer. Device returned with no charges."
        )
        db.add(tl)
        db.commit()
        db.refresh(sr)

        return jsonify({
            "success": True,
            "message": "Offer declined. You may collect your device from the store.",
            "sell_request": sr.to_dict()
        }), 200
    finally:
        db.close()
