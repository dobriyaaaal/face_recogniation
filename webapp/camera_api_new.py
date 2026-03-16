"""
Camera API — FastAPI APIRouter
Converted from Flask Blueprint. Same endpoints, same response shapes.
"""
import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from camera_manager import camera_manager, hardware_optimizer

router = APIRouter()


@router.get('/api/cameras/detect')
async def detect_cameras():
    """Detect all available cameras on the system (USB, built-in, list known RTSP patterns)."""
    try:
        cameras         = await asyncio.to_thread(camera_manager.detect_available_cameras)
        dropdown_options = camera_manager.get_camera_dropdown_options()
        hardware_info   = hardware_optimizer.get_optimization_recommendations()
        return JSONResponse({
            'success':        True,
            'cameras':        cameras,
            'dropdown_options': dropdown_options,
            'hardware_info':  hardware_info,
            'platform':       camera_manager.platform_name,
            'total_detected': len(cameras),
        })
    except Exception as e:
        return JSONResponse({
            'success': False,
            'error':   f'Camera detection failed: {str(e)}',
            'cameras': [], 'dropdown_options': [],
        })


@router.post('/api/cameras/test-advanced')
async def test_camera_advanced(request: Request):
    """Test a camera connection with a per-request timeout."""
    try:
        data = await request.json()

        if 'camera_info' in data:
            camera_info = data['camera_info']
        else:
            url = data.get('url', '')
            if not url:
                return JSONResponse({'success': False, 'error': 'camera_info or url required'})
            camera_info = {
                'id':       'manual_test',
                'name':     f"Manual: {url[:30]}{'...' if len(url) > 30 else ''}",
                'url':      url,
                'type':     'rtsp' if url.startswith('rtsp://') else
                            'http' if url.startswith('http://') else 'unknown',
                'platform': 'manual',
                'status':   'manual',
            }

        timeout = data.get('timeout', 15)
        success, message, properties = await asyncio.to_thread(
            camera_manager.test_camera_connection, camera_info, timeout
        )

        result = {
            'success':         success,
            'message':         message,
            'camera_info':     camera_info,
            'test_properties': properties,
            'optimization_used': camera_manager.get_optimized_capture_params(camera_info),
        }
        if success and properties:
            result['preview_available']    = True
            result['recommended_settings'] = {
                'resolution': properties.get('resolution', 'Auto'),
                'fps':        properties.get('fps', 30),
                'backend':    properties.get('backend', 'Default'),
            }
        return JSONResponse(result)

    except Exception as e:
        return JSONResponse({
            'success': False,
            'error':   f'Camera test failed: {str(e)}',
            'test_properties': None,
        })


@router.get('/api/cameras/platform-info')
async def get_platform_info():
    """Return platform-specific camera info and hardware capabilities."""
    try:
        platform_name = camera_manager.platform_name
        platform_info = {
            'platform':           platform_name,
            'supported_backends': [],
            'hardware':           hardware_optimizer.available_devices,
            'recommendations':    hardware_optimizer.get_optimization_recommendations(),
            'camera_examples':    [],
        }

        if platform_name == 'darwin':
            platform_info['supported_backends'] = ['AVFoundation', 'OpenCV', 'FFMPEG']
            platform_info['camera_examples'] = [
                {'name': 'Built-in FaceTime Camera', 'url': '0', 'description': 'Default built-in camera'},
                {'name': 'External USB Camera',      'url': '1', 'description': 'USB camera (index 1+)'},
            ]
        elif platform_name == 'windows':
            platform_info['supported_backends'] = ['DirectShow', 'Media Foundation', 'OpenCV', 'FFMPEG']
            platform_info['camera_examples'] = [
                {'name': 'Built-in Camera',    'url': '0', 'description': 'Default built-in camera'},
                {'name': 'External USB Camera','url': '1', 'description': 'USB camera (index 1+)'},
            ]
        elif platform_name == 'linux':
            platform_info['supported_backends'] = ['V4L2', 'OpenCV', 'FFMPEG']
            platform_info['camera_examples'] = [
                {'name': 'Video0 Device', 'url': '0', 'description': '/dev/video0'},
                {'name': 'USB Camera',    'url': '1', 'description': '/dev/video1'},
            ]

        platform_info['network_examples'] = [
            {'brand': 'Generic RTSP',
             'url': 'rtsp://username:password@192.168.1.100:554/stream',
             'description': 'Generic RTSP stream'},
            {'brand': 'Hikvision (main stream)',
             'url': 'rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101',
             'description': 'Hikvision main stream (101), sub (102)'},
            {'brand': 'Dahua',
             'url': 'rtsp://admin:password@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0',
             'description': 'Dahua main stream'},
            {'brand': 'Axis',
             'url': 'rtsp://root:password@192.168.1.100/axis-media/media.amp',
             'description': 'Axis camera'},
            {'brand': 'CP Plus / TVT (ONVIF)',
             'url': 'rtsp://admin:password@192.168.1.100:554/stream',
             'description': 'Most Indian mil-grade cameras — use ONVIF discover for exact URL'},
            {'brand': 'HTTP MJPEG',
             'url': 'http://192.168.1.100:8080/video',
             'description': 'HTTP MJPEG (IP Webcam, DroidCam)'},
        ]

        return JSONResponse({'success': True, 'platform_info': platform_info})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e), 'platform_info': {}})


