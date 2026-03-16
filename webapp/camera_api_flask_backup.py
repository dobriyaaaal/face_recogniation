"""
Enhanced camera API endpoints for better camera detection and management
"""
from flask import Blueprint, jsonify, request
from camera_manager import camera_manager, hardware_optimizer
import json

# Create Blueprint for camera routes
camera_bp = Blueprint('camera_enhanced', __name__)

@camera_bp.route('/api/cameras/detect', methods=['GET'])
def detect_cameras():
    """Detect all available cameras on the system"""
    try:
        print(">> Starting camera detection...")
        cameras = camera_manager.detect_available_cameras()
        
        # Get dropdown options for frontend
        dropdown_options = camera_manager.get_camera_dropdown_options()
        
        # Get hardware optimization info
        hardware_info = hardware_optimizer.get_optimization_recommendations()
        
        return jsonify({
            'success': True,
            'cameras': cameras,
            'dropdown_options': dropdown_options,
            'hardware_info': hardware_info,
            'platform': camera_manager.platform_name,
            'total_detected': len(cameras)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Camera detection failed: {str(e)}',
            'cameras': [],
            'dropdown_options': []
        })

@camera_bp.route('/api/cameras/test-advanced', methods=['POST'])
def test_camera_advanced():
    """Advanced camera testing with platform optimization"""
    try:
        data = request.get_json()
        
        # Handle different input types
        if 'camera_info' in data:
            # Testing from dropdown selection
            camera_info = data['camera_info']
        else:
            # Testing manual URL
            camera_url = data.get('url', '')
            if not camera_url:
                return jsonify({
                    'success': False,
                    'error': 'Camera URL or camera info is required'
                })
            
            # Create camera info for manual URL
            camera_info = {
                'id': 'manual_test',
                'name': f'Manual Entry: {camera_url[:30]}...' if len(camera_url) > 30 else f'Manual Entry: {camera_url}',
                'url': camera_url,
                'type': 'rtsp' if camera_url.startswith('rtsp://') else 'http' if camera_url.startswith('http://') else 'unknown',
                'platform': 'manual',
                'status': 'manual'
            }
        
        # Test connection with timeout
        timeout = data.get('timeout', 15)
        success, message, properties = camera_manager.test_camera_connection(camera_info, timeout)
        
        result = {
            'success': success,
            'message': message,
            'camera_info': camera_info,
            'test_properties': properties,
            'optimization_used': camera_manager.get_optimized_capture_params(camera_info)
        }
        
        if success and properties:
            result['preview_available'] = True
            result['recommended_settings'] = {
                'resolution': properties.get('resolution', 'Auto'),
                'fps': properties.get('fps', 30),
                'backend': properties.get('backend', 'Default')
            }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Camera test failed: {str(e)}',
            'camera_info': data.get('camera_info', {}),
            'test_properties': None
        })

@camera_bp.route('/api/cameras/platform-info', methods=['GET'])
def get_platform_info():
    """Get platform-specific camera information"""
    try:
        platform_info = {
            'platform': camera_manager.platform_name,
            'supported_backends': [],
            'hardware': hardware_optimizer.available_devices,
            'recommendations': hardware_optimizer.get_optimization_recommendations(),
            'camera_examples': []
        }
        
        # Add platform-specific information
        if camera_manager.platform_name == 'darwin':  # macOS
            platform_info['supported_backends'] = ['AVFoundation', 'OpenCV', 'FFMPEG']
            platform_info['camera_examples'] = [
                {
                    'name': 'Built-in FaceTime Camera',
                    'url': '0',
                    'description': 'Default built-in camera (usually index 0)'
                },
                {
                    'name': 'External USB Camera',
                    'url': '1',
                    'description': 'External USB camera (index 1 or higher)'
                }
            ]
            
        elif camera_manager.platform_name == 'windows':  # Windows
            platform_info['supported_backends'] = ['DirectShow', 'Media Foundation', 'OpenCV', 'FFMPEG']
            platform_info['camera_examples'] = [
                {
                    'name': 'Built-in Camera',
                    'url': '0',
                    'description': 'Default built-in camera (usually index 0)'
                },
                {
                    'name': 'External USB Camera',
                    'url': '1',
                    'description': 'External USB camera (index 1 or higher)'
                }
            ]
            
        elif camera_manager.platform_name == 'linux':  # Linux
            platform_info['supported_backends'] = ['V4L2', 'OpenCV', 'FFMPEG']
            platform_info['camera_examples'] = [
                {
                    'name': 'Video0 Device',
                    'url': '0',
                    'description': 'First video device (/dev/video0)'
                },
                {
                    'name': 'USB Camera',
                    'url': '1',
                    'description': 'USB camera device (/dev/video1)'
                }
            ]
        
        # Add common network examples
        platform_info['network_examples'] = [
            {
                'brand': 'Generic RTSP',
                'url': 'rtsp://username:password@192.168.1.100:554/stream',
                'description': 'Generic RTSP camera stream'
            },
            {
                'brand': 'Hikvision',
                'url': 'rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101',
                'description': 'Hikvision IP camera main stream'
            },
            {
                'brand': 'Dahua',
                'url': 'rtsp://admin:password@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0',
                'description': 'Dahua IP camera main stream'
            },
            {
                'brand': 'Axis',
                'url': 'rtsp://root:password@192.168.1.100/axis-media/media.amp',
                'description': 'Axis IP camera stream'
            },
            {
                'brand': 'HTTP MJPEG',
                'url': 'http://192.168.1.100:8080/video',
                'description': 'HTTP MJPEG stream (IP Webcam apps)'
            }
        ]
        
        return jsonify({
            'success': True,
            'platform_info': platform_info
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get platform info: {str(e)}',
            'platform_info': {}
        })

