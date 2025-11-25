# Import general libraries
import signal
import requests
import os
import yaml
import fcntl
import logging
from typing import Dict, Any

# global variable which sets if we should terminate
terminated_requested = False


def signal_handler(sig, frame):
    global terminated_requested
    terminated_requested = True
    print('terminate requested!!!!!')


def setup_signal_handle():
    signal.signal(signal.SIGINT, signal_handler)


def send_pushover_message(auth, text):
    if auth["pushover_enable"]:
        payload = {"message": text, "user": auth["pushover_user_key"], "token": auth["pushover_app_key"] }
        resp = requests.post('https://api.pushover.net/1/messages.json', data=payload, headers={'User-Agent': 'Python'})
        if not resp.ok:
            print("[error]: bad response from pushover: ")
            print(resp)


def update_history_file(history_file: str, video_id: str, entry: Dict[str, Any], logger: logging.Logger) -> None:
    """Safely update history file with file locking and reloading to preserve entries from other scripts."""
    if not os.path.exists(os.path.dirname(history_file)):
        os.makedirs(os.path.dirname(history_file))
    
    # Open file for reading and writing
    with open(history_file, 'a+') as f:
        # Acquire exclusive lock
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            # Reload the file to get latest state (may have been updated by other scripts)
            f.seek(0)
            content = f.read()
            if content.strip():
                current_history = yaml.load(content, Loader=yaml.FullLoader) or {}
            else:
                current_history = {}
            
            # Merge new entry with existing entry to preserve fields from other scripts
            if video_id in current_history:
                current_history[video_id].update(entry)
            else:
                current_history[video_id] = entry
            
            # Write back to file
            f.seek(0)
            f.truncate()
            yaml.dump(current_history, f)
            f.flush()
            os.fsync(f.fileno())
        finally:
            # Release lock
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

