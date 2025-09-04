#!/usr/bin/env python3
"""
Clean startup script for Simplified Face Recognition System
"""
import os
import sys
import warnings
import logging
from io import StringIO

# Suppress warnings
warnings.filterwarnings("ignore")
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

def setup_logging():
    """Configure logging levels to reduce noise"""
    logging.getLogger('insightface').setLevel(logging.ERROR)
    logging.getLogger('onnxruntime').setLevel(logging.ERROR) 
    logging.getLogger('pygame').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.ERROR)
    logging.getLogger('engineio').setLevel(logging.INFO)
    logging.getLogger('socketio').setLevel(logging.INFO)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

def main():
    print(">> Simple Face Recognition System")
    print(">> Loading system...")
    
    setup_logging()
    
    # Temporarily capture output during imports
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    
    try:
        sys.stdout = StringIO()
        sys.stderr = StringIO()
        
        from app import initialize_app, socketio, app
        
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    
    print(">> Ready!")
    print(">> Web interface: http://localhost:5000")
    
    # Get local IP
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        print(f">> Network access: http://{local_ip}:5000")
    except:
        print(">> Network access: http://localhost:5000")
    
    print(">> Press CTRL+C to stop\n")
    
    try:
        initialize_app()
        socketio.run(app, debug=False, host='0.0.0.0', port=5000, log_output=False)
    except KeyboardInterrupt:
        print("\n>> Face Recognition System stopped")
    except Exception as e:
        print(f">> Error: {e}")

if __name__ == '__main__':
    main()
