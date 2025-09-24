/**
 * Enhanced Camera Management for Face Recognition System
 * Handles camera detection, testing, and platform-specific optimizations
 */

class EnhancedCameraManager {
    constructor() {
        this.detectedCameras = [];
        this.platformInfo = null;
        this.isDetecting = false;
        this.isTestingCamera = false;
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Bind methods to maintain context
        this.detectCameras = this.detectCameras.bind(this);
        this.testSelectedCamera = this.testSelectedCamera.bind(this);
        this.buildCustomUrl = this.buildCustomUrl.bind(this);
    }

    async detectCameras() {
        if (this.isDetecting) return;
        
        this.isDetecting = true;
        this.showDetectionStatus('🔍 Detecting cameras...', 'info');
        
        try {
            const response = await fetch('/api/cameras/detect');
            const data = await response.json();
            
            if (data.success) {
                this.detectedCameras = data.cameras;
                this.platformInfo = {
                    platform: data.platform,
                    hardware_info: data.hardware_info,
                    total_detected: data.total_detected
                };
                
                this.updateCameraDropdown(data.dropdown_options);
                this.showPlatformInfo(data);
                this.showDetectionStatus(`✅ Found ${data.total_detected} cameras`, 'success');
            } else {
                this.showDetectionStatus(`❌ Detection failed: ${data.error}`, 'error');
            }
        } catch (error) {
            console.error('Camera detection failed:', error);
            this.showDetectionStatus(`❌ Detection error: ${error.message}`, 'error');
        } finally {
            this.isDetecting = false;
        }
    }

    updateCameraDropdown(options) {
        const dropdown = document.getElementById('cameraDropdown');
        if (!dropdown) return;

        // Clear existing options
        dropdown.innerHTML = '<option value="">Select a camera...</option>';

        options.forEach(option => {
            if (option.type === 'header') {
                // Create optgroup for headers
                const optgroup = document.createElement('optgroup');
                optgroup.label = option.label;
                dropdown.appendChild(optgroup);
            } else {
                // Create option
                const optionElement = document.createElement('option');
                optionElement.value = JSON.stringify(option);
                optionElement.textContent = option.label;
                
                if (option.type === 'template') {
                    optionElement.style.fontStyle = 'italic';
                    optionElement.title = option.description || '';
                }
                
                // Add to last optgroup if it exists, otherwise to dropdown
                const lastOptgroup = dropdown.querySelector('optgroup:last-child');
                if (lastOptgroup && option.type !== 'manual') {
                    lastOptgroup.appendChild(optionElement);
                } else {
                    dropdown.appendChild(optionElement);
                }
            }
        });

        // Enable dropdown and show camera controls
        dropdown.disabled = false;
        this.showCameraControls(true);
    }

    showPlatformInfo(data) {
        const infoContainer = document.getElementById('platformInfo');
        if (!infoContainer) return;

        const platform = data.platform || 'unknown';
        const platformName = platform.charAt(0).toUpperCase() + platform.slice(1);
        
        let html = `
            <div class="platform-info">
                <h4>🖥️ Platform: ${platformName}</h4>
                <div class="hardware-recommendations">
                    ${data.hardware_info.map(rec => `<div class="recommendation">${rec}</div>`).join('')}
                </div>
            </div>
        `;
        
        infoContainer.innerHTML = html;
        infoContainer.style.display = 'block';
    }

    showCameraControls(show) {
        const controls = document.getElementById('cameraControls');
        if (controls) {
            controls.style.display = show ? 'block' : 'none';
        }
    }

    async testSelectedCamera() {
        const dropdown = document.getElementById('cameraDropdown');
        const selectedValue = dropdown.value;
        
        if (!selectedValue) {
            this.showTestStatus('Please select a camera first', 'warning');
            return;
        }

        if (this.isTestingCamera) return;
        this.isTestingCamera = true;

        try {
            let requestData;
            
            if (selectedValue === 'manual') {
                // Handle manual URL entry
                const manualUrl = document.getElementById('manualCameraUrl')?.value;
                if (!manualUrl) {
                    this.showTestStatus('Please enter a camera URL', 'warning');
                    return;
                }
                requestData = { url: manualUrl };
            } else {
                // Handle dropdown selection
                const cameraOption = JSON.parse(selectedValue);
                
                if (cameraOption.type === 'template') {
                    this.showTestStatus('⚠️ This is a template. Please customize the URL first.', 'warning');
                    this.showUrlBuilder(cameraOption);
                    return;
                }
                
                requestData = { camera_info: cameraOption.camera_info };
            }

            this.showTestStatus('🔄 Testing camera connection...', 'info');
            
            const response = await fetch('/api/cameras/test-advanced', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showTestStatus('✅ Camera test successful!', 'success');
                this.showTestResults(data);
            } else {
                this.showTestStatus(`❌ Test failed: ${data.message}`, 'error');
            }
            
        } catch (error) {
            console.error('Camera test failed:', error);
            this.showTestStatus(`❌ Test error: ${error.message}`, 'error');
        } finally {
            this.isTestingCamera = false;
        }
    }

