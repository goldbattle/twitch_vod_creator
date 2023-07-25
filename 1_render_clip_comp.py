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
channel = 'sodapoppin'
max_clips = 30
date_start = '2023-06-01T00:00:00.00Z'
date_end = '2023-06-30T00:00:00.00Z'
min_views_required = 1000
get_latest_from_twitch = True
remove_rendered = True
clips_to_ignore = [
    "EasyFairLlamaHoneyBadger-rxZed8PoO1MR3PgL",
]


# ================================================================
# ================================================================

# paths of the cli and data
path_twitch_cli = path_base + "/thirdparty/Twitch_Downloader_1.53.0/TwitchDownloaderCLI"
path_twitch_ffmpeg = path_base + "/thirdparty/ffmpeg-4.3.1-amd64-static/ffmpeg"
path_twitch_ffprob = path_base + "/thirdparty/ffmpeg-4.3.1-amd64-static/ffprobe"
path_font = path_base.replace("\\", "/").replace(":", "\\\\:") + "/thirdparty/bebas_neue/BebasNeue-Regular.ttf"
path_root = path_base + "/../data_clips_new/"
path_render = path_base + "/../data_rendered/"
path_temp = "/tmp/tvc_render_clip_comp/"

# ================================================================
# ================================================================

# setup control+c handler
utils.setup_signal_handle()

# define this user directory and make if not exists
path_data = path_root + "/" + channel + "/"
if not os.path.exists(path_data):
    os.makedirs(path_data)
if not os.path.exists(path_temp):
    os.makedirs(path_temp)

# try to download any new clips if we are enabled
if get_latest_from_twitch:

    # convert the usernames to ids
    client_helix = twitch.TwitchHelix(client_id=client_id, client_secret=client_secret)
    client_helix.get_oauth()
    users = client_helix.get_users(login_names=[channel])
    assert (len(users) == 1)
    user = users[0]

    # loop through all clips
    gameid2name = {}
    print("getting clips for -> " + user["login"] + " (id " + str(user["id"]) + ")")
    vid_iter = client_helix.get_clips(broadcaster_id=user["id"], page_size=100, started_at=date_start, ended_at=date_end)
    # vid_iter = client_helix.get_clips(broadcaster_id=user["id"], page_size=100)
    try:
        for video in vid_iter:

            # check if we should download any more
            if utils.terminated_requested:
                print('terminate requested, not looking at any more clips...')
                exit(-1)

            # don't download any videos below our viewcount threshold
            # NOTE: twitch api seems to return in largest view count to smallest
            # NOTE: thus once we hit our viewcount limit just stop...
            if video['view_count'] < min_views_required:
                print("skipping " + video['url'] + " (only " + str(video['view_count']) + " views)")
                # continue
                break

            # api returns clips in order of most watch to least watched
            print("clip " + video['url'] + " (" + str(video['view_count']) + " views)")

            # extract what folder we should save into
            # create the folder if it isn't created already
            try:
                date = video['created_at']
                export_folder = format(date.year, '02') + "-" + format(date.month, '02') + "/"
            except:
                export_folder = "unknown/"
            if not os.path.exists(path_data + export_folder):
                os.makedirs(path_data + export_folder)

            # INFO: always save to file so our viewcount gets updated!
            # INFO: we only update the viewcount, as when the VOD gets deleted most elements are lost
            file_path_info = path_data + export_folder + str(video['id']) + "_info.json"
            if not utils.terminated_requested and not os.path.exists(file_path_info):
                print("\t- saving clip info: " + str(video['id']))

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

                # have to call the graphql api to get where the clip is in the VOD
                clip_data = utils.get_clip_data(video['id'])

                # finally write to file
                data = {
                    'id': video['id'],
                    'video_id': video['video_id'],
                    'video_offset': clip_data['offset'],
                    'creator_id': video['creator_id'],
                    'creator_name': video['creator_name'],
                    'title': video['title'],
                    'game_id': video['game_id'],
                    'game': game_title,
                    'url': video['url'],
                    'view_count': video['view_count'],
                    'duration': clip_data['duration'],
                    'created_at': video['created_at'].strftime('%Y-%m-%d %H:%M:%SZ'),
                }
                with open(file_path_info, 'w', encoding="utf-8") as file:
                    json.dump(data, file, indent=4)

            elif not utils.terminated_requested:
                print("\t- updating clip info!")
                with open(file_path_info) as f:
                    video_info = json.load(f)
                # update view count
                video_info["view_count"] = video['view_count']
                # update clip location if failed before
                if video_info["video_offset"] == -1:
                    clip_data = utils.get_clip_data(video['id'])
                    if clip_data['offset'] != -1:
                        video_info["video_offset"] = clip_data['offset']
                        video_info["duration"] = clip_data['duration']
                # finally write to file
                with open(file_path_info, 'w', encoding="utf-8") as file:
                    json.dump(video_info, file, indent=4)

            # VIDEO: check if the file exists
            file_path = path_data + export_folder + str(video['id']) + ".mp4"
            file_path_tmp = path_temp + str(video['id']) + ".mp4"
            if not utils.terminated_requested and not os.path.exists(file_path):
                print("\t- download clip: " + str(video['id']))
                cmd = path_twitch_cli + ' clipdownload' \
                    + ' --id https://clips.twitch.tv/' + str(video['id']) \
                    + ' -o ' + file_path_tmp
                #subprocess.Popen(cmd, shell=True).wait()
                subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
                shutil.move(file_path_tmp, file_path)

            # CHAT: check if the file exists
            try:
                file_path_chat = path_data + export_folder + str(video['id']) + "_chat.json"
                file_path_chat_tmp = path_temp + str(video['id']) + "_chat.json"
                if not utils.terminated_requested and not os.path.exists(file_path_chat):
                    print("\t- download chat: " + str(video['id']))
                    cmd = path_twitch_cli + ' chatdownload' \
                        + ' --id ' + str(video['id']) \
                        + ' --embed-images --chat-connections 6' \
                        + ' --bttv true --ffz true --stv true' \
                        + ' -o ' + file_path_chat_tmp
                    # subprocess.Popen(cmd, shell=True).wait()
                    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
                    shutil.move(file_path_chat_tmp, file_path_chat)
            except Exception as e:
                print(e)

    except Exception as e:
        print("twitch api failure.... stopping querying....")
        print(e)
        exit(-1)

