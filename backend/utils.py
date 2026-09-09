import os
import uuid
from functools import wraps
from flask import abort
from flask_login import current_user
from PIL import Image
from config import Config

def calculate_risk(spo2, bp_sys, bp_dia, fever_days, severe_flag):
    """
    NHM Standards ke hisaab se Risk Scoring:
    """
    # 1. Sabse pehle checkbox check karo (Agar koi galti se tick kare toh sab Emergency ho jayega)
    if severe_flag is True:
        return "Emergency"

    # 2. Emergency Thresholds (Red Zone)
    # Agar SpO2 92 se niche hai (Saans lene mein takleef)
    if spo2 is not None and 50 < spo2 < 92:
        return "Emergency"
    
    # Agar Systolic BP 160 se upar hai (Extreme BP)
    if bp_sys is not None and bp_sys >= 160:
        return "Emergency"

    # 3. Moderate Thresholds (Yellow Zone)
    # Agar 3 din se zyada fever hai
    if fever_days is not None and fever_days >= 3:
        return "Moderate"
    
    # Agar BP high hai par extreme nahi (140 to 159)
    if bp_sys is not None and 140 <= bp_sys < 160:
        return "Moderate"

    # 4. Baaki sab Normal (Green Zone)
    return "Normal"

def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in allowed_roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator

def process_and_save_image(file_storage, upload_folder):
    if not file_storage or not file_storage.filename:
        raise ValueError("Please select an image before uploading.")

    os.makedirs(upload_folder, exist_ok=True)
    try:
        file_storage.stream.seek(0)
        img = Image.open(file_storage.stream)
        img.verify()
        file_storage.stream.seek(0)
        img = Image.open(file_storage.stream).convert("RGB")
    except Exception as error:
        raise ValueError("The uploaded file is not a valid image. Please choose a JPG or PNG photo.") from error

    filename = f"{uuid.uuid4().hex}.jpg"
    save_path = os.path.join(upload_folder, filename)
    img.save(save_path, "JPEG", quality=85)
    return filename