    showTestResults(data) {
        const resultsContainer = document.getElementById('testResults');
        if (!resultsContainer) return;

        let html = `
            <div class="test-results">
                <h4>📊 Test Results</h4>
                <div class="result-item">
                    <strong>Camera:</strong> ${data.camera_info.name}
                </div>
                <div class="result-item">
                    <strong>Status:</strong> <span class="success">${data.message}</span>
                </div>
        `;

        if (data.test_properties) {
            html += `
                <div class="result-item">
                    <strong>Resolution:</strong> ${data.test_properties.resolution}
                </div>
                <div class="result-item">
                    <strong>FPS:</strong> ${data.test_properties.fps}
                </div>
                <div class="result-item">
                    <strong>Backend:</strong> ${data.test_properties.backend}
                </div>
            `;
        }

        if (data.recommended_settings) {
            html += `
                <div class="recommended-settings">
                    <h5>💡 Recommended Settings</h5>
                    <div class="setting-item">Resolution: ${data.recommended_settings.resolution}</div>
                    <div class="setting-item">FPS: ${data.recommended_settings.fps}</div>
                    <div class="setting-item">Backend: ${data.recommended_settings.backend}</div>
                </div>
            `;
        }

        html += '</div>';
        resultsContainer.innerHTML = html;
        resultsContainer.style.display = 'block';
    }

    showUrlBuilder(template) {
        const builderContainer = document.getElementById('urlBuilder');
        if (!builderContainer) return;

        let html = `
            <div class="url-builder">
                <h4>🔧 Customize Camera URL</h4>
                <div class="template-info">
                    <strong>Template:</strong> ${template.camera_info.name}
                    <br><strong>Format:</strong> <code>${template.camera_info.url}</code>
                    <br><strong>Description:</strong> ${template.camera_info.description || 'No description'}
                </div>
                
                <div class="builder-form">
                    <div class="form-row">
                        <label for="cameraIp">Camera IP Address:</label>
                        <input type="text" id="cameraIp" placeholder="192.168.1.100" />
                    </div>
                    
                    <div class="form-row">
                        <label for="cameraPort">Port (optional):</label>
                        <input type="text" id="cameraPort" placeholder="554" />
                    </div>
                    
                    <div class="form-row">
                        <label for="cameraUsername">Username:</label>
                        <input type="text" id="cameraUsername" placeholder="admin" />
                    </div>
                    
                    <div class="form-row">
                        <label for="cameraPassword">Password:</label>
                        <input type="password" id="cameraPassword" placeholder="password" />
                    </div>
                    
                    <button onclick="enhancedCameraManager.buildCustomUrl('${template.id}')" class="btn btn-primary">
                        🔗 Build URL
                    </button>
                </div>
                
                <div id="builtUrls" style="display: none;"></div>
            </div>
        `;

        builderContainer.innerHTML = html;
        builderContainer.style.display = 'block';
    }

