"""
UniTrack AI - Production WSGI Entry Point (Render / Gunicorn / Heroku / Docker)
"""

import os
import sys

# Ensure application package is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, 'Student_Performance_Analytics')
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
