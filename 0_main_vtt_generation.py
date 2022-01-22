# !/usr/bin/env python3

import twitch  # pip install python-twitch-client
import yaml  # pip install PyYAML

import os
import json
import time
import subprocess
import utils
import datetime
import shutil
from webvtt import WebVTT, Caption  # pip install webvtt-py
from vosk import Model, KaldiRecognizer, SetLogLevel  # pip install vosk


# authentication information
path_base = os.path.dirname(os.path.abspath(__file__))
auth_config = path_base + "/config/auth.yaml"
with open(auth_config) as f:
    auth = yaml.load(f, Loader=yaml.FullLoader)
client_id = auth["client_id"]
client_secret = auth["client_secret"]



# ================================================================
# ================================================================

# paths of the cli and data
# path_twitch_cli = path_base + "/thirdparty/Twitch_Downloader_1.39.4/TwitchDownloaderCLI.exe"
# path_twitch_ffmpeg = path_base + "/thirdparty/Twitch_Downloader_1.39.4/ffmpeg.exe"
path_twitch_cli = path_base + "/thirdparty/Twitch_Downloader_1.40.2/TwitchDownloaderCLI"
path_twitch_ffmpeg = path_base + "/thirdparty/ffmpeg-4.3.1-amd64-static/ffmpeg"
path_root = path_base + "/../data/"
path_model = path_base + "/thirdparty/vosk-model-small-en-us-0.15/"

# ================================================================
# ================================================================

# setup control+c handler
utils.setup_signal_handle()


channel = "clintstevens"


# find the live video files
files_names = []
files_out = []
for subdir, dirs, files in os.walk(path_root + "/" + channel + "/"):
    for file in files:
        ext = file.split(os.extsep)
        if len(ext) != 2:
            continue
        if ext[1] == "mp4":
            files_out.append(os.path.join(subdir, ext[0]+".vtt"))
            files_names.append(os.path.join(subdir, file))
            print(os.path.join(subdir, ext[0]+".vtt"))
print("found "+str(len(files_out))+" videos found to process")

# loop through each video and convert it using ffmpeg
for ct in range(len(files_names)):

    # check if we should download any more
    if utils.terminated_requested:
        print('terminate requested, not downloading any more..')
        break

    # check if old enough to process
    oldness = time.time()-os.path.getmtime(files_names[ct])
    if oldness < 60:
        print("skipping "+files_names[ct]+" since it is only "+str(oldness)+" sec old")
        continue
    
    # AUDIO-TO-TEXT: check if file exists
    file_path_webvtt = files_out[ct]
    print("transcribing: " + file_path_webvtt)
    if not utils.terminated_requested and os.path.exists(files_names[ct]) and not os.path.exists(file_path_webvtt):
        t0 = time.time()

        # open the model
        SetLogLevel(-1)
        sample_rate = 16000
        model = Model(path_model)
        rec = KaldiRecognizer(model, sample_rate)
        rec.SetWords(True)

        # open ffmpeg pipe stream of the audio file (from video)
        command = [path_twitch_ffmpeg, '-nostdin', '-loglevel', 'quiet', '-i', files_names[ct],
                   '-ar', str(sample_rate), '-ac', '1', '-f', 's16le', '-']
        # process = subprocess.Popen(command, stdout=subprocess.PIPE)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        results = []
        while True:
            data = process.stdout.read(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                text = rec.Result()
                results.append(text)
        results.append(rec.FinalResult())

        # convert to standard format
        vtt = WebVTT()
        for i, res in enumerate(results):
            words = json.loads(res).get('result')
            if not words:
                continue
            for word in words:
                start = utils.webvtt_time_string(word['start'])
                end = utils.webvtt_time_string(word['end'])
                vtt.captions.append(Caption(start, end, word['word']))
        vtt.save(file_path_webvtt)
        print("done in " + str(time.time() - t0) + " seconds\n")


