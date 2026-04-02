"""
Enhanced detector with hardware optimization and better platform support
"""
import os
import sys
import pickle
import numpy as np
import cv2
import platform

# Try to import dependencies with fallbacks
try:
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError as e:
    print(f">> InsightFace not available: {e}")
    INSIGHTFACE_AVAILABLE = False

try:
    from camera_manager import hardware_optimizer
    HARDWARE_OPTIMIZER_AVAILABLE = True
except ImportError as e:
    print(f">> Hardware optimizer not available: {e}")
    HARDWARE_OPTIMIZER_AVAILABLE = False
    # Create a basic hardware optimizer
    class BasicHardwareOptimizer:
        def __init__(self):
            self.available_devices = {'cpu': True, 'gpu': False}
            self.platform_name = platform.system().lower()
        
        def get_optimal_ctx_id(self):
            return -1  # Use CPU
        
        def get_optimization_recommendations(self):
            return [f"ℹ️ Running on {self.platform_name} with CPU inference"]
    
    hardware_optimizer = BasicHardwareOptimizer()

class OptimizedFaceDetector:
    def __init__(self):
        self.app = None
        self.known_faces = {}
        self.platform_name = platform.system().lower()
        self.hardware_info = hardware_optimizer.available_devices
        
    def initialize_detector(self):
        """Initialize the face detector with hardware optimization"""
        try:
            print(">> Initializing optimized face detector...")
            print(f">> Platform: {self.platform_name}")
            print(f">> Hardware: {self.hardware_info}")
            
            if not INSIGHTFACE_AVAILABLE:
                print(">> InsightFace not available, enhanced detector disabled")
                return None
            
            # Get optimal context ID based on hardware
            ctx_id = hardware_optimizer.get_optimal_ctx_id()
            print(f">> Using context ID: {ctx_id}")
            
            # Print optimization recommendations
            recommendations = hardware_optimizer.get_optimization_recommendations()
            for rec in recommendations:
                print(f">> {rec}")
            
            # antelopev2: ArcFace R100 backbone — highest accuracy for crowd/surveillance
            model_name = 'antelopev2'
            
            # Platform-specific optimizations
            if self.platform_name == 'darwin' and self.hardware_info.get('apple_neural_engine'):
                print(">> Optimizing for Apple Silicon (CoreML)...")
                self.app = FaceAnalysis(name=model_name,
                                        providers=['CoreMLExecutionProvider', 'CPUExecutionProvider'])
                self.app.prepare(ctx_id=-1, det_size=(640, 640))

            elif self.hardware_info.get('cuda'):
                print(">> Optimizing for CUDA GPU — det_size 1280x1280...")
                try:
                    self.app = FaceAnalysis(name=model_name,
                                            providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
                    self.app.prepare(ctx_id=0, det_size=(1280, 1280))
                    print(">> CUDA GPU active")
                except Exception as e:
                    print(f">> CUDA init failed ({e}), falling back to CPU 640x640")
                    self.app = FaceAnalysis(name=model_name)
                    self.app.prepare(ctx_id=-1, det_size=(640, 640))

            else:
                print(">> Using CPU inference — det_size 640x640...")
                self.app = FaceAnalysis(name=model_name)
                self.app.prepare(ctx_id=-1, det_size=(640, 640))
            
            # Load face database
            self._load_face_database()
            
            print(f">> Face detector initialized successfully")
            print(f">> Loaded {len(self.known_faces)} known faces")
            
            return self
            
        except Exception as e:
            print(f">> Error initializing detector: {e}")
            print(">> Falling back to basic detector")
            return None
    
    def _load_face_database(self):
        """Load FAISS index (fast, O(log n)) with numpy list fallback."""
        face_db_path = 'embeddings/face_db.pkl'
        faiss_path   = 'embeddings/face_db.faiss'
        names_path   = 'embeddings/face_db_names.pkl'

        self.known_faces  = {}
        self.faiss_index  = None
        self.faiss_names  = None

        # Try FAISS first
        try:
            import faiss as _faiss
            if os.path.exists(faiss_path) and os.path.exists(names_path):
                self.faiss_index = _faiss.read_index(faiss_path)
                with open(names_path, 'rb') as f:
                    self.faiss_names = pickle.load(f)
                print(f">> FAISS index loaded: {self.faiss_index.ntotal} vectors")
        except ImportError:
            print(">> faiss not installed — numpy fallback active")
        except Exception as e:
            print(f">> FAISS load error: {e} — numpy fallback active")

        # Always load pkl (needed for numpy fallback + person-count display)
        if os.path.exists(face_db_path):
            try:
                with open(face_db_path, 'rb') as f:
                    face_db = pickle.load(f)
                    for name, data in face_db.items():
                        if 'embeddings' in data:
                            self.known_faces[name] = data['embeddings']
                        elif 'embedding' in data:
                            self.known_faces[name] = [data['embedding']]
                print(f">> Loaded face DB: {len(self.known_faces)} people")
            except Exception as e:
                print(f">> Error loading face DB: {e}")
        else:
            print(">> No face database found, will detect unknown faces only")
    
    def reload_face_database(self):
        """Reload face database (call after adding new people)"""
        self._load_face_database()
        return len(self.known_faces)
    
    def process_frame_optimized(self, frame, confidence_threshold=0.3):
        """
        Process frame with optimizations for better performance
        
        Args:
            frame: Input image frame
            confidence_threshold: Minimum confidence for recognition
            
        Returns:
            Dictionary with detection results
        """
        try:
            if not self.app:
                return None
            
            original_frame = frame.copy()
            height, width = frame.shape[:2]

            # Pass full resolution to detector — antelopev2 with det_size=1280 handles it.
            # Only hard-cap at 1920 to avoid OOM on embedded hardware.
            max_dimension = 1920
            if max(width, height) > max_dimension:
                if width > height:
                    new_width = max_dimension
                    new_height = int(height * max_dimension / width)
                else:
                    new_height = max_dimension
                    new_width = int(width * max_dimension / height)
                frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
                scale_x = width / new_width
                scale_y = height / new_height
            else:
                scale_x = scale_y = 1.0
            
            # Detect faces using InsightFace
            faces = self.app.get(frame)

            # Multi-scale fallback: if nothing found, upsample 2x to catch distant/small faces
            if not faces:
                upscaled = cv2.resize(frame, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
                faces_up = self.app.get(upscaled)
                if faces_up:
                    # Halve bbox coords to map back to original (pre-upscale) space
                    for f in faces_up:
                        f.bbox /= 2.0
                    faces = faces_up
            
            if not faces:
                return {
                    'detected': False,
                    'faces': [],
                    'frame_processed': True,
                    'processing_size': f'{frame.shape[1]}x{frame.shape[0]}'
                }
            
            # Process all detected faces
            processed_faces = []
            
            for face in faces:
                embedding = face.normed_embedding
                bbox = face.bbox.astype(int)
                
                # Scale bbox back to original frame size
                bbox[0] = int(bbox[0] * scale_x)  # x1
                bbox[1] = int(bbox[1] * scale_y)  # y1
                bbox[2] = int(bbox[2] * scale_x)  # x2
                bbox[3] = int(bbox[3] * scale_y)  # y2
                
                # Extract face region from original frame
                x1, y1, x2, y2 = bbox
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(width, x2), min(height, y2)
                
                if x2 > x1 and y2 > y1:
                    face_img = original_frame[y1:y2, x1:x2]
                else:
                    face_img = None
                
                # ── Embedding matching ──────────────────────────────────────────
                best_name    = 'Unknown'
                best_score   = 0.0
                similarity_scores = {}

                if self.faiss_index is not None and self.faiss_names is not None:
                    # FAISS path: O(log n) search across entire DB
                    import faiss as _faiss
                    q = embedding.reshape(1, -1).astype(np.float32)
                    _faiss.normalize_L2(q)
                    scores, indices = self.faiss_index.search(q, k=min(3, self.faiss_index.ntotal))
                    for s, idx in zip(scores[0], indices[0]):
                        if idx < 0:
                            continue
                        n = self.faiss_names[int(idx)]
                        similarity_scores[n] = max(similarity_scores.get(n, 0.0), float(s))
                    if similarity_scores:
                        best_name  = max(similarity_scores, key=similarity_scores.get)
                        best_score = similarity_scores[best_name]
                else:
                    # Numpy fallback: score against all stored reference embeddings
                    for name, embeddings in self.known_faces.items():
                        score = max(float(np.dot(embedding, e)) for e in embeddings)
                        similarity_scores[name] = score
                        if score > best_score:
                            best_score = score
                            best_name  = name

                # Tiered confidence:
                #   >= 0.75 → HIGH  (auto-alert, high-confidence hit)
                #   >= 0.55 → SOFT  (flag for human review)
                #   < 0.55  → Unknown
                if best_score >= 0.75:
                    match_tier = 'HIGH'
                elif best_score >= 0.55:
                    match_tier = 'SOFT'
                else:
                    best_name  = 'Unknown'
                    best_score = 0.0
                    match_tier = 'NONE'
                
                # Get additional face attributes if available
                face_info = {
                    'name':             best_name,
                    'confidence':       best_score,
                    'match_tier':       match_tier,
                    'bbox':             bbox.tolist(),
                    'face_image':       face_img,
                    'similarity_scores': similarity_scores,
                    'embedding': embedding.tolist() if len(self.known_faces) == 0 else None,
                }
                
                # Add face attributes if available from InsightFace
                try:
                    if hasattr(face, 'age'):
                        face_info['age'] = int(face.age)
                    if hasattr(face, 'gender'):
                        face_info['gender'] = 'Male' if face.gender == 1 else 'Female'
                    if hasattr(face, 'emotion'):
                        face_info['emotion'] = face.emotion
                except:
                    pass
                
                processed_faces.append(face_info)
            
            # Return the best match (highest confidence) as primary result
            primary_face = max(processed_faces, key=lambda x: x['confidence']) if processed_faces else None
            
            result = {
                'detected': len(processed_faces) > 0,
                'face_count': len(processed_faces),
                'faces': processed_faces,
                'primary_face': primary_face,
                'frame_processed': True,
                'processing_size': f'{frame.shape[1]}x{frame.shape[0]}',
                'original_size': f'{width}x{height}'
            }
            
            # Backward compat keys (used by basic detector callers)
            if primary_face:
                result.update({
                    'name':       primary_face['name'],
                    'confidence': primary_face['confidence'],
                    'bbox':       primary_face['bbox'],
                    'face_image': primary_face['face_image'],
                    'match_tier': primary_face.get('match_tier', 'NONE'),
                })
            
            return result
            
        except Exception as e:
            print(f">> Error processing frame: {e}")
            return {
                'detected': False,
                'error': str(e),
                'frame_processed': False
            }
    
    def get_detection_stats(self):
        """Get detection statistics and performance info"""
        return {
            'platform': self.platform_name,
            'hardware': self.hardware_info,
            'known_faces': len(self.known_faces),
            'model_loaded': self.app is not None,
            'optimization_recommendations': hardware_optimizer.get_optimization_recommendations()
        }

# Global detector instance
optimized_detector = None

def initialize_detector():
    """Initialize the optimized detector (backward compatibility)"""
    global optimized_detector
    optimized_detector = OptimizedFaceDetector()
    result = optimized_detector.initialize_detector()
    return result

def process_frame(frame, detector):
    """Process frame (backward compatibility)"""
    if detector and hasattr(detector, 'process_frame_optimized'):
        return detector.process_frame_optimized(frame)
    elif optimized_detector:
        return optimized_detector.process_frame_optimized(frame)
    else:
        return None

def reload_face_database():
    """Reload face database"""
    if optimized_detector:
        return optimized_detector.reload_face_database()
    return 0