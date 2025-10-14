# Face Recognition System

A web-based face recognition system using InsightFace AI and Flask with enhanced camera detection and hardware optimization.

## ✨ Enhanced Features

- 🎯 **Real-time face detection and recognition**
- 📹 **Smart camera detection** - Automatically finds available cameras
- 💻 **Cross-platform support** - macOS, Windows, Linux
- 🚀 **Hardware acceleration** - Apple Silicon, CUDA GPU optimization
- 🌐 **Web-based interface** for managing people and cameras
- 📡 **Multiple camera types** - Built-in, USB, RTSP, HTTP streams
- 📊 **Detection history and gallery**
- 🔔 **Real-time alerts and notifications**

## 🚀 Quick Start

### Easy Launch (Recommended)

```bash
# Clone and navigate to project
cd face_recogniation

# Start everything with one command
python start.py
```

The launcher will:
- ✅ Check system dependencies
- 📦 Install missing packages (with `--install-deps`)
- 🔍 Detect available cameras
- 🌐 Start web server
- 🌍 Open browser automatically

### Alternative Start Options

```bash
# Check system status only
python start.py --check

# Install dependencies automatically
python start.py --install-deps

# Custom port and host
python start.py --port 8080 --host 0.0.0.0

# Debug mode
python start.py --debug

# Windows quick start
start.bat
```

### Manual Setup (if needed)

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the System**
   ```bash
   cd webapp
   python app.py
   ```

3. **Access the Web Interface**
   - 🌐 **URL**: http://localhost:5001
   - 👥 Add people by uploading their photos
   - 📹 Configure camera streams with auto-detection
   - ▶️ Start detection

## 📁 Project Structure

```
face_recogniation/
├── start.py                 # 🚀 Main launcher script
├── requirements.txt         # 📦 Python dependencies  
├── start.bat               # 🪟 Windows quick start
├── README.md               # 📖 Documentation
└── webapp/                 # 🎯 Main application
    ├── app.py              # 🌐 Flask web server
    ├── detector.py         # 👁️ Face detection logic
    ├── enhanced_detector.py # 🚀 Hardware-optimized detection
    ├── camera_manager.py   # 📹 Smart camera detection
    ├── camera_api.py       # 🔌 Camera API endpoints
    ├── face_db.py          # 💾 Face database management
    ├── simple_face_recognition.db # 🗄️ SQLite database
    ├── people/             # 👥 Training photos folder
    ├── embeddings/         # 🧠 AI face embeddings
    ├── gallery/            # 📸 Detection photos
    ├── static/             # 🎨 CSS, JS, images
    └── templates/          # 🖥️ Web interface
        └── index.html      # 📱 Enhanced dashboard
```

## 🎯 Enhanced Camera Setup

### Automatic Detection
1. Click "Add Camera" in the web interface
2. Click "Scan Cameras" button
3. Select from detected cameras dropdown
4. System automatically configures optimal settings

### Supported Camera Types
- **Built-in cameras** (FaceTime, Integrated Camera)
- **USB cameras** (External webcams)
- **RTSP streams** (IP cameras: `rtsp://user:pass@ip:port/stream`)
- **HTTP streams** (Web cameras: `http://ip:port/video`)
- **Camera indices** (Direct access: `0`, `1`, `2`...)

### Platform-Specific Support
- **🍎 macOS**: AVFoundation backend, Apple Silicon optimization
- **🪟 Windows**: DirectShow and Media Foundation backends
- **🐧 Linux**: V4L2 backend support

## 👥 Person Management

1. Go to "Add People" tab
2. Click "Add Person" 
3. Enter person's name
4. Upload 2-3 clear photos
5. Add custom fields (optional)
6. System trains AI model automatically
7. Person will be recognized in future detections

## 🔍 Detection Process

1. **Setup**: Add people and cameras
2. **Start**: Click "Start Detection" button
3. **Monitor**: View live feeds with face boxes
4. **Gallery**: Detection photos saved automatically
5. **History**: Track all detection events

## 🛠️ System Requirements

### Minimum Requirements
- Python 3.8+
- 4GB RAM
- Webcam or IP camera
- Modern web browser

### Recommended for Best Performance
- Python 3.10+
- 8GB+ RAM
- Apple Silicon Mac or NVIDIA GPU
- High-resolution cameras

## 🚨 Troubleshooting

### System Check
```bash
python start.py --check
```

### Common Issues

**🔧 Dependencies Missing**
```bash
python start.py --install-deps
```

**📹 Camera Not Detected**
- Check camera permissions in system settings
- Try different camera indices (0, 1, 2...)
- Ensure camera isn't used by another app

**🌐 Port Already in Use**
```bash
python start.py --port 8080
```

**🖥️ Performance Issues**
- Use hardware acceleration if available
- Reduce camera resolution
- Close other applications

### Logs and Debugging
- Console shows detailed status messages
- Use `--debug` flag for verbose output
- Check browser developer tools for frontend issues

## 🔧 Advanced Configuration

### Environment Variables
```bash
export FLASK_HOST=0.0.0.0      # Allow network access
export FLASK_PORT=5001         # Custom port
export FLASK_DEBUG=1           # Debug mode
```

### Hardware Optimization
The system automatically detects and uses:
- **Apple Silicon**: Neural Engine acceleration
- **NVIDIA GPU**: CUDA acceleration  
- **Intel**: OpenVINO optimization
- **Multi-core**: CPU threading

## 📝 API Endpoints

- `GET /api/camera/detect` - Scan for available cameras
- `POST /api/camera/test` - Test camera connection
- `GET /api/people` - List registered people
- `POST /api/detection/start` - Start detection
- `POST /api/detection/stop` - Stop detection

## 🤝 Contributing

This is an enhanced version of the original face recognition system with:
- Smart camera detection
- Cross-platform support  
- Hardware optimization
- Modern web interface

## 📄 License

Open source project for educational and development purposes.
