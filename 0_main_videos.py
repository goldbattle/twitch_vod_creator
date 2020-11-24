# !/usr/bin/env python3

# https://github.com/tsifrer/python-twitch-client
# pip install git+https://github.com/BoraxTheClean/python-twitch-client.git@add-oauth-token-fetch
import twitch

import yaml  # pip install PyYAML

import os
import json
import subprocess
from datetime import datetime
import utils

# authentication information
path_base = os.path.dirname(os.path.abspath(__file__))
auth_config = path_base + "/config/auth.yaml"
with open(auth_config) as f:
    auth = yaml.load(f, Loader=yaml.FullLoader)
client_id = auth["client_id"]
client_secret = auth["client_secret"]

# parameters
channels = ['sodapoppin', 'moonmoon', 'clintstevens', 'pokelawls', 'sevadus', 'happythoughts', 'nmplol']
max_videos = 80

# ================================================================
# ================================================================

# paths of the cli and data
path_twitch_cli = path_base + "/thirdparty/Twitch Downloader/TwitchDownloaderCLI.exe"
path_twitch_ffmpeg = path_base + "/thirdparty/Twitch Downloader/ffmpeg.exe"
path_root = path_base + "/../data/"

# ================================================================
# ================================================================

# setup control+c handler
utils.setup_signal_handle()

# convert the usernames to ids
client_v5 = twitch.TwitchClient(client_id)
users = client_v5.users.translate_usernames_to_ids(channels)

# now lets loop through each user and make sure we have downloaded
# their most recent VODs and if we have not, we should download them!
client_helix = twitch.TwitchHelix(client_id=client_id, client_secret=client_secret)
client_helix.get_oauth()

for user in users:

    # check if we should download any more
    if utils.terminated_requested:
        print('terminate requested, not looking at any more users...')
        break

    # check if the directory is created
    path_data = path_root + "/" + user.name.lower() + "/"
    if not os.path.exists(path_data):
        os.makedirs(path_data)

    # get the videos for this specific user
    print("getting videos for -> " + user.name.lower() + " (id " + str(user.id) + ")")
    vid_iter = client_helix.get_videos(user_id=user.id, page_size=100)
    arr_archive = []
    arr_highlight = []
    arr_upload = []
    ct_added = [0, 0, 0]
    for video in vid_iter:
        # skip the video if no thumbnail
        # this basically allows us to skip the current "live" stream
        # which shows up in the VODs even though it isn't one yet...
        if video['thumbnail_url'] == '':
            continue
        # else lets process
        # "all", "upload", "archive", "highlight"
        if video['type'] == 'archive' and ct_added[0] < max_videos:
            video_v5 = client_v5.videos.get_by_id(video['id'])
            arr_archive.append({'helix': video, 'v5': video_v5})
            ct_added[0] = ct_added[0] + 1
        elif video['type'] == 'highlight' and ct_added[1] < max_videos:
            video_v5 = client_v5.videos.get_by_id(video['id'])
            arr_highlight.append({'helix': video, 'v5': video_v5})
            ct_added[1] = ct_added[1] + 1
        elif video['type'] == 'upload' and ct_added[2] < max_videos:
            video_v5 = client_v5.videos.get_by_id(video['id'])
            arr_upload.append({'helix': video, 'v5': video_v5})
            ct_added[2] = ct_added[2] + 1

    # nice debug print
    print("\t- found " + str(len(arr_archive)) + " archives")
    print("\t- found " + str(len(arr_highlight)) + " highlights")
    print("\t- found " + str(len(arr_upload)) + " uploads")

    # loop through each and download
    for video in arr_archive:

        # check if we should download any more
        if utils.terminated_requested:
            print('terminate requested, not downloading any more..')
            break

        # DATA: api data of this vod
        video_data = {
            'id': video['helix']['id'],
            'user_id': video['helix']['user_id'],
            'user_name': video['helix']['user_name'],
            'title': video['helix']['title'],
            'duration': video['helix']['duration'],
            'game': video['v5']['game'],
            'url': video['v5']['url'],
            'views': video['v5']['views'],
            'moments': utils.get_vod_moments(video['helix']['id']),
            'muted_segments': (video['v5']['muted_segments'] if 'muted_segments' in video['v5'] else []),
            'recorded_at': video['v5']['recorded_at'],
        }

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
        print("\t- saving video info: " + file_path_info)
        if not utils.terminated_requested and not os.path.exists(file_path_info):
            with open(file_path_info, 'w') as file:
                json.dump(video_data, file, indent=4)

        # VIDEO: check if the file exists
        file_path = path_data + export_folder + str(video['helix']['id']) + ".mp4"
        print("\t- download video: " + file_path)
        if not utils.terminated_requested and not os.path.exists(file_path):
            cmd = path_twitch_cli + ' -m VideoDownload' \
                  + ' --id ' + str(video['helix']['id']) + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
                  + ' --quality 1080p60 -o ' + file_path
            subprocess.Popen(cmd).wait()

        # CHAT: check if the file exists
        file_path_chat = path_data + export_folder + str(video['helix']['id']) + "_chat.json"
        print("\t- download chat: " + file_path_chat)
        if not utils.terminated_requested and not os.path.exists(file_path_chat):
            cmd = path_twitch_cli + ' -m ChatDownload' \
                  + ' --id ' + str(video['helix']['id']) + ' --embed-emotes' \
                  + ' -o ' + file_path_chat
            subprocess.Popen(cmd).wait()

        # RENDER: check if the file exists
        file_path_chat = path_data + export_folder + str(video['helix']['id']) + "_chat.json"
        file_path_render = path_data + export_folder + str(video['helix']['id']) + "_chat.mp4"
        if os.path.exists(file_path_chat) and not os.path.exists(file_path_render):
            print("\t- rendering chat: " + file_path_render)
            cmd = path_twitch_cli + ' -m ChatRender' \
                  + ' -i ' + file_path_chat + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
                  + ' -h 1080 -w 320 --framerate 60 --font-size 13' \
                  + ' -o ' + file_path_render
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL).wait()
            # subprocess.Popen(cmd).wait()
