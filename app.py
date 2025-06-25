#!/usr/bin/env python3
"""
Remote Desktop Broker Server - Production Ready
Flask server with WebSocket support for Render.com deployment
"""

from flask import Flask, request, jsonify
from flask_sock import Sock
import json
import logging
import time
from collections import defaultdict
import os

# ### REPLACED threading with eventlet for non-blocking concurrency ###
import eventlet
# Since we are using an eventlet worker, we must use its non-blocking tools
eventlet.monkey_patch()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
sock = Sock(app)

# Global session management is now handled by the SessionManager instance

# Connection cleanup interval
CLEANUP_INTERVAL = 60  # seconds
INACTIVE_TIMEOUT = 300  # 5 minutes

class SessionManager:
    def __init__(self):
        self.sessions = {}
        # ### REPLACED threading.Lock with an eventlet-friendly Semaphore ###
        self.lock = eventlet.semaphore.Semaphore(1)
        
    def create_session(self, password):
        """Create a new session (internal, lock should be held)"""
        if password not in self.sessions:
            self.sessions[password] = {
                'client_ws': None,
                'helper_ws': None,
                'last_activity': time.time(),
                'active': True
            }
            logger.info(f"Created session: {password[:8]}...")
    
    def add_connection(self, password, role, websocket):
        """Add a connection to a session"""
        with self.lock:
            if password not in self.sessions:
                self.create_session(password)
            
            self.sessions[password][f'{role}_ws'] = websocket
            self.sessions[password]['last_activity'] = time.time()
            logger.info(f"Added {role} to session: {password[:8]}...")
    
    def remove_connection(self, password, role):
        """Remove a connection from a session"""
        with self.lock:
            if password in self.sessions:
                self.sessions[password][f'{role}_ws'] = None
                self.sessions[password]['last_activity'] = time.time()
                logger.info(f"Removed {role} from session: {password[:8]}...")
                
                # Clean up empty sessions
                if (self.sessions[password]['client_ws'] is None and 
                    self.sessions[password]['helper_ws'] is None):
                    del self.sessions[password]
                    logger.info(f"Cleaned up empty session: {password[:8]}...")
    
    def get_peer_ws(self, password, role):
        """Get the peer WebSocket for message forwarding"""
        with self.lock:
            if password in self.sessions:
                peer_role = 'helper' if role == 'client' else 'client'
                return self.sessions[password].get(f'{peer_role}_ws')
            return None
    
    def update_activity(self, password):
        """Update last activity timestamp"""
        with self.lock:
            if password in self.sessions:
                self.sessions[password]['last_activity'] = time.time()
    
    def cleanup_inactive_sessions(self):
        """Remove inactive sessions"""
        current_time = time.time()
        to_remove = []
        
        with self.lock:
            # Create a copy of items to avoid dictionary size change during iteration
            for password, session in list(self.sessions.items()):
                if current_time - session['last_activity'] > INACTIVE_TIMEOUT:
                    to_remove.append(password)
        
        # Lock again to perform the removal
        with self.lock:
            for password in to_remove:
                if password in self.sessions:
                    del self.sessions[password]
                    logger.info(f"Cleaned up inactive session: {password[:8]}...")

# Initialize session manager
session_manager = SessionManager()

def cleanup_loop():
    """Background greenlet for session cleanup"""
    while True:
        try:
            session_manager.cleanup_inactive_sessions()
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        # Use eventlet's non-blocking sleep
        eventlet.sleep(CLEANUP_INTERVAL)

# ### REPLACED threading.Thread with eventlet.spawn ###
# Start cleanup greenlet
eventlet.spawn(cleanup_loop)


