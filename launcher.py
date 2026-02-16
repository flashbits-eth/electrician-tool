"""
Launcher for the Electrical Estimator.
This is the entry point for the PyInstaller .exe build.
Opens the browser automatically and starts the Flask server.
"""
import os
import sys
import threading
import webbrowser

# When running as a PyInstaller bundle, files are extracted to a temp dir.
# We need to set the working directory so Flask/data paths resolve correctly.
if getattr(sys, 'frozen', False):
    # Running as compiled exe
    bundle_dir = sys._MEIPASS
    # Set working directory to where the exe lives (so data/ is found next to it)
    os.chdir(os.path.dirname(sys.executable))
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(bundle_dir)

def open_browser():
    """Open browser after a short delay to let the server start."""
    import time
    time.sleep(1.5)
    webbrowser.open('http://localhost:5000')

if __name__ == '__main__':
    # Open browser in a background thread
    threading.Thread(target=open_browser, daemon=True).start()

    # Import and run the Flask app
    from app import app

    print()
    print('  ============================================')
    print('   Electrical Estimator')
    print('   Running at http://localhost:5000')
    print('   Close this window to stop the server.')
    print('  ============================================')
    print()

    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
