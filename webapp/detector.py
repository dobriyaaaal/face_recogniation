# detector.py - Simplified detector for webapp
import os
import sys
import pickle
import numpy as np
import cv2
from insightface.app import FaceAnalysis

def initialize_detector():
    """Initialize the face detector"""
    try:
        print(">> Initializing face detector...")
        
        # antelopev2 uses ArcFace R100 backbone — highest accuracy for surveillance
        # 640x640 is safe on CPU; GPU can handle 1280x1280
        app = FaceAnalysis(name='antelopev2')
        app.prepare(ctx_id=-1, det_size=(640, 640))
        
        # Load face database
        face_db_path = 'embeddings/face_db.pkl'
        known_faces = {}
        
        if os.path.exists(face_db_path):
            with open(face_db_path, 'rb') as f:
                face_db = pickle.load(f)
                for name, data in face_db.items():
                    # Support both multi-embedding (list) and legacy single-embedding
                    if 'embeddings' in data:
                        known_faces[name] = data['embeddings']
                    elif 'embedding' in data:
                        known_faces[name] = [data['embedding']]
            print(f">> Loaded {len(known_faces)} known faces")
        else:
            print(">> No face database found, detection will only detect unknown faces")
        
        return {
            'app': app,
            'known_faces': known_faces
        }
        
    except Exception as e:
        print(f">> Error initializing detector: {e}")
        return None

def process_frame(frame, detector):
    """Process a frame for face detection"""
    try:
        if not detector:
            return None
        
        app = detector['app']
        known_faces = detector['known_faces']
        
        # Detect faces
        faces = app.get(frame)
        
        if not faces:
            return None
        
        # Process the first face found
        face = faces[0]
        embedding = face.normed_embedding
        bbox = face.bbox.astype(int)
        
        # Extract face region
        x1, y1, x2, y2 = bbox
        face_img = frame[y1:y2, x1:x2]
        
        # Find best match — compare against ALL stored embeddings, take max
        best_match = "Unknown"
        best_confidence = 0.0
        
        for name, embeddings in known_faces.items():
            # embeddings is a list; take best score across all reference images
            score = max(float(np.dot(embedding, e)) for e in embeddings)
            if score > best_confidence:
                best_confidence = score
                best_match = name
        
        # Tiered thresholds: ALERT=0.55, HIGH_CONFIDENCE=0.75
        if best_confidence >= 0.75:
            pass  # High-confidence hit
        elif best_confidence >= 0.55:
            pass  # Alert — flag for human review
        else:
            best_match = "Unknown"
            best_confidence = 0.0
        
        return {
            'detected': True,
            'name': best_match,
            'confidence': best_confidence,
            'bbox': bbox,
            'face_image': face_img,
            'full_frame': frame
        }
        
    except Exception as e:
        print(f">> Error processing frame: {e}")
        return None