# ================================================================
# ================================================================

# now we will re-load from disk to try to get any clips that have since been deleted
# clips can be deleted due to DMCA or other VODs being removed..
# only load clips which are within our time range, so our top clips are in the range selected
arr_clips = []
datetime_start = datetime.datetime.strptime(date_start, "%Y-%m-%dT%H:%M:%S.%fZ")
datetime_end = datetime.datetime.strptime(date_end, "%Y-%m-%dT%H:%M:%S.%fZ")
for root, dirs, files in os.walk(path_data):
    for file in files:
        if not file.endswith('_info.json'):
            continue
        with open(root + "/" + file) as f:
            video_info = json.load(f)
        datetime_created = datetime.datetime.strptime(video_info['created_at'], "%Y-%m-%d %H:%M:%SZ")
        export_folder = format(datetime_created.year, '02') + "-" + format(datetime_created.month, '02') + "/"
        file_path = path_data + export_folder + str(video_info['id']) + ".mp4"
        if not os.path.exists(file_path):
            print("WARNING: " + video_info['id'] + " is missing its main video file!!!!")
            continue
        filesize = os.path.getsize(file_path)
        if filesize < 1:
            print("WARNING: " + video_info['id'] + " clip is invalid!!!!")
            continue
        datetime_created = datetime.datetime.strptime(video_info['created_at'], "%Y-%m-%d %H:%M:%SZ")
        if datetime_created < datetime_start:
            continue
        if datetime_created > datetime_end:
            continue
        # skip if in ignore list
        if video_info["id"] in clips_to_ignore:
            print("WARNING: " + video_info['id'] + " clip has been IGNORED!!!!")
            continue
        arr_clips.append(video_info)

# Now we will loop through all clips and remove any that occur at the same time instance.
# We can check this by first checking if two clips come from the same vod, then
arr_clips_no_common = []
arr_clips.sort(key=lambda x: x['duration'] if "duration" in x else -1, reverse=True)
for id1, video1 in enumerate(arr_clips):
    # skip if we don't have offset information
    if "video_id" not in video1 or video1['video_id'] == "":
        arr_clips_no_common.append(id1)
        continue
    if "video_offset" not in video1 or video1['video_offset'] == -1:
        arr_clips_no_common.append(id1)
        continue
    if "duration" not in video1 or video1['duration'] == -1:
        arr_clips_no_common.append(id1)
        continue
    # see if there is one that occurs at this same time
    id_common = []
    for id2, video2 in enumerate(arr_clips):
        # skip if we don't have offset information
        if id1 == id2:
            continue
        if "video_id" not in video2 or video2['video_id'] == "":
            continue
        if "video_offset" not in video2 or video2['video_offset'] == -1:
            continue
        if "duration" not in video2 or video2['duration'] == -1:
            continue
        # skip if a different vod
        if video1['video_id'] != video2['video_id']:
            continue
        # skip if no overlaps
        start1 = video1['video_offset']
        end1 = video1['video_offset'] + video1['duration']
        start2 = video2['video_offset']
        end2 = video2['video_offset'] + video2['duration']
        if start1 < end2 and start2 < end1:
            id_common.append(id2)
    # if we have not detected a common feature add it
    if len(id_common) == 0:
        arr_clips_no_common.append(id1)
        continue
    # else if we have not appended at least one of the common
    num_added = 0
    for id3 in id_common:
        if id3 in arr_clips_no_common:
            num_added = num_added + 1
    if num_added == 0:
        # print("ADDING: " + video1['id'] + " has overlapping with " + str(len(id_common)) + " features")
        # for id3 in id_common:
        #    print(id3)
        arr_clips_no_common.append(id1)
        continue