    async buildCustomUrl(templateId) {
        const ip = document.getElementById('cameraIp')?.value;
        const port = document.getElementById('cameraPort')?.value;
        const username = document.getElementById('cameraUsername')?.value;
        const password = document.getElementById('cameraPassword')?.value;

        if (!ip) {
            this.showTestStatus('Please enter an IP address', 'warning');
            return;
        }

        try {
            // Determine camera type and brand from template
            const template = this.detectedCameras.find(cam => cam.id === templateId);
            let type = 'rtsp';
            let brand = 'generic';

            if (template) {
                type = template.type || 'rtsp';
                if (template.name.toLowerCase().includes('hikvision')) brand = 'hikvision';
                else if (template.name.toLowerCase().includes('dahua')) brand = 'dahua';
                else if (template.name.toLowerCase().includes('axis')) brand = 'axis';
            }

            const response = await fetch('/api/cameras/url-builder', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    type: type,
                    brand: brand,
                    ip: ip,
                    port: port,
                    username: username,
                    password: password
                })
            });

            const data = await response.json();

            if (data.success) {
                this.showBuiltUrls(data.built_urls);
            } else {
                this.showTestStatus(`URL building failed: ${data.error}`, 'error');
            }

        } catch (error) {
            console.error('URL building failed:', error);
            this.showTestStatus(`URL building error: ${error.message}`, 'error');
        }
    }

    showBuiltUrls(urls) {
        const container = document.getElementById('builtUrls');
        if (!container) return;

        let html = `
            <div class="built-urls">
                <h5>🔗 Generated URLs</h5>
        `;

        urls.forEach(urlData => {
            html += `
                <div class="url-item">
                    <div class="url-name">${urlData.name}</div>
                    <div class="url-value">
                        <code>${urlData.url}</code>
                        <button onclick="enhancedCameraManager.testCustomUrl('${urlData.url.replace(/'/g, '\\\'')}')" 
                                class="btn btn-sm btn-outline">
                            Test
                        </button>
                        <button onclick="enhancedCameraManager.useCustomUrl('${urlData.url.replace(/'/g, '\\\'')}')" 
                                class="btn btn-sm btn-success">
                            Use This URL
                        </button>
                    </div>
                </div>
            `;
        });

        html += '</div>';
        container.innerHTML = html;
        container.style.display = 'block';
    }

    async testCustomUrl(url) {
        if (this.isTestingCamera) return;
        this.isTestingCamera = true;

        try {
            this.showTestStatus('🔄 Testing custom URL...', 'info');

            const response = await fetch('/api/cameras/test-advanced', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: url })
            });

            const data = await response.json();

            if (data.success) {
                this.showTestStatus('✅ Custom URL test successful!', 'success');
                this.showTestResults(data);
            } else {
                this.showTestStatus(`❌ Test failed: ${data.message}`, 'error');
            }

        } catch (error) {
            console.error('Custom URL test failed:', error);
            this.showTestStatus(`❌ Test error: ${error.message}`, 'error');
        } finally {
            this.isTestingCamera = false;
        }
    }

    useCustomUrl(url) {
        // Fill the manual URL input and select manual option
        const manualInput = document.getElementById('manualCameraUrl');
        const dropdown = document.getElementById('cameraDropdown');
        
        if (manualInput) {
            manualInput.value = url;
        }
        
        if (dropdown) {
            dropdown.value = 'manual';
        }

        // Hide URL builder
        const builder = document.getElementById('urlBuilder');
        if (builder) {
            builder.style.display = 'none';
        }

        this.showTestStatus('📋 URL copied to manual entry field', 'info');
    }

    showDetectionStatus(message, type) {
        this.showStatus('detectionStatus', message, type);
    }

    showTestStatus(message, type) {
        this.showStatus('testStatus', message, type);
    }

    showStatus(containerId, message, type) {
        const container = document.getElementById(containerId);
        if (!container) return;

        container.innerHTML = `<div class="status-message ${type}">${message}</div>`;
        container.style.display = 'block';

        // Auto-hide success/info messages after 5 seconds
        if (type === 'success' || type === 'info') {
            setTimeout(() => {
                container.style.display = 'none';
            }, 5000);
        }
    }

    // Handle dropdown change
    onCameraSelectionChange() {
        const dropdown = document.getElementById('cameraDropdown');
        const manualSection = document.getElementById('manualUrlSection');
        const testResults = document.getElementById('testResults');
        const urlBuilder = document.getElementById('urlBuilder');

        // Hide previous results
        if (testResults) testResults.style.display = 'none';
        if (urlBuilder) urlBuilder.style.display = 'none';

        if (dropdown.value === 'manual') {
            // Show manual URL input
            if (manualSection) manualSection.style.display = 'block';
        } else {
            // Hide manual URL input
            if (manualSection) manualSection.style.display = 'none';
        }
    }

    // Initialize camera detection on page load
    init() {
        console.log('Enhanced Camera Manager initialized');
        
        // Auto-detect cameras on page load
        setTimeout(() => {
            this.detectCameras();
        }, 1000);

        // Setup dropdown change handler
        const dropdown = document.getElementById('cameraDropdown');
        if (dropdown) {
            dropdown.addEventListener('change', () => this.onCameraSelectionChange());
        }
    }
}

// Global instance
const enhancedCameraManager = new EnhancedCameraManager();

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    enhancedCameraManager.init();
});