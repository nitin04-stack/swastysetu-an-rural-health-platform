import csv
import io
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import func, or_
from extensions import db
from models import Patient, User, Triage, Consultation, Referral, Facility, InventoryItem
from utils import role_required

doctor_bp = Blueprint("doctor", __name__, url_prefix="/doctor")

RISK_ORDER = {"Emergency": 0, "Moderate": 1, "Normal": 2}

@doctor_bp.route("/dashboard")
@login_required
@role_required("doctor")
def dashboard():
    # 1. Get Pending Triage Queue
    pending_triages = Triage.query.filter(
        ~Triage.id.in_(db.session.query(Consultation.triage_id))
    ).all()
    pending_triages.sort(key=lambda t: (RISK_ORDER.get(t.risk_level, 3), t.created_at))

    # 2. SIH Feature: Quick Search for Longitudinal Records
    search_query = request.args.get('search', '')
    searched_patients = []
    if search_query:
        searched_patients = Patient.query.filter(
            or_(Patient.name.contains(search_query), Patient.abha_id.contains(search_query))
        ).limit(10).all()

    return render_template("doctor/dashboard.html", 
                           triages=pending_triages, 
                           searched_patients=searched_patients)

@doctor_bp.route("/analytics")
@login_required
@role_required("doctor")
def analytics():
    risk_counts = db.session.query(Triage.risk_level, func.count(Triage.id)).group_by(Triage.risk_level).all()
    cat_counts = db.session.query(Patient.category, func.count(Patient.id)).group_by(Patient.category).all()
    low_stock = InventoryItem.query.filter(InventoryItem.stock_count <= InventoryItem.low_stock_threshold).all()
    total_referrals = Referral.query.count()
    completed_referrals = Referral.query.filter_by(status="Completed").count()
    referral_success_rate = (
        round((completed_referrals / total_referrals) * 100, 1)
        if total_referrals else 0
    )
    
    return render_template("doctor/analytics.html", 
                           risk_data=dict(risk_counts), 
                           cat_data=dict(cat_counts),
                           low_stock=low_stock,
                           total_consults=Consultation.query.count(),
                           referral_success_rate=referral_success_rate,
                           completed_referrals=completed_referrals,
                           total_referrals=total_referrals)

@doctor_bp.route("/consult/<int:triage_id>", methods=["GET", "POST"])
@login_required
@role_required("doctor")
def consult(triage_id):
    triage = Triage.query.get_or_404(triage_id)
    patient = triage.patient
    asha = User.query.get(patient.registered_by_id)
    facilities = Facility.query.all()
    stock = InventoryItem.query.filter_by(facility_id=current_user.facility_id).all()

    if request.method == "POST":
        followup_str = request.form.get("next_followup_date")
        followup_date = datetime.strptime(followup_str, '%Y-%m-%d').date() if followup_str else None

        selected_tests = request.form.getlist("lab_tests")
        lab_tests_str = ", ".join(selected_tests)

        cons = Consultation(
            patient_id=triage.patient_id, triage_id=triage.id, doctor_id=current_user.id,
            notes=request.form["notes"], prescription=request.form["prescription"],
            decision=request.form["decision"],
            next_followup_date=followup_date,
            lab_tests_recommended=lab_tests_str,
        )
        db.session.add(cons)

        if request.form["decision"] == "referred":
            ref = Referral(
                patient_id=triage.patient_id, from_facility_id=current_user.facility_id,
                to_facility_id=request.form.get("to_facility_id"),
                initiated_by_id=current_user.id, reason=request.form.get("referral_reason"),
                status="Referred"
            )
            db.session.add(ref)

        db.session.commit()
        flash("Consultation completed.", "success")
        return redirect(url_for("doctor.dashboard"))

    return render_template(
        "doctor/consult.html",
        triage=triage,
        patient=patient,
        asha=asha,
        facilities=facilities,
        stock=stock,
    )

