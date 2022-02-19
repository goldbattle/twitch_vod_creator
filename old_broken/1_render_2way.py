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
import shutil

# authentication information
path_base = os.path.dirname(os.path.abspath(__file__))
auth_config = path_base + "/config/auth.yaml"
with open(auth_config) as f:
    auth = yaml.load(f, Loader=yaml.FullLoader)
client_id = auth["client_id"]
client_secret = auth["client_secret"]

# parameters
title = "simple test 02"
syncoffset = "00:45:05"
syncending = "01:10:00"

# video files we will composite together
video0 = "hasanabi/2021-09/1161184256"
starttime0 = "00:54:29"
video1 = "xqcow/2021-09/1161192739"
starttime1 = "00:44:35"


# ================================================================
# ================================================================

# paths of the cli and data
# path_twitch_cli = path_base + "/thirdparty/Twitch_Downloader_1.40.7/TwitchDownloaderCLI.exe"
# path_twitch_ffmpeg = path_base + "/thirdparty/Twitch_Downloader_1.40.7/ffmpeg.exe"
path_twitch_cli = path_base + "/thirdparty/Twitch_Downloader_1.40.7/TwitchDownloaderCLI"
path_twitch_ffmpeg = path_base + "/thirdparty/ffmpeg-4.3.1-amd64-static/ffmpeg"
path_root = path_base + "/../data/"
path_render = path_base + "/../data_rendered/"
path_temp = "/tmp/tvc_render_2way/"

# ================================================================
# ================================================================

# setup control+c handler
utils.setup_signal_handle()

# VIDEO: check that we have the video
videos = [video0, video1]
videopaths = []
for video in videos:
    file_path_video = path_root + video + ".mp4"
    videopaths.append(file_path_video)
    if not os.path.exists(file_path_video):
        print("\t- ERROR: could not find the video file!")
        print("\t- " + file_path_video)
        quit()

# CHAT: check that we have chats
chatpaths = []
chatpathsvideo = []
chatpathsvideo_tmp = []
for video in videos:
    file_path_chat = path_root + video + "_chat.json"
    file_path_chat_video = path_root + video + "_chat_2way.mp4"
    file_path_chat_video_tmp = path_temp + video + "_chat_2way.mp4"
    chatpaths.append(file_path_chat)
    chatpathsvideo.append(file_path_chat_video)
    chatpathsvideo_tmp.append(file_path_chat_video_tmp)
    if not os.path.exists(file_path_chat):
        print("\t- ERROR: could not find the chat file!")
        print("\t- " + file_path_chat)
        quit()


# CHAT: actually make sure we render it
for i in range(len(chatpathsvideo)):
    if not os.path.exists(chatpathsvideo[i]):
        folder = os.path.abspath(os.path.join(chatpathsvideo_tmp[i], os.pardir))
        if not os.path.exists(folder):
            os.makedirs(folder)
        print("\t- rendering chat: " + chatpathsvideo[i])
        cmd = path_twitch_cli + ' -m ChatRender' \
              + ' -i ' + chatpaths[i] + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
              + ' -h 540 -w 960 --update-rate 0.1 --framerate 60 --font-size 15' \
              + ' -o ' + chatpathsvideo_tmp[i]
              # + ' -h 464 -w 272 --update-rate 0.1 --framerate 60 --font-size 15' \
        subprocess.Popen(cmd, shell=True).wait()
        # subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
        shutil.move(chatpathsvideo_tmp[i], chatpathsvideo[i]) 


