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

from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, Response, render_template_string
from flask_socketio import SocketIO, emit
import sqlite3
import base64
import cv2
import numpy as np
import threading
import time
import json
import shutil
from datetime import datetime
import pygame
import pytz
from collections import defaultdict
import signal
import concurrent.futures

app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')
app.config['SECRET_KEY'] = 'simple_face_recognition_key'

# Import enhanced camera management
try:
    from camera_api import camera_bp
    from camera_manager import camera_manager, hardware_optimizer
    USE_ENHANCED_FEATURES = True
    print(">> Enhanced camera features loaded")
    # Register enhanced camera blueprint
    app.register_blueprint(camera_bp)
except ImportError as e:
    print(f">> Enhanced features not available: {e}")
    USE_ENHANCED_FEATURES = False

# Try enhanced detector, fallback to basic
try:
    from enhanced_detector import initialize_detector as enhanced_initialize_detector, process_frame as enhanced_process_frame
    USE_ENHANCED_DETECTOR = True
    print(">> Enhanced detector loaded")
except ImportError as e:
    print(f">> Enhanced detector not available, using basic detector: {e}")
    USE_ENHANCED_DETECTOR = False

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Database and directories
DB_PATH = 'simple_face_recognition.db'
ALERT_SOUND_FILE = 'alarm.mp3'  # Use local alarm file
GALLERY_FOLDER = 'gallery'
PEOPLE_FOLDER = 'people'
EMBEDDINGS_FOLDER = 'embeddings'
FACE_DB_PATH = os.path.join(EMBEDDINGS_FOLDER, 'face_db.pkl')

# Ensure directories exist
os.makedirs(GALLERY_FOLDER, exist_ok=True)
os.makedirs(PEOPLE_FOLDER, exist_ok=True)
os.makedirs(EMBEDDINGS_FOLDER, exist_ok=True)

def connect_camera_with_timeout(stream_url, timeout=10):
    """Connect to camera with timeout - Working RTSP optimization"""
    def connect():
        try:
            print(f">> Creating VideoCapture for {stream_url}")
            
            # RTSP-specific optimizations
            if 'rtsp://' in stream_url.lower():
                print(f">> Applying working RTSP optimizations...")
                
                # Try the approaches that work (based on test results)
                rtsp_configs = [
                    {
                        'url': f"{stream_url}?tcp=1&timeout=3",
                        'backend': cv2.CAP_FFMPEG,
                        'description': 'TCP with timeout parameters'
                    },
                    {
                        'url': f"{stream_url}?buffer_size=0&timeout=3", 
                        'backend': cv2.CAP_FFMPEG,
                        'description': 'Zero buffer with timeout'
                    },
                    {
                        'url': stream_url,  # Plain URL - this one worked!
                        'backend': cv2.CAP_FFMPEG,
                        'description': 'Plain RTSP URL'
                    }
                ]
                
                for i, config in enumerate(rtsp_configs, 1):
                    print(f">> RTSP attempt {i}: {config['description']}")
                    
                    try:
                        # Create VideoCapture with specific backend
                        cap = cv2.VideoCapture(config['url'], config['backend'])
                        
                        # Set optimizations immediately
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        
                        print(f">> Checking if VideoCapture {i} is opened...")
                        if cap.isOpened():
                            print(f">> VideoCapture {i} opened! Testing frame read...")
                            
                            # Quick frame test with threading timeout
                            frame_result = {'ret': False, 'frame': None, 'completed': False}
                            
                            def read_frame():
                                try:
                                    start_time = time.time()
                                    ret, frame = cap.read()
                                    end_time = time.time()
                                    frame_result.update({
                                        'ret': ret, 
                                        'frame': frame, 
                                        'read_time': end_time - start_time,
                                        'completed': True
                                    })
                                except Exception as e:
                                    frame_result.update({'error': str(e), 'completed': True})
                            
                            # Start frame reading in separate thread
                            read_thread = threading.Thread(target=read_frame)
                            read_thread.daemon = True
                            read_thread.start()
                            
                            # Wait max 3 seconds for frame
                            read_thread.join(timeout=3.0)
                            
                            if frame_result['completed']:
                                ret = frame_result['ret']
                                frame = frame_result['frame']
                                read_time = frame_result.get('read_time', 0)
                                
                                print(f">> Frame read completed in {read_time:.3f}s, ret={ret}")
                                
                                if ret and frame is not None and frame.size > 0:
                                    height, width = frame.shape[:2]
                                    print(f">> 🎉 SUCCESS! RTSP {i} works (size: {width}x{height}, time: {read_time:.3f}s)")
                                    return cap, True, f"RTSP success #{i} in {read_time:.3f}s"
                                else:
                                    print(f">> RTSP {i} read failed: frame_valid={frame is not None}")
                                    cap.release()
                            else:
                                print(f">> RTSP {i} frame read timed out after 3s")
                                cap.release()
                        else:
                            print(f">> RTSP {i} failed to open")
                            cap.release()
                    
                    except Exception as config_err:
                        print(f">> RTSP {i} config error: {config_err}")
                        try:
                            cap.release()
                        except:
                            pass
                
                # If all RTSP attempts fail
                print(f">> All RTSP attempts failed")
                return None, False, "All RTSP attempts failed"
            
            else:
                # Standard approach for HTTP streams
                cap = cv2.VideoCapture(stream_url)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                print(f">> Checking if VideoCapture is opened...")
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        return cap, True, "HTTP stream success"
                    else:
                        cap.release()
                        return None, False, "Cannot read HTTP frames"
                else:
                    return None, False, "Cannot open HTTP stream"
                    
        except Exception as e:
            print(f">> Exception during connection: {e}")
            return None, False, str(e)
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(connect)
        try:
            cap, success, message = future.result(timeout=timeout)
            return cap, success, message
        except concurrent.futures.TimeoutError:
            print(f">> ThreadPoolExecutor timeout after {timeout}s")
            return None, False, f"Connection timeout after {timeout}s"

