import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = 2
worker_class = "sync"
worker_connections = 1000
keepalive = 120
timeout = 120
graceful_timeout = 30
preload_app = True
accesslog = "-"
errorlog = "-"
loglevel = "info"
