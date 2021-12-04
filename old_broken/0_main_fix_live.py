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
path_root = path_base + "/../data_live/"
path_trash = path_root + "/TRASH/"

# ================================================================
# ================================================================

# setup control+c handler
utils.setup_signal_handle()


if not os.path.exists(path_trash):
    os.makedirs(path_trash)

# find the live video files
files_names = []
files_out = []
files_tmp = []
for subdir, dirs, files in os.walk(path_root):
    if "TRASH" in subdir:
        continue
    for file in files:
        ext = file.split(os.extsep)
        if len(ext) != 3:
            continue
        if ext[1] == "tmp" and ext[2] == "mp4":
            files_out.append(os.path.join(subdir, ext[0]+".mp4"))
            files_tmp.append(os.path.join(subdir, file))
            files_names.append(file)
print("found "+str(len(files_out))+" live videos")
print("found "+str(len(files_tmp))+" temp live videos")

# loop through each video and convert it using ffmpeg
for ct in range(len(files_tmp)):

    # check if we should download any more
    if utils.terminated_requested:
        print('terminate requested, not downloading any more..')
        break

    # check if old enough to process
    oldness = time.time()-os.path.getmtime(files_tmp[ct])
    if oldness < 60:
        print("skipping "+files_names[ct]+" since it is only "+str(oldness)+" sec old")
        continue
    
    # else lets try to convert it using ffmpeg
    if not os.path.exists(files_out[ct]):
        print("processing "+files_names[ct])
        cmd = path_twitch_ffmpeg + '  ' \
              + ' -err_detect ignore_err -i ' + files_tmp[ct] \
              + ' -c copy ' + files_out[ct]
        #print(cmd)
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
        # subprocess.Popen(cmd, shell=True).wait()


    # move the temp file over
    if os.path.exists(files_out[ct]) and os.stat(files_out[ct]).st_size > 1024:
        shutil.move(files_tmp[ct], path_trash) 


