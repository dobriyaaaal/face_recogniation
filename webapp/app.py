"""
Simplified Face Recognition System - Main Application
No encryption, simple file storage, uses existing detector
"""
import os
import sys
import warnings
import logging

# Suppress specific warnings before importing other modules
warnings.filterwarnings("ignore", category=UserWarning, module="pygame")
warnings.filterwarnings("ignore", category=UserWarning, module="pkg_resources")
warnings.filterwarnings("ignore", category=UserWarning, module="onnxruntime")

# Suppress pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

# Configure logging to suppress excessive output
logging.getLogger('onnxruntime').setLevel(logging.ERROR)
logging.getLogger('insightface').setLevel(logging.ERROR)

from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from flask_socketio import SocketIO, emit
import sqlite3
import base64
import cv2
import numpy as np
import threading
import time
import json
from datetime import datetime
import pygame
import pytz
from collections import defaultdict

app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')
app.config['SECRET_KEY'] = 'simple_face_recognition_key'

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Database and directories
DB_PATH = 'simple_face_recognition.db'
ALERT_SOUND_FILE = '../archive/alert.mp3'
GALLERY_FOLDER = '../gallery'
PEOPLE_FOLDER = '../people'
EMBEDDINGS_FOLDER = '../embeddings'
FACE_DB_PATH = os.path.join(EMBEDDINGS_FOLDER, 'face_db.pkl')

# Ensure directories exist
os.makedirs(GALLERY_FOLDER, exist_ok=True)
os.makedirs(PEOPLE_FOLDER, exist_ok=True)
os.makedirs(EMBEDDINGS_FOLDER, exist_ok=True)

# Global variables for detection
detector = None
detection_running = False
detection_thread = None

# Timezone configuration
LOCAL_TIMEZONE = pytz.timezone('America/New_York')
recent_alerts = []

# Add archive/libs to Python path for detector
archive_libs_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'archive', 'libs')
if archive_libs_path not in sys.path:
    sys.path.append(archive_libs_path)

