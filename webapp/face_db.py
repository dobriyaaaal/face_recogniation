# face_db.py - Updated for webapp integration
import os
import sys
import json
import pickle
import numpy as np
from pathlib import Path
from insightface.app import FaceAnalysis
import cv2

_BASE_DIR = Path(__file__).parent.resolve()

def _augment_face(face_img):
    """
    Generate augmented variants of a face crop to handle low-quality/varied reference photos.
    Returns list of augmented images.
    """
    variants = [face_img]
    # Horizontal flip
    variants.append(cv2.flip(face_img, 1))
    # Slight brightness boost (simulate overexposure)
    bright = np.clip(face_img.astype(np.float32) * 1.2, 0, 255).astype(np.uint8)
    variants.append(bright)
    # Slight brightness reduction (simulate poor lighting / night cam)
    dark = np.clip(face_img.astype(np.float32) * 0.8, 0, 255).astype(np.uint8)
    variants.append(dark)
    # Slight blur (simulate distant/compressed camera)
    blurred = cv2.GaussianBlur(face_img, (3, 3), 0)
    variants.append(blurred)
    return variants


def build_face_embeddings():
    """Build face embeddings from people directory.
    Stores ALL individual embeddings per person (not a mean) so matching
    can pick the best score across all reference poses/conditions.
    """
    print("[INFO] Building face embeddings...")
    # antelopev2 uses ArcFace R100 — best accuracy for low-quality / crowd photos
    app = FaceAnalysis(name='antelopev2')
    app.prepare(ctx_id=-1, det_size=(1280, 1280))
    
    base_dir = str(_BASE_DIR / 'people')
    output_path = str(_BASE_DIR / 'embeddings' / 'face_db.pkl')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    face_db = {}

    if not os.path.exists(base_dir):
        print(f"[WARNING] People directory {base_dir} does not exist")
        with open(output_path, 'wb') as f:
            pickle.dump(face_db, f)
        return

    for person_name in os.listdir(base_dir):
        person_dir = os.path.join(base_dir, person_name)
        if not os.path.isdir(person_dir):
            continue

        embeddings = []
        for img_name in sorted(os.listdir(person_dir)):
            if not img_name.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            img_path = os.path.join(person_dir, img_name)
            img = cv2.imread(img_path)
            if img is None:
                print(f"[WARN] Could not read {img_path}")
                continue

            faces = app.get(img)
            if not faces:
                # Try upscaling if face not detected — handles very small/low-res refs
                img_up = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
                faces = app.get(img_up)
            if not faces:
                print(f"[WARN] No face in {img_path}, skipping")
                continue

            base_face = faces[0]
            # Store embedding from original
            embeddings.append(base_face.normed_embedding)

            # Generate augmented variants and store their embeddings too
            bbox = base_face.bbox.astype(int)
            h, w = img.shape[:2]
            x1, y1 = max(0, bbox[0]), max(0, bbox[1])
            x2, y2 = min(w, bbox[2]), min(h, bbox[3])
            if x2 > x1 and y2 > y1:
                face_crop = img[y1:y2, x1:x2]
                for aug in _augment_face(face_crop)[1:]:  # skip original, already have it
                    aug_faces = app.get(aug)
                    if aug_faces:
                        embeddings.append(aug_faces[0].normed_embedding)

        if embeddings:
            # Load per-person metadata if exists
            metadata_path = os.path.join(person_dir, 'info.json')
            info = {}
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r') as f:
                    info = json.load(f)

            face_db[person_name] = {
                "embeddings": embeddings,   # list of all embeddings
                "embedding": np.mean(embeddings, axis=0),  # legacy key — kept for backward compat
                "info": info,
                "photo_count": len(embeddings),
            }
            print(f"[INFO] {person_name}: {len(embeddings)} embeddings from {img_name}")
        else:
            print(f"[WARN] No usable faces for {person_name}, skipping")

    with open(output_path, 'wb') as f:
        pickle.dump(face_db, f)

    print(f"[DONE] Face DB saved. Total people: {len(face_db)}")

    # ── Build FAISS index for O(log n) embedding search ────────────────────
    # Flat inner-product index on L2-normalised vectors = cosine similarity.
    # Falls back silently if faiss is not installed.
    try:
        import faiss as _faiss
        all_emb   = []
        all_names = []
        for name, data in face_db.items():
            for emb in data['embeddings']:
                all_emb.append(emb.astype(np.float32))
                all_names.append(name)
        if all_emb:
            matrix = np.array(all_emb, dtype=np.float32)
            _faiss.normalize_L2(matrix)          # in-place L2 normalise
            index = _faiss.IndexFlatIP(matrix.shape[1])   # inner product = cosine after normalise
            index.add(matrix)
            _faiss.write_index(index, os.path.join(os.path.dirname(output_path), 'face_db.faiss'))
            with open(os.path.join(os.path.dirname(output_path), 'face_db_names.pkl'), 'wb') as f:
                pickle.dump(all_names, f)
            print(f"[INFO] FAISS index: {len(all_emb)} vectors, dim={matrix.shape[1]}")
    except ImportError:
        print("[INFO] faiss not installed — numpy fallback will be used for matching")
    except Exception as _fe:
        print(f"[WARN] FAISS index build failed: {_fe}")

if __name__ == "__main__":
    build_face_embeddings()
