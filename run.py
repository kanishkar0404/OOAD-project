import sys
import os

# Ensure project directory is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app

if __name__ == '__main__':
    print("=" * 65)
    print("   LOGICGRID MASTER - OOAD ONLINE LOGIC PUZZLE PLATFORM")
    print("=" * 65)
    print(" Server running locally at: http://127.0.0.1:5000")
    print(" API Endpoints initialized for Puzzles, Games, Leaderboards & OOAD Diagrams")
    print(" Press Ctrl+C to terminate the server.")
    print("=" * 65)
    app.run(host='127.0.0.1', port=5000, debug=True)
