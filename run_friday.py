import subprocess
import sys
import time


def main():
    print("Starting FRIDAY...")
    friday_process = subprocess.Popen([sys.executable, "test_voice.py"])

    time.sleep(2)  # give the WebSocket server a moment to start before the orb connects

    print("Starting the orb...")
    orb_process = subprocess.Popen([sys.executable, "orb/orb_app.py"])

    try:
        friday_process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        orb_process.terminate()


if __name__ == "__main__":
    main()