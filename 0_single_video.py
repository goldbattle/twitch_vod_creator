# !/usr/bin/env python3

import twitch  # pip install python-twitch-client
import yaml  # pip install PyYAML
from webvtt import WebVTT, Caption  # pip install webvtt-py
from vosk import Model, KaldiRecognizer, SetLogLevel  # pip install vosk

import os
import sys
import json
import subprocess
import shutil
from datetime import datetime
import utils
import time


# the vod which we wish to download
if len(sys.argv) != 2:
    print("please pass at least a single vod id to download...")
    exit(-1)
vod_id_to_download = int(sys.argv[1])
render_chat = False
transcribe = False

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
# path_twitch_cli = path_base + "/thirdparty/Twitch_Downloader_1.40.7/TwitchDownloaderCLI.exe"
# path_twitch_ffmpeg = path_base + "/thirdparty/Twitch_Downloader_1.40.7/ffmpeg.exe"
path_twitch_cli = path_base + "/thirdparty/Twitch_Downloader_1.40.7/TwitchDownloaderCLI"
path_twitch_ffmpeg = path_base + "/thirdparty/ffmpeg-4.3.1-amd64-static/ffmpeg"
path_root = path_base + "/../data/"
# path_temp = path_base + "/../data_temp/single_video/"
path_temp = "/tmp/tvc_single_video/"
path_model = path_base + "/thirdparty/vosk-model-small-en-us-0.15/"

# ================================================================
# ================================================================

# setup control+c handler
utils.setup_signal_handle()

# create our twitch api python objects for query
client_helix = twitch.TwitchHelix(client_id=client_id, client_secret=client_secret)
client_helix.get_oauth()

print("trying to pull api info for vod " + str(vod_id_to_download))
videos = client_helix.get_videos(video_ids=[vod_id_to_download])
assert (len(videos) == 1)

# create the video object with all our information
video = {
    'helix': videos[0],
}

# DATA: api data of this vod
video_data = {
    'id': video['helix']['id'],
    'user_id': video['helix']['user_id'],
    'user_name': video['helix']['user_name'],
    'title': video['helix']['title'],
    'duration': video['helix']['duration'],
    'url': video['helix']['url'],
    'views': video['helix']['view_count'],
    'moments': utils.get_vod_moments(video['helix']['id']),
    'muted_segments': (video['helix']['muted_segments'] if video['helix']['muted_segments'] != None else []),
    'recorded_at': video['helix']['created_at'].strftime('%Y-%m-%dT%H:%M:%SZ'),
}

# check if the directory is created
path_data = path_root + "/" + video_data['user_name'].lower() + "/"
if not os.path.exists(path_data):
    os.makedirs(path_data)
if not os.path.exists(path_temp):
    os.makedirs(path_temp)
print("saving into " + video_data['user_name'].lower() + " user folder")

# extract what folder we should save into
# create the folder if it isn't created already
try:
    date = datetime.strptime(video_data['recorded_at'], '%Y-%m-%dT%H:%M:%SZ')
    export_folder = format(date.year, '02') + "-" + format(date.month, '02') + "/"
except:
    export_folder = "unknown/"
if not os.path.exists(path_data + export_folder):
    os.makedirs(path_data + export_folder)

# VIDEO: check if the file exists
file_path_info = path_data + export_folder + str(video['helix']['id']) + "_info.json"
print("saving video info: " + file_path_info)
if not utils.terminated_requested and not os.path.exists(file_path_info):
    with open(file_path_info, 'w', encoding="utf-8") as file:
        json.dump(video_data, file, indent=4)

# VIDEO: check if the file exists
file_path = path_data + export_folder + str(video['helix']['id']) + ".mp4"
print("download video: " + file_path)
if not utils.terminated_requested and not os.path.exists(file_path):
    cmd = path_twitch_cli + ' -m VideoDownload' \
          + ' --id ' + str(video['helix']['id']) + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
          + ' --temp-path "' + path_temp + '" --quality 1080p60 -o ' + file_path
    # subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
    subprocess.Popen(cmd, shell=True).wait()

# CHAT: check if the file exists
file_path_chat = path_data + export_folder + str(video['helix']['id']) + "_chat.json"
file_path_chat_tmp = path_temp + str(video['helix']['id']) + "_chat.json"
print("download chat: " + file_path_chat)
if not utils.terminated_requested and not os.path.exists(file_path_chat):
    cmd = path_twitch_cli + ' -m ChatDownload' \
          + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
          + ' --id ' + str(video['helix']['id']) + ' --embed-emotes' \
          + ' -o ' + file_path_chat_tmp
    #subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
    subprocess.Popen(cmd, shell=True).wait()
    shutil.move(file_path_chat_tmp, file_path_chat) 

# AUDIO-TO-TEXT: check if file exists
if transcribe:
    file_path_webvtt = path_data + export_folder + str(video['helix']['id']) + ".vtt"
    if not utils.terminated_requested and os.path.exists(file_path) and not os.path.exists(file_path_webvtt):
        print("transcribing: " + file_path_webvtt)
        t0 = time.time()

        # open the model
        SetLogLevel(-1)
        sample_rate = 16000
        model = Model(path_model)
        rec = KaldiRecognizer(model, sample_rate)
        rec.SetWords(True)

        # open ffmpeg pipe stream of the audio file (from video)
        command = [path_twitch_ffmpeg, '-nostdin', '-loglevel', 'quiet', '-i', file_path,
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
        print("done in " + str(time.time() - t0) + " seconds")

# RENDER: check if the file exists
if render_chat:
    file_path_chat = path_data + export_folder + str(video['helix']['id']) + "_chat.json"
    file_path_render = path_data + export_folder + str(video['helix']['id']) + "_chat.mp4"
    file_path_render_tmp = path_temp + str(video['helix']['id']) + "_chat.mp4"
    if os.path.exists(file_path_chat) and not os.path.exists(file_path_render):
        print("rendering chat: " + file_path_render)
        cmd = path_twitch_cli + ' -m ChatRender' \
              + ' -i ' + file_path_chat + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
              + ' -h 926 -w 274 --update-rate 0.1 --framerate 60 --font-size 15' \
              + ' --temp-path "' + path_temp + '" -o ' + file_path_render_tmp
        # subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
        subprocess.Popen(cmd, shell=True).wait()
        shutil.move(file_path_render_tmp, file_path_render) 



