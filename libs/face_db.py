# face_db.py
import os
import json
import pickle
import numpy as np
from insightface.app import FaceAnalysis
import cv2

def build_face_embeddings():
    print("[INFO] Building face embeddings...")
    app = FaceAnalysis(name='buffalo_s')
    app.prepare(ctx_id=-1)
    
    base_dir = 'people'
    output_path = 'embeddings/face_db.pkl'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    face_db = {}

    for person_name in os.listdir(base_dir):
        person_dir = os.path.join(base_dir, person_name)
        if not os.path.isdir(person_dir):
            continue

        embeddings = []
        for img_name in os.listdir(person_dir):
            if img_name.lower().endswith(('.jpg', '.jpeg', '.png')):
                img_path = os.path.join(person_dir, img_name)
                img = cv2.imread(img_path)
                if img is None:
                    continue

                faces = app.get(img)
                if not faces:
                    continue

                embedding = faces[0].normed_embedding
                embeddings.append(embedding)

        if embeddings:
            mean_embedding = np.mean(embeddings, axis=0)

            # Load per-person metadata
            metadata_path = os.path.join(person_dir, 'info.json')
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r') as f:
                    info = json.load(f)
            else:
                info = {}

            face_db[person_name] = {"embedding": mean_embedding, "info": info}

    with open(output_path, 'wb') as f:
        pickle.dump(face_db, f)

    print("[DONE] Face embeddings built and saved.")

if __name__ == "__main__":
    build_face_embeddings()