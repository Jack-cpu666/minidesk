#!/usr/bin/env python3
"""
Remote Desktop Broker Server
Relays WebSocket messages between client and helper
Compatible with Render.com deployment
"""

from flask import Flask, render_template_string
from flask_sock import Sock
import json
import logging
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
sock = Sock(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Session management
sessions = {}

# HTML/CSS/JS for helper interface
HELPER_INTERFACE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Remote Desktop Helper</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a1a;
            color: #fff;
            overflow: hidden;
        }
        
        #login-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
        }
        
        .login-box {
            background: rgba(255, 255, 255, 0.1);
            padding: 40px;
            border-radius: 10px;
            backdrop-filter: blur(10px);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            text-align: center;
            max-width: 400px;
            width: 100%;
        }
        
        .login-box h1 {
            margin-bottom: 30px;
            font-size: 28px;
            font-weight: 300;
        }
        
        .login-box input {
            width: 100%;
            padding: 12px 16px;
            margin-bottom: 20px;
            border: 1px solid rgba(255, 255, 255, 0.3);
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            border-radius: 5px;
            font-size: 16px;
            transition: all 0.3s ease;
        }
        
        .login-box input:focus {
            outline: none;
            border-color: #3498db;
            background: rgba(255, 255, 255, 0.15);
        }
        
        .login-box input::placeholder {
            color: rgba(255, 255, 255, 0.6);
        }
        
        .login-box button {
            width: 100%;
            padding: 12px 24px;
            background: #3498db;
            color: #fff;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        .login-box button:hover {
            background: #2980b9;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(52, 152, 219, 0.4);
        }
        
        .login-box button:disabled {
            background: #7f8c8d;
            cursor: not-allowed;
            transform: none;
        }
        
        #screen-container {
            display: none;
            position: relative;
            width: 100vw;
            height: 100vh;
            background: #000;
        }
        
        #screen-view {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: contain;
            cursor: crosshair;
            user-select: none;
            -webkit-user-select: none;
            -moz-user-select: none;
            -ms-user-select: none;
        }
        
        #status-bar {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            background: rgba(0, 0, 0, 0.8);
            color: #fff;
            padding: 10px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 14px;
            backdrop-filter: blur(10px);
            z-index: 1000;
        }
        
        .status-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 8px;
            background: #e74c3c;
        }
        
        .status-indicator.connected {
            background: #2ecc71;
        }
        
        .disconnect-btn {
            padding: 6px 16px;
            background: #e74c3c;
            color: #fff;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s ease;
        }
        
        .disconnect-btn:hover {
            background: #c0392b;
        }
        
        #error-message {
            display: none;
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(231, 76, 60, 0.9);
            color: #fff;
            padding: 20px 30px;
            border-radius: 8px;
            font-size: 16px;
            z-index: 2000;
            backdrop-filter: blur(10px);
        }
        
        .loading-spinner {
            display: none;
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 50px;
            height: 50px;
            border: 3px solid rgba(255, 255, 255, 0.3);
            border-top-color: #3498db;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            z-index: 1001;
        }
        
        @keyframes spin {
            to { transform: translate(-50%, -50%) rotate(360deg); }
        }
    </style>
