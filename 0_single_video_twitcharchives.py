# !/usr/bin/env python3

import twitch  # pip install python-twitch-client
import yaml  # pip install PyYAML
from youtube_dl import YoutubeDL # pip install youtube_dl

import os
import sys
import json
import time
import requests
import subprocess
from datetime import datetime
import utils


# the vod which we wish to download
if len(sys.argv) != 2:
    print("please pass at least a single vod id (twitch archive) to download...")
    exit(-1)
vod_id_to_download = int(sys.argv[1])


# ================================================================
# ================================================================

# paths of the cli and data
path_base = os.path.dirname(os.path.abspath(__file__))
# path_twitch_ffmpeg = path_base + "/thirdparty/Twitch_Downloader_1.39.4/ffmpeg.exe"
path_twitch_ffmpeg = path_base + "/thirdparty/ffmpeg-4.3.1-amd64-static/ffmpeg"
path_root = path_base + "/../data/"

# ================================================================
# ================================================================


# setup control+c handler
utils.setup_signal_handle()

# query their api endpoint
print("trying to pull api info for vod " + str(vod_id_to_download))
data_raw = requests.get("https://api.twitcharchives.com/videos?id="+str(vod_id_to_download))
videos = data_raw.json()
assert (len(videos) == 1)


# create the video object with all our information
# DATA: api data of this vod
video = videos[0]
video_data = {
    'id': str(video['vodId']),
    'user_id': str(video['channelId']),
    'user_name': video['channelName'],
    'title': video['title'],
    'duration': -1,
    'game': "",
    'url': "https://www.twitch.tv/videos/"+str(video['vodId']),
    'views': -1,
    'moments': utils.get_vod_moments_from_twitcharchive_string(video['chapters']),
    'muted_segments': [],
    'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.localtime(video['created'])),
    'twitcharchives': {
        "id": video['id'],
        "youtubeVideo": video['videoYoutubeId'],
        "youtubeChat": video['chatYoutubeId'],
    }
}


# check if the directory is created
path_data = path_root + "/" + video_data['user_name'].lower() + "/"
if not os.path.exists(path_data):
    os.makedirs(path_data)
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
file_path_info = path_data + export_folder + str(video_data['id']) + "_info.json"
print("saving video info: " + file_path_info)
if not utils.terminated_requested and not os.path.exists(file_path_info):
    with open(file_path_info, 'w', encoding="utf-8") as file:
        json.dump(video_data, file, indent=4)

# VIDEO: check if the file exists
file_path = path_data + export_folder + str(video_data['id']) + ".mp4"
print("download video: " + file_path)
if not utils.terminated_requested and not os.path.exists(file_path):
    youtube_url = 'https://youtu.be/'+video_data["twitcharchives"]["youtubeVideo"]
    print("downloading from youtube: "+youtube_url)
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'recodevideo': 'mp4',
        'outtmpl': path_data + export_folder + str(video_data['id']) + '.%(ext)s',
    }
    ydl = YoutubeDL(ydl_opts)
    retcode = ydl.download([youtube_url])
    print("\nreturn code: "+str(retcode))


# CHAT VIDEO: check if the file exists
# file_path_render = path_data + export_folder + str(video_data['id']) + "_chat.mp4"
# if os.path.exists(file_path_chat) and not os.path.exists(file_path_render):
#     print("rendering chat: " + file_path_render)
#     cmd = path_twitch_cli + ' -m ChatRender' \
#           + ' -i ' + file_path_chat + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
#           + ' -h 1080 -w 320 --framerate 60 --font-size 13' \
#           + ' -o ' + file_path_render
#     # subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL).wait()
#     subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()



