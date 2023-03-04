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
# channels = ['xqc', 'moonmoon', 'sodapoppin', 'clintstevens', 'pokelawls', 'forsen', 'nmplol', 'jerma985', 'veibae']
channel = 'veibae' # xqcow
channel_new = 'veibae' # xqc

# ================================================================
# ================================================================

# paths of the cli and data
path_root = path_base + "/../../data_clips/"
path_data = path_root + "/" + channel + "/"

# new location
path_root_new = path_base + "/../../data_clips_new/"
path_data_new = path_root_new + "/" + channel_new + "/"


# now lets loop through each clip!
t0 = time.time()
count_total_clips_checked = 0
for root, dirs, files in os.walk(path_data):
    for file in files:

        # only move valid files that have a json info and non-zero size mp4
        if not file.endswith('_info.json'):
            continue
        with open(root + "/" + file) as f:
            video_info = json.load(f)
        file_path = path_data + str(video_info['id']) + ".mp4"
        if not os.path.exists(file_path):
            print("WARNING: " + video_info['id'] + " is missing its main video file!!!!")
            continue
        filesize = os.path.getsize(file_path)
        if filesize < 1:
            print("WARNING: " + video_info['id'] + " clip is invalid!!!!")
            continue

        # export folder
        datetime_created = datetime.datetime.strptime(video_info['created_at'], "%Y-%m-%d %H:%M:%SZ")
        export_folder = format(datetime_created.year, '02') + "-" + format(datetime_created.month, '02') + "/"
        if not os.path.exists(path_data_new + export_folder):
            os.makedirs(path_data_new + export_folder)
        print("clip " + format(datetime_created.year, '02') + "-" + format(datetime_created.month, '02') + " -> " + str(video_info['id']))
        #print(video_info)
        count_total_clips_checked = count_total_clips_checked + 1

        # info file
        file_path = path_data + str(video_info['id']) + "_info.json"
        file_path_new = path_data_new + export_folder + str(video_info['id']) + "_info.json"
        if os.path.exists(file_path):
            print("  - moving info file")
            shutil.move(file_path, file_path_new)
        
        # main video
        file_path = path_data + str(video_info['id']) + ".mp4"
        file_path_new = path_data_new + export_folder + str(video_info['id']) + ".mp4"
        if os.path.exists(file_path):
            print("  - moving main video file")
            shutil.move(file_path, file_path_new)
        
        # chat log
        file_path = path_data + str(video_info['id']) + "_chat.json"
        file_path_new = path_data_new + export_folder + str(video_info['id']) + "_chat.json"
        if os.path.exists(file_path):
            print("  - moving chat json file")
            shutil.move(file_path, file_path_new)
        
        # chat rendering
        file_path = path_data + str(video_info['id']) + "_chat.mp4"
        file_path_new = path_data_new + export_folder + str(video_info['id']) + "_chat.mp4"
        if os.path.exists(file_path):
            print("  - moving chat rendering file")
            shutil.move(file_path, file_path_new)
        
        # full video rendering
        file_path = path_data + str(video_info['id']) + "_rendered.mp4"
        file_path_new = path_data_new + export_folder + str(video_info['id']) + "_rendered.mp4"
        if os.path.exists(file_path):
            print("  - moving rendered clip file")
            shutil.move(file_path, file_path_new)


# done :)
t1 = time.time()
print("number of checked clips: " + str(count_total_clips_checked))
print("total execution time: " + str(t1 - t0))