@router.get('/api/cameras/common-urls')
async def get_common_camera_urls():
    """Return common camera URL patterns grouped by brand."""
    common_urls = {
        'builtin_cameras': [
            {'name': 'Default Camera', 'url': '0', 'description': 'Built-in or first USB camera'},
            {'name': 'Second Camera',  'url': '1', 'description': 'Second camera device'},
            {'name': 'Third Camera',   'url': '2', 'description': 'Third camera device'},
        ],
        'ip_cameras': {
            'hikvision': [
                {'name': 'Main Stream (High Quality)',
                 'url': 'rtsp://admin:password@IP:554/Streaming/Channels/101'},
                {'name': 'Sub Stream (Low Bandwidth)',
                 'url': 'rtsp://admin:password@IP:554/Streaming/Channels/102'},
            ],
            'dahua': [
                {'name': 'Main Stream',
                 'url': 'rtsp://admin:password@IP:554/cam/realmonitor?channel=1&subtype=0'},
                {'name': 'Sub Stream',
                 'url': 'rtsp://admin:password@IP:554/cam/realmonitor?channel=1&subtype=1'},
            ],
            'axis': [
                {'name': 'Default Stream',
                 'url': 'rtsp://root:password@IP/axis-media/media.amp'},
            ],
            'cp_plus_tvt': [
                {'name': 'RTSP Stream',
                 'url': 'rtsp://admin:password@IP:554/stream'},
            ],
            'generic': [
                {'name': 'RTSP Stream',
                 'url': 'rtsp://username:password@IP:554/stream'},
            ],
        },
        'mobile_apps': [
            {'name': 'IP Webcam (Android)', 'url': 'http://IP:8080/video'},
            {'name': 'DroidCam',             'url': 'http://IP:4747/mjpegfeed?640x480'},
        ],
    }
    return JSONResponse({
        'success': True,
        'common_urls': common_urls,
        'notes': [
            'Replace IP with your camera IP address',
            'Replace username:password with camera credentials',
            'Use /api/cameras/onvif-discover to auto-detect Hikvision/Dahua/TVT/CP Plus cameras',
        ],
    })


