"""
CV Inference module.
Loads a lightweight MobileNetV3-Small model, fine-tuned per biomarker type
(eye / nail / tongue), and returns a NON-DIAGNOSTIC descriptive finding.

Governance rule (spec 3-D): we NEVER output a disease name like "Anemia".
We only output an observation + a recommendation to get it clinically checked.

IMPORTANT: the number/names of classes are NOT hardcoded here. Whatever
folders you used under ml/datasets/<biomarker>/ during training (2, 3, or
more classes) is exactly what gets loaded at prediction time too, because
train_model.py saves a small "<biomarker>_classes.json" file alongside the
weights recording the exact class list it trained on.
"""

import os
import json
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image

ML_DIR = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_DIR = os.path.join(ML_DIR, "weights")
os.makedirs(WEIGHTS_DIR, exist_ok=True)

# Used ONLY when no trained weights exist yet for a biomarker (untrained demo mode).
DEFAULT_CLASSES = ["Normal", "Moderate Change", "Severe Change"]

# Non-diagnostic phrasing shown to the doctor. Keyed by biomarker type, then by
# class name. If a class name isn't found here (e.g. your dataset folders were
# named differently, like "anemic"/"non-anemic"), we fall back to a safe
# generic sentence built from the class name itself - see _finding_text().
FINDING_TEXT = {
    "eye": {
        "Normal": "Conjunctiva appears normally vascularized (pink).",
        "Moderate Change": "Mild conjunctival pallor observed - consider Hemoglobin check.",
        "Severe Change": "Marked conjunctival pallor observed - Recommended for urgent clinical Hemoglobin check.",
    },
    "nail": {
        "Normal": "Nail bed color and perfusion appear normal.",
        "Moderate Change": "Mild nail bed pallor/discoloration observed - clinical correlation advised.",
        "Severe Change": "Significant nail bed discoloration/cyanosis pattern observed - Recommended for urgent clinical review.",
    },
    "tongue": {
        "Normal": "Tongue surface and coloration appear normal.",
        "Moderate Change": "Mild tongue coating/color variance observed - clinical correlation advised.",
        "Severe Change": "Notable tongue depapillation/coating observed - Recommended for clinical nutritional/hemoglobin check.",
    },
}

_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

_model_cache = {}


def build_model(num_classes):
    """MobileNetV3-Small architecture with a fresh classification head.
    This is the SAME architecture used in train_model.py so weight files match."""
    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
    in_features = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(in_features, num_classes)
    model.eval()
    return model


def _load_classes(biomarker_type):
    """Reads <biomarker>_classes.json saved by train_model.py.
    Falls back to DEFAULT_CLASSES if the model hasn't been trained yet."""
    classes_path = os.path.join(WEIGHTS_DIR, f"{biomarker_type}_classes.json")
    if os.path.exists(classes_path):
        with open(classes_path) as f:
            return json.load(f)
    return DEFAULT_CLASSES


def _finding_text(biomarker_type, label):
    known = FINDING_TEXT.get(biomarker_type, {})
    if label in known:
        return known[label]
    # Safe generic fallback for custom class names from your own dataset
    return f"Finding: '{label}' - recommended for clinical correlation/review."


def _get_model(biomarker_type):
    """Loads (and caches) the fine-tuned weight file for a given biomarker type,
    using however many classes it was ACTUALLY trained on."""
    if biomarker_type in _model_cache:
        return _model_cache[biomarker_type]

    classes = _load_classes(biomarker_type)
    model = build_model(num_classes=len(classes))
    weight_path = os.path.join(WEIGHTS_DIR, f"{biomarker_type}_model.pth")

    trained = False
    if os.path.exists(weight_path):
        state_dict = torch.load(weight_path, map_location="cpu")
        try:
            model.load_state_dict(state_dict)
            trained = True
        except RuntimeError as e:
            # Weight file doesn't match the class list we just loaded - most likely
            # the classes.json is missing/stale for an older trained model.
            # We don't crash - we just run in "untrained" mode and tell the caller why.
            print(f"[predict.py] WARNING: could not load weights for '{biomarker_type}': {e}")
            print(f"[predict.py] Delete {weight_path} and retrain with the current train_model.py, "
                  f"or check that {os.path.basename(weight_path).replace('_model.pth', '_classes.json')} matches your dataset folders.")
            trained = False

    model.eval()
    _model_cache[biomarker_type] = (model, trained, classes)
    return model, trained, classes


def predict_biomarker(image_path, biomarker_type):
    """
    Returns dict: {label, note, confidence, model_trained}
    biomarker_type must be one of: 'eye', 'nail', 'tongue'
    """
    if biomarker_type not in ("eye", "nail", "tongue"):
        raise ValueError("biomarker_type must be eye, nail or tongue")

    model, trained, classes = _get_model(biomarker_type)

    img = Image.open(image_path).convert("RGB")
    tensor = _transform(img).unsqueeze(0)

    with torch.no_grad():
        outputs = model(tensor)
        probs = torch.softmax(outputs, dim=1)[0]
        conf, pred_idx = torch.max(probs, dim=0)

    label = classes[pred_idx.item()]
    return {
        "label": label,
        "note": _finding_text(biomarker_type, label),
        "confidence": round(conf.item(), 3),
        "model_trained": trained,  # False = weights not trained yet, flag this in UI
    }
