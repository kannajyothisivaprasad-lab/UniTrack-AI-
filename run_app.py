"""
Root Launcher for UniTrack AI Web Application
Run directly from root folder: python run_app.py
"""

import os
import sys

# Ensure application base directory is in sys.path without chdir
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, 'Student_Performance_Analytics')
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app import app

if __name__ == '__main__':
    # Ensure Windows console handles UTF-8 safely
    if sys.platform.startswith('win'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print("=" * 80)
    print("UniTrack AI - Multi-University Management & Student Performance Analytics")
    print("=" * 80)
    print(">> Portal URL: http://127.0.0.1:5000")
    print("")
    print(">> Pre-Configured Demo Credentials:")
    print("   1. Platform Super Admin: admin@unitrack.ai   | Password: Admin@123")
    print("   2. University A Admin:   admin@apex.edu       | Password: ApexAdmin@123")
    print("   3. University A Staff:   prof.sharma@apex.edu | Password: Staff@123")
    print("   4. University B Admin:   admin@pacific.edu    | Password: PacificAdmin@123")
    print("=" * 80)
    print("Press Ctrl + C to stop the server\n")
    # use_reloader=False prevents Werkzeug path issues on Windows
    app.run(host='0.0.0.0', port=5000, debug=False)
