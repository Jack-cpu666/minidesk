import os
import json
import logging
from flask import Flask, Response
from flask_sock import Sock

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Flask App Initialization ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secret-key-for-dev')
sock = Sock(app)

# --- Session Management ---
sessions = {}

# --- Helper Interface (Controller UI) with Auto-Reconnect ---
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
        #status-bar { position: fixed; top: 0; left: 0; background-color: rgba(0,0,0,0.7); padding: 5px 10px; font-size: 14px; border-bottom-right-radius: 5px; z-index: 100; transition: background-color 0.3s; }
        #status-bar.reconnecting { background-color: #e67e22; }
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
        let sessionPassword = '';
        let reconnectInterval;

        const MOUSE_BUTTON_MAP = { 0: 'left', 1: 'middle', 2: 'right' };
        const KEY_MAP = {"Control":"ctrl","Shift":"shift","Alt":"alt","Meta":"cmd","ArrowUp":"up","ArrowDown":"down","ArrowLeft":"left","ArrowRight":"right","Enter":"enter","Escape":"esc","Backspace":"backspace","Tab":"tab","Delete":"delete","Insert":"insert","Home":"home","End":"end","PageUp":"page_up","PageDown":"page_down","F1":"f1","F2":"f2","F3":"f3","F4":"f4","F5":"f5","F6":"f6","F7":"f7","F8":"f8","F9":"f9","F10":"f10","F11":"f11","F12":"f12"};

        function startConnection() {
            if (reconnectInterval) clearInterval(reconnectInterval);

            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${wsProtocol}//${window.location.host}/ws/connect`;
            
            ws = new WebSocket(wsUrl);
            
            statusBar.textContent = 'Status: Connecting...';
            statusBar.classList.remove('reconnecting');

            ws.onopen = () => {
                console.log("WebSocket connection opened.");
                statusBar.textContent = 'Status: Authenticating...';
                ws.send(JSON.stringify({ role: 'helper', password: sessionPassword }));
            };

            ws.onmessage = (event) => {
                if (event.data.startsWith('s:')) {
                    if (mainContainer.style.display !== 'block') {
                        authContainer.style.display = 'none';
                        mainContainer.style.display = 'block';
                    }
                    statusBar.textContent = 'Status: Connected';
                    statusBar.classList.remove('reconnecting');
                    if (reconnectInterval) clearInterval(reconnectInterval);
                    screenView.src = 'data:image/jpeg;base64,' + event.data.substring(2);
                }
            };

            ws.onclose = () => {
                console.log("WebSocket connection closed. Attempting to reconnect...");
                ws = null;
                mainContainer.style.display = 'block'; 
                statusBar.textContent = 'Status: Reconnecting...';
                statusBar.classList.add('reconnecting');

                if (!reconnectInterval) {
                    reconnectInterval = setInterval(startConnection, 5000);
                }
            };

            ws.onerror = (error) => {
                console.error("WebSocket error:", error);
                ws.close();
            };
        }
        
        function initiateSession() {
            sessionPassword = passwordInput.value;
            if (!sessionPassword) {
                alert("Please enter a password.");
                return;
            }
            startConnection();
        }

        connectBtn.addEventListener('click', initiateSession);
        passwordInput.addEventListener('keyup', (e) => e.key === 'Enter' && initiateSession());
        
        function sendControlMessage(data) { if (ws && ws.readyState === WebSocket.OPEN) { ws.send(JSON.stringify(data)); } }
        screenView.addEventListener('mousemove', (e) => { const r = screenView.getBoundingClientRect(); sendControlMessage({ type: 'mouse_move', x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height }); });
        screenView.addEventListener('mousedown', (e) => { e.preventDefault(); const r = screenView.getBoundingClientRect(); sendControlMessage({ type: 'mouse_down', button: MOUSE_BUTTON_MAP[e.button], x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height }); });
        screenView.addEventListener('mouseup', (e) => { e.preventDefault(); const r = screenView.getBoundingClientRect(); sendControlMessage({ type: 'mouse_up', button: MOUSE_BUTTON_MAP[e.button], x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height }); });
        screenView.addEventListener('wheel', (e) => { e.preventDefault(); sendControlMessage({ type: 'mouse_scroll', dx: -e.deltaX, dy: -e.deltaY }); });
        screenView.addEventListener('contextmenu', (e) => e.preventDefault());
        document.addEventListener('keydown', (e) => { if (mainContainer.style.display === 'block') { e.preventDefault(); let k = KEY_MAP[e.key] || e.key; sendControlMessage({ type: 'key_down', key: k.length === 1 ? k.toLowerCase() : k }); } });
        document.addEventListener('keyup', (e) => { if (mainContainer.style.display === 'block') { e.preventDefault(); let k = KEY_MAP[e.key] || e.key; sendControlMessage({ type: 'key_up', key: k.length === 1 ? k.toLowerCase() : k }); } });
    </script>