# Global variables for detection
detector = None
detection_running = False
detection_thread = None
detection_frames = {}  # Store latest frames for each camera
detection_results = {}  # Store latest detection results

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
    """Save person images to people folder (from base64 data)"""
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

def save_person_images_from_files(person_name, image_files):
    """Save person images to people folder (from uploaded files)"""
    person_folder = os.path.join(PEOPLE_FOLDER, person_name)
    os.makedirs(person_folder, exist_ok=True)
    
    saved_files = []
    for i, image_file in enumerate(image_files):
        filename = f"image_{i+1}.jpg"
        filepath = os.path.join(person_folder, filename)
        
        # Save the uploaded file
        image_file.save(filepath)
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

# Global dictionary to store active camera streams for preview
active_streams = {}

@app.route('/api/camera/stream/<int:stream_id>')
def video_stream(stream_id):
    """Stream live video from camera"""
    def generate_frames(camera_url):
        cap = cv2.VideoCapture(camera_url)
        if not cap.isOpened():
            return
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Resize frame for web streaming
                height, width = frame.shape[:2]
                if width > 640:
                    ratio = 640 / width
                    new_width = 640
                    new_height = int(height * ratio)
                    frame = cv2.resize(frame, (new_width, new_height))
                
                # Encode frame as JPEG
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if not ret:
                    continue
                    
                frame_bytes = buffer.tobytes()
                
                # Yield frame in multipart format
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
        finally:
            cap.release()
    
    # Get camera URL from database
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT url FROM streams WHERE id = ? AND active = 1', (stream_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            from flask import Response
            return Response("Camera not found", status=404)
        
        camera_url = result[0]
        
        from flask import Response
        return Response(generate_frames(camera_url),
                       mimetype='multipart/x-mixed-replace; boundary=frame')
        
    except Exception as e:
        from flask import Response
        return Response(f"Error: {str(e)}", status=500)

