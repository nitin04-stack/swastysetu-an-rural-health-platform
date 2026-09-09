import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from datetime import date
from extensions import db
from models import Patient, User, Triage, BiomarkerImage, Consultation, Referral
from utils import role_required, calculate_risk, process_and_save_image
from ml.predict import predict_biomarker

asha_bp = Blueprint("asha", __name__, url_prefix="/asha")

@asha_bp.route("/dashboard")
@login_required
@role_required("asha")
def dashboard():
    patients = Patient.query.filter_by(registered_by_id=current_user.id).order_by(Patient.created_at.desc()).all()
    upcoming_followups = Consultation.query.join(Patient).filter(
        Patient.registered_by_id == current_user.id,
        Consultation.next_followup_date >= date.today()
    ).all()
    return render_template("asha/dashboard.html", patients=patients, followups=upcoming_followups)

@asha_bp.route("/high_risk_followup")
@login_required
@role_required("asha")
def high_risk_followup():
    # SIH Requirement: Tracking High-risk patients (Maternal/Child/Chronic)
    high_risk_patients = Patient.query.join(Triage).filter(
        Patient.registered_by_id == current_user.id,
        Triage.risk_level.in_(['Emergency', 'Moderate']),
        Patient.category.in_(['pregnant', 'infant', 'chronic'])
    ).distinct().all()
    return render_template("asha/high_risk.html", patients=high_risk_patients)

@asha_bp.route("/patient/register", methods=["GET", "POST"])
@login_required
@role_required("asha")
def register_patient():
    if request.method == "POST":
        name = request.form["name"].strip()
        age = request.form.get("age") or None
        gender = request.form.get("gender")
        category = request.form.get("category", "general")
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "")

        patient = Patient(
            name=name, age=age, gender=gender, category=category,
            phone=phone, address=address,
            registered_by_id=current_user.id,
            home_facility_id=current_user.facility_id,
        )
        db.session.add(patient)
        db.session.flush()

        temp_password = None
        if phone and not User.query.filter_by(phone=phone).first():
            temp_password = patient.abha_id[-6:]
            patient_user = User(name=name, phone=phone, role="patient")
            patient_user.set_password(temp_password)
            db.session.add(patient_user)
            db.session.flush()
            patient.user_id = patient_user.id

        db.session.commit()
        flash(f"Registered {name} as {category}. ABHA: {patient.abha_id}", "success")
        return redirect(url_for("asha.new_triage", patient_id=patient.id))
    return render_template("asha/register_patient.html")

@asha_bp.route("/patient/<int:patient_id>/delete", methods=["POST"])
@login_required
@role_required("asha")
def delete_patient(patient_id):
    patient = Patient.query.filter_by(
        id=patient_id,
        registered_by_id=current_user.id,
    ).first_or_404()

    for triage in list(patient.triages):
        for image in list(triage.biomarker_images):
            image_path = os.path.join(
                current_app.config["UPLOAD_FOLDER"], image.image_path or ""
            )
            if image.image_path and os.path.isfile(image_path):
                os.remove(image_path)
            db.session.delete(image)
        if triage.consultation:
            db.session.delete(triage.consultation)
        db.session.delete(triage)

    for referral in list(patient.referrals):
        db.session.delete(referral)

    patient_user = User.query.filter_by(id=patient.user_id, role="patient").first()
    db.session.delete(patient)
    if patient_user:
        db.session.delete(patient_user)
    db.session.commit()
    flash(f"Deleted patient record for {patient.name}.", "success")
    return redirect(url_for("asha.dashboard"))

@asha_bp.route("/triage/new/<int:patient_id>", methods=["GET", "POST"])
@login_required
@role_required("asha")
def new_triage(patient_id):
    patient = Patient.query.get_or_404(patient_id)

    if request.method == "POST":
        # Form se data nikalna aur string ko number mein badalna
        try:
            s = request.form.get("spo2")
            spo2 = int(s) if (s and s.strip()) else None
            
            bs = request.form.get("bp_systolic")
            bp_sys = int(bs) if (bs and bs.strip()) else None
            
            bd = request.form.get("bp_diastolic")
            bp_dia = int(bd) if (bd and bd.strip()) else None

            ps = request.form.get("pulse")
            pulse = int(ps) if (ps and ps.strip()) else None

            temperature_value = request.form.get("temperature_f")
            temperature_f = float(temperature_value) if temperature_value else None
            
            fd = request.form.get("fever_days")
            fever_days = int(fd) if (fd and fd.strip()) else 0
            
            # Checkbox handle karna (on = True, None = False)
            severe_flag = True if request.form.get("severe_symptom_flag") == "on" else False
            
            m_details = request.form.get("maternal_details", "").strip()
            complaint = request.form.get("chief_complaint", "").strip()
            final_complaint = (
                f"[Pregnancy: {m_details}] {complaint}" if m_details else complaint
            )
            
            # Risk Calculate karna
            risk = calculate_risk(spo2, bp_sys, bp_dia, fever_days, severe_flag)

            triage = Triage(
                patient_id=patient.id, recorded_by_id=current_user.id,
                bp_systolic=bp_sys, bp_diastolic=bp_dia, spo2=spo2,
                pulse=pulse, temperature_f=temperature_f,
                fever_days=fever_days, chief_complaint=final_complaint,
                severe_symptom_flag=severe_flag, risk_level=risk
            )
            db.session.add(triage)
            db.session.commit()

            flash(f"Check-up saved as {risk}", "success")
            return redirect(url_for("asha.biomarker_capture", triage_id=triage.id))
        
        except Exception as e:
            flash(f"Error in vitals: {str(e)}", "error")
            return redirect(url_for("asha.new_triage", patient_id=patient.id))
        

    return render_template("asha/triage.html", patient=patient)

@asha_bp.route("/biomarker/<int:triage_id>", methods=["GET", "POST"])
@login_required
@role_required("asha")
def biomarker_capture(triage_id):
    triage = Triage.query.get_or_404(triage_id)
    if request.method == "POST":
        try:
            b_type = request.form.get("biomarker_type", "").strip().lower()
            file = request.files.get("photo")
            if b_type not in {"eye", "nail", "tongue"}:
                raise ValueError("Please select a valid biomarker type.")
            if not file or not file.filename:
                raise ValueError("Please select an image before submitting.")

            filename = process_and_save_image(file, current_app.config["UPLOAD_FOLDER"])
            result = predict_biomarker(
                os.path.join(current_app.config["UPLOAD_FOLDER"], filename), b_type
            )
            img = BiomarkerImage(
                patient_id=triage.patient_id, triage_id=triage.id, biomarker_type=b_type,
                image_path=filename,
                prediction_label=result["label"],
                prediction_note=result["note"],
                confidence=result["confidence"],
            )
            db.session.add(img)
            db.session.commit()
            flash(f"{b_type.capitalize()} analysis: {result['label']}", "success")
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Biomarker upload failed")
            flash("The image could not be saved or analyzed. Please try another photo.", "error")
        return redirect(url_for("asha.biomarker_capture", triage_id=triage.id))
    return render_template("asha/biomarker_capture.html", triage=triage, patient=triage.patient)

@asha_bp.route("/biomarker/<int:triage_id>/done")
@login_required
def finish_case(triage_id):
    flash("Submitted to Doctor Queue", "success")
    return redirect(url_for("asha.dashboard"))