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
HELPER_HTML = """ ... PASTE YOUR EXISTING HTML HERE ... """


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