# (Your HTML and other routes remain the same)
# ... The entire HELPER_HTML string goes here ...
HELPER_HTML = """
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
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        
        .container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.1);
            text-align: center;
            min-width: 400px;
        }
        
        .title {
            color: #333;
            margin-bottom: 30px;
            font-size: 2rem;
            font-weight: 300;
        }
        
        .login-form {
            margin-bottom: 20px;
        }
        
        .input-group {
            margin-bottom: 20px;
        }
        
        .input-group input {
            width: 100%;
            padding: 15px;
            border: 2px solid #e1e1e1;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        
        .input-group input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            transition: transform 0.2s;
            width: 100%;
        }
        
        .btn:hover {
            transform: translateY(-2px);
        }
        
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .status {
            margin-top: 15px;
            padding: 10px;
            border-radius: 5px;
            font-weight: bold;
        }
        
        .status.connected {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .status.error {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .status.connecting {
            background-color: #fff3cd;
            color: #856404;
            border: 1px solid #ffeaa7;
        }
        
        .screen-container {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: #000;
            z-index: 1000;
        }
        
        .screen-container.active {
            display: block;
        }
        
        .screen-header {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 40px;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 20px;
            z-index: 1001;
        }
        
        .disconnect-btn {
            background: #dc3545;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        
        .disconnect-btn:hover {
            background: #c82333;
        }
        
        .screen-view {
            width: 100%;
            height: 100%;
            object-fit: contain;
            cursor: none;
            user-select: none;
            padding-top: 40px;
        }
        
        .fps-counter {
            position: absolute;
            top: 50px;
            right: 20px;
            color: #00ff00;
            font-family: monospace;
            font-size: 12px;
            background: rgba(0, 0, 0, 0.7);
            padding: 5px 10px;
            border-radius: 3px;
        }
    </style>
</head>
<body>
    <div class="container" id="loginContainer">
        <h1 class="title">Remote Desktop Helper</h1>
        <div class="login-form">
            <div class="input-group">
                <input type="password" id="passwordInput" placeholder="Enter session password" />
            </div>
            <button class="btn" id="connectBtn" onclick="connect()">Connect</button>
        </div>
        <div class="status" id="status" style="display: none;"></div>
    </div>
    
    <div class="screen-container" id="screenContainer">
        <div class="screen-header">
            <span id="sessionInfo">Remote Desktop Session</span>
            <div>
                <span class="fps-counter" id="fpsCounter">FPS: 0</span>
                <button class="disconnect-btn" onclick="disconnect()">Disconnect</button>
            </div>
        </div>
        <img id="screenView" class="screen-view" />
    </div>

    <script>
        let ws = null;
        let connected = false;
        let frameCount = 0;
        let lastFpsUpdate = Date.now();
        
        // UI Elements
        const loginContainer = document.getElementById('loginContainer');
        const screenContainer = document.getElementById('screenContainer');
        const passwordInput = document.getElementById('passwordInput');
        const connectBtn = document.getElementById('connectBtn');
        const status = document.getElementById('status');
        const screenView = document.getElementById('screenView');
        const sessionInfo = document.getElementById('sessionInfo');
        const fpsCounter = document.getElementById('fpsCounter');
        
        // Keyboard tracking
        const pressedKeys = new Set();
        
        function showStatus(message, type = 'info') {
            status.textContent = message;
            status.className = `status ${type}`;
            status.style.display = 'block';
        }
        
        function hideStatus() {
            status.style.display = 'none';
        }
        
        function updateFPS() {
            const now = Date.now();
            if (now - lastFpsUpdate >= 1000) {
                fpsCounter.textContent = `FPS: ${frameCount}`;
                frameCount = 0;
                lastFpsUpdate = now;
            }
        }
        
        function connect() {
            const password = passwordInput.value.trim();
            if (!password) {
                showStatus('Please enter a password', 'error');
                return;
            }
            
            connectBtn.disabled = true;
            showStatus('Connecting...', 'connecting');
            
            try {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/connect`;
                
                ws = new WebSocket(wsUrl);
                
                ws.onopen = function() {
                    // Send handshake
                    const handshake = {
                        role: 'helper',
                        password: password
                    };
                    ws.send(JSON.stringify(handshake));
                };
                
                ws.onmessage = function(event) {
                    try {
                        if (event.data.startsWith('s:')) {
                            // Screen data
                            const base64Data = event.data.substring(2);
                            screenView.src = `data:image/jpeg;base64,${base64Data}`;
                            frameCount++;
                            updateFPS();
                            
                            if (!connected) {
                                connected = true;
                                loginContainer.style.display = 'none';
                                screenContainer.classList.add('active');
                                sessionInfo.textContent = `Session: ${password.substring(0, 8)}...`;
                                setupInputHandlers();
                            }
                        }
                    } catch (error) {
                        console.error('Message handling error:', error);
                    }
                };
                
                ws.onclose = function(event) {
                    connected = false;
                    connectBtn.disabled = false;
                    screenContainer.classList.remove('active');
                    loginContainer.style.display = 'block';
                    
                    if (event.code === 1000) {
                        showStatus('Disconnected', 'info');
                    } else {
                        showStatus('Connection lost. Please try again.', 'error');
                    }
                };
                
                ws.onerror = function(error) {
                    console.error('WebSocket error:', error);
                    showStatus('Connection error. Please try again.', 'error');
                    connectBtn.disabled = false;
                };
                
            } catch (error) {
                console.error('Connection error:', error);
                showStatus('Failed to connect. Please try again.', 'error');
                connectBtn.disabled = false;
            }
        }
        
        function disconnect() {
            if (ws) {
                ws.close();
            }
        }
        
        function setupInputHandlers() {
            // Mouse events
            screenView.addEventListener('mousemove', function(e) {
                if (!connected || !ws) return;
                
                const rect = screenView.getBoundingClientRect();
                const x = (e.clientX - rect.left) / rect.width;
                const y = (e.clientY - rect.top) / rect.height;
                
                const msg = {
                    type: 'mousemove',
                    x: Math.max(0, Math.min(1, x)),
                    y: Math.max(0, Math.min(1, y))
                };
                
                ws.send(JSON.stringify(msg));
            });
            
            screenView.addEventListener('mousedown', function(e) {
                if (!connected || !ws) return;
                e.preventDefault();
                
                const button = e.button === 0 ? 'left' : 'right';
                const msg = {
                    type: 'mousedown',
                    button: button
                };
                
                ws.send(JSON.stringify(msg));
            });
            
            screenView.addEventListener('mouseup', function(e) {
                if (!connected || !ws) return;
                e.preventDefault();
                
                const button = e.button === 0 ? 'left' : 'right';
                const msg = {
                    type: 'mouseup',
                    button: button
                };
                
                ws.send(JSON.stringify(msg));
            });
            
            screenView.addEventListener('contextmenu', function(e) {
                e.preventDefault();
            });
            
            screenView.addEventListener('wheel', function(e) {
                if (!connected || !ws) return;
                e.preventDefault();
                
                const msg = {
                    type: 'scroll',
                    delta: -e.deltaY / 100
                };
                
                ws.send(JSON.stringify(msg));
            });
            
            // Keyboard events
            document.addEventListener('keydown', function(e) {
                if (!connected || !ws) return;
                
                const key = e.key;
                if (pressedKeys.has(key)) return; // Prevent key repeat
                
                pressedKeys.add(key);
                
                const msg = {
                    type: 'keydown',
                    key: key.length === 1 ? key : e.code.replace('Key', '').toLowerCase()
                };
                
                ws.send(JSON.stringify(msg));
                e.preventDefault();
            });
            
            document.addEventListener('keyup', function(e) {
                if (!connected || !ws) return;
                
                const key = e.key;
                pressedKeys.delete(key);
                
                const msg = {
                    type: 'keyup',
                    key: key.length === 1 ? key : e.code.replace('Key', '').toLowerCase()
                };
                
                ws.send(JSON.stringify(msg));
                e.preventDefault();
            });
            
            // Focus management
            window.addEventListener('blur', function() {
                pressedKeys.clear();
            });
        }
        
        // Enter key to connect
        passwordInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                connect();
            }
        });
        
        // Auto-focus password input
        passwordInput.focus();
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Serve the helper interface"""
    return HELPER_HTML