@camera_bp.route('/api/cameras/common-urls', methods=['GET'])
def get_common_camera_urls():
    """Get common camera URL patterns and examples"""
    
    common_urls = {
        'builtin_cameras': [
            {'name': 'Default Camera', 'url': '0', 'description': 'Built-in or first USB camera'},
            {'name': 'Second Camera', 'url': '1', 'description': 'Second camera device'},
            {'name': 'Third Camera', 'url': '2', 'description': 'Third camera device'},
        ],
        
        'ip_cameras': {
            'hikvision': [
                {
                    'name': 'Main Stream (High Quality)',
                    'url': 'rtsp://admin:password@IP:554/Streaming/Channels/101',
                    'description': 'Primary high-resolution stream'
                },
                {
                    'name': 'Sub Stream (Low Quality)',
                    'url': 'rtsp://admin:password@IP:554/Streaming/Channels/102',
                    'description': 'Secondary low-resolution stream'
                }
            ],
            
            'dahua': [
                {
                    'name': 'Main Stream',
                    'url': 'rtsp://admin:password@IP:554/cam/realmonitor?channel=1&subtype=0',
                    'description': 'Main stream for channel 1'
                },
                {
                    'name': 'Sub Stream',
                    'url': 'rtsp://admin:password@IP:554/cam/realmonitor?channel=1&subtype=1',
                    'description': 'Sub stream for channel 1'
                }
            ],
            
            'axis': [
                {
                    'name': 'Default Stream',
                    'url': 'rtsp://root:password@IP/axis-media/media.amp',
                    'description': 'Default Axis camera stream'
                }
            ],
            
            'foscam': [
                {
                    'name': 'Main Stream',
                    'url': 'rtsp://admin:password@IP:554/videoMain',
                    'description': 'Foscam main video stream'
                }
            ],
            
            'generic': [
                {
                    'name': 'RTSP Stream',
                    'url': 'rtsp://username:password@IP:554/stream',
                    'description': 'Generic RTSP stream format'
                },
                {
                    'name': 'RTSP with Path',
                    'url': 'rtsp://username:password@IP:554/path/to/stream',
                    'description': 'RTSP stream with specific path'
                }
            ]
        },
        
        'mobile_apps': [
            {
                'name': 'IP Webcam (Android)',
                'url': 'http://IP:8080/video',
                'description': 'IP Webcam app video stream'
            },
            {
                'name': 'DroidCam',
                'url': 'http://IP:4747/mjpegfeed?640x480',
                'description': 'DroidCam MJPEG stream'
            },
            {
                'name': 'EpocCam',
                'url': 'http://IP:8080/stream.mjpg',
                'description': 'EpocCam MJPEG stream'
            }
        ],
        
        'streaming_services': [
            {
                'name': 'YouTube Live (with youtube-dl)',
                'url': 'https://youtube.com/watch?v=VIDEO_ID',
                'description': 'YouTube live stream (requires youtube-dl)'
            },
            {
                'name': 'RTMP Stream',
                'url': 'rtmp://server/live/stream',
                'description': 'RTMP streaming protocol'
            }
        ]
    }
    
    return jsonify({
        'success': True,
        'common_urls': common_urls,
        'notes': [
            'Replace IP with your camera\'s IP address',
            'Replace username:password with your camera credentials',
            'Port numbers may vary depending on camera configuration',
            'Some cameras may use different paths or parameters'
        ]
    })

