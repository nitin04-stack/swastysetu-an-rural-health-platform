import secrets
import string
from datetime import datetime, date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db

def gen_id(prefix, length=8):
    """Generates a random ID like ABHA-X7F92K1Q"""
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}-{''.join(secrets.choice(chars) for _ in range(length))}"

class Facility(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    ftype = db.Column(db.String(20), nullable=False)  # subcentre, phc, rh, dh
    village = db.Column(db.String(120))
    users = db.relationship("User", backref="facility", lazy=True)
    inventory_items = db.relationship("InventoryItem", backref="facility", lazy=True)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # asha, doctor, patient
    language_pref = db.Column(db.String(5), default="hi")
    facility_id = db.Column(db.Integer, db.ForeignKey("facility.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    patient_profile = db.relationship("Patient", backref="account", uselist=False, foreign_keys="Patient.user_id")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)
    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    abha_id = db.Column(db.String(30), unique=True, nullable=False, default=lambda: gen_id("ABHA", 10))
    name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    phone = db.Column(db.String(15))
    address = db.Column(db.String(255))
    
    category = db.Column(db.String(20), default="general") 
    
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    registered_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    home_facility_id = db.Column(db.Integer, db.ForeignKey("facility.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    triages = db.relationship("Triage", backref="patient", lazy=True, order_by="Triage.created_at.desc()")
    consultations = db.relationship("Consultation", backref="patient", lazy=True, order_by="Consultation.created_at.desc()")
    referrals = db.relationship("Referral", backref="patient", lazy=True, order_by="Referral.created_at.desc()")

class Triage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    bp_systolic = db.Column(db.Integer)
    bp_diastolic = db.Column(db.Integer)
    spo2 = db.Column(db.Integer)
    pulse = db.Column(db.Integer)
    temperature_f = db.Column(db.Float)
    fever_days = db.Column(db.Integer, default=0)
    chief_complaint = db.Column(db.String(500))
    severe_symptom_flag = db.Column(db.Boolean, default=False)
    risk_level = db.Column(db.String(20)) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    biomarker_images = db.relationship("BiomarkerImage", backref="triage", lazy=True)
    consultation = db.relationship("Consultation", backref="triage", uselist=False)

class BiomarkerImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    triage_id = db.Column(db.Integer, db.ForeignKey("triage.id"), nullable=False)
    biomarker_type = db.Column(db.String(20))
    image_path = db.Column(db.String(255))
    prediction_label = db.Column(db.String(50))
    prediction_note = db.Column(db.String(255))
    confidence = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Consultation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    triage_id = db.Column(db.Integer, db.ForeignKey("triage.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    lab_tests_recommended = db.Column(db.String(500))
    notes = db.Column(db.Text)
    prescription = db.Column(db.Text)
    decision = db.Column(db.String(20))
    
    # बदलाव: फॉलो-अप तारीख स्टोर करने के लिए
    next_followup_date = db.Column(db.Date, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Referral(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    from_facility_id = db.Column(db.Integer, db.ForeignKey("facility.id"))
    to_facility_id = db.Column(db.Integer, db.ForeignKey("facility.id"))
    initiated_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    status = db.Column(db.String(20), default="Referred")
    reason = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    from_facility = db.relationship("Facility", foreign_keys=[from_facility_id])
    to_facility = db.relationship("Facility", foreign_keys=[to_facility_id])

class InventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    facility_id = db.Column(db.Integer, db.ForeignKey("facility.id"), nullable=False)
    item_name = db.Column(db.String(120), nullable=False)
    item_type = db.Column(db.String(20))
    stock_count = db.Column(db.Integer, default=0)
    low_stock_threshold = db.Column(db.Integer, default=10)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)