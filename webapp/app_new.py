"""
Face Recognition System — FastAPI
Replaces Flask + Flask-SocketIO + pygame.
Same API surface and same Socket.IO event names — frontend works unchanged.

Architecture:
  - FastAPI (async HTTP) + python-socketio ASGI (WebSocket)
  - Per-camera daemon threads: frame capture + ONNX inference (GIL released during inference)
  - asyncio.Queue bridges threads → async broadcast loop (no polling)
  - FAISS index for O(log n) embedding search (numpy fallback if faiss not installed)
  - SQLite for dev storage (swap _db() connection string for PostgreSQL in production)
  - No pygame — alerts are pure WebSocket push to all connected dashboards
"""
import os
import sys
import re
import base64
import sqlite3
import json
import shutil
import threading
import asyncio
import time
import warnings
import logging
import concurrent.futures
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import pytz

warnings.filterwarnings("ignore", category=UserWarning)
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
logging.getLogger('onnxruntime').setLevel(logging.ERROR)
logging.getLogger('insightface').setLevel(logging.ERROR)

import socketio
from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ─── Constants ────────────────────────────────────────────────────────────────
DB_PATH          = 'simple_face_recognition.db'
GALLERY_FOLDER   = 'gallery'
PEOPLE_FOLDER    = 'people'
EMBEDDINGS_FOLDER = 'embeddings'
FACE_DB_PATH     = os.path.join(EMBEDDINGS_FOLDER, 'face_db.pkl')
LOCAL_TIMEZONE   = pytz.timezone('Asia/Kolkata')
ALERT_THRESHOLD  = 0.55   # min confidence to fire alert  (SOFT tier)

for _d in [GALLERY_FOLDER, PEOPLE_FOLDER, EMBEDDINGS_FOLDER]:
    os.makedirs(_d, exist_ok=True)

# ─── Socket.IO + FastAPI bootstrap ───────────────────────────────────────────
sio = socketio.AsyncServer(
    async_mode='asgi', cors_allowed_origins='*',
    logger=False, engineio_logger=False
)

@asynccontextmanager
async def lifespan(fapp: FastAPI):
    global _main_loop
    _main_loop = asyncio.get_event_loop()
    _init_database()
    print(">> Face Recognition System ready")
    yield

fastapi_app = FastAPI(lifespan=lifespan)
# ASGI entry-point (used by uvicorn): socketio wraps fastapi
app = socketio.ASGIApp(sio, fastapi_app)

fastapi_app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ─── Optional enhanced camera module ─────────────────────────────────────────
USE_ENHANCED_FEATURES = False
camera_manager    = None
hardware_optimizer = None

try:
    from camera_api import router as camera_router
    from camera_manager import camera_manager as _cm, hardware_optimizer as _ho
    camera_manager    = _cm
    hardware_optimizer = _ho
    fastapi_app.include_router(camera_router)
    USE_ENHANCED_FEATURES = True
    print(">> Enhanced camera features loaded")
except ImportError as e:
    print(f">> Enhanced features not available: {e}")

# ─── Detector ─────────────────────────────────────────────────────────────────
try:
    from enhanced_detector import OptimizedFaceDetector, initialize_detector
    _USE_ENHANCED_DETECTOR = True
    print(">> Enhanced detector (antelopev2) loaded")
except ImportError:
    from detector import initialize_detector
    _USE_ENHANCED_DETECTOR = False
    print(">> Basic detector loaded")

def _process_frame(frame, detector):
    """Unified frame processor — uses enhanced or basic detector."""
    if hasattr(detector, 'process_frame_optimized'):
        return detector.process_frame_optimized(frame)
    # basic detector fallback
    from detector import process_frame
    return process_frame(frame, detector)

# ─── Detection state ─────────────────────────────────────────────────────────
detection_running: bool   = False
detection_frames:  dict   = {}   # stream_id → latest np.ndarray (atomic dict write, GIL-safe)
detection_results: dict   = {}   # stream_id → latest result dict
recent_alerts:     list   = []
_detection_task: Optional[asyncio.Task] = None
_main_loop: Optional[asyncio.AbstractEventLoop] = None