# URL patterns for different scenarios
@camera_bp.route('/api/cameras/url-builder', methods=['POST'])
def build_camera_url():
    """Build camera URL based on user inputs"""
    try:
        data = request.get_json()
        camera_type = data.get('type', '')
        brand = data.get('brand', '')
        ip = data.get('ip', '')
        port = data.get('port', '')
        username = data.get('username', '')
        password = data.get('password', '')
        channel = data.get('channel', '1')
        
        if not ip:
            return jsonify({
                'success': False,
                'error': 'IP address is required'
            })
        
        built_urls = []
        
        if camera_type == 'rtsp':
            # Build RTSP URLs based on brand
            if brand.lower() == 'hikvision':
                main_url = f'rtsp://{username}:{password}@{ip}:{port or "554"}/Streaming/Channels/101'
                sub_url = f'rtsp://{username}:{password}@{ip}:{port or "554"}/Streaming/Channels/102'
                built_urls = [
                    {'name': 'Main Stream (High Quality)', 'url': main_url},
                    {'name': 'Sub Stream (Low Quality)', 'url': sub_url}
                ]
                
            elif brand.lower() == 'dahua':
                main_url = f'rtsp://{username}:{password}@{ip}:{port or "554"}/cam/realmonitor?channel={channel}&subtype=0'
                sub_url = f'rtsp://{username}:{password}@{ip}:{port or "554"}/cam/realmonitor?channel={channel}&subtype=1'
                built_urls = [
                    {'name': 'Main Stream', 'url': main_url},
                    {'name': 'Sub Stream', 'url': sub_url}
                ]
                
            elif brand.lower() == 'axis':
                url = f'rtsp://{username}:{password}@{ip}:{port or "554"}/axis-media/media.amp'
                built_urls = [{'name': 'Default Stream', 'url': url}]
                
            else:  # Generic RTSP
                url = f'rtsp://{username}:{password}@{ip}:{port or "554"}/stream'
                built_urls = [{'name': 'Generic RTSP Stream', 'url': url}]
                
        elif camera_type == 'http':
            # Build HTTP URLs
            url = f'http://{ip}:{port or "8080"}/video'
            built_urls = [{'name': 'HTTP MJPEG Stream', 'url': url}]
            
        return jsonify({
            'success': True,
            'built_urls': built_urls,
            'parameters_used': {
                'type': camera_type,
                'brand': brand,
                'ip': ip,
                'port': port or 'default',
                'channel': channel
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'URL building failed: {str(e)}',
            'built_urls': []
        })


@camera_bp.route('/api/cameras/onvif-discover', methods=['POST'])
def onvif_discover():
    """
    Discover ONVIF-compatible cameras on the local network and return their RTSP stream URLs.
    Supports most Indian military-grade cameras: Hikvision, Dahua, TVT, CP Plus, etc.
    
    POST body: { "host": "192.168.1.64", "port": 80, "username": "admin", "password": "password" }
    OR:        { "scan": true, "subnet": "192.168.1", "username": "admin", "password": "password" }
    """
    try:
        try:
            from onvif import ONVIFCamera
            ONVIF_AVAILABLE = True
        except ImportError:
            ONVIF_AVAILABLE = False

        if not ONVIF_AVAILABLE:
            return jsonify({
                'success': False,
                'error': 'onvif-zeep not installed. Run: pip install onvif-zeep',
                'cameras': []
            })

        data = request.get_json() or {}
        username = data.get('username', 'admin')
        password = data.get('password', 'admin')

        discovered = []

        # --- Single camera probe ---
        if 'host' in data:
            hosts = [(data['host'], int(data.get('port', 80)))]
        # --- Subnet scan ---
        elif data.get('scan'):
            subnet = data.get('subnet', '192.168.1')
            hosts = [(f'{subnet}.{i}', 80) for i in range(1, 255)]
        else:
            return jsonify({'success': False, 'error': 'Provide host or scan:true with subnet', 'cameras': []})

        for host, port in hosts:
            try:
                cam = ONVIFCamera(host, port, username, password, no_cache=True)
                media_service = cam.create_media_service()
                device_service = cam.create_devicemgmt_service()

                device_info = device_service.GetDeviceInformation()
                profiles = media_service.GetProfiles()

                streams = []
                for profile in profiles:
                    req = media_service.create_type('GetStreamUri')
                    req.ProfileToken = profile.token
                    req.StreamSetup = {
                        'Stream': 'RTP-Unicast',
                        'Transport': {'Protocol': 'RTSP'}
                    }
                    uri_resp = media_service.GetStreamUri(req)
                    rtsp_url = uri_resp.Uri

                    # Inject credentials into URL if not present
                    if username and f'@' not in rtsp_url:
                        rtsp_url = rtsp_url.replace('rtsp://', f'rtsp://{username}:{password}@')

                    streams.append({
                        'profile': profile.Name,
                        'token': profile.token,
                        'rtsp_url': rtsp_url,
                        'resolution': (
                            f"{profile.VideoEncoderConfiguration.Resolution.Width}"
                            f"x{profile.VideoEncoderConfiguration.Resolution.Height}"
                        ) if hasattr(profile, 'VideoEncoderConfiguration') and profile.VideoEncoderConfiguration else 'unknown'
                    })

                discovered.append({
                    'host': host,
                    'port': port,
                    'manufacturer': device_info.Manufacturer,
                    'model': device_info.Model,
                    'firmware': device_info.FirmwareVersion,
                    'serial': device_info.SerialNumber,
                    'streams': streams
                })

            except Exception:
                # Not an ONVIF camera or not reachable — skip silently during scan
                continue

        return jsonify({
            'success': True,
            'cameras_found': len(discovered),
            'cameras': discovered
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'ONVIF discovery failed: {str(e)}',
            'cameras': []
        })