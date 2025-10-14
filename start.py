#!/usr/bin/env python3
"""
Face Recognition System Launcher
================================

This script provides a convenient way to start the entire face recognition system.
It handles environment setup, dependency checks, and launches the web application.

Usage:
    python start.py                    # Start with default settings
    python start.py --port 5001       # Start on specific port
    python start.py --host 0.0.0.0    # Start accessible from network
    python start.py --debug           # Start in debug mode
    python start.py --check           # Only check system status
"""

import os
import sys
import subprocess
import argparse
import platform
import time
import webbrowser
from pathlib import Path

class FaceRecognitionLauncher:
    def __init__(self):
        self.root_dir = Path(__file__).parent.absolute()
        self.webapp_dir = self.root_dir / "webapp"
        self.python_executable = sys.executable
        self.system_info = {
            'platform': platform.system().lower(),
            'architecture': platform.machine().lower(),
            'python_version': sys.version
        }
        
    def print_banner(self):
        """Print system banner with information"""
        print("=" * 60)
        print("🎯 Face Recognition System Launcher")
        print("=" * 60)
        print(f"📁 Root Directory: {self.root_dir}")
        print(f"🐍 Python: {self.python_executable}")
        print(f"💻 Platform: {self.system_info['platform']} ({self.system_info['architecture']})")
        print(f"📦 Python Version: {sys.version.split()[0]}")
        print("=" * 60)
    
    def check_directories(self):
        """Check if required directories exist"""
        print("📂 Checking directory structure...")
        
        required_dirs = [
            self.webapp_dir,
            self.webapp_dir / "templates",
            self.webapp_dir / "people",
            self.webapp_dir / "embeddings"
        ]
        
        missing_dirs = []
        for directory in required_dirs:
            if directory.exists():
                print(f"  ✅ {directory.relative_to(self.root_dir)}")
            else:
                print(f"  ❌ {directory.relative_to(self.root_dir)} (missing)")
                missing_dirs.append(directory)
        
        # Create missing directories
        if missing_dirs:
            print("\n🔧 Creating missing directories...")
            for directory in missing_dirs:
                directory.mkdir(parents=True, exist_ok=True)
                print(f"  ✅ Created {directory.relative_to(self.root_dir)}")
        
        return len(missing_dirs) == 0
    
    def check_files(self):
        """Check if required files exist"""
        print("\n📄 Checking required files...")
        
        required_files = [
            self.webapp_dir / "app.py",
            self.webapp_dir / "detector.py",
            self.webapp_dir / "face_db.py",
            self.webapp_dir / "templates" / "index.html"
        ]
        
        missing_files = []
        for file_path in required_files:
            if file_path.exists():
                print(f"  ✅ {file_path.relative_to(self.root_dir)}")
            else:
                print(f"  ❌ {file_path.relative_to(self.root_dir)} (missing)")
                missing_files.append(file_path)
        
        return len(missing_files) == 0
    
    def check_dependencies(self):
        """Check if Python dependencies are installed"""
        print("\n📦 Checking Python dependencies...")
        required_packages = [
            ('flask', 'Flask web framework'),
            ('flask_socketio', 'WebSocket support'),
            ('opencv-python', 'Computer vision library'),
            ('insightface', 'Face recognition AI'),
            ('numpy', 'Numerical computing'),
            ('pillow', 'Image processing'),
            ('sqlite3', 'Database (built-in)')
        ]

        # Map package name -> actual import name
        import_names = {
            'flask': 'flask',
            'flask_socketio': 'flask_socketio',
            'opencv-python': 'cv2',
            'insightface': 'insightface',
            'numpy': 'numpy',
            'pillow': 'PIL',          # <-- key fix
            'sqlite3': 'sqlite3',
        }

        missing_packages = []
        for package, description in required_packages:
            try:
                __import__(import_names[package])
                print(f"  ✅ {package} - {description}")
            except ImportError:
                print(f"  ❌ {package} - {description} (missing)")
                missing_packages.append(package)
        
        return missing_packages
    
    def install_dependencies(self, missing_packages):
        """Install missing dependencies"""
        if not missing_packages:
            return True
            
        print(f"\n🔧 Installing {len(missing_packages)} missing dependencies...")
        
        # Map package import names to pip install names
        pip_names = {
            'flask_socketio': 'flask-socketio',
            'opencv-python': 'opencv-python',
            'insightface': 'insightface',
            'pillow': 'Pillow'
        }
        
        for package in missing_packages:
            if package == 'sqlite3':
                continue  # Built-in module
                
            pip_name = pip_names.get(package, package)
            print(f"  📦 Installing {pip_name}...")
            
            try:
                subprocess.run([
                    self.python_executable, "-m", "pip", "install", pip_name
                ], check=True, capture_output=True, text=True)
                print(f"  ✅ {pip_name} installed successfully")
            except subprocess.CalledProcessError as e:
                print(f"  ❌ Failed to install {pip_name}: {e.stderr}")
                return False
        
        return True
    
    def check_ports(self, port):
        """Check if port is available"""
        import socket
        
        print(f"\n🌐 Checking port {port} availability...")
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                print(f"  ✅ Port {port} is available")
                return True
        except OSError:
            print(f"  ❌ Port {port} is already in use")
            return False
    
    def find_available_port(self, start_port=5001):
        """Find next available port"""
        import socket
        
        for port in range(start_port, start_port + 100):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', port))
                    return port
            except OSError:
                continue
        return None
    
    def system_check(self):
        """Perform complete system check"""
        print("🔍 Performing system check...")
        
        # Check directories and files
        dirs_ok = self.check_directories()
        files_ok = self.check_files()
        
        # Check dependencies
        missing_packages = self.check_dependencies()
        
        if not dirs_ok or not files_ok:
            print("\n❌ System check failed: Missing required files or directories")
            return False
            
        if missing_packages:
            print(f"\n⚠️  Found {len(missing_packages)} missing dependencies")
            return missing_packages
            
        print("\n✅ All system checks passed!")
        return True
    
    def start_application(self, host='127.0.0.1', port=5001, debug=False):
        """Start the face recognition application"""
        print(f"\n🚀 Starting Face Recognition System...")
        print(f"   Host: {host}")
        print(f"   Port: {port}")
        print(f"   Debug: {debug}")
        print(f"   URL: http://{host}:{port}")
        
        # Change to webapp directory
        os.chdir(self.webapp_dir)
        
        # Prepare environment
        env = os.environ.copy()
        env['FLASK_HOST'] = host
        env['FLASK_PORT'] = str(port)
        if debug:
            env['FLASK_DEBUG'] = '1'
        
        # Start the application
        try:
            print("\n" + "=" * 60)
            print("🎯 Face Recognition System Starting...")
            print("=" * 60)
            print(f"🌐 Server will be available at: http://{host}:{port}")
            print("🔧 Enhanced features: Camera detection, Hardware optimization")
            print("📱 Browser will open automatically in 3 seconds...")
            print("⌨️  Press Ctrl+C to stop the server")
            print("=" * 60)
            
            # Wait a moment then open browser
            if not debug:
                import threading
                def open_browser():
                    time.sleep(3)
                    webbrowser.open(f'http://localhost:{port}')
                
                threading.Thread(target=open_browser, daemon=True).start()
            
            # Start Flask app
            subprocess.run([
                self.python_executable, "app.py"
            ], env=env, check=True)
            
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down Face Recognition System...")
            print("👋 Goodbye!")
        except subprocess.CalledProcessError as e:
            print(f"\n❌ Failed to start application: {e}")
            return False
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            return False
        
        return True

