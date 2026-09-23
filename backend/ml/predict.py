import os
import json
import gc
from PIL import Image

ML_DIR = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_DIR = os.path.join(ML_DIR, "weights")

_torch = None
_nn = None
_models = None
_transform = None
_model_cache = {}


def _load_ml_dependencies():
    global _torch, _nn, _models, _transform
    if _torch is not None:
        return

    import torch
    import torch.nn as nn
    from torchvision import models, transforms

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    _torch = torch
    _nn = nn
    _models = models
    _transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

def build_model(num_classes):
    _load_ml_dependencies()
    model = _models.mobilenet_v3_small(weights=None)
    in_features = model.classifier[3].in_features
    model.classifier[3] = _nn.Linear(in_features, num_classes)
    return model


def _get_model(biomarker_type, classes, weight_path):
    if biomarker_type in _model_cache:
        return _model_cache[biomarker_type]

    # Render's small instances cannot safely retain all three classifiers.
    # Keep only the model needed by the current request in memory.
    _model_cache.clear()
    gc.collect()

    model = build_model(len(classes))
    state_dict = _torch.load(weight_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state_dict)
    model.eval()
    _model_cache[biomarker_type] = model
    return model

def predict_biomarker(image_path, biomarker_type):
    classes = ["Normal", "Moderate_change", "Severe_change"]

    try:
        _load_ml_dependencies()
        # 1. Check if weight file exists
        weight_path = os.path.join(WEIGHTS_DIR, f"{biomarker_type}_model.pth")
        classes_path = os.path.join(WEIGHTS_DIR, f"{biomarker_type}_classes.json")

        if os.path.exists(classes_path):
            with open(classes_path) as f:
                classes = json.load(f)

        if not os.path.exists(weight_path):
            # Agar weight file nahi hai, toh crash mat karo, Demo data bhejo
            return {
                "label": "Demo Analysis",
                "note": "AI Model weights not found on server. Showing demo result.",
                "confidence": 0.50
            }

        model = _get_model(biomarker_type, classes, weight_path)

        # 3. Process Image
        img = Image.open(image_path).convert("RGB")
        tensor = _transform(img).unsqueeze(0)

        with _torch.inference_mode():
            outputs = model(tensor)
            probs = _torch.softmax(outputs, dim=1)[0]
            conf, pred_idx = _torch.max(probs, dim=0)

        return {
            "label": classes[pred_idx.item()],
            "note": f"AI Scan completed for {biomarker_type}.",
            "confidence": round(float(conf.item()), 2)
        }

    except Exception as e:
        # Sabse important: Kuch bhi galat ho, Error 500 mat do!
        print(f"ML Error: {e}")
        return {
            "label": "Manual Review Required",
            "note": "Analysis skipped due to system load. Doctor should check photo.",
            "confidence": 0.0
        }