def init_database():
    """Initialize the simple database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Simple tables without encryption
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS streams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_name TEXT,
            confidence REAL,
            camera_source TEXT,
            detection_time TIMESTAMP,
            detection_image TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def rebuild_face_database():
    """Rebuild the face database from people folder"""
    try:
        from face_db import build_face_embeddings
        
        # Set the base directory to our people folder
        import face_db
        face_db.build_face_embeddings()
        print(">> Face database rebuilt successfully")
        return True
    except Exception as e:
        print(f">> Error rebuilding face database: {e}")
        return False

def save_person_images(person_name, image_files):
    """Save person images to people folder"""
    person_folder = os.path.join(PEOPLE_FOLDER, person_name)
    os.makedirs(person_folder, exist_ok=True)
    
    saved_files = []
    for i, image_data in enumerate(image_files):
        filename = f"image_{i+1}.jpg"
        filepath = os.path.join(person_folder, filename)
        
        # Decode base64 image
        if ',' in image_data:
            image_binary = base64.b64decode(image_data.split(',')[1])
        else:
            image_binary = base64.b64decode(image_data)
        
        with open(filepath, 'wb') as f:
            f.write(image_binary)
        
        saved_files.append(filepath)
    
    return saved_files

def play_alert_sound():
    """Play alert sound"""
    try:
        if os.path.exists(ALERT_SOUND_FILE):
            pygame.mixer.init()
            pygame.mixer.music.load(ALERT_SOUND_FILE)
            pygame.mixer.music.play()
    except Exception as e:
        print(f"Alert sound error: {e}")

def send_alert_notification(person_name, confidence, camera_source):
    """Send real-time alert"""
    alert_data = {
        'person': person_name,
        'confidence': f"{confidence:.1%}",
        'camera': camera_source,
        'timestamp': datetime.now().isoformat(),
        'message': f"🚨 DETECTION: {person_name} detected with {confidence:.1%} confidence"
    }
    
    recent_alerts.insert(0, alert_data)
    if len(recent_alerts) > 50:
        recent_alerts.pop()
    
    socketio.emit('detection_alert', alert_data)

def save_detection_image(image_data, person_name, timestamp_info):
    """Save detection image"""
    try:
        date_folder = os.path.join(GALLERY_FOLDER, timestamp_info['folder_date'])
        os.makedirs(date_folder, exist_ok=True)
        
        safe_name = "".join(c for c in person_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"{timestamp_info['filename_time']}_{safe_name}.jpg"
        filepath = os.path.join(date_folder, filename)
        
        if isinstance(image_data, np.ndarray):
            cv2.imwrite(filepath, image_data)
        else:
            with open(filepath, 'wb') as f:
                f.write(image_data)
        
        return filepath
    except Exception as e:
        print(f"Error saving detection image: {e}")
        return None

def format_timestamp_for_timezone(utc_timestamp):
    """Convert UTC timestamp to local timezone"""
    try:
        if isinstance(utc_timestamp, str):
            utc_dt = datetime.fromisoformat(utc_timestamp.replace('Z', '+00:00'))
        else:
            utc_dt = utc_timestamp
        
        local_dt = utc_dt.replace(tzinfo=pytz.UTC).astimezone(LOCAL_TIMEZONE)
        
        return {
            'date': local_dt.strftime('%Y-%m-%d'),
            'time': local_dt.strftime('%I:%M:%S %p'),
            'datetime': local_dt.strftime('%Y-%m-%d %I:%M:%S %p'),
            'filename_time': local_dt.strftime('%I-%M-%S_%p'),
            'folder_date': local_dt.strftime('%Y-%m-%d'),
            'timestamp': local_dt.isoformat()
        }
    except Exception as e:
        print(f"Timestamp formatting error: {e}")
        now = datetime.now(LOCAL_TIMEZONE)
        return {
            'date': now.strftime('%Y-%m-%d'),
            'time': now.strftime('%I:%M:%S %p'),
            'datetime': now.strftime('%Y-%m-%d %I:%M:%S %p'),
            'filename_time': now.strftime('%I-%M-%S_%p'),
            'folder_date': now.strftime('%Y-%m-%d'),
            'timestamp': now.isoformat()
        }

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/camera/test', methods=['POST'])
def test_camera():
    """Test camera stream"""
    try:
        data = request.get_json()
        camera_url = data.get('url', '')
        
        if not camera_url:
            return jsonify({'success': False, 'error': 'Camera URL is required'})
        
        cap = cv2.VideoCapture(camera_url)
        
        if not cap.isOpened():
            return jsonify({'success': False, 'error': 'Unable to connect to camera stream'})
        
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return jsonify({'success': False, 'error': 'Unable to read frame from camera'})
        
        # Resize frame for preview
        height, width = frame.shape[:2]
        if width > 640:
            ratio = 640 / width
            new_width = 640
            new_height = int(height * ratio)
            frame = cv2.resize(frame, (new_width, new_height))
        
        _, buffer = cv2.imencode('.jpg', frame)
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        
        return jsonify({
            'success': True, 
            'message': 'Camera test successful',
            'preview': f'data:image/jpeg;base64,{frame_base64}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Camera test failed: {str(e)}'})

@app.route('/api/streams', methods=['POST'])
def add_stream():
    """Add a new camera stream"""
    try:
        data = request.get_json()
        name = data.get('name', '')
        url = data.get('url', '')
        
        if not name or not url:
            return jsonify({'success': False, 'error': 'Name and URL are required'})
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO streams (name, url) VALUES (?, ?)
        ''', (name, url))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Camera stream added successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to add stream: {str(e)}'})

@app.route('/api/streams')
def get_streams():
    """Get all camera streams"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, name, url FROM streams WHERE active = 1')
        rows = cursor.fetchall()
        conn.close()
        
        streams = [{'id': row[0], 'name': row[1], 'url': row[2]} for row in rows]
        
        return jsonify({'success': True, 'streams': streams})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to load streams: {str(e)}', 'streams': []})

