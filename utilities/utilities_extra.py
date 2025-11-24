# Import general libraries
import signal
import requests

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