</head>
<body>
    <div id="login-container">
        <div class="login-box">
            <h1>Remote Desktop Helper</h1>
            <input type="password" id="password-input" placeholder="Enter session password" autocomplete="off">
            <button id="connect-btn" onclick="connect()">Connect</button>
        </div>
    </div>
    
    <div id="screen-container">
        <div id="status-bar">
            <div>
                <span class="status-indicator" id="status-indicator"></span>
                <span id="status-text">Disconnected</span>
                <span id="fps-counter" style="margin-left: 20px;"></span>
            </div>
            <button class="disconnect-btn" onclick="disconnect()">Disconnect</button>
        </div>
        <img id="screen-view" alt="Remote Screen">
        <div class="loading-spinner" id="loading-spinner"></div>
        <div id="error-message"></div>
    </div>
    
    <script>
        let ws = null;
        let isConnected = false;
        let lastFrameTime = Date.now();
        let frameCount = 0;
        let fps = 0;
        
        // Key mappings
        const keyMap = {
            'Enter': 'enter',
            'Tab': 'tab',
            ' ': 'space',
            'Backspace': 'backspace',
            'Delete': 'delete',
            'Escape': 'escape',
            'ArrowUp': 'up',
            'ArrowDown': 'down',
            'ArrowLeft': 'left',
            'ArrowRight': 'right',
            'Home': 'home',
            'End': 'end',
            'PageUp': 'page_up',
            'PageDown': 'page_down',
            'CapsLock': 'caps_lock',
            'Shift': 'shift',
            'Control': 'ctrl',
            'Alt': 'alt',
            'Meta': 'cmd',
            'F1': 'f1',
            'F2': 'f2',
            'F3': 'f3',
            'F4': 'f4',
            'F5': 'f5',
            'F6': 'f6',
            'F7': 'f7',
            'F8': 'f8',
            'F9': 'f9',
            'F10': 'f10',
            'F11': 'f11',
            'F12': 'f12'
        };
        
        function connect() {
            const password = document.getElementById('password-input').value;
            if (!password) {
                alert('Please enter a password');
                return;
            }
            
            document.getElementById('connect-btn').disabled = true;
            document.getElementById('connect-btn').textContent = 'Connecting...';
            
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/connect`;
            
            ws = new WebSocket(wsUrl);
            
            ws.onopen = () => {
                // Send handshake
                ws.send(JSON.stringify({
                    role: 'helper',
                    password: password
                }));
                
                isConnected = true;
                document.getElementById('login-container').style.display = 'none';
                document.getElementById('screen-container').style.display = 'block';
                document.getElementById('status-indicator').classList.add('connected');
                document.getElementById('status-text').textContent = 'Connected';
                document.getElementById('loading-spinner').style.display = 'block';
                
                // Setup event listeners
                setupEventListeners();
            };
            
            ws.onmessage = (event) => {
                const data = event.data;
                
                // Check if it's screen data
                if (data.startsWith('s:')) {
                    const base64Data = data.substring(2);
                    const img = document.getElementById('screen-view');
                    img.src = `data:image/jpeg;base64,${base64Data}`;
                    
                    // Hide loading spinner on first frame
                    document.getElementById('loading-spinner').style.display = 'none';
                    
                    // Update FPS counter
                    updateFPS();
                }
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                showError('Connection error occurred');
            };
            
            ws.onclose = () => {
                isConnected = false;
                document.getElementById('status-indicator').classList.remove('connected');
                document.getElementById('status-text').textContent = 'Disconnected';
                showError('Connection closed');
                setTimeout(() => {
                    location.reload();
                }, 2000);
            };
        }
        
        function disconnect() {
            if (ws) {
                ws.close();
            }
            location.reload();
        }
        
        function setupEventListeners() {
            const screen = document.getElementById('screen-view');
            
            // Mouse events
            screen.addEventListener('mousemove', (e) => {
                if (!isConnected) return;
                
                const rect = screen.getBoundingClientRect();
                const x = (e.clientX - rect.left) / rect.width;
                const y = (e.clientY - rect.top) / rect.height;
                
                sendCommand({
                    type: 'mousemove',
                    x: Math.max(0, Math.min(1, x)),
                    y: Math.max(0, Math.min(1, y))
                });
            });
            
            screen.addEventListener('mousedown', (e) => {
                if (!isConnected) return;
                e.preventDefault();
                
                const button = e.button === 0 ? 'left' : e.button === 2 ? 'right' : 'middle';
                sendCommand({
                    type: 'mousedown',
                    button: button
                });
            });
            
            screen.addEventListener('mouseup', (e) => {
                if (!isConnected) return;
                e.preventDefault();
                
                const button = e.button === 0 ? 'left' : e.button === 2 ? 'right' : 'middle';
                sendCommand({
                    type: 'mouseup',
                    button: button
                });
            });
            
            screen.addEventListener('dblclick', (e) => {
                if (!isConnected) return;
                e.preventDefault();
                
                sendCommand({
                    type: 'doubleclick',
                    button: 'left'
                });
            });
            
            screen.addEventListener('wheel', (e) => {
                if (!isConnected) return;
                e.preventDefault();
                
                sendCommand({
                    type: 'scroll',
                    dx: e.deltaX / 100,
                    dy: e.deltaY / 100
                });
            });
            
            // Disable context menu
            screen.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                return false;
            });
            
            // Keyboard events
            document.addEventListener('keydown', (e) => {
                if (!isConnected) return;
                
                // Don't capture F5, F11, etc. for browser functionality
                if (e.key === 'F5' || (e.key === 'F11' && !e.ctrlKey && !e.altKey)) {
                    return;
                }
                
                e.preventDefault();
                
                const key = keyMap[e.key] || e.key.toLowerCase();
                sendCommand({
                    type: 'keydown',
                    key: key
                });
            });
            
            document.addEventListener('keyup', (e) => {
                if (!isConnected) return;
                
                if (e.key === 'F5' || (e.key === 'F11' && !e.ctrlKey && !e.altKey)) {
                    return;
                }
                
                e.preventDefault();
                
                const key = keyMap[e.key] || e.key.toLowerCase();
                sendCommand({
                    type: 'keyup',
                    key: key
                });
            });
        }
        
        function sendCommand(command) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify(command));
            }
        }
        
        function showError(message) {
            const errorEl = document.getElementById('error-message');
            errorEl.textContent = message;
            errorEl.style.display = 'block';
            setTimeout(() => {
                errorEl.style.display = 'none';
            }, 5000);
        }
        
        function updateFPS() {
            frameCount++;
            const now = Date.now();
            const delta = now - lastFrameTime;
            
            if (delta >= 1000) {
                fps = Math.round((frameCount * 1000) / delta);
                document.getElementById('fps-counter').textContent = `${fps} FPS`;
                frameCount = 0;
                lastFrameTime = now;
            }
        }
        
        // Allow Enter key to connect
        document.getElementById('password-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                connect();
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Serve the helper interface"""
    return render_template_string(HELPER_INTERFACE)

@sock.route('/ws/connect')
def websocket_handler(ws):
    """Handle WebSocket connections"""
    role = None
    password = None
    
    try:
        # Wait for handshake message
        handshake_data = ws.receive()
        handshake = json.loads(handshake_data)
        
        role = handshake.get('role')
        password = handshake.get('password')
        
        if not role or not password:
            ws.send(json.dumps({'error': 'Invalid handshake'}))
            return
        
        logger.info(f"New {role} connection for session: {password}")
        
        # Initialize session if doesn't exist
        if password not in sessions:
            sessions[password] = {'client_ws': None, 'helper_ws': None}
        
        # Store WebSocket reference
        if role == 'client':
            sessions[password]['client_ws'] = ws
        elif role == 'helper':
            sessions[password]['helper_ws'] = ws
        else:
            ws.send(json.dumps({'error': 'Invalid role'}))
            return
        
        # Message relay loop
        while True:
            message = ws.receive()
            if message is None:
                break
            
            # Relay message to the other party
            if role == 'client' and sessions[password]['helper_ws']:
                try:
                    sessions[password]['helper_ws'].send(message)
                except Exception as e:
                    logger.error(f"Error relaying to helper: {e}")
                    
            elif role == 'helper' and sessions[password]['client_ws']:
                try:
                    sessions[password]['client_ws'].send(message)
                except Exception as e:
                    logger.error(f"Error relaying to client: {e}")
    
    except json.JSONDecodeError:
        logger.error("Invalid JSON in handshake")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Clean up on disconnect
        if password and password in sessions:
            if role == 'client':
                sessions[password]['client_ws'] = None
            elif role == 'helper':
                sessions[password]['helper_ws'] = None
            
            # Remove empty sessions
            if sessions[password]['client_ws'] is None and sessions[password]['helper_ws'] is None:
                del sessions[password]
        
        logger.info(f"{role} disconnected from session: {password}")

if __name__ == '__main__':
    # Development server
    app.run(debug=True, host='0.0.0.0', port=5000)