@router.post('/api/cameras/url-builder')
async def build_camera_url(request: Request):
    """Build RTSP/HTTP URL strings from component inputs."""
    try:
        data     = await request.json()
        cam_type = data.get('type', '')
        brand    = data.get('brand', '').lower()
        ip       = data.get('ip', '')
        port     = data.get('port', '')
        username = data.get('username', '')
        password = data.get('password', '')
        channel  = data.get('channel', '1')

        if not ip:
            return JSONResponse({'success': False, 'error': 'IP address is required'})

        creds   = f"{username}:{password}@" if username else ''
        p       = port or '554'
        built   = []

        if cam_type == 'rtsp':
            if brand == 'hikvision':
                built = [
                    {'name': 'Main Stream', 'url': f'rtsp://{creds}{ip}:{p}/Streaming/Channels/101'},
                    {'name': 'Sub Stream',  'url': f'rtsp://{creds}{ip}:{p}/Streaming/Channels/102'},
                ]
            elif brand == 'dahua':
                built = [
                    {'name': 'Main Stream', 'url': f'rtsp://{creds}{ip}:{p}/cam/realmonitor?channel={channel}&subtype=0'},
                    {'name': 'Sub Stream',  'url': f'rtsp://{creds}{ip}:{p}/cam/realmonitor?channel={channel}&subtype=1'},
                ]
            elif brand == 'axis':
                built = [{'name': 'Default', 'url': f'rtsp://{creds}{ip}:{p}/axis-media/media.amp'}]
            else:
                built = [{'name': 'Generic RTSP', 'url': f'rtsp://{creds}{ip}:{p}/stream'}]

        elif cam_type == 'http':
            built = [{'name': 'MJPEG Stream', 'url': f'http://{ip}:{port or "8080"}/video'}]

        return JSONResponse({'success': True, 'built_urls': built})
    except Exception as e:
        return JSONResponse({'success': False, 'error': str(e), 'built_urls': []})


@router.post('/api/cameras/onvif-discover')
async def onvif_discover(request: Request):
    """
    Auto-discover ONVIF cameras on the network.
    Supports Hikvision, Dahua, TVT, CP Plus and any ONVIF-compliant camera.

    Body options:
      { "host": "192.168.1.64", "port": 80, "username": "admin", "password": "admin" }
      { "scan": true, "subnet": "192.168.1", "username": "admin", "password": "admin" }
    """
    try:
        try:
            from onvif import ONVIFCamera
        except ImportError:
            return JSONResponse({
                'success': False,
                'error':   'onvif-zeep not installed. Run: pip install onvif-zeep',
                'cameras': [],
            })

        data     = await request.json() or {}
        username = data.get('username', 'admin')
        password = data.get('password', 'admin')

        if 'host' in data:
            hosts = [(data['host'], int(data.get('port', 80)))]
        elif data.get('scan'):
            subnet = data.get('subnet', '192.168.1')
            hosts  = [(f'{subnet}.{i}', 80) for i in range(1, 255)]
        else:
            return JSONResponse({'success': False,
                                  'error': 'Provide "host" or "scan":true + "subnet"',
                                  'cameras': []})

        def _probe_host(host, port):
            try:
                cam          = ONVIFCamera(host, port, username, password, no_cache=True)
                media_svc    = cam.create_media_service()
                device_svc   = cam.create_devicemgmt_service()
                device_info  = device_svc.GetDeviceInformation()
                profiles     = media_svc.GetProfiles()
                streams = []
                for profile in profiles:
                    req = media_svc.create_type('GetStreamUri')
                    req.ProfileToken  = profile.token
                    req.StreamSetup   = {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}}
                    uri = media_svc.GetStreamUri(req).Uri
                    if username and '@' not in uri:
                        uri = uri.replace('rtsp://', f'rtsp://{username}:{password}@')
                    res = 'unknown'
                    try:
                        enc = profile.VideoEncoderConfiguration
                        res = f"{enc.Resolution.Width}x{enc.Resolution.Height}"
                    except Exception:
                        pass
                    streams.append({'profile': profile.Name, 'token': profile.token,
                                    'rtsp_url': uri, 'resolution': res})
                return {
                    'host': host, 'port': port,
                    'manufacturer': device_info.Manufacturer,
                    'model':        device_info.Model,
                    'firmware':     device_info.FirmwareVersion,
                    'serial':       device_info.SerialNumber,
                    'streams':      streams,
                }
            except Exception:
                return None  # not ONVIF or unreachable

        results = []
        for host, port in hosts:
            r = await asyncio.to_thread(_probe_host, host, port)
            if r:
                results.append(r)

        return JSONResponse({'success': True, 'cameras_found': len(results), 'cameras': results})

    except Exception as e:
        return JSONResponse({'success': False, 'error': f'ONVIF discovery failed: {e}', 'cameras': []})
