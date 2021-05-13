# !/usr/bin/env python3

import twitch  # pip install python-twitch-client
import yaml  # pip install PyYAML

import os
import re
import json
import time
import subprocess
import datetime
import utils

# authentication information
path_base = os.path.dirname(os.path.abspath(__file__))
auth_config = path_base + "/config/auth.yaml"
with open(auth_config) as f:
    auth = yaml.load(f, Loader=yaml.FullLoader)
client_id = auth["client_id"]
client_secret = auth["client_secret"]

# parameters
title = "4-Way Puzzle Box with Shroud, AnneMunition, and Sacriel #ad - (sodapoppin) - May 7, 2021"
syncoffset = "00:04:15"
duration = "01:31:47"

# video files we will composite together
video0 = "sodapoppin/2021-05/1014588993"
starttime0 = "01:19:53"
video1 = "annemunition/2021-05/1014683883"
starttime1 = "00:07:12"
video2 = "sacriel/2021-05/1014237350"
starttime2 = "06:45:51"
video3 = "shroud/2021-05/1014620817"
starttime3 = "00:56:46"


# ================================================================
# ================================================================

# paths of the cli and data
# path_twitch_cli = path_base + "/thirdparty/Twitch_Downloader_1.39.4/TwitchDownloaderCLI.exe"
# path_twitch_ffmpeg = path_base + "/thirdparty/Twitch_Downloader_1.39.4/ffmpeg.exe"
path_twitch_cli = path_base + "/thirdparty/Twitch_Downloader_1.39.4/TwitchDownloaderCLI"
path_twitch_ffmpeg = path_base + "/thirdparty/ffmpeg-4.3.1-amd64-static/ffmpeg"
path_root = path_base + "/../data/"
path_render = path_base + "/../data_rendered/"

# ================================================================
# ================================================================

# setup control+c handler
utils.setup_signal_handle()


# VIDEO: check that we have the video
videos = [video0, video1, video2, video3]
videopaths = []
for video in videos:
    file_path_video = path_root + video + ".mp4"
    videopaths.append(file_path_video)
    if not os.path.exists(file_path_video):
        print("\t- ERROR: could not find the video file!")
        print("\t- " + file_path_video)
        quit()

# CHAT: check that we have video0 chat
file_path_chat = path_root + video0 + "_chat.json"
file_path_render = path_root + video0 + "_chat.mp4"
if not os.path.exists(file_path_chat):
    print("\t- ERROR: could not find the chat file!")
    print("\t- " + file_path_chat)
    quit()

# CHAT: actuall make sure we render it
if not os.path.exists(file_path_render):
    print("\t- rendering chat: " + file_path_chat)
    cmd = path_twitch_cli + ' -m ChatRender' \
          + ' -i ' + file_path_chat + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
          + ' -h 926 -w 274 --update-rate 0.1 --framerate 60 --font-size 15' \
          + ' -o ' + file_path_render
    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()


# COMPOSITE: render the composite image
clean_video_title = utils.get_valid_filename(title)
file_path_composite = path_render + "4WAY/" + clean_video_title + ".mp4"
file_path_composite_tmp = path_render + "4WAY/" + clean_video_title + ".tmp.mp4"
print("rendering composite: " + file_path_composite)


# Create our export folder if needed
dir_path_composite = os.path.dirname(os.path.abspath(file_path_composite))
if not os.path.exists(dir_path_composite):
    os.makedirs(dir_path_composite)
if os.path.exists(file_path_composite):
    print("\t- ERROR: rendered video file already exists!")
    print("\t- " + file_path_composite)
    quit()

# for each video construct the start / end times
synctimes = [starttime0, starttime1, starttime2, starttime3]
starttimes = []
endtimes = []
for synctime in synctimes:
    h0, m0, s0 = syncoffset.split(':')
    h1, m1, s1 = synctime.split(':')
    h2, m2, s2 = duration.split(':')
    time0_s = 3600 * int(h0) + 60 * int(m0) + int(s0)
    time1_s = 3600 * int(h1) + 60 * int(m1) + int(s1)
    time2_s = 3600 * int(h2) + 60 * int(m2) + int(s2)
    m, s = divmod(time1_s - time0_s, 60)
    h, m = divmod(m, 60)
    starttime = format(h, '02') + ':' + format(m, '02') + ':' + format(s, '02')
    m, s = divmod(time1_s + time2_s, 60)
    h, m = divmod(m, 60)
    endtime = format(h, '02') + ':' + format(m, '02') + ':' + format(s, '02')
    print("segment video"+str(len(endtimes))+": "+starttime+" -> "+endtime)
    starttimes.append(starttime)
    endtimes.append(endtime)


# RENDER: actually render the video
#   - main video is 1646x926
#   - small videos are 823x463
#   - chat render is 274x926
print("rendering with chat overlay...")
cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
      + ' -ss ' + starttimes[0] + ' -to ' + endtimes[0] + ' -i ' + videopaths[0] \
      + ' -ss ' + starttimes[1] + ' -to ' + endtimes[1] + ' -i ' + videopaths[1] \
      + ' -ss ' + starttimes[2] + ' -to ' + endtimes[2] + ' -i ' + videopaths[2] \
      + ' -ss ' + starttimes[3] + ' -to ' + endtimes[3] + ' -i ' + videopaths[3] \
      + ' -ss ' + starttimes[0] + ' -i ' + file_path_render \
      + ' -filter_complex "' \
      + ' [0:v] scale=823x463 [tmp0];[1:v] scale=823x463 [tmp1];' \
      + ' [2:v] scale=823x463 [tmp2];[3:v] scale=823x463 [tmp3];' \
      + ' [tmp0][tmp1]hstack=inputs=2:shortest=1[top]; ' \
      + ' [tmp2][tmp3]hstack=inputs=2:shortest=1[bottom]; ' \
      + ' [top][bottom]vstack=inputs=2:shortest=1[main]; ' \
      + ' [main][4:v]hstack=inputs=2:shortest=1[stack]" -shortest -map "[stack]" -map 0:a ' \
      + ' -vcodec libx264 -crf 18 -preset veryfast -avoid_negative_ts make_zero -framerate 60 ' \
      + ' -c:a aac ' \
      + file_path_composite_tmp
print(cmd)
# subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
subprocess.Popen(cmd, shell=True).wait()


# finally copy temp file to new location
print("renaming temp export file to final filename")
if not utils.terminated_requested and os.path.exists(file_path_composite_tmp):
    os.rename(file_path_composite_tmp, file_path_composite)


