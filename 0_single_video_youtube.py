# !/usr/bin/env python3

import yaml  # pip install PyYAML

# pip install youtube_dl
# pip3 install -U git+https://github.com/ytdl-org/youtube-dl
from youtube_dl import YoutubeDL 

import os
import sys
import json
import time
import requests
import subprocess
from datetime import datetime
from datetime import timedelta
import utils


# the vod which we wish to download
if len(sys.argv) != 3:
    print("please pass at least a user and youtube hash...")
    exit(-1)
channel = sys.argv[1]
vod_yt_hash = sys.argv[2]


# ================================================================
# ================================================================

# paths of the cli and data
path_base = os.path.dirname(os.path.abspath(__file__))
path_twitch_ffmpeg = path_base + "/thirdparty/ffmpeg-4.3.1-amd64-static/ffmpeg"
path_root = path_base + "/../data/"

# ================================================================
# ================================================================


# setup control+c handler
utils.setup_signal_handle()


# create the video object with all our information
# DATA: api data of this vod
youtube_url = 'https://youtu.be/'+vod_yt_hash
print("getting video data from " + youtube_url)
ydl = YoutubeDL()
info_dict = ydl.extract_info(youtube_url, download=False)


# Record the data
video_date = datetime.strptime(info_dict.get('upload_date', None), "%Y%m%d")
date_in_sec = (video_date-datetime(1970,1,1)).total_seconds()
video_data = {
    'id': str(-1),
    'user_name': channel,
    'title': info_dict.get('title', None),
    'duration': time.strftime('%Hh%Mm%Ss', time.localtime(info_dict.get('duration', None))), #str(timedelta(seconds=info_dict.get('duration', None))),
    'game': "",
    'url': "",
    'views': info_dict.get('view_count', None),
    'moments': info_dict.get('chapters', None),
    'muted_segments': [],
    'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.localtime(date_in_sec)),
    'youtube': {
        "youtubeVideo": info_dict.get("id", None),
        "description": info_dict.get("description", None),
        "uploader": info_dict.get("uploader", None),
        "uploader_url": info_dict.get("uploader_url", None),
        "uploader_url": info_dict.get("uploader_url", None),
    }
}


# check if the directory is created
path_data = path_root + "/" + channel.lower() + "/"
if not os.path.exists(path_data):
    os.makedirs(path_data)
print("saving into " + channel.lower() + " user folder")


# extract what folder we should save into
# create the folder if it isn't created already
try:
    export_folder = format(video_date.year, '02') + "-" + format(video_date.month, '02') + "/"
except:
    export_folder = "unknown/"
if not os.path.exists(path_data + export_folder):
    os.makedirs(path_data + export_folder)


# VIDEO: check if the file exists
file_path_info = path_data + export_folder + str(vod_yt_hash) + "_info.json"
print("saving video info: " + file_path_info)
if not utils.terminated_requested and not os.path.exists(file_path_info):
    with open(file_path_info, 'w', encoding="utf-8") as file:
        json.dump(video_data, file, indent=4)


# VIDEO: check if the file exists
file_path = path_data + export_folder + str(vod_yt_hash) + ".mp4"
print("download video: " + file_path)
if not utils.terminated_requested and not os.path.exists(file_path):
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'recodevideo': 'mp4',
        'outtmpl': path_data + export_folder + str(vod_yt_hash) + '.%(ext)s',
    }
    ydl = YoutubeDL(ydl_opts)
    retcode = ydl.download([youtube_url])
    print("\nreturn code: "+str(retcode))