@doctor_bp.route("/patient/<int:patient_id>")
@login_required
@role_required("doctor")
def patient_dossier(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    return render_template("doctor/patient_dossier.html", patient=patient)

@doctor_bp.route("/patient/<int:patient_id>/download")
@login_required
@role_required("doctor")
def download_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    output = io.StringIO(newline="")
    writer = csv.writer(output)

    writer.writerow(["Patient Details"])
    writer.writerow(["Name", patient.name])
    writer.writerow(["ABHA ID", patient.abha_id])
    writer.writerow(["Age", patient.age or ""])
    writer.writerow(["Gender", patient.gender or ""])
    writer.writerow(["Category", patient.category or ""])
    writer.writerow(["Phone", patient.phone or ""])
    writer.writerow(["Address", patient.address or ""])
    writer.writerow(["Registered At", patient.created_at.strftime("%Y-%m-%d %H:%M")])

    writer.writerow([])
    writer.writerow(["Triage History"])
    writer.writerow(["Date", "Risk", "Blood Pressure", "SpO2", "Fever Days", "Chief Complaint"])
    for triage in patient.triages:
        writer.writerow([
            triage.created_at.strftime("%Y-%m-%d %H:%M"),
            triage.risk_level or "",
            f"{triage.bp_systolic or ''}/{triage.bp_diastolic or ''}",
            triage.spo2 or "",
            triage.fever_days or 0,
            triage.chief_complaint or "",
        ])

    writer.writerow([])
    writer.writerow(["Consultations"])
    writer.writerow(["Date", "Decision", "Prescription", "Lab Tests", "Notes", "Follow-up"])
    for consultation in patient.consultations:
        writer.writerow([
            consultation.created_at.strftime("%Y-%m-%d %H:%M"),
            consultation.decision or "",
            consultation.prescription or "",
            consultation.lab_tests_recommended or "",
            consultation.notes or "",
            consultation.next_followup_date or "",
        ])

    writer.writerow([])
    writer.writerow(["Referrals"])
    writer.writerow(["Date", "Status", "Reason"])
    for referral in patient.referrals:
        writer.writerow([
            referral.created_at.strftime("%Y-%m-%d %H:%M"),
            referral.status or "",
            referral.reason or "",
        ])

    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="patient_{patient.id}_details.csv"'
    )
    return response

@doctor_bp.route("/referrals")
@login_required
@role_required("doctor")
def referrals():
    return render_template("doctor/referrals.html", referrals=Referral.query.order_by(Referral.created_at.desc()).all())

@doctor_bp.route("/referrals/<int:referral_id>/update", methods=["POST"])
@login_required
def update_referral(referral_id):
    ref = Referral.query.get_or_404(referral_id)
    ref.status = request.form["status"]
    db.session.commit()
    return redirect(url_for("doctor.referrals"))

@doctor_bp.route("/inventory")
@login_required
def inventory():
    return render_template("doctor/inventory.html", items=InventoryItem.query.all(), facilities=Facility.query.all())

@doctor_bp.route("/inventory/update/<int:item_id>", methods=["POST"])
@login_required
@role_required("doctor")
def update_inventory(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    item.stock_count = max(0, int(request.form.get("stock_count", 0)))
    db.session.commit()
    flash("Inventory updated successfully.", "success")
    return redirect(url_for("doctor.inventory"))

@doctor_bp.route("/inventory/add", methods=["POST"])
@login_required
@role_required("doctor")
def add_inventory():
    item = InventoryItem(
        facility_id=int(request.form["facility_id"]),
        item_name=request.form["item_name"].strip(),
        item_type=request.form.get("item_type", "medicine"),
        stock_count=max(0, int(request.form.get("stock_count", 0))),
        low_stock_threshold=max(0, int(request.form.get("low_stock_threshold", 10))),
    )
    db.session.add(item)
    db.session.commit()
    flash("Inventory item added successfully.", "success")
    return redirect(url_for("doctor.inventory"))