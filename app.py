import os
import json
import logging
import gevent
import redis
from flask import Flask, Response
from flask_sock import Sock

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Flask App & Redis Initialization ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secret-key-for-dev')
sock = Sock(app)

# Connect to Redis using the URL provided by Render's environment variables
# This will automatically handle authentication.
try:
    redis_url = os.environ.get('REDIS_URL')
    if not redis_url:
        raise ValueError("REDIS_URL environment variable not set. Please add a Redis instance on Render.")
    redis_client = redis.from_url(redis_url, decode_responses=True)
    redis_client.ping() # Check the connection
    logging.info("Successfully connected to Redis.")
except Exception as e:
    logging.error(f"FATAL: Could not connect to Redis: {e}")
    # In a real-world scenario, you might prevent the app from starting.
    redis_client = None

# --- Helper Interface (No Changes Needed Here) ---
# [The HELPER_INTERFACE_HTML string remains exactly the same as before]
HELPER_INTERFACE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Remote Control Helper</title>
    <style>
        body, html { margin: 0; padding: 0; height: 100%; overflow: hidden; background-color: #1a1a1a; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        #auth-container { display: flex; align-items: center; justify-content: center; height: 100%; flex-direction: column; gap: 15px; }
        #auth-container input { padding: 10px; width: 200px; background-color: #333; border: 1px solid #555; color: #fff; border-radius: 4px; }
        #auth-container button { padding: 10px 20px; cursor: pointer; background-color: #007bff; color: white; border: none; border-radius: 4px; font-weight: bold; }
        #auth-container button:hover { background-color: #0056b3; }
        #main-container { display: none; width: 100%; height: 100%; }
        #screen-view { width: 100%; height: 100%; object-fit: contain; cursor: crosshair; }
        #status-bar { position: fixed; top: 0; left: 0; background-color: rgba(0,0,0,0.7); padding: 5px 10px; font-size: 14px; border-bottom-right-radius: 5px; }
    </style>
</head>
<body>
    <div id="auth-container">
        <h2>Enter Session Password</h2>
        <input type="password" id="password-input" placeholder="Password">
        <button id="connect-btn">Connect</button>
    </div>
    <div id="main-container">
        <div id="status-bar">Status: Disconnected</div>
        <img id="screen-view" alt="Remote screen stream">
    </div>
    <script>
        const passwordInput = document.getElementById('password-input');
        const connectBtn = document.getElementById('connect-btn');
        const authContainer = document.getElementById('auth-container');
        const mainContainer = document.getElementById('main-container');
        const screenView = document.getElementById('screen-view');
        const statusBar = document.getElementById('status-bar');
        let ws;
        const MOUSE_BUTTON_MAP = { 0: 'left', 1: 'middle', 2: 'right' };
        const KEY_MAP = {"Control": "ctrl", "Shift": "shift", "Alt": "alt","Meta": "cmd", "ArrowUp": "up", "ArrowDown": "down","ArrowLeft": "left", "ArrowRight": "right", "Enter": "enter","Escape": "esc", "Backspace": "backspace", "Tab": "tab","Delete": "delete", "Insert": "insert", "Home": "home", "End": "end","PageUp": "page_up", "PageDown": "page_down","F1": "f1", "F2": "f2", "F3": "f3", "F4": "f4","F5": "f5", "F6": "f6", "F7": "f7", "F8": "f8","F9": "f9", "F10": "f10", "F11": "f11", "F12": "f12",};
        function connect() {
            const password = passwordInput.value;
            if (!password) {alert("Please enter a password."); return;}
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${wsProtocol}//${window.location.host}/ws/connect`;
            ws = new WebSocket(wsUrl);
            ws.onopen = () => {
                console.log("WebSocket connection opened.");
                statusBar.textContent = 'Status: Authenticating...';
                ws.send(JSON.stringify({role: 'helper', password: password}));
            };
            ws.onmessage = (event) => {
                if (event.data.startsWith('s:')) {
                    if (authContainer.style.display !== 'none') {
                        authContainer.style.display = 'none';
                        mainContainer.style.display = 'block';
                        statusBar.textContent = 'Status: Connected';
                    }
                    screenView.src = 'data:image/jpeg;base64,' + event.data.substring(2);
                } else {console.log("Received non-screen data:", event.data);}
            };
            ws.onclose = () => {
                console.log("WebSocket connection closed.");
                statusBar.textContent = 'Status: Disconnected';
                alert("Connection lost. Please reconnect.");
                mainContainer.style.display = 'none';
                authContainer.style.display = 'flex';
                ws = null;
            };
            ws.onerror = (error) => {
                console.error("WebSocket error:", error);
                statusBar.textContent = 'Status: Error';
                alert("Connection error occurred.");
            };
        }
        connectBtn.addEventListener('click', connect);
        passwordInput.addEventListener('keyup', (event) => { if (event.key === 'Enter') {connect();} });
        function sendControlMessage(data) { if (ws && ws.readyState === WebSocket.OPEN) {ws.send(JSON.stringify(data));} }
        screenView.addEventListener('mousemove', (e) => {
            const rect = screenView.getBoundingClientRect(); const x = e.clientX - rect.left; const y = e.clientY - rect.top;
            sendControlMessage({ type: 'mouse_move', x: x / rect.width, y: y / rect.height });
        });
        screenView.addEventListener('mousedown', (e) => {
            e.preventDefault(); const rect = screenView.getBoundingClientRect(); const x = e.clientX - rect.left; const y = e.clientY - rect.top;
            sendControlMessage({ type: 'mouse_down', x: x / rect.width, y: y / rect.height, button: MOUSE_BUTTON_MAP[e.button] });
        });
        screenView.addEventListener('mouseup', (e) => {
            e.preventDefault(); const rect = screenView.getBoundingClientRect(); const x = e.clientX - rect.left; const y = e.clientY - rect.top;
            sendControlMessage({ type: 'mouse_up', x: x / rect.width, y: y / rect.height, button: MOUSE_BUTTON_MAP[e.button] });
        });
        screenView.addEventListener('wheel', (e) => { e.preventDefault(); sendControlMessage({ type: 'mouse_scroll', dx: -e.deltaX, dy: -e.deltaY }); });
        screenView.addEventListener('contextmenu', (e) => e.preventDefault());
        document.addEventListener('keydown', (e) => {
            if (mainContainer.style.display === 'block') { e.preventDefault(); let key = KEY_MAP[e.key] || e.key; if(key.length === 1) key = key.toLowerCase(); sendControlMessage({ type: 'key_down', key: key }); }
        });
        document.addEventListener('keyup', (e) => {
            if (mainContainer.style.display === 'block') { e.preventDefault(); let key = KEY_MAP[e.key] || e.key; if(key.length === 1) key = key.toLowerCase(); sendControlMessage({ type: 'key_up', key: key }); }
        });
    </script>
</body>
</html>
"""

# --- Scalable WebSocket Logic using Redis Pub/Sub ---
@app.route('/')
def index():
    return Response(HELPER_INTERFACE_HTML, mimetype='text/html')

class Broadcaster:
    """Manages Redis Pub/Sub for a single WebSocket connection."""
    def __init__(self, password, role):
        if not redis_client:
            raise ConnectionError("Redis is not available.")
        
        # Define Redis channel names based on session password
        self.password = password
        self.role = role
        # Client sends to screen_channel, Helper sends to control_channel
        self.screen_channel = f"session-{password}-screen"
        self.control_channel = f"session-{password}-control"
        
        # Set up a Redis PubSub object
        self.pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
        # Subscribe to the channel this role needs to LISTEN to
        if self.role == 'helper':
            self.pubsub.subscribe(self.screen_channel)
        else: # role == 'client'
            self.pubsub.subscribe(self.control_channel)

    def __iter__(self):
        """Yields messages from the subscribed Redis channel."""
        for message in self.pubsub.listen():
            yield message['data']

    def publish(self, data):
        """Publishes a message to the appropriate Redis channel."""
        channel = self.control_channel if self.role == 'helper' else self.screen_channel
        redis_client.publish(channel, data)

    def close(self):
        """Unsubscribe and close the pubsub connection."""
        self.pubsub.unsubscribe()
        self.pubsub.close()
        logging.info(f"Closed Redis PubSub for {self.role} in session '{self.password}'")


@sock.route('/ws/connect')
def connect_websocket(ws):
    """Handles WebSocket connections for both clients and helpers."""
    broadcaster = None
    try:
        # 1. Handshake
        handshake_data = ws.receive(timeout=10)
        data = json.loads(handshake_data)
        role = data.get('role')
        password = data.get('password')
        if not all([role, password]):
            logging.error("Invalid handshake.")
            return

        logging.info(f"Handshake received: role={role}, pass=***, from={ws.environ.get('REMOTE_ADDR')}")
        
        # 2. Setup Redis Broadcaster
        broadcaster = Broadcaster(password, role)

        # 3. Create two independent greenlets (lightweight threads)
        #    - One to listen for incoming messages from the WebSocket and publish them to Redis
        #    - One to listen for messages from Redis and send them to the WebSocket
        
        # Greenlet for receiving from WebSocket and publishing to Redis
        receiver_greenlet = gevent.spawn(lambda: [broadcaster.publish(message) for message in ws])
        
        # Greenlet for receiving from Redis and sending to WebSocket
        # The broadcaster itself is an iterator that listens to Redis
        sender_greenlet = gevent.spawn(lambda: [ws.send(message) for message in broadcaster])

        # gevent.joinall will wait for either greenlet to exit.
        # This will happen if the websocket closes (receiver exits) or if a Redis error occurs.
        gevent.joinall([receiver_greenlet, sender_greenlet], raise_error=True)

    except Exception as e:
        # A closed connection is normal, not an error we need to spam logs with.
        if "Connection closed" not in str(e) and isinstance(e, (ConnectionError, gevent.GreenletExit)) == False:
            logging.error(f"Error in websocket handler: {type(e).__name__}: {e}", exc_info=False)
            
    finally:
        # No matter what happens, ensure the broadcaster is closed to clean up the Redis subscription.
        if broadcaster:
            broadcaster.close()

# Main entry point (for local testing, Render uses gunicorn)
if __name__ == '__main__':
    if not redis_client:
        print("Cannot start server: Redis connection failed. Check your REDIS_URL or Redis server status.")
    else:
        from gevent.pywsgi import WSGIServer
        port = int(os.environ.get("PORT", 5000))
        print(f"Starting server with gevent on http://127.0.0.1:{port}")
        http_server = WSGIServer(('', port), app)
        http_server.serve_forever()