def main():
    parser = argparse.ArgumentParser(
        description='Face Recognition System Launcher',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python start.py                    # Start with default settings
  python start.py --port 8080       # Use port 8080
  python start.py --host 0.0.0.0    # Accept connections from network
  python start.py --debug           # Enable debug mode
  python start.py --check           # Only check system status
        """
    )
    
    parser.add_argument('--host', default='127.0.0.1',
                       help='Host to bind to (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=5001,
                       help='Port to bind to (default: 5001)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode')
    parser.add_argument('--check', action='store_true',
                       help='Only perform system check, don\'t start server')
    parser.add_argument('--install-deps', action='store_true',
                       help='Install missing dependencies automatically')
    
    args = parser.parse_args()
    
    # Create launcher instance
    launcher = FaceRecognitionLauncher()
    launcher.print_banner()
    
    # Perform system check
    check_result = launcher.system_check()
    
    # Handle missing dependencies
    if isinstance(check_result, list):  # Missing packages
        if args.install_deps:
            if not launcher.install_dependencies(check_result):
                print("\n❌ Failed to install dependencies")
                sys.exit(1)
            # Re-check after installation
            check_result = launcher.system_check()
        else:
            print(f"\n⚠️  Missing dependencies detected. Run with --install-deps to install them:")
            print(f"   python start.py --install-deps")
            sys.exit(1)
    
    if not check_result:
        print("\n❌ System check failed")
        sys.exit(1)
    
    # If only checking, exit here
    if args.check:
        print("\n✅ System check completed successfully!")
        sys.exit(0)
    
    # Check port availability
    if not launcher.check_ports(args.port):
        print(f"   Searching for alternative port...")
        alternative_port = launcher.find_available_port(args.port + 1)
        if alternative_port:
            print(f"   Using port {alternative_port} instead")
            args.port = alternative_port
        else:
            print("   No available ports found")
            sys.exit(1)
    
    # Start application
    success = launcher.start_application(args.host, args.port, args.debug)
    
    if not success:
        sys.exit(1)

if __name__ == '__main__':
    main()