# ─── Database ─────────────────────────────────────────────────────────────────
@contextmanager
def _db():
    """SQLite context manager. Replace sqlite3.connect() with psycopg2/asyncpg for PostgreSQL."""
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _init_database():
    with _db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS streams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url  TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_name   TEXT,
            confidence    REAL,
            camera_source TEXT,
            detection_time TIMESTAMP,
            detection_image TEXT)''')

# ─── Camera connection ────────────────────────────────────────────────────────
def _connect_camera(stream_url, timeout=15):
    """Connect to any camera type with timeout and RTSP retry logic."""
    def _try():
        camera_url = stream_url
        if isinstance(stream_url, str) and stream_url.isdigit():
            camera_url = int(stream_url)

        if isinstance(stream_url, str) and 'rtsp://' in stream_url.lower():
            configs = [
                (f"{stream_url}?tcp=1&timeout=3",         cv2.CAP_FFMPEG),
                (f"{stream_url}?buffer_size=0&timeout=3", cv2.CAP_FFMPEG),
                (stream_url,                               cv2.CAP_FFMPEG),
            ]
            for url, backend in configs:
                cap = cv2.VideoCapture(url, backend)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if not cap.isOpened():
                    continue
                result = {'ret': False, 'frame': None, 'done': False}
                def _read():
                    r, f = cap.read()
                    result.update({'ret': r, 'frame': f, 'done': True})
                t = threading.Thread(target=_read, daemon=True)
                t.start(); t.join(3.0)
                if result['done'] and result['ret'] and result['frame'] is not None:
                    return cap, True, "RTSP connected"
                cap.release()
            return None, False, "All RTSP attempts failed"

        cap = cv2.VideoCapture(camera_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                return cap, True, "Connected"
            cap.release()
        return None, False, f"Cannot open camera: {stream_url}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(_try)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return None, False, f"Timeout after {timeout}s"

# ─── Helpers ──────────────────────────────────────────────────────────────────
def _fmt_ts(utc_timestamp=None):
    try:
        if utc_timestamp is None:
            dt = datetime.now(LOCAL_TIMEZONE)
        elif isinstance(utc_timestamp, str):
            dt = datetime.fromisoformat(utc_timestamp.replace('Z', '+00:00'))
            dt = dt.replace(tzinfo=pytz.UTC).astimezone(LOCAL_TIMEZONE)
        else:
            dt = utc_timestamp.replace(tzinfo=pytz.UTC).astimezone(LOCAL_TIMEZONE)
    except Exception:
        dt = datetime.now(LOCAL_TIMEZONE)
    return {
        'date':          dt.strftime('%Y-%m-%d'),
        'time':          dt.strftime('%I:%M:%S %p'),
        'datetime':      dt.strftime('%Y-%m-%d %I:%M:%S %p'),
        'filename_time': dt.strftime('%I-%M-%S_%p'),
        'folder_date':   dt.strftime('%Y-%m-%d'),
        'timestamp':     dt.isoformat(),
    }

def _save_detection_image(image, person_name, ts):
    try:
        folder = os.path.join(GALLERY_FOLDER, ts['folder_date'])
        os.makedirs(folder, exist_ok=True)
        safe = re.sub(r'[^\w\s\-]', '', person_name).strip()
        path = os.path.join(folder, f"{ts['filename_time']}_{safe}.jpg")
        if isinstance(image, np.ndarray):
            cv2.imwrite(path, image)
        else:
            Path(path).write_bytes(image)
        return path
    except Exception as e:
        print(f">> save_detection_image error: {e}")
        return None

def _rebuild_face_db():
    try:
        from face_db import build_face_embeddings
        build_face_embeddings()
        return True
    except Exception as e:
        print(f">> Error rebuilding face DB: {e}")
        return False

def _write_detection_db(person_name, confidence, source, ts, image_path):
    with _db() as conn:
        conn.execute(
            '''INSERT INTO detections
               (person_name, confidence, camera_source, detection_time, detection_image)
               VALUES (?, ?, ?, ?, ?)''',
            (person_name, confidence, source, ts['timestamp'], image_path)
        )

async def _broadcast_alert(person_name, confidence, camera_source, image_path, tier):
    ts = _fmt_ts()
    alert = {
        'person':          person_name,
        'confidence':      f"{confidence:.1%}",
        'raw_confidence':  confidence,
        'tier':            tier,
        'camera':          camera_source,
        'timestamp':       ts['timestamp'],
        'image':           image_path or '',
        'message':         f"🚨 [{tier}] {person_name} — {confidence:.1%} on {camera_source}",
    }
    recent_alerts.insert(0, alert)
    if len(recent_alerts) > 50:
        recent_alerts.pop()
    await sio.emit('detection_alert', alert)

# ─── Per-camera worker thread ─────────────────────────────────────────────────
def _camera_thread(stream_id, stream_name, stream_url,
                   detector, result_queue, loop, stop_evt):
    """
    One thread per camera stream.
    ONNX Runtime releases the GIL during inference → real parallel execution
    across multiple cameras on multi-core hardware / GPU.
    Results are pushed to an asyncio.Queue via loop.call_soon_threadsafe (thread-safe).
    """
    cap, success, msg = _connect_camera(stream_url, timeout=30)
    if not success:
        print(f">> Camera '{stream_name}': {msg}")
        loop.call_soon_threadsafe(
            result_queue.put_nowait,
            {'type': 'camera_error', 'stream_name': stream_name, 'error': msg}
        )
        return

    print(f">> Camera '{stream_name}' connected")
    loop.call_soon_threadsafe(
        result_queue.put_nowait,
        {'type': 'camera_connected', 'stream_name': stream_name}
    )

    is_rtsp = isinstance(stream_url, str) and 'rtsp://' in stream_url.lower()
    frame_count        = 0
    consecutive_fails  = 0
    PROCESS_EVERY      = 5     # run detection every Nth frame (reduces CPU load)

    try:
        while not stop_evt.is_set():
            # RTSP: flush stale buffer frames before reading the live one
            if is_rtsp:
                for _ in range(2):
                    cap.read()

            ret, frame = cap.read()

            if not ret or frame is None:
                consecutive_fails += 1
                if consecutive_fails > 10:
                    print(f">> '{stream_name}' reconnecting…")
                    cap.release()
                    cap, ok, msg2 = _connect_camera(stream_url, timeout=30)
                    if not ok:
                        print(f">> '{stream_name}' reconnect failed: {msg2}")
                        break
                    consecutive_fails = 0
                time.sleep(0.05)
                continue

            consecutive_fails = 0
            detection_frames[stream_id] = frame   # atomic dict write (GIL-protected)

            frame_count += 1
            if frame_count % PROCESS_EVERY != 0:
                continue

            # --- Inference (GIL released by ONNX Runtime) ---
            result = _process_frame(frame, detector)
            detection_results[stream_id] = result

            if not (result and result.get('detected')):
                continue

            for face in result.get('faces', [result.get('primary_face')] if result.get('primary_face') else []):
                if not face:
                    continue
                confidence = face.get('confidence', 0.0)
                name       = face.get('name', 'Unknown')
                tier       = face.get('match_tier', 'NONE')

                if tier in ('HIGH', 'SOFT') and name != 'Unknown':
                    loop.call_soon_threadsafe(
                        result_queue.put_nowait,
                        {
                            'type':        'detection',
                            'stream_id':   stream_id,
                            'stream_name': stream_name,
                            'person_name': name,
                            'confidence':  confidence,
                            'tier':        tier,
                            'face_image':  face.get('face_image'),
                            'bbox':        face.get('bbox'),
                        }
                    )
    finally:
        cap.release()
        print(f">> Camera thread '{stream_name}' exited")


# ─── Async detection orchestrator ────────────────────────────────────────────
async def _detection_main(streams):
    """
    Loads the detector, spawns per-camera threads, collects results
    from asyncio.Queue, persists to DB, and broadcasts via WebSocket.
    """
    global detection_running

    await sio.emit('detection_status', {'status': 'loading_detector',
                                         'message': 'Loading face detector (antelopev2)…'})
    try:
        detector = await asyncio.to_thread(initialize_detector)
    except Exception as e:
        await sio.emit('detection_error', {'error': f'Detector init failed: {e}'})
        detection_running = False
        return

    if not detector:
        await sio.emit('detection_error', {'error': 'Detector returned None'})
        detection_running = False
        return

    result_queue = asyncio.Queue()
    stop_evt     = threading.Event()
    loop         = asyncio.get_event_loop()

    await sio.emit('detection_status', {
        'status': 'connecting_cameras',
        'message': f'Connecting to {len(streams)} camera(s)…'
    })

    threads = []
    for stream_id, name, url in streams:
        t = threading.Thread(
            target=_camera_thread,
            args=(stream_id, name, url, detector, result_queue, loop, stop_evt),
            daemon=True,
        )
        t.start()
        threads.append(t)

    await sio.emit('detection_status', {
        'status': 'running',
        'message': f'🎥 Monitoring {len(threads)} camera(s)'
    })

    # ── Result broadcast loop ──────────────────────────────────────────────
    while detection_running:
        try:
            hit = await asyncio.wait_for(result_queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue

        msg_type = hit.get('type', 'detection')

        if msg_type == 'camera_error':
            await sio.emit('detection_status', {
                'status': 'warning',
                'message': f"⚠️ Camera '{hit['stream_name']}': {hit['error']}"
            })
            continue

        if msg_type == 'camera_connected':
            await sio.emit('detection_status', {
                'status': 'info',
                'message': f"✅ Camera '{hit['stream_name']}' live"
            })
            continue

        # Actual detection hit
        person_name = hit['person_name']
        confidence  = hit['confidence']
        stream_name = hit['stream_name']
        tier        = hit['tier']
        face_image  = hit.get('face_image')

        ts = _fmt_ts()
        image_path = None
        if face_image is not None:
            image_path = await asyncio.to_thread(
                _save_detection_image, face_image, person_name, ts
            )

        await asyncio.to_thread(
            _write_detection_db, person_name, confidence, stream_name, ts, image_path
        )
        await _broadcast_alert(person_name, confidence, stream_name, image_path, tier)
        print(f">> [{tier}] {person_name} ({confidence:.1%}) on {stream_name}")

    # Teardown
    stop_evt.set()
    await sio.emit('detection_status', {'status': 'stopped', 'message': 'Detection stopped'})


# ═══════════════════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════════════════

@fastapi_app.get('/')
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── Detections / Gallery ──────────────────────────────────────────────────────
@fastapi_app.get('/api/detections')
async def get_detections():
    try:
        with _db() as conn:
            rows = conn.execute('''
                SELECT id, person_name, confidence, camera_source, detection_time, detection_image
                FROM detections ORDER BY detection_time DESC LIMIT 100
            ''').fetchall()
        detections = [
            {'id': r[0], 'person_name': r[1], 'confidence': float(r[2] or 0),
             'camera_source': r[3], 'detection_time': r[4], 'detection_image': r[5]}
            for r in rows
        ]
        return JSONResponse({'success': True, 'detections': detections})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e), 'detections': []})


@fastapi_app.get('/api/gallery/dates')
async def get_gallery_dates():
    try:
        dates = []
        if os.path.exists(GALLERY_FOLDER):
            for item in os.listdir(GALLERY_FOLDER):
                dp = os.path.join(GALLERY_FOLDER, item)
                if os.path.isdir(dp) and re.match(r'\d{4}-\d{2}-\d{2}', item):
                    count = len([f for f in os.listdir(dp) if f.lower().endswith(('.jpg', '.png'))])
                    dates.append({
                        'date': item, 'image_count': count,
                        'formatted_date': datetime.strptime(item, '%Y-%m-%d').strftime('%d %B %Y')
                    })
        dates.sort(key=lambda x: x['date'], reverse=True)
        return JSONResponse({'success': True, 'dates': dates})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e), 'dates': []})


@fastapi_app.get('/api/gallery/images/{date}')
async def get_gallery_images(date: str):
    try:
        folder = os.path.join(GALLERY_FOLDER, date)
        images = []
        if os.path.exists(folder):
            for fn in os.listdir(folder):
                if fn.lower().endswith(('.jpg', '.jpeg', '.png')):
                    fp   = os.path.join(folder, fn)
                    base = fn.rsplit('.', 1)[0]
                    parts = base.split('_')
                    person = '_'.join(parts[2:]) if len(parts) > 2 else 'Unknown'
                    images.append({
                        'filename':    fn,
                        'person_name': person,
                        'time':        f"{parts[0]} {parts[1]}".replace('-', ':') if len(parts) > 1 else '',
                        'path':        f'/api/gallery/image/{date}/{fn}',
                        'timestamp':   os.path.getmtime(fp),
                    })
        images.sort(key=lambda x: x['timestamp'], reverse=True)
        return JSONResponse({'success': True, 'images': images})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e), 'images': []})


@fastapi_app.get('/api/gallery/image/{date}/{filename}')
async def get_gallery_image(date: str, filename: str):
    # Security: block path traversal
    if '..' in filename or filename.startswith('/'):
        return JSONResponse({'error': 'Invalid path'}, status_code=400)
    path = os.path.join(GALLERY_FOLDER, date, filename)
    if os.path.exists(path):
        return FileResponse(path)
    return JSONResponse({'error': 'Not found'}, status_code=404)


# ── Camera ────────────────────────────────────────────────────────────────────
@fastapi_app.get('/api/camera/detect')
async def detect_cameras_basic():
    try:
        if USE_ENHANCED_FEATURES:
            cameras = await asyncio.to_thread(camera_manager.detect_available_cameras)
            return JSONResponse({'success': True, 'cameras': cameras, 'total_detected': len(cameras)})
        cameras = []
        for i in range(5):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ret, frm = cap.read()
                if ret and frm is not None:
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    cameras.append({
                        'id': f'camera_{i}',
                        'name': 'Built-in Camera' if i == 0 else f'Camera {i}',
                        'url': str(i), 'type': 'builtin' if i == 0 else 'usb',
                        'resolution': f'{w}x{h}', 'status': 'available'
                    })
            cap.release()
        return JSONResponse({'success': True, 'cameras': cameras, 'total_detected': len(cameras)})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e), 'cameras': [], 'total_detected': 0})


@fastapi_app.post('/api/camera/test')
async def test_camera(request: Request):
    try:
        data = await request.json()
        url  = data.get('url', '')
        if not url:
            return JSONResponse({'success': False, 'error': 'Camera URL is required'})
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            return JSONResponse({'success': False, 'error': 'Unable to connect to camera'})
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return JSONResponse({'success': False, 'error': 'Unable to read frame'})
        h, w = frame.shape[:2]
        if w > 640:
            frame = cv2.resize(frame, (640, int(h * 640 / w)))
        _, buf = cv2.imencode('.jpg', frame)
        preview = f"data:image/jpeg;base64,{base64.b64encode(buf).decode()}"
        return JSONResponse({'success': True, 'message': 'Camera test successful', 'preview': preview})
    except Exception as e:
        return JSONResponse({'success': False, 'error': f'Camera test failed: {str(e)}'})


def _mjpeg_generator(camera_url: str):
    """Synchronous MJPEG generator (runs in threadpool via StreamingResponse)."""
    cap = cv2.VideoCapture(camera_url)
    if not cap.isOpened():
        return
    is_rtsp = isinstance(camera_url, str) and 'rtsp://' in camera_url.lower()
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    skip = 4 if is_rtsp else 2
    i = 0
    try:
        while True:
            if is_rtsp:
                for _ in range(2):
                    cap.read()
            ret, frame = cap.read()
            if not ret:
                break
            i += 1
            if i % skip != 0:
                continue
            tw = 320 if is_rtsp else 480
            h, w = frame.shape[:2]
            if w > tw:
                frame = cv2.resize(frame, (tw, int(h * tw / w)), interpolation=cv2.INTER_AREA)
            q = 50 if is_rtsp else 65
            ret2, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, q])
            if ret2:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n'
            time.sleep(0.05 if is_rtsp else 0.03)
    finally:
        cap.release()


@fastapi_app.get('/api/camera/stream/{stream_id}')
async def video_stream(stream_id: int):
    with _db() as conn:
        row = conn.execute(
            'SELECT url FROM streams WHERE id = ? AND active = 1', (stream_id,)
        ).fetchone()
    if not row:
        return JSONResponse({'error': 'Not found'}, status_code=404)
    return StreamingResponse(
        _mjpeg_generator(row[0]),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )


@fastapi_app.get('/api/camera/stream_url')
async def video_stream_by_url(request: Request):
    url = request.query_params.get('url', '')
    if not url:
        return JSONResponse({'error': 'URL required'}, status_code=400)
    return StreamingResponse(
        _mjpeg_generator(url),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )


@fastapi_app.get('/api/camera/preview')
async def camera_preview(request: Request):
    camera_url  = request.query_params.get('url', '')
    camera_name = request.query_params.get('name', 'Camera')
    if not camera_url:
        return HTMLResponse("Camera URL required", status_code=400)
    html = f"""<!DOCTYPE html><html><head><title>Camera Test — {camera_name}</title>
    <style>body{{background:#0f172a;color:white;font-family:Arial;margin:0;padding:20px;min-height:100vh;}}
    .spinner{{width:50px;height:50px;border:4px solid #334155;border-top:4px solid #3b82f6;
    border-radius:50%;animation:spin 1s linear infinite;margin:40px auto;}}
    @keyframes spin{{to{{transform:rotate(360deg);}}}}
    img{{max-width:100%;border-radius:8px;}}
    button{{padding:10px 24px;background:#ef4444;color:white;border:none;
    border-radius:6px;cursor:pointer;font-size:16px;margin-top:16px;}}
    </style></head><body>
    <h1>📹 {camera_name}</h1>
    <div id="v"><div class="spinner"></div></div>
    <button onclick="window.close()">Close</button>
    <script>
    var img=new Image();img.style.maxWidth='100%';
    img.onload=function(){{document.getElementById('v').innerHTML='';document.getElementById('v').appendChild(img);}};
    img.onerror=function(){{document.getElementById('v').innerHTML='<p style="color:#f87171">Stream failed — check camera URL</p>';}};
    img.src='/api/camera/stream_url?url={camera_url}&t='+Date.now();
    </script></body></html>"""
    return HTMLResponse(html)


# ── Streams ───────────────────────────────────────────────────────────────────
@fastapi_app.get('/api/streams')
async def get_streams():
    try:
        with _db() as conn:
            rows = conn.execute('SELECT id, name, url, active FROM streams').fetchall()
        return JSONResponse({
            'success': True,
            'streams': [{'id': r[0], 'name': r[1], 'url': r[2], 'active': bool(r[3])} for r in rows]
        })
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e), 'streams': []})


@fastapi_app.post('/api/streams')
async def add_stream(request: Request):
    try:
        data = await request.json()
        name = data.get('name', '').strip()
        url  = data.get('url', '').strip()
        if not name or not url:
            return JSONResponse({'success': False, 'error': 'Name and URL are required'})
        with _db() as conn:
            if conn.execute('SELECT id FROM streams WHERE url = ?', (url,)).fetchone():
                return JSONResponse({'success': False, 'error': 'A stream with this URL already exists'})
            if conn.execute('SELECT id FROM streams WHERE name = ?', (name,)).fetchone():
                return JSONResponse({'success': False, 'error': f'Name "{name}" already exists'})
            conn.execute('INSERT INTO streams (name, url, active) VALUES (?, ?, 1)', (name, url))
        return JSONResponse({'success': True, 'message': 'Camera stream added successfully'})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)})


@fastapi_app.delete('/api/streams/{stream_id}')
async def delete_stream(stream_id: int):
    try:
        with _db() as conn:
            n = conn.execute('DELETE FROM streams WHERE id = ?', (stream_id,)).rowcount
        if n:
            return JSONResponse({'success': True, 'message': 'Stream deleted'})
        return JSONResponse({'success': False, 'error': 'Stream not found'})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)})


# ── People ────────────────────────────────────────────────────────────────────
@fastapi_app.get('/api/people')
async def get_people():
    try:
        with _db() as conn:
            rows = conn.execute('SELECT id, name, created_at FROM people ORDER BY name').fetchall()
        people = []
        for pid, name, created_at in rows:
            folder = os.path.join(PEOPLE_FOLDER, name)
            count  = len([f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.png'))]) \
                     if os.path.exists(folder) else 0
            people.append({'id': pid, 'name': name, 'created_at': created_at, 'image_count': count})
        return JSONResponse({'success': True, 'people': people})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e), 'people': []})


@fastapi_app.post('/api/people/add')
async def add_person(request: Request):
    try:
        form = await request.form()
        name = form.get('name', '').strip()
        if not name:
            return JSONResponse({'success': False, 'error': 'Name is required'})

        image_files = [v for k, v in form.multi_items()
                       if k.startswith('image_') and hasattr(v, 'filename') and v.filename]
        if not image_files:
            return JSONResponse({'success': False, 'error': 'At least one image is required'})

        with _db() as conn:
            try:
                conn.execute('INSERT INTO people (name) VALUES (?)', (name,))
                person_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            except Exception:
                return JSONResponse({'success': False, 'error': f'Person "{name}" already exists'})

        folder = os.path.join(PEOPLE_FOLDER, name)
        os.makedirs(folder, exist_ok=True)
        saved = 0
        for i, f in enumerate(image_files):
            content = await f.read()
            with open(os.path.join(folder, f'image_{i + 1}.jpg'), 'wb') as out:
                out.write(content)
            saved += 1

        await asyncio.to_thread(_rebuild_face_db)
        return JSONResponse({
            'success': True, 'message': f'{name} added successfully',
            'person_id': person_id, 'saved_files': saved
        })
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)})


@fastapi_app.delete('/api/people/{person_id}')
async def delete_person(person_id: int):
    try:
        with _db() as conn:
            row = conn.execute('SELECT name FROM people WHERE id = ?', (person_id,)).fetchone()
            if not row:
                return JSONResponse({'success': False, 'error': 'Person not found'})
            name = row[0]
            conn.execute('DELETE FROM people WHERE id = ?', (person_id,))
            conn.execute('DELETE FROM detections WHERE person_name = ?', (name,))
        folder = os.path.join(PEOPLE_FOLDER, name)
        if os.path.exists(folder):
            shutil.rmtree(folder)
        await asyncio.to_thread(_rebuild_face_db)
        return JSONResponse({'success': True, 'message': f'{name} deleted'})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)})


@fastapi_app.put('/api/people/{person_id}')
async def edit_person(person_id: int, request: Request):
    try:
        form     = await request.form()
        new_name = form.get('name', '').strip()
        if not new_name:
            return JSONResponse({'success': False, 'error': 'Name is required'})

        with _db() as conn:
            row = conn.execute('SELECT name FROM people WHERE id = ?', (person_id,)).fetchone()
            if not row:
                return JSONResponse({'success': False, 'error': 'Person not found'})
            old_name = row[0]
            if new_name != old_name:
                if conn.execute(
                    'SELECT id FROM people WHERE name = ? AND id != ?', (new_name, person_id)
                ).fetchone():
                    return JSONResponse({'success': False, 'error': f'"{new_name}" already exists'})
            conn.execute('UPDATE people SET name = ? WHERE id = ?', (new_name, person_id))
            conn.execute('UPDATE detections SET person_name = ? WHERE person_name = ?',
                         (new_name, old_name))

        old_folder = os.path.join(PEOPLE_FOLDER, old_name)
        new_folder = os.path.join(PEOPLE_FOLDER, new_name)
        if old_name != new_name and os.path.exists(old_folder):
            os.rename(old_folder, new_folder)

        remove_json = form.get('remove_images')
        if remove_json:
            for fn in json.loads(remove_json):
                p = os.path.join(new_folder, fn)
                if os.path.exists(p):
                    os.remove(p)

        new_files = [v for k, v in form.multi_items()
                     if k.startswith('image_') and hasattr(v, 'filename') and v.filename]
        existing  = len([f for f in os.listdir(new_folder)
                         if f.lower().endswith(('.jpg', '.png'))]) if os.path.exists(new_folder) else 0
        for i, f in enumerate(new_files):
            content = await f.read()
            with open(os.path.join(new_folder, f'image_{existing + i + 1}.jpg'), 'wb') as out:
                out.write(content)

        await asyncio.to_thread(_rebuild_face_db)
        return JSONResponse({'success': True, 'message': 'Updated', 'new_name': new_name})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e)})


@fastapi_app.get('/api/people/{person_id}/image')
async def get_person_image(person_id: int):
    with _db() as conn:
        row = conn.execute('SELECT name FROM people WHERE id = ?', (person_id,)).fetchone()
    if not row:
        return JSONResponse({'error': 'Not found'}, status_code=404)
    folder = os.path.join(PEOPLE_FOLDER, row[0])
    if os.path.exists(folder):
        for fn in sorted(os.listdir(folder)):
            if fn.lower().endswith(('.jpg', '.png', '.jpeg')):
                return FileResponse(os.path.join(folder, fn), media_type='image/jpeg')
    return JSONResponse({'error': 'No image'}, status_code=404)


@fastapi_app.get('/api/people/{person_id}/images')
async def get_person_images(person_id: int):
    with _db() as conn:
        row = conn.execute('SELECT name FROM people WHERE id = ?', (person_id,)).fetchone()
    if not row:
        return JSONResponse({'error': 'Not found'}, status_code=404)
    folder = os.path.join(PEOPLE_FOLDER, row[0])
    imgs = []
    if os.path.exists(folder):
        for fn in sorted(os.listdir(folder)):
            if fn.lower().endswith(('.jpg', '.png', '.jpeg')):
                imgs.append({'filename': fn, 'url': f'/api/people/{person_id}/images/{fn}'})
    return JSONResponse({'success': True, 'images': imgs})


@fastapi_app.get('/api/people/{person_id}/images/{filename}')
async def get_person_image_file(person_id: int, filename: str):
    if '..' in filename or filename.startswith('/'):
        return JSONResponse({'error': 'Invalid filename'}, status_code=400)
    with _db() as conn:
        row = conn.execute('SELECT name FROM people WHERE id = ?', (person_id,)).fetchone()
    if not row:
        return JSONResponse({'error': 'Not found'}, status_code=404)
    path = os.path.join(PEOPLE_FOLDER, row[0], filename)
    if os.path.exists(path) and filename.lower().endswith(('.jpg', '.png', '.jpeg')):
        return FileResponse(path, media_type='image/jpeg')
    return JSONResponse({'error': 'Not found'}, status_code=404)


# ── Detection control ─────────────────────────────────────────────────────────
@fastapi_app.post('/api/detection/start')
async def start_detection():
    global detection_running, _detection_task
    if detection_running:
        return JSONResponse({'success': False, 'error': 'Detection already running'})

    with _db() as conn:
        people_count = conn.execute('SELECT COUNT(*) FROM people').fetchone()[0]
        streams      = conn.execute(
            'SELECT id, name, url FROM streams WHERE active = 1'
        ).fetchall()

    if people_count == 0:
        return JSONResponse({'success': False, 'error': 'No people added yet. Add at least one person.'})
    if not streams:
        return JSONResponse({'success': False, 'error': 'No camera streams configured.'})

    if not os.path.exists(FACE_DB_PATH):
        await asyncio.to_thread(_rebuild_face_db)

    detection_running = True
    await sio.emit('detection_status', {'status': 'starting', 'message': 'Initialising…'})
    _detection_task = asyncio.create_task(_detection_main(list(streams)))
    return JSONResponse({'success': True, 'message': 'Detection started'})


@fastapi_app.post('/api/detection/stop')
async def stop_detection():
    global detection_running, _detection_task
    detection_running = False
    if _detection_task:
        _detection_task.cancel()
        _detection_task = None
    await sio.emit('detection_status', {'status': 'stopped', 'message': 'Detection stopped'})
    return JSONResponse({'success': True, 'message': 'Detection stopped'})


@fastapi_app.get('/api/detection/status')
async def detection_status_endpoint():
    return JSONResponse({
        'running':            detection_running,
        'active_cameras':     len(detection_frames),
        'recent_detections':  len(detection_results),
    })


@fastapi_app.get('/api/detection/feed/{stream_id}')
async def detection_feed(stream_id: int):
    """Async MJPEG feed with bounding-box overlays drawn by tier colour."""
    async def generate():
        while detection_running:
            raw = detection_frames.get(stream_id)
            if raw is not None:
                frame  = raw.copy()
                result = detection_results.get(stream_id)
                if result and result.get('detected'):
                    for face in result.get('faces', []):
                        bbox = face.get('bbox')
                        name = face.get('name', 'Unknown')
                        conf = face.get('confidence', 0.0)
                        tier = face.get('match_tier', '')
                        if bbox:
                            x1, y1, x2, y2 = bbox
                            colour = (0, 255, 0) if tier == 'HIGH' else \
                                     (0, 165, 255) if tier == 'SOFT' else (128, 128, 128)
                            cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 2)
                            cv2.putText(frame, f"{name} {conf:.0%}",
                                        (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2)
                ret2, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret2:
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                           + buf.tobytes() + b'\r\n')
            await asyncio.sleep(0.1)

    return StreamingResponse(generate(), media_type='multipart/x-mixed-replace; boundary=frame')


@fastapi_app.get('/api/alerts/recent')
async def get_recent_alerts():
    return JSONResponse({'success': True, 'alerts': recent_alerts})


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    print(f">> Starting Face Recognition on http://0.0.0.0:{port}")
    uvicorn.run(app, host='0.0.0.0', port=port, log_level='warning')
