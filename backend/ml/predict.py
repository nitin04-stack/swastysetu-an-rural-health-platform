import os
import json
from PIL import Image

ML_DIR = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_DIR = os.path.join(ML_DIR, "weights")

_torch = None
_nn = None
_models = None
_transform = None


def _load_ml_dependencies():
    global _torch, _nn, _models, _transform
    if _torch is not None:
        return

    import torch
    import torch.nn as nn
    from torchvision import models, transforms

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
    model.eval()
    return model

def predict_biomarker(image_path, biomarker_type):
    try:
        _load_ml_dependencies()
        classes = ["Normal", "Moderate Change", "Severe Change"]
        classes_path = os.path.join(WEIGHTS_DIR, f"{biomarker_type}_classes.json")
        if os.path.exists(classes_path):
            with open(classes_path) as f:
                classes = json.load(f)

        model = build_model(len(classes))
        weight_path = os.path.join(WEIGHTS_DIR, f"{biomarker_type}_model.pth")
        if os.path.exists(weight_path):
            model.load_state_dict(_torch.load(weight_path, map_location="cpu"))

        model.eval()
        img = Image.open(image_path).convert("RGB")
        tensor = _transform(img).unsqueeze(0)
        
        with _torch.no_grad():
            outputs = model(tensor)
            probs = _torch.softmax(outputs, dim=1)[0]
            conf, pred_idx = _torch.max(probs, dim=0)
            
            final_conf = round(conf.item(), 2)
    except Exception as error:
        print(f"Prediction Error: {error}")
        return {
            "label": "Image not identified",
            "note": "This image could not be identified. Please upload a clear, close-up image and try again.",
            "confidence": 0.0,
        }

    return {
        "label": classes[pred_idx.item()],
        "note": f"Observation found for {biomarker_type}.",
        "confidence": final_conf
    }