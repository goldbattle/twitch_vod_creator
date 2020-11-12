# !/usr/bin/env python3

# https://github.com/PetterKraabol/Twitch-Python
# pip install git+https://github.com/BoraxTheClean/python-twitch-client.git@add-oauth-token-fetch
import twitch

import yaml  # pip install PyYAML

import os
import json
import time
import subprocess
import utils

# authentication information
path_base = os.path.dirname(os.path.abspath(__file__))
auth_config = path_base + "/config/auth.yaml"
with open(auth_config) as f:
    auth = yaml.load(f, Loader=yaml.FullLoader)
client_id = auth["client_id"]
client_secret = auth["client_secret"]

# parameters
channels = ['xqcow', 'moonmoon', 'sodapoppin', 'clintstevens', 'pokelawls', 'forsen', 'nmplol']
min_view_counts = [5000, 4000, 4000, 1500, 2500, 6000, 2500]

# ================================================================
# ================================================================

# paths of the cli and data
path_twitch_cli = path_base + "/thirdparty/Twitch Downloader/TwitchDownloaderCLI.exe"
path_twitch_ffmpeg = path_base + "/thirdparty/Twitch Downloader/ffmpeg.exe"
path_root = path_base + "/../data_clips/"

# ================================================================
# ================================================================

# setup control+c handler
utils.setup_signal_handle()

# convert the usernames to ids
client_v5 = twitch.TwitchClient(client_id)
users = client_v5.users.translate_usernames_to_ids(channels)

# get the mapping between the current game ids and name
gameid2name = {}
for game in client_v5.games.get_top(limit=100):
    gameid2name[game['game']['id']] = game['game']['name']

# now lets loop through each user and make sure we have downloaded
# their most recent VODs and if we have not, we should download them!
t0 = time.time()
count_total_clips_checked = 0
count_total_clips_downloaded = 0
for idx, user in enumerate(users):

    # check if we should download any more
    if utils.terminated_requested:
        print('terminate requested, not looking at any more users...')
        break

    # check if the directory is created
    path_data = path_root + "/" + user.name + "/"
    if not os.path.exists(path_data):
        os.makedirs(path_data)

    # get the videos for this specific user
    try:
        print("getting clips for -> " + user.name + " (id " + str(user.id) + ")")
        client_helix = twitch.TwitchHelix(client_id=client_id, client_secret=client_secret)
        client_helix.get_oauth()
        vid_iter = client_helix.get_clips(broadcaster_id=user.id, page_size=100)
        arr_clips = []
        for video in vid_iter:

            # check if we should download any more
            if utils.terminated_requested:
                print('terminate requested, not downloading any more..')
                break
            # time.sleep(random.uniform(0.0, 0.5))

            # don't download any videos below our viewcount threshold
            if video['view_count'] < min_view_counts[idx]:
                print("skipping " + video['url'] + " (only " + str(video['view_count']) + " views)")
                continue

            # nice debug print
            arr_clips.append(video)
            count_total_clips_checked = count_total_clips_checked + 1
            print("processing " + video['url'])

            # VIDEO: check if the file exists
            file_path_info = path_data + str(video['id']) + "_info.json"
            if not utils.terminated_requested and not os.path.exists(file_path_info):
                print("\t- saving clip info: " + file_path_info)

                # load the game information if we don't have it
                # note sometimes game_id isn't defined (unlisted)
                # in this case just report an empty game
                if video['game_id'] not in gameid2name:
                    game = client_helix.get_games(game_ids=[video['game_id']])
                    if len(game) > 0 and video['game_id'] == game[0]['id']:
                        gameid2name[game[0]['id']] = game[0]['name']
                        game_title = gameid2name[video['game_id']]
                    else:
                        game_title = ""
                else:
                    game_title = gameid2name[video['game_id']]

                # finally write to file
                data = {
                    'id': video['id'],
                    'video_id': video['video_id'],
                    'creator_id': video['creator_id'],
                    'creator_name': video['creator_name'],
                    'title': video['title'],
                    'game_id': video['game_id'],
                    'game': game_title,
                    'url': video['url'],
                    'view_count': video['view_count'],
                    'created_at': video['created_at'].strftime('%Y-%m-%d %H:%M:%SZ'),
                }
                with open(file_path_info, 'w') as file:
                    json.dump(data, file, indent=4)

            # VIDEO: check if the file exists
            file_path = path_data + str(video['id']) + ".mp4"
            print("\t- download clip: " + file_path)
            if not utils.terminated_requested and not os.path.exists(file_path):
                cmd = path_twitch_cli + ' -m ClipDownload' \
                      + ' --id ' + str(video['id']) + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
                      + ' --quality 1080p60 -o ' + file_path
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL).wait()
                count_total_clips_downloaded = count_total_clips_downloaded + 1

            # CHAT: check if the file exists
            file_path_chat = path_data + str(video['id']) + "_chat.json"
            print("\t- download chat: " + file_path_chat)
            if not utils.terminated_requested and not os.path.exists(file_path_chat):
                cmd = path_twitch_cli + ' -m ChatDownload' \
                      + ' --id ' + str(video['id']) + ' --embed-emotes' \
                      + ' -o ' + file_path_chat
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()

        # # loop through each and download
        # for video in arr_clips:
        #
        #     # check if we should download any more
        #     if terminated_requested:
        #         print('terminate requested, not rendering any more..')
        #         break
        #
        #     # RENDER: check if the file exists
        #     file_path_chat = path_data + str(video['id']) + "_chat.json"
        #     file_path_render = path_data + str(video['id']) + "_chat.mp4"
        #     print("\t- rendering: " + file_path_render)
        #     if os.path.exists(file_path_chat) and not os.path.exists(file_path_render):
        #         cmd = path_twitch_cli + ' -m ChatRender' \
        #               + ' -i ' + file_path_chat + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
        #               + ' -h 1080 -w 320 --framerate 60 --font-size 13' \
        #               + ' -o ' + file_path_render
        #         subprocess.Popen(cmd, stdout=subprocess.DEVNULL).wait()

    except Exception as e:
        print(e)

t1 = time.time()
print("number of checked clips: " + str(count_total_clips_checked))
print("number of downloaded clips: " + str(count_total_clips_downloaded))
print("total execution time: " + str(t1 - t0))