@app.route('/health')
def health_check():
    """Health check endpoint for Render.com"""
    # Use the lock to safely get the number of sessions
    with session_manager.lock:
        num_sessions = len(session_manager.sessions)
    return jsonify({
        'status': 'healthy',
        'sessions': num_sessions,
        'timestamp': time.time()
    })

@sock.route('/ws/connect')
def websocket_handler(ws):
    """Main WebSocket endpoint for both clients and helpers"""
    password = None
    role = None
    
    try:
        # Wait for handshake message
        handshake_data = ws.receive(timeout=10)
        if handshake_data is None:
            return # Connection closed before handshake
        handshake = json.loads(handshake_data)
        
        password = handshake.get('password', '').strip()
        role = handshake.get('role', '').strip()
        
        if not password or not role or role not in ['client', 'helper']:
            # Silently close for invalid handshake to prevent probing
            return
        
        # Add connection to session
        session_manager.add_connection(password, role, ws)
        
        logger.info(f"WebSocket connected: {role} for session {password[:8]}...")
        
        # Message forwarding loop
        while True:
            message = ws.receive()
            if message is None:
                # Connection closed by client
                break
                
            session_manager.update_activity(password)
            
            peer_ws = session_manager.get_peer_ws(password, role)
            if peer_ws:
                try:
                    peer_ws.send(message)
                except Exception:
                    # Peer has likely disconnected, break the loop
                    break
    
    except Exception as e:
        # Log most exceptions, but treat timeouts/closed connections as normal
        if "timeout" not in str(e).lower() and "closed" not in str(e).lower():
            logger.error(f"WebSocket handler error: {e}")
    
    finally:
        # Clean up connection
        if password and role:
            session_manager.remove_connection(password, role)
            logger.info(f"WebSocket disconnected: {role} for session {password[:8]}...")

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # This part is for local development and not used by Gunicorn
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
