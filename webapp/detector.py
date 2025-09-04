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
        
        # Initialize InsightFace
        app = FaceAnalysis(name='buffalo_s')
        app.prepare(ctx_id=-1)
        
        # Load face database
        face_db_path = 'embeddings/face_db.pkl'
        known_faces = {}
        
        if os.path.exists(face_db_path):
            with open(face_db_path, 'rb') as f:
                face_db = pickle.load(f)
                for name, data in face_db.items():
                    known_faces[name] = data['embedding']
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
        
        # Find best match
        best_match = "Unknown"
        best_confidence = 0.0
        
        for name, known_embedding in known_faces.items():
            # Calculate cosine similarity
            similarity = np.dot(embedding, known_embedding)
            if similarity > best_confidence:
                best_confidence = similarity
                best_match = name
        
        # Threshold for recognition
        if best_confidence < 0.3:  # Adjust as needed
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