@app.route('/api/streams/<int:stream_id>', methods=['DELETE'])
def delete_stream(stream_id):
    """Delete a camera stream"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('UPDATE streams SET active = 0 WHERE id = ?', (stream_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Stream deleted successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to delete stream: {str(e)}'})

@app.route('/api/people/add', methods=['POST'])
def add_person():
    """Add a new person with images"""
    try:
        data = request.get_json()
        name = data.get('name', '')
        images = data.get('images', [])
        
        if not name:
            return jsonify({'success': False, 'error': 'Name is required'})
        
        if not images:
            return jsonify({'success': False, 'error': 'At least one image is required'})
        
        # Save person to database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('INSERT INTO people (name) VALUES (?)', (name,))
        person_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        # Save images to people folder
        saved_files = save_person_images(name, images)
        
        # Rebuild face database
        rebuild_face_database()
        
        return jsonify({
            'success': True, 
            'message': f'Person {name} added successfully',
            'person_id': person_id,
            'saved_files': len(saved_files)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to add person: {str(e)}'})

@app.route('/api/people')
def get_people():
    """Get all people"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, name, created_at FROM people ORDER BY name')
        rows = cursor.fetchall()
        conn.close()
        
        people = [{'id': row[0], 'name': row[1], 'created_at': row[2]} for row in rows]
        
        return jsonify({'success': True, 'people': people})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to load people: {str(e)}', 'people': []})

