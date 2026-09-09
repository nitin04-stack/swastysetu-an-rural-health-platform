"""
Run this SEPARATELY (not part of the live web app) to train each biomarker model.

STEP A - Download a dataset (per spec Section 4), e.g.:
  - Eye:    Kaggle "Eye-Conjunctiva" / anemia conjunctiva pallor dataset
  - Nail:   Kaggle nail disease/discoloration dataset
  - Tongue: BioHit tongue image dataset

STEP B - Arrange images into this exact folder structure (ImageFolder format).
Folder names become the class labels - use EXACTLY these 3 names:

  backend/ml/datasets/eye/Normal/img1.jpg, img2.jpg, ...
  backend/ml/datasets/eye/Moderate Change/img1.jpg, ...
  backend/ml/datasets/eye/Severe Change/img1.jpg, ...

  (repeat same structure under datasets/nail/... and datasets/tongue/...)

If the source dataset only has 2 classes (e.g. "anemic"/"non-anemic"), that's fine -
map: non-anemic -> Normal, anemic -> Severe Change, and put a handful of
in-between examples into "Moderate Change" yourself (or skip that class and
edit CLASSES in predict.py to 2 classes - just keep predict.py and this file in sync).

STEP C - Run:  python ml/train_model.py --biomarker eye
   (then repeat with --biomarker nail  and  --biomarker tongue)

This saves weights/eye_model.pth etc. which predict.py auto-loads.
"""

import os
import json
import argparse
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, random_split
from torchvision import datasets, transforms
from predict import build_model, WEIGHTS_DIR

ML_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(ML_DIR, "datasets")

train_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.RandomHorizontalFlip(),
    transforms.RandomRotation(10),
    transforms.ColorJitter(brightness=0.15, contrast=0.15),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


def train(biomarker, epochs=10, batch_size=16, lr=1e-4):
    data_dir = os.path.join(DATASETS_DIR, biomarker)
    if not os.path.isdir(data_dir):
        print(f"ERROR: put images in {data_dir}/<ClassName>/*.jpg first. See docstring at top of this file.")
        return

    full_dataset = datasets.ImageFolder(data_dir, transform=train_transform)
    print("Detected classes (must match predict.py CLASSES order):", full_dataset.classes)

    val_size = max(1, int(0.15 * len(full_dataset)))
    train_size = len(full_dataset) - val_size
    train_ds, val_ds = random_split(full_dataset, [train_size, val_size])

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(num_classes=len(full_dataset.classes)).to(device)
    model.train()

    # Freeze early feature-extraction layers, only fine-tune the last few layers
    # + the new classifier head. This is standard transfer learning practice -
    # trains fast, needs less data, avoids overfitting on a small dataset.
    for name, param in model.named_parameters():
        if "classifier" not in name and "features.12" not in name:
            param.requires_grad = False

    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=lr)
    criterion = nn.CrossEntropyLoss()

    best_val_acc = 0.0
    weight_path = os.path.join(WEIGHTS_DIR, f"{biomarker}_model.pth")
    classes_path = os.path.join(WEIGHTS_DIR, f"{biomarker}_classes.json")

    # Save the exact class list NOW, before training even finishes, so that
    # predict.py always knows how many classes this model has - this is what
    # prevents the "size mismatch" error when your dataset doesn't happen to
    # have exactly 3 folders/classes.
    with open(classes_path, "w") as f:
        json.dump(full_dataset.classes, f)
    print(f"Saved class list to {classes_path}: {full_dataset.classes}")

    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()

        # Validation
        model.eval()
        correct, total = 0, 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                _, preds = torch.max(outputs, 1)
                correct += (preds == labels).sum().item()
                total += labels.size(0)
        val_acc = correct / total if total else 0

        print(f"[{biomarker}] Epoch {epoch+1}/{epochs} - loss: {running_loss/len(train_loader):.4f} - val_acc: {val_acc:.3f}")

        if val_acc >= best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), weight_path)

    print(f"Best val accuracy: {best_val_acc:.3f}. Saved weights to {weight_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--biomarker", required=True, choices=["eye", "nail", "tongue"])
    parser.add_argument("--epochs", type=int, default=10)
    args = parser.parse_args()
    train(args.biomarker, epochs=args.epochs)