@app.route('/api/camera/preview')
def camera_preview():
    """Serve camera preview page"""
    camera_url = request.args.get('url', '')
    camera_name = request.args.get('name', 'Camera')
    
    if not camera_url:
        return "Camera URL required", 400
    
    # Create a temporary stream entry for preview
    temp_id = abs(hash(camera_url)) % 10000
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Camera Test - {camera_name}</title>
        <style>
            body {{
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
                color: white;
                font-family: Arial, sans-serif;
                min-height: 100vh;
            }}
            .container {{
                max-width: 900px;
                margin: 0 auto;
                text-align: center;
            }}
            .header {{
                background: rgba(30, 41, 59, 0.8);
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                backdrop-filter: blur(10px);
            }}
            .status {{
                padding: 10px 20px;
                border-radius: 20px;
                font-weight: bold;
                margin: 10px 0;
                display: inline-block;
            }}
            .status.connecting {{
                background: #ff9800;
                color: white;
            }}
            .status.connected {{
                background: #4caf50;
                color: white;
            }}
            .status.error {{
                background: #f44336;
                color: white;
            }}
            .video-container {{
                background: rgba(0, 0, 0, 0.8);
                border: 2px solid #334155;
                border-radius: 12px;
                overflow: hidden;
                margin: 20px 0;
                min-height: 400px;
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;
            }}
            .video-stream {{
                max-width: 100%;
                height: auto;
                display: block;
            }}
            .loading {{
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 20px;
                color: #94a3b8;
            }}
            .spinner {{
                width: 50px;
                height: 50px;
                border: 4px solid #334155;
                border-top: 4px solid #3b82f6;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            .live-indicator {{
                position: absolute;
                top: 10px;
                right: 10px;
                background: rgba(239, 68, 68, 0.9);
                color: white;
                padding: 5px 10px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: bold;
                letter-spacing: 1px;
            }}
            .info {{
                background: rgba(30, 41, 59, 0.8);
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
                backdrop-filter: blur(10px);
                text-align: left;
            }}
            .close-btn {{
                padding: 12px 24px;
                background: linear-gradient(135deg, #ef4444, #dc2626);
                color: white;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-size: 16px;
                font-weight: bold;
                transition: all 0.3s ease;
            }}
            .close-btn:hover {{
                background: linear-gradient(135deg, #dc2626, #b91c1c);
                transform: translateY(-1px);
            }}
            .url-display {{
                background: rgba(0, 0, 0, 0.3);
                padding: 8px 12px;
                border-radius: 4px;
                font-family: monospace;
                word-break: break-all;
                font-size: 14px;
                color: #94a3b8;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📹 {camera_name}</h1>
                <div id="status" class="status connecting">
                    🔄 Connecting to camera...
                </div>
            </div>
            
            <div class="info">
                <p><strong>Stream URL:</strong></p>
                <div class="url-display">{camera_url}</div>
            </div>
            
            <div class="video-container" id="videoContainer">
                <div id="loading" class="loading">
                    <div class="spinner"></div>
                    <div>📡 Establishing connection...</div>
                    <div style="font-size: 14px; color: #64748b;">Please wait while we connect to your camera</div>
                </div>
                <img id="videoStream" class="video-stream" style="display: none;" />
                <div id="liveIndicator" class="live-indicator" style="display: none;">🔴 LIVE</div>
            </div>
            
            <button class="close-btn" onclick="window.close()">Close Test Window</button>
        </div>
        
        <script>
            const statusDiv = document.getElementById('status');
            const videoStream = document.getElementById('videoStream');
            const loading = document.getElementById('loading');
            const liveIndicator = document.getElementById('liveIndicator');
            
            let connectionTimeout;
            let retryCount = 0;
            const maxRetries = 3;
            
            function updateStatus(message, type) {{
                statusDiv.textContent = message;
                statusDiv.className = 'status ' + type;
            }}
            
            function tryLoadStream() {{
                const streamUrl = '/api/camera/stream_url?url={camera_url}&t=' + new Date().getTime();
                
                updateStatus('🔗 Loading video stream...', 'connecting');
                
                videoStream.onload = function() {{
                    console.log('Video stream loaded successfully');
                    loading.style.display = 'none';
                    videoStream.style.display = 'block';
                    liveIndicator.style.display = 'block';
                    updateStatus('✅ Live stream active', 'connected');
                    clearTimeout(connectionTimeout);
                }};
                
                videoStream.onerror = function() {{
                    console.log('Stream error, retrying...');
                    retryCount++;
                    if (retryCount < maxRetries) {{
                        updateStatus(`⚠️ Connection issue, retrying... (${{retryCount}}/${{maxRetries}})`, 'connecting');
                        setTimeout(() => {{
                            tryLoadStream();
                        }}, 2000);
                    }} else {{
                        loading.style.display = 'none';
                        updateStatus('❌ Failed to load stream after multiple attempts', 'error');
                        videoContainer.innerHTML = '<div style="padding: 40px; color: #f87171;"><h3>Stream Connection Failed</h3><p>Unable to connect to the camera stream.<br>Please check your camera settings.</p></div>';
                    }}
                }};
                
                videoStream.src = streamUrl;
            }}
            
            // Start connection attempt
            setTimeout(() => {{
                tryLoadStream();
            }}, 1000);
            
            // Timeout after 30 seconds
            connectionTimeout = setTimeout(() => {{
                if (statusDiv.className.includes('connecting')) {{
                    updateStatus('⏱️ Connection timeout - Camera may be offline', 'error');
                    loading.style.display = 'none';
                    videoContainer.innerHTML = '<div style="padding: 40px; color: #f87171;"><h3>Connection Timeout</h3><p>Camera is not responding.<br>Please verify the camera is online and accessible.</p></div>';
                }}
            }}, 30000);
        </script>
    </body>
    </html>
    """
    
    from flask import Response
    return Response(html_content, mimetype='text/html')

@app.route('/api/camera/stream_url')
def video_stream_by_url():
    """Stream live video from camera URL"""
    camera_url = request.args.get('url', '')
    
    if not camera_url:
        from flask import Response
        return Response("Camera URL required", status=400)
    
    def generate_frames(url):
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            return
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Resize frame for web streaming
                height, width = frame.shape[:2]
                if width > 640:
                    ratio = 640 / width
                    new_width = 640
                    new_height = int(height * ratio)
                    frame = cv2.resize(frame, (new_width, new_height))
                
                # Encode frame as JPEG
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if not ret:
                    continue
                    
                frame_bytes = buffer.tobytes()
                
                # Yield frame in multipart format
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
        finally:
            cap.release()
    
    from flask import Response
    return Response(generate_frames(camera_url),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

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
        # Handle FormData from frontend
        name = request.form.get('name', '').strip()
        
        if not name:
            return jsonify({'success': False, 'error': 'Name is required'})
        
        # Get image files from FormData
        image_files = []
        for key in request.files:
            if key.startswith('image_'):
                image_file = request.files[key]
                if image_file and image_file.filename:
                    image_files.append(image_file)
        
        if not image_files:
            return jsonify({'success': False, 'error': 'At least one image is required'})
        
        # Save person to database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        try:
            cursor.execute('INSERT INTO people (name) VALUES (?)', (name,))
            person_id = cursor.lastrowid
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({'success': False, 'error': f'Person with name "{name}" already exists'})
        
        conn.close()
        
        # Save images to people folder
        saved_files = save_person_images_from_files(name, image_files)
        
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

@app.route('/api/people/<int:person_id>', methods=['DELETE'])
def delete_person(person_id):
    """Delete a person and their images"""
    try:
        # Get person info first
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT name FROM people WHERE id = ?', (person_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return jsonify({'success': False, 'error': 'Person not found'})
        
        person_name = result[0]
        
        # Delete from database
        cursor.execute('DELETE FROM people WHERE id = ?', (person_id,))
        cursor.execute('DELETE FROM detections WHERE person_name = ?', (person_name,))
        conn.commit()
        conn.close()
        
        # Delete person folder and images
        person_folder = os.path.join(PEOPLE_FOLDER, person_name)
        if os.path.exists(person_folder):
            shutil.rmtree(person_folder)
        
        # Rebuild face database
        rebuild_face_database()
        
        return jsonify({
            'success': True, 
            'message': f'Person {person_name} deleted successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to delete person: {str(e)}'})

@app.route('/api/people/<int:person_id>', methods=['PUT'])
def edit_person(person_id):
    """Edit a person's name and/or images"""
    try:
        # Get current person info
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT name FROM people WHERE id = ?', (person_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return jsonify({'success': False, 'error': 'Person not found'})
        
        old_name = result[0]
        new_name = request.form.get('name', '').strip()
        
        if not new_name:
            return jsonify({'success': False, 'error': 'Name is required'})
        
        # Check if new name already exists (but not for the same person)
        cursor.execute('SELECT id FROM people WHERE name = ? AND id != ?', (new_name, person_id))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': f'Person with name "{new_name}" already exists'})
        
        # Update database
        cursor.execute('UPDATE people SET name = ? WHERE id = ?', (new_name, person_id))
        cursor.execute('UPDATE detections SET person_name = ? WHERE person_name = ?', (new_name, old_name))
        conn.commit()
        conn.close()
        
        # Handle folder rename if name changed
        old_folder = os.path.join(PEOPLE_FOLDER, old_name)
        new_folder = os.path.join(PEOPLE_FOLDER, new_name)
        
        if old_name != new_name and os.path.exists(old_folder):
            os.rename(old_folder, new_folder)
        
        # Handle image removal if specified
        remove_images_json = request.form.get('remove_images')
        if remove_images_json:
            try:
                images_to_remove = json.loads(remove_images_json)
                for filename in images_to_remove:
                    image_path = os.path.join(new_folder, filename)
                    if os.path.exists(image_path):
                        os.remove(image_path)
            except Exception as e:
                print(f"Error removing images: {e}")
        
        # Handle new images if provided
        image_files = []
        for key in request.files:
            if key.startswith('image_'):
                image_file = request.files[key]
                if image_file and image_file.filename:
                    image_files.append(image_file)
        
        if image_files:
            # Save new images (don't remove old ones unless specifically requested)
            save_person_images_from_files(new_name, image_files)
        
        # Rebuild face database
        rebuild_face_database()
        
        return jsonify({
            'success': True, 
            'message': f'Person updated successfully',
            'person_id': person_id,
            'new_name': new_name
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to edit person: {str(e)}'})

@app.route('/api/people')
def get_people():
    """Get all people"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, name, created_at FROM people ORDER BY name')
        rows = cursor.fetchall()
        conn.close()
        
        people = []
        for row in rows:
            person_id, name, created_at = row
            
            # Count images for this person
            person_folder = os.path.join(PEOPLE_FOLDER, name)
            image_count = 0
            if os.path.exists(person_folder):
                image_files = [f for f in os.listdir(person_folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                image_count = len(image_files)
            
            people.append({
                'id': person_id, 
                'name': name, 
                'created_at': created_at,
                'image_count': image_count
            })
        
        return jsonify({'success': True, 'people': people})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to load people: {str(e)}', 'people': []})

@app.route('/api/people/<int:person_id>/image')
def get_person_image(person_id):
    """Get the first image for a person"""
    try:
        # Get person name from database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM people WHERE id = ?', (person_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({'error': 'Person not found'}), 404
        
        person_name = row[0]
        person_folder = os.path.join(PEOPLE_FOLDER, person_name)
        
        # Look for the first image file
        if os.path.exists(person_folder):
            for filename in sorted(os.listdir(person_folder)):
                if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    image_path = os.path.join(person_folder, filename)
                    return send_file(image_path, mimetype='image/jpeg')
        
        return jsonify({'error': 'No image found'}), 404
        
    except Exception as e:
        return jsonify({'error': f'Failed to load image: {str(e)}'}), 500

@app.route('/api/people/<int:person_id>/images')
def get_person_images(person_id):
    """Get all images for a person"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT name FROM people WHERE id = ?', (person_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return jsonify({'error': 'Person not found'}), 404
        
        person_name = result[0]
        person_folder = os.path.join(PEOPLE_FOLDER, person_name)
        
        images = []
        if os.path.exists(person_folder):
            for filename in sorted(os.listdir(person_folder)):
                if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    images.append({
                        'filename': filename,
                        'url': f'/api/people/{person_id}/images/{filename}'
                    })
        
        return jsonify({'success': True, 'images': images})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Failed to load images: {str(e)}'})

@app.route('/api/people/<int:person_id>/images/<filename>')
def get_person_image_by_filename(person_id, filename):
    """Get a specific image file for a person"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT name FROM people WHERE id = ?', (person_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return jsonify({'error': 'Person not found'}), 404
        
        person_name = result[0]
        person_folder = os.path.join(PEOPLE_FOLDER, person_name)
        image_path = os.path.join(person_folder, filename)
        
        if os.path.exists(image_path) and filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            return send_file(image_path, mimetype='image/jpeg')
        
        return jsonify({'error': 'Image not found'}), 404
        
    except Exception as e:
        return jsonify({'error': f'Failed to load image: {str(e)}'}), 500

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
                socketio.emit('detection_status', {'status': 'loading_streams', 'message': f'Testing {len(active_streams)} camera connections...'})
                
                for i, (stream_id, stream_name, stream_url) in enumerate(active_streams):
                    status_msg = f'Connecting to "{stream_name}" ({i+1}/{len(active_streams)})...'
                    socketio.emit('detection_status', {
                        'status': 'loading_streams', 
                        'message': status_msg
                    })
                    print(f">> {status_msg}")
                    time.sleep(0.1)  # Give time for message to be sent
                    
                    try:
                        # Use timeout wrapper for camera connection
                        # Use longer timeout for RTSP streams as they need more time to establish connection
                        timeout_duration = 60 if 'rtsp://' in stream_url.lower() else 15
                        print(f">> Attempting connection to {stream_name} at {stream_url}")
                        cap, success, message = connect_camera_with_timeout(stream_url, timeout=timeout_duration)
                        
                        if success and cap:
                            camera_caps[stream_id] = {
                                'cap': cap,
                                'name': stream_name,
                                'url': stream_url
                            }
                            success_msg = f'✅ Connected to "{stream_name}" ({i+1}/{len(active_streams)})'
                            print(f">> Connected to camera: {stream_name}")
                            socketio.emit('detection_status', {
                                'status': 'loading_streams', 
                                'message': success_msg
                            })
                        else:
                            error_msg = f'❌ {message} for "{stream_name}" ({i+1}/{len(active_streams)})'
                            print(f">> Failed to connect to {stream_name}: {message}")
                            socketio.emit('detection_status', {
                                'status': 'loading_streams', 
                                'message': error_msg
                            })
                            # Add a delay to let frontend show the error
                            time.sleep(1)
                    except Exception as e:
                        error_msg = f'❌ Error with "{stream_name}": {str(e)[:50]}...'
                        print(f">> Error connecting to {stream_name}: {e}")
                        socketio.emit('detection_status', {
                            'status': 'loading_streams', 
                            'message': error_msg
                        })
                        # Add a delay to let frontend show the error
                        time.sleep(1)
                    
                    # Small delay between connections
                    time.sleep(0.2)
                
                if not camera_caps:
                    error_message = 'No cameras could be connected. Please check your camera URLs and try again.'
                    print(f">> {error_message}")
                    socketio.emit('detection_error', {'error': error_message})
                    socketio.emit('detection_status', {'status': 'error', 'message': error_message})
                    return
                
                socketio.emit('detection_status', {
                    'status': 'running', 
                    'message': f'🎥 Monitoring {len(camera_caps)} camera{"s" if len(camera_caps) > 1 else ""}'
                })
                
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
                            print(f">> Lost connection to {stream_name}, attempting reconnect...")
                            # Try to reconnect
                            cap.release()
                            try:
                                new_cap = cv2.VideoCapture(stream_data['url'])
                                if new_cap.isOpened():
                                    ret, frame = new_cap.read()
                                    if ret:
                                        camera_caps[stream_id]['cap'] = new_cap
                                        print(f">> Reconnected to {stream_name}")
                                        # Store frame for live feed
                                        detection_frames[stream_id] = frame.copy()
                                    else:
                                        new_cap.release()
                                        print(f">> Reconnection failed for {stream_name}")
                                        continue
                                else:
                                    print(f">> Cannot reconnect to {stream_name}")
                                    continue
                            except Exception as e:
                                print(f">> Reconnection error for {stream_name}: {e}")
                                continue
                        else:
                            # Store frame for live feed
                            detection_frames[stream_id] = frame.copy()
                        
                        # Process every 5th frame to reduce CPU load
                        if frame_count % 5 != 0:
                            continue
                        
                        # Process frame for face detection
                        result = process_frame(frame, detector)
                        
                        # Store detection result for live feed
                        detection_results[stream_id] = result
                        
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

@app.route('/api/detection/feed/<int:stream_id>')
def detection_feed(stream_id):
    """Live detection video feed for a specific camera"""
    print(f">> Detection feed requested for stream {stream_id}")
    
    def generate():
        frame_count = 0
        while detection_running:
            frame_count += 1
            if stream_id in detection_frames:
                frame_data = detection_frames[stream_id]
                if frame_data is not None:
                    try:
                        # Draw detection boxes if available
                        frame = frame_data.copy()
                        if stream_id in detection_results:
                            result = detection_results[stream_id]
                            if result and result.get('detected'):
                                bbox = result.get('bbox')
                                name = result.get('name', 'Unknown')
                                confidence = result.get('confidence', 0.0)
                                
                                if bbox is not None:
                                    x1, y1, x2, y2 = bbox
                                    # Draw bounding box
                                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                    # Draw label
                                    label = f"{name} ({confidence:.1%})"
                                    cv2.putText(frame, label, (x1, y1-10), 
                                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        # Encode frame as JPEG
                        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        if ret:
                            frame_bytes = buffer.tobytes()
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                            
                            # Debug every 30 frames
                            if frame_count % 30 == 0:
                                print(f">> Streaming frame {frame_count} for stream {stream_id}")
                    except Exception as e:
                        print(f">> Error generating frame for stream {stream_id}: {e}")
            else:
                # No frame available yet, send a placeholder or wait
                if frame_count % 10 == 0:
                    print(f">> No frame available for stream {stream_id} (frame {frame_count})")
            
            time.sleep(0.1)  # Control frame rate
        
        print(f">> Detection feed ended for stream {stream_id}")
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/detection/status')
def detection_status():
    """Get current detection status"""
    return jsonify({
        'running': detection_running,
        'active_cameras': len(detection_frames),
        'recent_detections': len(detection_results)
    })

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
    socketio.run(app, debug=False, host='0.0.0.0', port=5001)
