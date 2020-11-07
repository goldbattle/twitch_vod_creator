# !/usr/bin/env python3

import yaml  # pip install PyYAML

import os
import time
import json
import subprocess
import utils

# video file we wish to render
video_file = "config/01_videos.yaml"

# paths of the cli and data
path_base = os.path.dirname(os.path.abspath(__file__))
path_twitch_cli = path_base + "/Twitch Downloader/TwitchDownloaderCLI.exe"
path_twitch_ffmpeg = path_base + "/Twitch Downloader/ffmpeg.exe"
path_root = path_base + "/../data/"
path_render = path_base + "/../data_rendered/"


# video_file = "config/01_videos_tmp.yaml"
# path_root = "C:/Users/Patrick/Downloads/data_temp/"
# path_render = "C:/Users/Patrick/Downloads/data_rendered/"

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

        # render with chat
        # https://superuser.com/a/1296511
        # log levels: -hide_banner -loglevel quiet -stats
        # hardware encoding: ffmpeg.exe -h encoder=h264_nvenc
        # hardware encoding: -hwaccel_device 0 -hwaccel cuda -loglevel quiet
        # hardware encoding: -c:v h264_nvenc -b:v 0 -cq 20
        # cpu encoding: -vcodec libx264 -crf 18 -preset ultrafast -tune zerolatency
        t0 = time.time()
        if os.path.exists(file_path_render):
            print("\t- rendering with chat overlay")
            cmd = path_twitch_ffmpeg + ' -hwaccel cuda -hide_banner -loglevel quiet -stats ' \
                  + ' -ss ' + video["t_start"] + ' -i ' + file_path_video + ' -to ' + video["t_end"] \
                  + ' -ss ' + video["t_start"] + ' -i ' + file_path_render \
                  + ' -filter_complex "scale=1600x900,pad=1920:1080:0:90:black [tmp1]; ' \
                  + '[tmp1][1:v] overlay=shortest=0:x=1600:y=0:eof_action=endall" -shortest ' \
                  + ' -c:v h264_nvenc -preset llhq -rc:v cbr -b:v 10M -vsync 0 -c:a copy ' \
                  + file_path_composite
            subprocess.Popen(cmd).wait()

        else:
            print("\t- rendering *without* chat overlay")
            cmd = path_twitch_ffmpeg + ' -hwaccel auto -hide_banner -stats -threads 8 ' \
                  + ' -ss ' + video["t_start"] + ' -i ' + file_path_video + ' -to ' + video["t_end"] \
                  + ' -vcodec libx264 -crf 20 -preset veryfast ' \
                  + '-ss ' + video["t_start"] + ' -to ' + video["t_end"] + ' ' \
                  + file_path_composite
            subprocess.Popen(cmd).wait()

        # end timing and compute debug stats
        t1 = time.time()
        h1, m1, s1 = video["t_start"].split(':')
        h2, m2, s2 = video["t_end"].split(':')
        dur_segment = (int(h2) - int(h1)) * 3600 + (int(m2) - int(m1)) * 60 + (int(s2) - int(s1))
        dur_render = t1 - t0 + 1e-6
        print("\t- time to render: " + str(dur_render))
        print("\t- segment duration: " + str(dur_segment))
        print("\t- realtime factor: " + str(dur_segment / dur_render))
        print("")

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
        tmp = video["title"] + "\n" + tmp
        with open(file_path_desc, "w") as text_file:
            text_file.write(tmp)

