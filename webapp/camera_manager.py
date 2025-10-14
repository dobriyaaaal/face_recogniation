"""
Enhanced Camera Management System for Face Recognition
Provides cross-platform camera detection and hardware optimization
"""

import os
import sys
import platform
import subprocess
import signal
import threading
import time
import json
from typing import List, Dict, Tuple, Optional, Any

# Set OpenCV environment variables for macOS camera authorization
os.environ['OPENCV_AVFOUNDATION_SKIP_AUTH'] = '1'

# Import availability flags
CV2_AVAILABLE = True
PSUTIL_AVAILABLE = True

# Import dependencies with fallbacks
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    print(">> OpenCV not available, camera detection disabled")
    CV2_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    print(">> psutil not available, some system info disabled")
    PSUTIL_AVAILABLE = False

class CameraManager:
    def __init__(self):
        self.platform_name = platform.system().lower()
        self.detected_cameras = []
        self.supported_formats = {
            'builtin': ['Built-in Camera', 'FaceTime HD Camera', 'Integrated Camera'],
            'usb': ['USB Camera', 'UVC Camera', 'External Camera'],
            'rtsp': ['IP Camera', 'Network Camera', 'Security Camera'],
            'http': ['HTTP Stream', 'MJPEG Stream', 'Web Camera']
        }
        
    def detect_available_cameras(self) -> List[Dict]:
        """Detect all available cameras on the system"""
        cameras = []
        
        # Test basic camera indices (0-9)
        cameras.extend(self._test_camera_indices())
        
        # Platform-specific detection
        if self.platform_name == 'darwin':  # macOS
            cameras.extend(self._detect_macos_cameras())
        elif self.platform_name == 'windows':
            cameras.extend(self._detect_windows_cameras())
        elif self.platform_name == 'linux':
            cameras.extend(self._detect_linux_cameras())
        
        self.detected_cameras = cameras
        return cameras
    
    def _test_camera_indices(self) -> List[Dict]:
        """Test camera indices 0-9 for connected devices"""
        cameras = []
        
        if not CV2_AVAILABLE:
            print(">> OpenCV not available, skipping camera index testing")
            return cameras
            
        print(">> Testing camera indices...")
        
        for i in range(10):
            try:
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        # Get camera properties
                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        fps = int(cap.get(cv2.CAP_PROP_FPS))
                        
                        # Determine camera type and name
                        if i == 0:
                            camera_name = 'Built-in Camera'
                            camera_type = 'builtin'
                        else:
                            # Check if it's a Continuity Camera (iPhone/iPad)
                            if width == 1280 and height == 720:
                                camera_name = f'iPhone Camera (Continuity)'
                                camera_type = 'continuity'
                            else:
                                camera_name = f'USB Camera {i}'
                                camera_type = 'usb'
                        
                        camera_info = {
                            'id': f'camera_{i}',
                            'name': camera_name,
                            'url': i,  # Store as integer, not string
                            'type': camera_type,
                            'platform': self.platform_name,
                            'resolution': f'{width}x{height}',
                            'fps': fps,
                            'status': 'available',
                            'backend': 'opencv_index',
                            'index': i  # Also store the index explicitly
                        }
                        
                        cameras.append(camera_info)
                        print(f">> Found {camera_name}: {width}x{height} @ {fps}fps")
                
                cap.release()
                
            except Exception as e:
                continue
                
        return cameras
    
    def _detect_macos_cameras(self) -> List[Dict]:
        """macOS-specific camera detection"""
        cameras = []
        
        try:
            # Use system_profiler to get camera info
            result = subprocess.run([
                'system_profiler', 'SPCameraDataType', '-json'
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for category in data.get('SPCameraDataType', []):
                    for item in category.get('_items', []):
                        name = item.get('_name', 'Unknown Camera')
                        cameras.append({
                            'id': f'macos_{name.lower().replace(" ", "_")}',
                            'name': f'{name} (macOS)',
                            'url': '0',  # Usually the first camera
                            'type': 'builtin',
                            'platform': 'darwin',
                            'resolution': 'Auto',
                            'fps': 30,
                            'status': 'available',
                            'backend': 'avfoundation'
                        })
        except Exception as e:
            print(f">> macOS camera detection failed: {e}")
            
        # Add AVFoundation backend option for better macOS support
        if cameras:
            cameras.append({
                'id': 'macos_avf_0',
                'name': 'Camera 0 (AVFoundation)',
                'url': '0',
                'type': 'builtin',
                'platform': 'darwin',
                'resolution': 'Auto',
                'fps': 30,
                'status': 'available',
                'backend': 'avfoundation',
                'cv2_backend': cv2.CAP_AVFOUNDATION
            })
            
        return cameras
    
    def _detect_windows_cameras(self) -> List[Dict]:
        """Windows-specific camera detection"""
        cameras = []
        
        try:
            # Use DirectShow backend for Windows
            cameras.append({
                'id': 'win_dshow_0',
                'name': 'Camera 0 (DirectShow)',
                'url': '0',
                'type': 'builtin',
                'platform': 'windows',
                'resolution': 'Auto',
                'fps': 30,
                'status': 'available',
                'backend': 'dshow',
                'cv2_backend': cv2.CAP_DSHOW
            })
            
            # Add Media Foundation backend
            cameras.append({
                'id': 'win_msmf_0',
                'name': 'Camera 0 (Media Foundation)',
                'url': '0',
                'type': 'builtin',
                'platform': 'windows',
                'resolution': 'Auto',
                'fps': 30,
                'status': 'available',
                'backend': 'msmf',
                'cv2_backend': cv2.CAP_MSMF
            })
            
        except Exception as e:
            print(f">> Windows camera detection failed: {e}")
            
        return cameras
    
    def _detect_linux_cameras(self) -> List[Dict]:
        """Linux-specific camera detection using V4L2"""
        cameras = []
        
        try:
            # Check /dev/video* devices
            video_devices = []
            for i in range(10):
                device_path = f'/dev/video{i}'
                if os.path.exists(device_path):
                    video_devices.append((i, device_path))
            
            for i, device_path in video_devices:
                cameras.append({
                    'id': f'linux_v4l2_{i}',
                    'name': f'Video{i} (V4L2)',
                    'url': str(i),
                    'type': 'builtin' if i == 0 else 'usb',
                    'platform': 'linux',
                    'resolution': 'Auto',
                    'fps': 30,
                    'status': 'available',
                    'backend': 'v4l2',
                    'cv2_backend': cv2.CAP_V4L2,
                    'device_path': device_path
                })
                
        except Exception as e:
            print(f">> Linux camera detection failed: {e}")
            
        return cameras
    
    def _get_network_camera_templates(self) -> List[Dict]:
        """Get common network camera URL templates"""
        return [
            {
                'id': 'template_rtsp_generic',
                'name': '📹 Generic RTSP Camera',
                'url': 'rtsp://username:password@ip:554/stream',
                'type': 'rtsp',
                'platform': 'network',
                'resolution': 'Variable',
                'fps': 'Variable',
                'status': 'template',
                'backend': 'ffmpeg',
                'description': 'Generic RTSP stream format'
            },
            {
                'id': 'template_http_mjpeg',
                'name': '🌐 HTTP MJPEG Stream',
                'url': 'http://ip:port/mjpeg/stream',
                'type': 'http',
                'platform': 'network',
                'resolution': 'Variable',
                'fps': 'Variable',
                'status': 'template',
                'backend': 'opencv',
                'description': 'HTTP MJPEG stream format'
            },
            {
                'id': 'template_hikvision',
                'name': '🏢 Hikvision Camera',
                'url': 'rtsp://admin:password@ip:554/Streaming/Channels/101',
                'type': 'rtsp',
                'platform': 'network',
                'resolution': 'Variable',
                'fps': 'Variable',
                'status': 'template',
                'backend': 'ffmpeg',
                'description': 'Hikvision IP camera format'
            },
            {
                'id': 'template_dahua',
                'name': '🏢 Dahua Camera',
                'url': 'rtsp://admin:password@ip:554/cam/realmonitor?channel=1&subtype=0',
                'type': 'rtsp',
                'platform': 'network',
                'resolution': 'Variable',
                'fps': 'Variable',
                'status': 'template',
                'backend': 'ffmpeg',
                'description': 'Dahua IP camera format'
            }
        ]
    
    def get_optimized_capture_params(self, camera_info: Dict) -> Dict:
        """Get optimized capture parameters based on platform and hardware"""
        params = {
            'backend': cv2.CAP_ANY,
            'buffer_size': 1,
            'properties': {}
        }
        
        # Platform-specific backends
        if 'cv2_backend' in camera_info:
            params['backend'] = camera_info['cv2_backend']
        elif camera_info.get('backend') == 'avfoundation':
            params['backend'] = cv2.CAP_AVFOUNDATION
        elif camera_info.get('backend') == 'dshow':
            params['backend'] = cv2.CAP_DSHOW
        elif camera_info.get('backend') == 'msmf':
            params['backend'] = cv2.CAP_MSMF
        elif camera_info.get('backend') == 'v4l2':
            params['backend'] = cv2.CAP_V4L2
        elif camera_info.get('backend') == 'ffmpeg':
            params['backend'] = cv2.CAP_FFMPEG
        
        # Optimize based on camera type
        if camera_info['type'] == 'rtsp':
            params['properties'].update({
                cv2.CAP_PROP_BUFFERSIZE: 1,
                cv2.CAP_PROP_FPS: 15,  # Lower FPS for stability
            })
        else:
            params['properties'].update({
                cv2.CAP_PROP_BUFFERSIZE: 1,
                cv2.CAP_PROP_FPS: 30,
                cv2.CAP_PROP_FRAME_WIDTH: 640,
                cv2.CAP_PROP_FRAME_HEIGHT: 480,
            })
        
        return params
    
    def test_camera_connection(self, camera_info: Dict, timeout: int = 10) -> Tuple[bool, str, Optional[Dict]]:
        """Test if camera connection works and return basic info"""
        if not CV2_AVAILABLE:
            return False, "OpenCV not available", None
            
        url = camera_info.get('url', '0')
        capture_params = self.get_optimized_capture_params(camera_info)
        
        def timeout_handler(signum, frame):
            raise TimeoutError("Camera test timed out")
        
        try:
            # Set timeout if on Unix-like system
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(timeout)
            
            # Create capture with timeout protection
            def read_frame():
                cap = cv2.VideoCapture(url if isinstance(url, int) or url.isdigit() else url)
                if not cap.isOpened():
                    return False, "Could not open camera", None
                return cap.read()
            
            def threaded_read():
                try:
                    cap = cv2.VideoCapture(url if isinstance(url, int) or url.isdigit() else url, 
                                         capture_params.get('backend', cv2.CAP_ANY))
                    
                    if not cap.isOpened():
                        return False, "Could not open camera", None
                    
                    # Test frame read
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        cap.release()
                        return False, "Could not read frame", None
                    
                    # Get camera properties
                    info = {
                        'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                        'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                        'fps': int(cap.get(cv2.CAP_PROP_FPS)),
                        'format': int(cap.get(cv2.CAP_PROP_FORMAT)),
                        'brightness': cap.get(cv2.CAP_PROP_BRIGHTNESS),
                        'contrast': cap.get(cv2.CAP_PROP_CONTRAST),
                        'saturation': cap.get(cv2.CAP_PROP_SATURATION)
                    }
                    
                    cap.release()
                    return True, "Connection successful", info
                    
                except Exception as e:
                    return False, f"Connection failed: {str(e)}", None
            
            # Run test in thread with timeout
            import threading
            result = [None]
            thread = threading.Thread(target=lambda: result.__setitem__(0, threaded_read()))
            thread.daemon = True
            thread.start()
            thread.join(timeout)
            
            if thread.is_alive() or result[0] is None:
                return False, "Connection timed out", None
                
            return result[0]
            
        except TimeoutError:
            return False, "Connection timed out", None
        except Exception as e:
            return False, f"Test failed: {str(e)}", None
        finally:
            # Clear timeout if set
            if hasattr(signal, 'alarm'):
                signal.alarm(0)
    
    def get_camera_dropdown_options(self) -> List[Dict]:
        """Get formatted options for camera dropdown"""
        if not self.detected_cameras:
            self.detect_available_cameras()
        
        options = []
        
        # Group cameras by type
        builtin_cameras = [cam for cam in self.detected_cameras if cam['type'] == 'builtin']
        usb_cameras = [cam for cam in self.detected_cameras if cam['type'] == 'usb']
        network_templates = [cam for cam in self.detected_cameras if cam['status'] == 'template']
        
        # Add section headers and cameras
        if builtin_cameras:
            options.append({'type': 'header', 'label': '🔹 Built-in Cameras'})
            options.extend([{
                'id': cam['id'],
                'label': f"{cam['name']} ({cam['resolution']})",
                'value': cam['url'],
                'camera_info': cam,
                'type': 'camera'
            } for cam in builtin_cameras])
        
        if usb_cameras:
            options.append({'type': 'header', 'label': '🔹 USB Cameras'})
            options.extend([{
                'id': cam['id'],
                'label': f"{cam['name']} ({cam['resolution']})",
                'value': cam['url'],
                'camera_info': cam,
                'type': 'camera'
            } for cam in usb_cameras])
        
        if network_templates:
            options.append({'type': 'header', 'label': '🔹 Network Camera Templates'})
            options.extend([{
                'id': cam['id'],
                'label': cam['name'],
                'value': cam['url'],
                'camera_info': cam,
                'type': 'template',
                'description': cam.get('description', '')
            } for cam in network_templates])
        
        # Add manual entry option
        options.append({'type': 'header', 'label': '🔹 Manual Entry'})
        options.append({
            'id': 'manual_entry',
            'label': '✏️ Enter Custom URL',
            'value': 'manual',
            'type': 'manual'
        })
        
        return options

# Hardware optimization detector
class HardwareOptimizer:
    def __init__(self):
        self.platform_name = platform.system().lower()
        self.available_devices = self._detect_compute_devices()
    
    def _detect_compute_devices(self) -> Dict:
        """Detect available compute devices for face recognition"""
        devices = {
            'cpu': True,  # Always available
            'gpu': False,
            'apple_neural_engine': False,
            'cuda': False,
            'opencl': False,
            'details': {}
        }
        
        # Check for CUDA (NVIDIA GPU)
        try:
            import onnxruntime as ort
            cuda_providers = [p for p in ort.get_available_providers() if 'CUDA' in p]
            if cuda_providers:
                devices['cuda'] = True
                devices['gpu'] = True
                devices['details']['cuda_providers'] = cuda_providers
        except:
            pass
        
        # Check for Apple Silicon (Metal Performance Shaders)
        if self.platform_name == 'darwin':
            try:
                # Check if running on Apple Silicon
                result = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], 
                                      capture_output=True, text=True)
                if 'Apple' in result.stdout:
                    devices['apple_neural_engine'] = True
                    devices['gpu'] = True
                    devices['details']['apple_silicon'] = result.stdout.strip()
            except:
                pass
        
        # Check for OpenCL
        try:
            import pyopencl as cl
            platforms = cl.get_platforms()
            if platforms:
                devices['opencl'] = True
                devices['gpu'] = True
                devices['details']['opencl_platforms'] = len(platforms)
        except:
            pass
        
        return devices
    
    def get_optimal_ctx_id(self) -> int:
        """Get optimal context ID for InsightFace based on available hardware"""
        if self.available_devices['apple_neural_engine']:
            return -1  # CPU is often better on Apple Silicon for now
        elif self.available_devices['cuda']:
            return 0   # Use first CUDA GPU
        else:
            return -1  # Use CPU
    
    def get_optimization_recommendations(self) -> List[str]:
        """Get hardware optimization recommendations"""
        recommendations = []
        
        if self.available_devices['apple_neural_engine']:
            recommendations.append("✅ Apple Silicon detected - Optimized for Metal Performance Shaders")
        elif self.available_devices['cuda']:
            recommendations.append("✅ NVIDIA GPU detected - CUDA acceleration available")
        else:
            recommendations.append("ℹ️ Using CPU inference - Consider GPU for better performance")
        
        if self.platform_name == 'darwin':
            recommendations.append("💡 macOS: Consider using AVFoundation backend for cameras")
        elif self.platform_name == 'windows':
            recommendations.append("💡 Windows: DirectShow/Media Foundation backends available")
        elif self.platform_name == 'linux':
            recommendations.append("💡 Linux: V4L2 backend recommended for USB cameras")
        
        return recommendations

# Main camera manager instance
camera_manager = CameraManager()
hardware_optimizer = HardwareOptimizer()