from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User, Facility

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    """
    Self-signup is ONLY for staff (asha/doctor) - per the workflow, patients
    do not self-register (low literacy per problem statement); ASHA creates
    their record + login for them instead (see asha_routes.register_patient).
    """
    facilities = Facility.query.all()

    if request.method == "POST":
        name = request.form["name"].strip()
        phone = request.form["phone"].strip()
        password = request.form["password"]
        role = request.form["role"]  # asha or doctor only, enforced below
        facility_id = request.form.get("facility_id")

        if role not in ("asha", "doctor"):
            flash("Invalid role for self-signup.", "error")
            return redirect(url_for("auth.signup"))

        if User.query.filter_by(phone=phone).first():
            flash("An account with this phone number already exists.", "error")
            return redirect(url_for("auth.signup"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("auth.signup"))

        user = User(name=name, phone=phone, role=role, facility_id=facility_id or None)
        user.set_password(password)  # hashed with werkzeug (bcrypt-style salted hash)
        db.session.add(user)
        db.session.commit()

        flash("Account created. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/signup.html", facilities=facilities)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(f"{current_user.role}.dashboard"))

    if request.method == "POST":
        phone = request.form["phone"].strip()
        password = request.form["password"]

        user = User.query.filter_by(phone=phone).first()

        # Deliberately generic error message (security: don't reveal whether
        # the phone number exists or the password was wrong - avoids account enumeration)
        if user is None or not user.check_password(password):
            flash("Invalid phone number or password.", "error")
            return redirect(url_for("auth.login"))

        login_user(user)
        return redirect(url_for(f"{user.role}.dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "success")
    return redirect(url_for("auth.login"))