@app.route('/api/detection/start', methods=['POST'])
def start_detection():
    """Start face detection"""
    global detection_running, detection_thread, detector
    
    try:
        if detection_running:
            return jsonify({'success': False, 'error': 'Detection is already running'})
        
        # Check prerequisites
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM people')
        people_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM streams WHERE active = 1')
        streams_count = cursor.fetchone()[0]
        
        conn.close()
        
        if people_count == 0:
            return jsonify({'success': False, 'error': 'No people added yet. Please add at least one person to recognize.'})
        
        if streams_count == 0:
            return jsonify({'success': False, 'error': 'No camera streams configured. Please add at least one camera stream.'})
        
        # Check if face database exists
        if not os.path.exists(FACE_DB_PATH):
            rebuild_face_database()
        
        detection_running = True
        socketio.emit('detection_status', {'status': 'starting', 'message': 'Initializing detection system...'})
        
        def detection_worker():
            global detection_running, detector
            
            try:
                from detector import initialize_detector, process_frame
                
                socketio.emit('detection_status', {'status': 'loading_detector', 'message': 'Loading face detector...'})
                detector = initialize_detector()
                
                if not detector:
                    socketio.emit('detection_error', {'error': 'Failed to initialize detector'})
                    return
                
                socketio.emit('detection_status', {'status': 'loading_streams', 'message': 'Connecting to cameras...'})
                
                # Get active streams
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute('SELECT id, name, url FROM streams WHERE active = 1')
                active_streams = cursor.fetchall()
                conn.close()
                
                # Initialize camera captures
                camera_caps = {}
                for stream_id, stream_name, stream_url in active_streams:
                    try:
                        cap = cv2.VideoCapture(stream_url)
                        if cap.isOpened():
                            camera_caps[stream_id] = {
                                'cap': cap,
                                'name': stream_name,
                                'url': stream_url
                            }
                            print(f">> Connected to camera: {stream_name}")
                        else:
                            print(f">> Failed to connect to camera: {stream_name}")
                    except Exception as e:
                        print(f">> Error connecting to {stream_name}: {e}")
                
                if not camera_caps:
                    socketio.emit('detection_error', {'error': 'No cameras could be connected'})
                    return
                
                socketio.emit('detection_status', {'status': 'running', 'message': f'Monitoring {len(camera_caps)} cameras'})
                
                frame_count = 0
                while detection_running:
                    frame_count += 1
                    
                    for stream_id, stream_data in camera_caps.items():
                        if not detection_running:
                            break
                            
                        cap = stream_data['cap']
                        stream_name = stream_data['name']
                        
                        ret, frame = cap.read()
                        if not ret:
                            print(f">> Lost connection to {stream_name}")
                            continue
                        
                        # Process every 5th frame to reduce CPU load
                        if frame_count % 5 != 0:
                            continue
                        
                        # Process frame for face detection
                        result = process_frame(frame, detector)
                        
                        if result and result.get('detected'):
                            person_name = result.get('name', 'Unknown')
                            confidence = result.get('confidence', 0.0)
                            
                            if confidence > 0.7:  # Confidence threshold
                                # Save detection
                                timestamp_info = format_timestamp_for_timezone(datetime.now())
                                
                                # Save detection image
                                detection_image_path = save_detection_image(
                                    result.get('face_image', frame), 
                                    person_name, 
                                    timestamp_info
                                )
                                
                                # Save to database
                                conn = sqlite3.connect(DB_PATH)
                                cursor = conn.cursor()
                                
                                cursor.execute('''
                                    INSERT INTO detections (person_name, confidence, camera_source, detection_time, detection_image)
                                    VALUES (?, ?, ?, ?, ?)
                                ''', (person_name, confidence, stream_name, timestamp_info['timestamp'], detection_image_path))
                                
                                conn.commit()
                                conn.close()
                                
                                # Send alerts
                                send_alert_notification(person_name, confidence, stream_name)
                                play_alert_sound()
                                
                                print(f">> Detected {person_name} (confidence: {confidence:.2f}) on {stream_name}")
                    
                    time.sleep(0.2)  # Small delay
                
            except Exception as e:
                print(f">> Detection worker error: {e}")
                socketio.emit('detection_error', {'error': str(e)})
            finally:
                # Clean up
                if 'camera_caps' in locals():
                    for stream_data in camera_caps.values():
                        try:
                            stream_data['cap'].release()
                        except:
                            pass
                
                detection_running = False
                socketio.emit('detection_status', {'status': 'stopped', 'message': 'Detection stopped'})
        
        detection_thread = threading.Thread(target=detection_worker, daemon=True)
        detection_thread.start()
        
        return jsonify({'success': True, 'message': 'Detection started successfully'})
        
    except Exception as e:
        detection_running = False
        return jsonify({'success': False, 'error': f'Failed to start detection: {str(e)}'})

@app.route('/api/detection/stop', methods=['POST'])
def stop_detection():
    """Stop face detection"""
    global detection_running
    
    try:
        detection_running = False
        socketio.emit('detection_status', {'status': 'stopping', 'message': 'Stopping detection...'})
        time.sleep(1)
        socketio.emit('detection_status', {'status': 'stopped', 'message': 'Detection stopped'})
        return jsonify({'success': True, 'message': 'Detection stopped successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to stop detection: {str(e)}'})

@app.route('/api/detections')
def get_detections():
    """Get recent detections"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT person_name, confidence, camera_source, detection_time, detection_image
            FROM detections
            ORDER BY detection_time DESC
            LIMIT 50
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        detections = []
        for row in rows:
            detections.append({
                'person_name': row[0],
                'confidence': row[1],
                'camera_source': row[2],
                'detection_time': row[3],
                'detection_image': row[4]
            })
        
        return jsonify({'success': True, 'detections': detections})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to load detections: {str(e)}', 'detections': []})

def initialize_app():
    """Initialize the application"""
    print(">> Initializing Face Recognition System...")
    init_database()
    print(">> Database initialized")
    
    # Initialize pygame for sound
    try:
        pygame.mixer.init()
        print(">> Audio system initialized")
    except Exception as e:
        print(f">> Audio initialization failed: {e}")

if __name__ == '__main__':
    initialize_app()
    socketio.run(app, debug=False, host='0.0.0.0', port=5000)
