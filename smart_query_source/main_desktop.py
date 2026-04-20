"""
Simple PySide6 desktop launcher that starts the FastAPI backend (uvicorn) in a background thread
and opens a QWebEngineView pointing to the local server.

Requirements:
- Python packages: pyside6, uvicorn, requests
  pip install pyside6 uvicorn requests
- If PySide6 Qt WebEngine is not available, install PySide6 (newer versions include webengine)

Run:
  python main_desktop.py

Notes:
- This launcher assumes the FastAPI app is importable as src.fastapi_app:app
- Backend listens on 127.0.0.1:8010 by default. Adjust if needed.
"""

import sys
import threading
import time
import socket
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView

import uvicorn

# Import the FastAPI app
try:
    from src.fastapi_app import app as fastapi_app
except Exception as e:
    print("Failed to import FastAPI app from src.fastapi_app:", e)
    raise

HOST = "127.0.0.1"
PORT = 8010
BASE_URL = f"http://{HOST}:{PORT}"


def is_port_open(host, port, timeout=1.0):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def start_server():
    # uvicorn.run will block this thread; run with default loop
    uvicorn.run(fastapi_app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    # Start backend in daemon thread
    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    # Wait for server to open port
    for i in range(30):
        if is_port_open(HOST, PORT):
            break
        time.sleep(0.5)
    else:
        print(f"Server did not start on {HOST}:{PORT} after wait; opening UI may fail.")

    app = QApplication(sys.argv)
    web = QWebEngineView()
    web.load(QUrl(BASE_URL))
    web.setWindowTitle("智能问数（离线桌面）")
    web.resize(1200, 800)
    web.show()

    sys.exit(app.exec())
