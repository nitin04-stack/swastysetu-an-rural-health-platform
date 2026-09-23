from datetime import date

from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user

from models import Patient
from utils import role_required

patient_bp = Blueprint("patient", __name__, url_prefix="/patient")


@patient_bp.route("/dashboard")
@login_required
@role_required("patient")
def dashboard():
    # DATA ISOLATION (the important one): a patient can ONLY ever see the
    # Patient record linked to THEIR OWN user_id. There is no patient_id in
    # this URL for a reason - it is impossible for one patient to view
    # another patient's data by editing the address bar.
    patient = Patient.query.filter_by(user_id=current_user.id).first()

    if patient is None:
        abort(404)  # account exists but not yet linked to a clinical record

    upcoming_followups = [
        consultation
        for consultation in patient.consultations
        if consultation.next_followup_date
        and consultation.next_followup_date >= date.today()
    ]

    return render_template(
        "patient/dashboard.html",
        patient=patient,
        upcoming_followups=upcoming_followups,
    )
