import os
from flask import Flask, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import inspect, text

from config import Config
from extensions import db, login_manager
from models import User, Facility, InventoryItem


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from routes.auth_routes import auth_bp
    from routes.asha_routes import asha_bp
    from routes.doctor_routes import doctor_bp
    from routes.patient_routes import patient_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(asha_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(patient_bp)

    @app.route("/")
    def home():
        if current_user.is_authenticated:
            return redirect(url_for(f"{current_user.role}.dashboard"))
        return redirect(url_for("auth.login"))

    @app.errorhandler(403)
    def forbidden(e):
        return "<h2>403 - You don't have permission to view this page.</h2><a href='/'>Go home</a>", 403

    @app.errorhandler(404)
    def not_found(e):
        return "<h2>404 - Not found.</h2><a href='/'>Go home</a>", 404

    with app.app_context():
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        db.create_all()
        migrate_existing_schema()
        seed_data()

    return app


def migrate_existing_schema():
    """Add columns introduced after the original SQLite database was created."""
    inspector = inspect(db.engine)
    migrations = {
        "consultation": {
            "lab_tests_recommended": "VARCHAR(500)",
        },
        "biomarker_image": {
            "confidence": "FLOAT",
        },
    }

    with db.engine.begin() as connection:
        for table_name, columns in migrations.items():
            existing_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name, column_type in columns.items():
                if column_name not in existing_columns:
                    connection.execute(
                        text(
                            f'ALTER TABLE "{table_name}" '
                            f'ADD COLUMN "{column_name}" {column_type}'
                        )
                    )


def seed_data():
    """Creates a couple of demo facilities + sample inventory + one admin-ish
    doctor account, ONLY if the database is empty. Safe to run every startup."""
    if Facility.query.first():
        return 

    subcentre = Facility(name="Sub-Centre Wadala", ftype="subcentre", village="Wadala")
    phc = Facility(name="PHC Karjat", ftype="phc", village="Karjat")
    rh = Facility(name="Rural Hospital Raigad", ftype="rh", village="Raigad")
    db.session.add_all([subcentre, phc, rh])
    db.session.flush()

    demo_items = [
        InventoryItem(facility_id=phc.id, item_name="Paracetamol 500mg", item_type="medicine", stock_count=120, low_stock_threshold=30),
        InventoryItem(facility_id=phc.id, item_name="ORS Packets", item_type="medicine", stock_count=8, low_stock_threshold=20),
        InventoryItem(facility_id=phc.id, item_name="Hemoglobin Test Kit", item_type="diagnostic", stock_count=15, low_stock_threshold=10),
        InventoryItem(facility_id=rh.id, item_name="IV Fluids", item_type="medicine", stock_count=40, low_stock_threshold=15),
    ]
    db.session.add_all(demo_items)
    db.session.commit()
    print("Seeded demo facilities + inventory.")


app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    use_dev_https = os.environ.get("DEV_HTTPS", "0") == "1"
    app.run(
        debug=debug,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        ssl_context="adhoc" if use_dev_https else None,
    )