# replace our list of clips with non-overlapping ones
arr_clips_new = []
for id1, video1 in enumerate(arr_clips):
    if id1 in arr_clips_no_common:
        arr_clips_new.append(video1)
arr_clips = arr_clips_new

# sort the clip array first by view count, then by date
print("sorting " + str(len(arr_clips)) + " clips by viewcount")
arr_clips.sort(key=lambda x: x['view_count'])
start_id = max(0, len(arr_clips) - max_clips)
arr_clips = arr_clips[start_id:]
print("sorting " + str(len(arr_clips)) + " clips by date")
arr_clips.sort(key=lambda x: x['created_at'])

# stop the program if we don't have enough clips
if len(arr_clips) < max_clips:
    print("ERROR: unable to find enough requested clips....")
    print("ERROR: either decrease the min view count or number of requested clips..")
    exit(-1)
print("")

# ================================================================
# ================================================================


# now lets loop through each and download / render them
for video in arr_clips:
    # debug print
    print("clip has " + str(video['view_count']) + " views (clipped at " + video['created_at'] + ")")
    print("\t- " + video['url'])

    # recover sub-folder this clip is in
    datetime_created = datetime.datetime.strptime(video['created_at'], "%Y-%m-%d %H:%M:%SZ")
    export_folder = format(datetime_created.year, '02') + "-" + format(datetime_created.month, '02') + "/"

    # CHAT: check if the file exists, render if needed
    file_path_chat = path_data + export_folder + str(video['id']) + "_chat.json"
    file_path_render = path_data + export_folder + str(video['id']) + "_chat.mp4"
    if not utils.terminated_requested and os.path.exists(file_path_chat) and not os.path.exists(file_path_render):
        print("\t- rendering chat: " + export_folder + str(video['id']) + "_chat.mp4")
        cmd = path_twitch_cli + ' chatrender' \
                + ' -i ' + file_path_chat + ' -o ' + file_path_render \
                + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
                + ' -h 926 -w 274 --update-rate 0.1 --framerate 60 --font-size 15' \
                + ' --bttv true --ffz true --stv true --sub-messages true --badges true --sharpening true --dispersion true' \
                + ' --temp-path "' + path_temp + '" '
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
        # subprocess.Popen(cmd, shell=True).wait()

    # COMPOSITE: render the composite image
    file_path = path_data + export_folder + str(video['id']) + ".mp4"
    file_path_composite = path_data + export_folder + str(video['id']) + "_rendered.mp4"
    if not utils.terminated_requested and not os.path.exists(file_path_composite):
        print("\t- rendering composite: " + export_folder + str(video['id']) + "_rendered.mp4")

        # make directory if needed
        dir_path_composite = os.path.dirname(os.path.abspath(file_path_composite))
        if not os.path.exists(dir_path_composite):
            os.makedirs(dir_path_composite)

        # render with chat
        # text fading based on: http://ffmpeg.shanewhite.co/
        # -hide_banner -loglevel quiet -stats
        t0 = time.time()
        title_clean = re.sub(r'http\S+', '', video["title"])
        title_clean = re.sub(r'www\S+', '', title_clean)
        title_clean = re.sub(r"[^a-zA-Z0-9'.?: ]", '', title_clean)
        title_clean = title_clean.replace("'", "\u2019")
        if os.path.exists(file_path_render):
            print("\t- rendering *with* chat overlay")
            cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
                  + ' -i ' + file_path \
                  + ' -i ' + file_path_render \
                  + ' -filter_complex "scale=1646x926,pad=1920:926:0:90:black [tmp0];' \
                  + ' [tmp0]drawtext=text=\'' + title_clean \
                  + '\':x=25:y=25:fontfile=' + path_font + ':fontsize=85:fontcolor=white:bordercolor=black:borderw=5' \
                  + ':alpha=\'if(lt(t,0),0,if(lt(t,0),(t-0)/0,if(lt(t,4),1,if(lt(t,4.5),(0.5-(t-4))/0.5,0))))\'[tmp1]; ' \
                  + ' [tmp1][1:v] overlay=shortest=0:x=1646:y=0:eof_action=endall" -shortest ' \
                  + ' -c:a aac -ar 48k -ac 2 -vcodec libx264 -crf 19 -preset fast ' \
                  + ' -video_track_timescale 90000 -avoid_negative_ts make_zero -map_chapters -1 -fflags +genpts -framerate 60 ' \
                  + file_path_composite
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
            #subprocess.Popen(cmd, shell=True).wait()
        else:
            print("\t- rendering *without* chat overlay ")
            cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
                  + ' -i ' + file_path \
                  + ' -vf "scale=1646x926,pad=1920:926:0:90:black,' \
                  + 'drawtext=text=\'' + title_clean \
                  + '\':x=25:y=25:fontfile=' + path_font + ':fontsize=85:fontcolor=white:bordercolor=black:borderw=5' \
                  + ':alpha=\'if(lt(t,0),0,if(lt(t,0),(t-0)/0,if(lt(t,4),1,if(lt(t,4.5),(0.5-(t-4))/0.5,0))))\' ' \
                  + ' " -c:a aac -ar 48k -ac 2 -vcodec libx264 -crf 19 -preset fast ' \
                  + ' -video_track_timescale 90000 -avoid_negative_ts make_zero -map_chapters -1 -fflags +genpts -framerate 60 ' \
                  + file_path_composite
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
            #subprocess.Popen(cmd, shell=True).wait()

        # end timing
        t1 = time.time()
        dur_render = t1 - t0 + 1e-6
        print("\t- time to render: " + str(dur_render))
        print()

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

            # recover sub-folder this clip is in
            datetime_created = datetime.datetime.strptime(video['created_at'], "%Y-%m-%d %H:%M:%SZ")
            export_folder = format(datetime_created.year, '02') + "-" + format(datetime_created.month, '02') + "/"

            # append to our file
            tmp_output_file = path_data + export_folder + str(video['id']) + "_rendered.mp4"
            if os.path.exists(tmp_output_file):
                the_file.write('file \'' + os.path.abspath(tmp_output_file) + '\'\n')
            else:
                print("\t- WARNING: skipping " + os.path.abspath(tmp_output_file))

    # now render
    t0_big = time.time()
    print("\t- combining all videos into a single segment!")
    cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
          + '-f concat -safe 0 ' \
          + ' -i ' + text_file_temp_videos \
          + ' -c copy -avoid_negative_ts make_zero -map_chapters -1 ' \
          + file_path_composite
    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
    #subprocess.Popen(cmd, shell=True).wait()
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

        # recover sub-folder this clip is in
        datetime_created = datetime.datetime.strptime(video['created_at'], "%Y-%m-%d %H:%M:%SZ")
        export_folder = format(datetime_created.year, '02') + "-" + format(datetime_created.month, '02') + "/"

        # construct the filepath
        file_path_info = path_data + export_folder + str(video['id']) + "_info.json"
        tmp_output_file = path_data + export_folder + str(video['id']) + "_rendered.mp4"
        if not os.path.exists(tmp_output_file):
            print("\t- WARNING: skipping " + tmp_output_file)
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
        title_clean = re.sub(r"[^a-zA-Z0-9'.?: ]", '', video_info["title"])
        title_clean = title_clean.replace("\\\\", "\\\\\\\\").replace("'", "\u2019")
        tmp = tmp + timestamp + " \"" + title_clean \
              + "\" clipped by " + video_info["creator_name"] + "\n"
        # tmp = tmp + "Clipped by: " + video_info["creator_name"] + "\n"
        # tmp = tmp + "Viewcount: " + str(video_info["view_count"]) + "\n"
        # tmp = tmp + "Created At: " + video_info["created_at"] + "\n"
        # tmp = tmp + "URL: " + video_info["url"] + "\n\n"
        print("=============================")
        print("  "+str(timestamp)+ " - "+video_info["id"])
        print("  "+title_clean)

        # add how long this clip is
        # https://superuser.com/a/945604
        cmd = path_twitch_ffprob \
              + " -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 " \
              + tmp_output_file
        pipe = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        vid_length = pipe.communicate()[0]
        num_second_into_video += float(vid_length)

    # finally write the description to file
    with open(file_path_desc, "w", encoding="utf-8") as text_file:
        text_file.write(tmp)


# finally remove the old render file to save space...
if not utils.terminated_requested and remove_rendered:
    for video in arr_clips:
        datetime_created = datetime.datetime.strptime(video['created_at'], "%Y-%m-%d %H:%M:%SZ")
        export_folder = format(datetime_created.year, '02') + "-" + format(datetime_created.month, '02') + "/"
        tmp_output_file = path_data + export_folder + str(video['id']) + "_rendered.mp4"
        if os.path.exists(tmp_output_file):
            os.remove(tmp_output_file)
