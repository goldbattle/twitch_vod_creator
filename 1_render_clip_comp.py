# !/usr/bin/env python3

# https://github.com/tsifrer/python-twitch-client
# pip install git+https://github.com/BoraxTheClean/python-twitch-client.git@add-oauth-token-fetch
import twitch

import yaml  # pip install PyYAML

import os
import json
import time
import subprocess
import functools
import utils

# authentication information
path_base = os.path.dirname(os.path.abspath(__file__))
auth_config = path_base + "/config/auth.yaml"
with open(auth_config) as f:
    auth = yaml.load(f, Loader=yaml.FullLoader)
client_id = auth["client_id"]
client_secret = auth["client_secret"]

# parameters
channel = 'sodapoppin'
max_clips = 50
date_start = '2020-10-01T00:00:00.00Z'
date_end = '2020-11-01T00:00:00.00Z'
min_views_required = 500

# ================================================================
# ================================================================

# paths of the cli and data
path_twitch_cli = path_base + "/thirdparty/Twitch Downloader 1.38/TwitchDownloaderCLI.exe"
path_twitch_ffmpeg = path_base + "/thirdparty/Twitch Downloader 1.38/ffmpeg.exe"
path_twitch_ffprob = path_base + "/thirdparty/ffmpeg-N-99900-g89429cf2f2-win64-lgpl/ffprobe.exe"
path_root = path_base + "/../data_clips/"
path_render = path_base + "/../data_rendered/"

# ================================================================
# ================================================================

# setup control+c handler
utils.setup_signal_handle()

# convert the usernames to ids
client_v5 = twitch.TwitchClient(client_id)
users = client_v5.users.translate_usernames_to_ids(channel)
assert (len(users) == 1)
user = users[0]

# get the mapping between the current game ids and name
gameid2name = {}
for game in client_v5.games.get_top(limit=100):
    gameid2name[game['game']['id']] = game['game']['name']

# start timing, we will now try to get clips within our time window
t0 = time.time()
print("getting clips for -> " + user.name + " (id " + str(user.id) + ")")
client_helix = twitch.TwitchHelix(client_id=client_id, client_secret=client_secret)
client_helix.get_oauth()
vid_iter = client_helix.get_clips(broadcaster_id=user.id, page_size=100, started_at=date_start, ended_at=date_end)
arr_clips = []
for video in vid_iter:

    # check if we should download any more
    if utils.terminated_requested:
        print('terminate requested, not looking at any more clips...')
        break

    # we are done when we have enough features
    if len(arr_clips) >= max_clips:
        break

    # don't download any videos below our viewcount threshold
    # NOTE: twitch api seems to return in largest view count to smallest
    # NOTE: thus once we hit our viewcount limit just stop...
    if video['view_count'] < min_views_required:
        # print("skipping " + video['url'] + " (only " + str(video['view_count']) + " views)")
        # continue
        break

    # append this clip to our clip array
    # api returns clips in order of most watch to least watched
    print("\t- clip " + video['url'] + " (" + str(video['view_count']) + " views)")
    arr_clips.append(video)

# ================================================================
# ================================================================

# check if the directory is created
path_data = path_root + "/" + user.name + "/"
if not os.path.exists(path_data):
    os.makedirs(path_data)


# function which sorts based on the clip created timestamp
def compare_video_by_datetime(item1, item2):
    return item1['created_at'].strftime("%Y-%m-%d %H:%M:%S") < item2['created_at'].strftime("%Y-%m-%d %H:%M:%S")


# sort the clip array
print("sorting " + str(len(arr_clips)) + " clips by date")
# arr_clips.sort(key=functools.cmp_to_key(compare_video_by_datetime))
arr_clips.sort(key=lambda x: x['created_at'])

# ================================================================
# ================================================================

