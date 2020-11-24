# !/usr/bin/env python3

import yaml  # pip install PyYAML

import os
import time
import json
import subprocess
import utils
import shutil

# video file we wish to render
video_file = "config/01_videos.yaml"  # sodapoppin
# video_file = "config/02_videos.yaml"  # sevadus
# video_file = "config/03_videos.yaml"  # nmplol

# paths of the cli and data
path_base = os.path.dirname(os.path.abspath(__file__))
path_twitch_cli = path_base + "/thirdparty/Twitch Downloader/TwitchDownloaderCLI.exe"
path_twitch_ffmpeg = path_base + "/thirdparty/Twitch Downloader/ffmpeg.exe"
path_root = path_base + "/../data/"
path_render = path_base + "/../data_rendered/"
path_temp = path_base + "/../data_temp/"

# ================================================================
# ================================================================

# load the template file for the description
template_file = "config/template.txt"
with open(template_file, "r") as myfile:
    template = myfile.read()

# setup control+c handler
utils.setup_signal_handle()

# load the yaml from file
with open(video_file) as f:
    data = yaml.load(f, Loader=yaml.FullLoader)
print("loaded " + str(len(data)) + " videos to render")

# loop through each video and render each segment
# we will want to first ensure chat is rendered
# from there we will render the full segmented video
for video in data:

    # check if we should download any more
    if utils.terminated_requested:
        print('terminate requested, not downloading any more..')
        break

    # nice debug print
    print("processing " + video["video"])

    # VIDEO: check that we have the video
    file_path_video = path_root + video["video"] + ".mp4"
    if not os.path.exists(file_path_video):
        print("\t- ERROR: could not find the video file!")
        print("\t- " + file_path_video)
        continue

    # INFO: open the data file
    file_path_info = path_root + video["video"] + "_info.json"
    # print("\t- opening info: " + file_path_info)
    with open(file_path_info) as f:
        video_info = json.load(f)

    # delete the temp folder if it is there
    if os.path.exists(path_temp) and os.path.isdir(path_temp):
        shutil.rmtree(path_temp)
    if not os.path.exists(path_temp):
        os.makedirs(path_temp)

    # CHAT: check if the file exists, render if needed
    file_path_chat = path_root + video["video"] + "_chat.json"
    file_path_render = path_root + video["video"] + "_chat.mp4"
    if not utils.terminated_requested and os.path.exists(file_path_chat) and not os.path.exists(file_path_render):
        print("\t- rendering chat: " + file_path_chat)
        cmd = path_twitch_cli + ' -m ChatRender' \
              + ' -i ' + file_path_chat + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
              + ' -h 1080 -w 320 --framerate 60 --font-size 13' \
              + ' -o ' + file_path_render
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL).wait()
        # subprocess.Popen(cmd).wait()

    # COMPOSITE: render the composite image
    clean_video_title = video["title"].lower().replace(' ', '_')
    file_path_composite = path_render + video["video"] + "_" + clean_video_title + ".mp4"
    if not utils.terminated_requested and not os.path.exists(file_path_composite):
        print("\t- rendering composite: " + file_path_composite)

        # make directory if needed
        dir_path_composite = os.path.dirname(os.path.abspath(file_path_composite))
        if not os.path.exists(dir_path_composite):
            os.makedirs(dir_path_composite)

        # here we will render each
        seg_start = video["t_start"].split(",")
        seg_end = video["t_end"].split(",")
        dur_segment_total = 0
        t0_big = time.time()
        for idx in range(len(seg_start)):

            # export the segment to a temp folder
            # if we only have a single segment, then no need!
            tmp_output_file = path_temp + "temp_" + str(idx) + ".mp4"
            if len(seg_start) == 1:
                tmp_output_file = file_path_composite

            # check if we should download any more
            if utils.terminated_requested:
                print('terminate requested, not rendering more segments..')
                break

            # render with chat
            # https://superuser.com/a/1296511
            # log levels: -hide_banner -loglevel quiet -stats
            # hardware encoding: ffmpeg.exe -h encoder=h264_nvenc
            # hardware encoding: -hwaccel_device 0 -hwaccel cuda -loglevel quiet
            # hardware encoding: -c:a aac -c:v h264_nvenc
            # hardware encoding: 1) -preset llhq -rc:v cbr -b:v 10M -avoid_negative_ts make_zero
            # hardware encoding: 2) -preset p6 -tune hq -b:v 8M -maxrate:v 10M -qmin 10 -qmax 23 -avoid_negative_ts make_zero
            # cpu encoding: -c:a aac -vcodec libx264 -crf 20 -preset veryfast
            t0 = time.time()
            if os.path.exists(file_path_render):
                print("\t- rendering with chat overlay " + seg_start[idx] + " to " + seg_end[idx])
                cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
                      + ' -ss ' + seg_start[idx] + ' -i ' + file_path_video + ' -to ' + seg_end[idx] \
                      + ' -ss ' + seg_start[idx] + ' -i ' + file_path_render \
                      + ' -filter_complex "scale=1600x900,pad=1920:1080:0:90:black [tmp1];' \
                      + ' [tmp1][1:v] overlay=shortest=0:x=1600:y=0:eof_action=endall" -shortest ' \
                      + ' -c:a aac -vcodec libx264 -crf 19 -preset fast -avoid_negative_ts make_zero ' \
                      + tmp_output_file
                subprocess.Popen(cmd).wait()
            else:
                print("\t- rendering *without* chat overlay " + seg_start[idx] + " to " + seg_end[idx])
                h1, m1, s1 = seg_start[idx].split(':')
                h2, m2, s2 = seg_end[idx].split(':')
                time1_s = 3600 * int(h1) + 60 * int(m1) + int(s1)
                time2_s = 3600 * int(h2) + 60 * int(m2) + int(s2)
                m, s = divmod(time2_s - time1_s, 60)
                h, m = divmod(m, 60)
                seg_length = format(h, '02') + ':' + format(m, '02') + ':' + format(s, '02')
                print(seg_length)
                cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
                      + ' -ss ' + seg_start[idx] + ' -i ' + file_path_video + ' -t ' + seg_length \
                      + ' -c:a aac -vcodec libx264 -crf 19 -preset fast -avoid_negative_ts make_zero ' \
                      + tmp_output_file
                subprocess.Popen(cmd).wait()

            # end timing and compute debug stats
            t1 = time.time()
            h1, m1, s1 = seg_start[idx].split(':')
            h2, m2, s2 = seg_end[idx].split(':')
            dur_segment = (int(h2) - int(h1)) * 3600 + (int(m2) - int(m1)) * 60 + (int(s2) - int(s1))
            dur_render = t1 - t0 + 1e-6
            dur_segment_total += dur_segment
            print("\t- time to render: " + str(dur_render))
            print("\t- segment duration: " + str(dur_segment))
            print("\t- realtime factor: " + str(dur_segment / dur_render))

        # If we have multiple segments, then we need to combine them
        # https://stackoverflow.com/a/36045659
        if not utils.terminated_requested and len(seg_start) != 1:
            # text file will all segments
            text_file_temp_videos = path_temp + "videos.txt"
            with open(text_file_temp_videos, 'a') as the_file:
                for idx in range(len(seg_start)):
                    tmp_output_file = path_temp + "temp_" + str(idx) + ".mp4"
                    the_file.write('file \'' + tmp_output_file + '\'\n')
            # now render
            print("\t- combining all videos into a single segment!")
            cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
                  + '-f concat -safe 0 ' \
                  + ' -i ' + text_file_temp_videos \
                  + ' -c copy -avoid_negative_ts make_zero ' \
                  + file_path_composite
            subprocess.Popen(cmd).wait()

            # end timing and compute debug stats
            t1_big = time.time()
            dur_render = t1_big - t0_big + 1e-6
            print("\t- time to render: " + str(dur_render))
            print("\t- segment durations: " + str(dur_segment_total))
            print("\t- realtime factor: " + str(dur_segment_total / dur_render))

    # DESC: description file
    file_path_desc = path_render + video["video"] + "_" + clean_video_title + "_desc.txt"
    if not utils.terminated_requested and not os.path.exists(file_path_desc):
        print("\t- writting info: " + file_path_desc)
        tmp = str(template)
        tmp = tmp.replace("$id", video_info["id"])
        tmp = tmp.replace("$title", video_info["title"])
        tmp = tmp.replace("$game", video_info["game"])
        tmp = tmp.replace("$views", str(video_info["views"]))
        tmp = tmp.replace("$t_start", video["t_start"])
        tmp = tmp.replace("$t_end", video["t_end"])
        tmp = tmp.replace("$recorded", video_info["recorded_at"])
        tmp = tmp.replace("$file", video["video"] + ".mp4")
        tmp = tmp.replace("$url", video_info["url"])
        tmp = video["title"] + "\n\n" + tmp
        with open(file_path_desc, "w") as text_file:
            text_file.write(tmp)

    # nice split between each segment
    print("")