# COMPOSITE: render the composite image
clean_video_title = utils.get_valid_filename(title)
file_path_composite = path_render + "2WAY/" + clean_video_title + ".mp4"
file_path_composite_tmp = path_render + "2WAY/" + clean_video_title + ".tmp.mp4"
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
synctimes = [starttime0, starttime1]
starttimes = []
endtimes = []
for synctime in synctimes:
    h0, m0, s0 = syncoffset.split(':')
    h1, m1, s1 = synctime.split(':')
    h2, m2, s2 = syncending.split(':')
    time0_s = 3600 * int(h0) + 60 * int(m0) + int(s0)
    time1_s = 3600 * int(h1) + 60 * int(m1) + int(s1)
    time2_s = 3600 * int(h2) + 60 * int(m2) + int(s2)
    duration = time2_s - time0_s
    m, s = divmod(time1_s - time0_s, 60)
    h, m = divmod(m, 60)
    starttime = format(h, '02') + ':' + format(m, '02') + ':' + format(s, '02')
    m, s = divmod(time1_s + duration, 60)
    h, m = divmod(m, 60)
    endtime = format(h, '02') + ':' + format(m, '02') + ':' + format(s, '02')
    print("segment video"+str(len(endtimes))+": "+starttime+" -> "+endtime)
    starttimes.append(starttime)
    endtimes.append(endtime)


# RENDER: actually render the video
# - video1: 824x928
#   video2: 824x928
#   hconcat -> 1648x928
#
# - chat1: 272x464
#   chat2: 272x464
#   vconcat -> 272x928
#
# - final video 1920x928
#
#  ffmpeg -i in.mp4 -filter:v "scale=1648x928,crop=824:928" -c:a copy out.mp4
#  ffmpeg -i in.mp4 -filter:v "scale=1000x928:force_original_aspect_ratio=decrease,pad=1098:928:-1:-1:color=black,crop=824:928" -c:a copy out.mp4
print("rendering with chat overlay...")
# cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
#       + ' -ss ' + starttimes[0] + ' -to ' + endtimes[0] + ' -i ' + videopaths[0] \
#       + ' -ss ' + starttimes[1] + ' -to ' + endtimes[1] + ' -i ' + videopaths[1] \
#       + ' -ss ' + starttimes[0] + ' -to ' + endtimes[0] + ' -i ' + chatpathsvideo[0] \
#       + ' -ss ' + starttimes[1] + ' -i ' + chatpathsvideo[1] \
#       + ' -filter_complex "' \
#       + ' [0:v] scale=1000x928:force_original_aspect_ratio=decrease,pad=1098:928:-1:-1:color=black,crop=824:928 [tmp0];' \
#       + ' [1:v] scale=1000x928:force_original_aspect_ratio=decrease,pad=1098:928:-1:-1:color=black,crop=824:928 [tmp1];' \
#       + ' [tmp0][tmp1]hstack=inputs=2:shortest=1[left]; ' \
#       + ' [2:v][3:v]vstack=inputs=2:shortest=1[right]; ' \
#       + ' [left][right]hstack=inputs=2:shortest=1[stack]" -shortest -map "[stack]" -map 0:a ' \
#       + ' -vcodec libx264 -crf 18 -preset veryfast -avoid_negative_ts make_zero -framerate 60 ' \
#       + ' -c:a aac ' \
#       + file_path_composite_tmp
# print(cmd)
# subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
# subprocess.Popen(cmd, shell=True).wait()

# RENDER: actually render the video
# - video1: 960x540
#   video2: 960x540
#   hconcat -> 1920x540
#
# - chat1: 960x540
#   chat2: 960x540
#   vconcat -> 1920x540
#
# - final video 1920x1080
#
cmd = path_twitch_ffmpeg + '  ' \
      + ' -ss ' + starttimes[0] + ' -to ' + endtimes[0] + ' -i ' + videopaths[0] \
      + ' -ss ' + starttimes[1] + ' -to ' + endtimes[1] + ' -i ' + videopaths[1] \
      + ' -ss ' + starttimes[0] + ' -to ' + endtimes[0] + ' -i ' + chatpathsvideo[0] \
      + ' -ss ' + starttimes[1] + ' -i ' + chatpathsvideo[1] \
      + ' -filter_complex "' \
      + ' [0:v] scale=960x540 [tmp0];' \
      + ' [1:v] scale=960x540 [tmp1];' \
      + ' [tmp0][tmp1]hstack=inputs=2:shortest=1[top]; ' \
      + ' [2:v][3:v]hstack=inputs=2:shortest=1[bottom]; ' \
      + ' [top][bottom]vstack=inputs=2:shortest=1[stack]" -shortest -map "[stack]" -map 0:a ' \
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