</body>
</html>
"""

# --- Flask Routes ---
@app.route('/')
def index():
    return Response(HELPER_INTERFACE_HTML, mimetype='text/html')

@sock.route('/ws/connect')
def connect_websocket(ws):
    ws_role, ws_pass = None, None
    try:
        handshake_data = ws.receive(timeout=10)
        if not handshake_data:
            logging.warning("WebSocket handshake timeout.")
            return

        data = json.loads(handshake_data)
        ws_role = data.get('role')
        ws_pass = data.get('password')

        if not all([ws_role, ws_pass]):
            logging.error(f"Invalid handshake: {handshake_data}")
            return
        
        logging.info(f"Handshake received: role={ws_role}, pass=***, from={ws.environ.get('REMOTE_ADDR')}")

        if ws_pass not in sessions:
            sessions[ws_pass] = {'client_ws': None, 'helper_ws': None}

        # --- SELF-HEALING LOGIC ---
        if ws_role == 'client':
            if sessions[ws_pass]['client_ws'] is not None:
                logging.warning(f"Replacing stale client for session '{ws_pass}'.")
                try:
                    sessions[ws_pass]['client_ws'].close(reason=1001, message="New client connected")
                except Exception as e:
                    logging.warning(f"Could not close stale client socket: {e}")
            sessions[ws_pass]['client_ws'] = ws
        
        elif ws_role == 'helper':
            if sessions[ws_pass]['helper_ws'] is not None:
                logging.warning(f"Replacing stale helper for session '{ws_pass}'.")
                try:
                    sessions[ws_pass]['helper_ws'].close(reason=1001, message="New helper connected")
                except Exception as e:
                    logging.warning(f"Could not close stale helper socket: {e}")
            sessions[ws_pass]['helper_ws'] = ws
        else:
            logging.error(f"Unknown role '{ws_role}'")
            return

        while True:
            message = ws.receive()
            if message is None: break
            session = sessions.get(ws_pass)
            if not session: break
            
            if ws_role == 'client' and session.get('helper_ws'):
                session['helper_ws'].send(message)
            elif ws_role == 'helper' and session.get('client_ws'):
                session['client_ws'].send(message)

    except Exception as e:
        if "Connection closed" in str(e):
            logging.info(f"WebSocket {ws_role} in session '{ws_pass}' disconnected: {e}")
        else:
            logging.error(f"Error in WebSocket handler for {ws_role} in session '{ws_pass}': {e}")
    
    finally:
        # ROBUST Cleanup
        if ws_pass and ws_role and ws_pass in sessions:
            if sessions[ws_pass].get(f'{ws_role}_ws') == ws:
                sessions[ws_pass][f'{ws_role}_ws'] = None
                logging.info(f"Cleaned up active {ws_role} for session '{ws_pass}'.")
            if not sessions[ws_pass]['client_ws'] and not sessions[ws_pass]['helper_ws']:
                logging.info(f"Session '{ws_pass}' is now empty and is being deleted.")
                del sessions[ws_pass]

if __name__ == '__main__':
    # This block is for local testing. Render uses the Procfile command.
    from gevent.pywsgi import WSGIServer
    from geventwebsocket.handler import WebSocketHandler
    print("Starting development server on http://127.0.0.1:5000")
    server = WSGIServer(('', 5000), app, handler_class=WebSocketHandler)
    server.serve_forever()
