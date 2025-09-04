# Face Recognition System

A web-based face recognition system using InsightFace AI and Flask.

## Features

- Real-time face detection and recognition
- Web-based interface for managing people and cameras
- RTSP camera support
- Detection history and gallery
- Real-time alerts

## Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the System**
   ```bash
   # Windows
   start.bat
   
   # Or manually
   cd webapp
   python start.py
   ```

3. **Access the Web Interface**
   - Open browser to: http://localhost:5000
   - Add people by uploading their photos
   - Configure camera streams
   - Start detection

## Project Structure

```
face_recognition/
├── requirements.txt          # Python dependencies
├── start.bat                # Quick start script
├── README.md                # This file
└── webapp/                  # Main application
    ├── app.py               # Flask web server
    ├── detector.py          # Face detection logic
    ├── face_db.py           # Face database management
    ├── start.py             # Application launcher
    ├── simple_face_recognition.db  # SQLite database
    ├── people/              # Training photos folder
    ├── embeddings/          # AI face embeddings
    ├── gallery/             # Detection photos
    └── templates/           # Web interface
        └── index.html       # Main dashboard
```

## Configuration

The system is self-contained in the `webapp/` directory. All data files (database, images, embeddings) are stored locally.

## Camera Setup

1. Add camera streams in the web interface
2. Supported formats:
   - RTSP streams (rtsp://...)
   - HTTP streams (http://...)
   - USB cameras (0, 1, 2...)

## Person Management

1. Click "Add Person" in the web interface
2. Upload 2-3 clear photos of the person
3. The system will automatically train the AI model
4. Person will be recognized in future detections

## Detection

1. Add people and cameras first
2. Click "Start Detection" 
3. View live feeds and detection results
4. Detection photos are saved in gallery/

## Troubleshooting

- Check console logs for detailed error messages
- Ensure camera URLs are accessible
- Verify Python dependencies are installed
- Check firewall settings for web access