# now lets loop throuch each and download / render them
for video in arr_clips:

    # debug print
    print("clip has " + str(video['view_count']) + " views (clipped at "
          + video['created_at'].strftime("%Y-%m-%d %H:%M:%S")
          + ") - " + video['url'])

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
    if not utils.terminated_requested and not os.path.exists(file_path):
        print("\t- download clip: " + file_path)
        cmd = path_twitch_cli + ' -m ClipDownload' \
              + ' --id ' + str(video['id']) + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
              + ' --quality 1080p60 -o ' + file_path
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL).wait()

    # CHAT: check if the file exists
    file_path_chat = path_data + str(video['id']) + "_chat.json"
    if not utils.terminated_requested and not os.path.exists(file_path_chat):
        print("\t- download chat: " + file_path_chat)
        cmd = path_twitch_cli + ' -m ChatDownload' \
              + ' --id ' + str(video['id']) + ' --embed-emotes' \
              + ' -o ' + file_path_chat
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()

    # CHAT: check if the file exists, render if needed
    file_path_render = path_data + str(video['id']) + "_chat.mp4"
    if not utils.terminated_requested and os.path.exists(file_path_chat) and not os.path.exists(file_path_render):
        print("\t- rendering chat: " + file_path_render)
        cmd = path_twitch_cli + ' -m ChatRender' \
              + ' -i ' + file_path_chat + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
              + ' -h 1080 -w 320 --framerate 60 --font-size 13' \
              + ' -o ' + file_path_render
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL).wait()
        # subprocess.Popen(cmd).wait()

    # COMPOSITE: render the composite image
    file_path_composite = path_data + str(video['id']) + "_rendered.mp4"
    if not utils.terminated_requested and not os.path.exists(file_path_composite):
        print("\t- rendering composite: " + file_path_composite)

        # make directory if needed
        dir_path_composite = os.path.dirname(os.path.abspath(file_path_composite))
        if not os.path.exists(dir_path_composite):
            os.makedirs(dir_path_composite)

        # render with chat
        t0 = time.time()
        if os.path.exists(file_path_render):
            print("\t- rendering *with* chat overlay")
            cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
                  + ' -i ' + file_path \
                  + ' -i ' + file_path_render \
                  + ' -filter_complex "scale=1600x900,pad=1920:1080:0:90:black [tmp1];' \
                  + ' [tmp1][1:v] overlay=shortest=0:x=1600:y=0:eof_action=endall" -shortest ' \
                  + ' -c:a aac -ar 48k -ac 2 -vcodec libx264 -crf 19 -preset fast ' \
                  + ' -video_track_timescale 90000 -avoid_negative_ts make_zero -framerate 60 ' \
                  + file_path_composite
            subprocess.Popen(cmd).wait()
        else:
            print("\t- rendering *without* chat overlay ")
            cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
                  + ' -i ' + file_path \
                  + ' -c:a aac -ar 48k -ac 2 -vcodec libx264 -crf 19 -preset fast ' \
                  + ' -video_track_timescale 90000 -avoid_negative_ts make_zero -framerate 60 ' \
                  + file_path_composite
            subprocess.Popen(cmd).wait()

        # end timing
        t1 = time.time()
        dur_render = t1 - t0 + 1e-6
        print("\t- time to render: " + str(dur_render))

# ================================================================
# ================================================================

# Now we will stick all the individual videos into a big one
# https://stackoverflow.com/a/36045659
text_file_temp_videos = path_render + "/CLIPS/" + channel + "_" + date_start[:10] + "_" + date_end[:10] + ".txt"
file_path_composite = path_render + "/CLIPS/" + channel + "_" + date_start[:10] + "_" + date_end[:10] + ".mp4"
print("starting to render the composite video (will take a while)...")
if not utils.terminated_requested and not os.path.exists(file_path_composite):

    # make directory if needed
    dir_path_composite = os.path.dirname(os.path.abspath(file_path_composite))
    if not os.path.exists(dir_path_composite):
        os.makedirs(dir_path_composite)

    # text file will all segments
    with open(text_file_temp_videos, 'a') as the_file:
        for video in arr_clips:
            tmp_output_file = path_data + str(video['id']) + "_rendered.mp4"
            if os.path.exists(tmp_output_file):
                the_file.write('file \'' + tmp_output_file + '\'\n')
            else:
                print("\t- WARNING: skipping " + tmp_output_file)

    # now render
    t0_big = time.time()
    print("\t- combining all videos into a single segment!")
    cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
          + '-f concat -safe 0 ' \
          + ' -i ' + text_file_temp_videos \
          + ' -c copy -avoid_negative_ts make_zero ' \
          + file_path_composite
    subprocess.Popen(cmd).wait()
    os.remove(text_file_temp_videos)

    # end timing and compute debug stats
    t1_big = time.time()
    dur_render = t1_big - t0_big + 1e-6
    print("\t- time to render: " + str(dur_render))

# DESC: description file
file_path_desc = path_render + "/CLIPS/" + channel + "_" + date_start[:10] + "_" + date_end[:10] + "_desc.txt"
if not utils.terminated_requested and not os.path.exists(file_path_desc):
    print("\t- writting info: " + file_path_desc)
    tmp = "Top " + str(max_clips) + " Between " + date_start[:10] + " to " + date_end[:10] + "\n\n"

    # loop through each clip, and calculate its location in the video
    num_second_into_video = 0
    for video in arr_clips:
        file_path_info = path_data + str(video['id']) + "_info.json"
        tmp_output_file = path_data + str(video['id']) + "_rendered.mp4"
        if not os.path.exists(tmp_output_file):
            continue
        with open(file_path_info) as f:
            video_info = json.load(f)
        # get what time this video will be in the main video
        m, s = divmod(int(num_second_into_video), 60)
        h, m = divmod(m, 60)
        if h > 0:
            timestamp = format(h, '02') + ':' + format(m, '02') + ':' + format(s, '02')
        else:
            timestamp = format(m, '02') + ':' + format(s, '02')

        # append to the description
        tmp = tmp + timestamp + " \"" + video_info["title"] + "\" clipped by " + video_info["creator_name"] + "\n"
        # tmp = tmp + "Clipped by: " + video_info["creator_name"] + "\n"
        # tmp = tmp + "Viewcount: " + str(video_info["view_count"]) + "\n"
        # tmp = tmp + "Created At: " + video_info["created_at"] + "\n"
        # tmp = tmp + "URL: " + video_info["url"] + "\n\n"

        # add how long this clip is
        # https://superuser.com/a/945604
        cmd = path_twitch_ffprob \
              + " -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 " \
              + tmp_output_file
        pipe = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        vid_length = pipe.communicate()[0]
        num_second_into_video += float(vid_length)

    # finally writ ethe description to file
    with open(file_path_desc, "w") as text_file:
        text_file.write(tmp)