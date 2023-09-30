# !/usr/bin/env python3

import yaml  # pip install PyYAML

import os
import time
import json
import subprocess
import utils
import shutil

# video file we wish to render
path_base = os.path.dirname(os.path.abspath(__file__))
video_file = path_base + "/config/soda_04_videos.yaml"
config_file = path_base + "/config/soda_config_youtube.yaml"
# video_file = path_base + "/config/clint_01_videos.yaml"
# config_file = path_base + "/config/clint_config_youtube.yaml"

# paths of the cli and data
path_twitch_cli = path_base + "/thirdparty/Twitch_Downloader_1.53.0/TwitchDownloaderCLI"
path_twitch_ffmpeg = path_base + "/thirdparty/ffmpeg-4.3.1-amd64-static/ffmpeg"
path_twitch_ffprob = path_base + "/thirdparty/ffmpeg-4.3.1-amd64-static/ffprobe"
path_root = path_base + "/../"
path_render = path_base + "/../data_rendered/"
# path_temp = path_base + "/../data_temp/render_segments/"
path_temp = "/tmp/tvc_render_segments/"

# ================================================================
# ================================================================

# load the yaml from file
with open(config_file) as f:
    config = yaml.load(f, Loader=yaml.FullLoader)
print("loaded config file: " + config_file)

# load the template file for the description
template_file = path_base + "/config/" + config["yt_template"]
with open(template_file, "r") as myfile:
    template = myfile.read()
print("loaded template file: " + template_file)

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
    clean_video_title = utils.get_valid_filename(video["title"])
    path_temp_parts = path_temp + "/parts/" + clean_video_title + "/"
    if os.path.exists(path_temp_parts) and os.path.isdir(path_temp_parts):
        shutil.rmtree(path_temp_parts)
    if not os.path.exists(path_temp):
        os.makedirs(path_temp)
    if not os.path.exists(path_temp_parts):
        os.makedirs(path_temp_parts)
        
    try:

        # COMPOSITE: render the composite image
        file_path_composite = path_render + video["video"] + "_" + clean_video_title + ".mp4"
        file_path_composite_tmp = path_temp + clean_video_title + ".tmp.mp4"
        if not utils.terminated_requested and not os.path.exists(file_path_composite):

            # see if user requested the render
            should_render_chat = True
            if "with_chat" in video:
                should_render_chat = video["with_chat"]

            # check if the chat exists, render if needed
            file_path_chat = path_root + video["video"] + "_chat.json"
            file_path_render = path_root + video["video"] + "_chat.mp4"
            file_path_render_tmp = path_temp + clean_video_title + "_chat.mp4"
            if not utils.terminated_requested and should_render_chat and os.path.exists(file_path_chat) and not os.path.exists(file_path_render):
                print("\t- rendering chat: " + file_path_chat)
                cmd = path_twitch_cli + ' chatrender' \
                    + ' -i ' + file_path_chat + ' -o ' + file_path_render_tmp \
                    + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
                    + ' -h 926 -w 274 --update-rate 0.1 --framerate 60 --font-size 15' \
                    + ' --bttv true --ffz true --stv true --sub-messages true --badges true --sharpening true --dispersion true' \
                    + ' --temp-path "' + path_temp + '" '
                subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
                #subprocess.Popen(cmd, shell=True).wait()
                shutil.move(file_path_render_tmp, file_path_render) 

            # now we can render the composite
            print("\t- rendering composite: " + file_path_composite)

            # make directory if needed
            dir_path_composite = os.path.dirname(os.path.abspath(file_path_composite))
            if not os.path.exists(dir_path_composite):
                os.makedirs(dir_path_composite)

            # delete temp file if it is there
            if os.path.exists(file_path_composite_tmp):
                print("\t- deleting temp file: " + file_path_composite_tmp)
                os.remove(file_path_composite_tmp)

            # here we will render each
            seg_start = video["t_start"].split(",")
            seg_end = video["t_end"].split(",")
            dur_segment_total = 0
            t0_big = time.time()
            for idx in range(len(seg_start)):

                # export the segment to a temp folder
                # if we only have a single segment, then no need!
                tmp_output_file = path_temp_parts + "temp_" + str(idx) + ".mp4"
                if len(seg_start) == 1:
                    tmp_output_file = file_path_composite_tmp

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
                if should_render_chat and os.path.exists(file_path_render):
                    print("\t- rendering with chat overlay " + seg_start[idx] + " to " + seg_end[idx])
                    # get a chat time offset if we have it
                    h1, m1, s1 = seg_start[idx].split(':')
                    time1_s = 3600 * int(h1) + 60 * int(m1) + int(s1)
                    if "t_chat_offset" in video:
                        time1_s = time1_s + int(video["t_chat_offset"])
                        print("\t- chat has offset of "+str(int(video["t_chat_offset"])) + " seconds")
                    m, s = divmod(time1_s, 60)
                    h, m = divmod(m, 60)
                    seg_start_chat = format(h, '02') + ':' + format(m, '02') + ':' + format(s, '02')
                    # finally render!
                    cmd = path_twitch_ffmpeg + '  ' \
                        + ' -ss ' + seg_start[idx] + ' -i ' + file_path_video + ' -to ' + seg_end[idx] \
                        + ' -ss ' + seg_start_chat + ' -i ' + file_path_render \
                        + ' -filter_complex "[0:v] scale=1646x926 [tmp1];' \
                        + ' [tmp1][1:v]hstack=inputs=2:shortest=1[stack]" -shortest -map "[stack]" -map 0:a ' \
                        + ' -vcodec libx264 -crf 10 -preset veryfast -avoid_negative_ts make_zero -framerate 60 -vsync 2 -map_chapters -1 ' \
                        + ' -c:a aac ' \
                        + tmp_output_file
                    # print(cmd)
                    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
                    # subprocess.Popen(cmd, shell=True).wait()
                else:
                    print("\t- rendering *without* chat overlay " + seg_start[idx] + " to " + seg_end[idx])
                    h1, m1, s1 = seg_start[idx].split(':')
                    h2, m2, s2 = seg_end[idx].split(':')
                    time1_s = 3600 * int(h1) + 60 * int(m1) + int(s1)
                    time2_s = 3600 * int(h2) + 60 * int(m2) + int(s2)
                    m, s = divmod(time2_s - time1_s, 60)
                    h, m = divmod(m, 60)
                    seg_length = format(h, '02') + ':' + format(m, '02') + ':' + format(s, '02')
                    cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
                        + ' -ss ' + seg_start[idx] + ' -i ' + file_path_video + ' -t ' + seg_length \
                        + ' -vf scale=w=1920:h=1080 ' \
                        + ' -c:a aac -vcodec libx264 -crf 10 -preset fast -avoid_negative_ts make_zero -vsync 2 -map_chapters -1 ' \
                        + tmp_output_file
                    #print(cmd)
                    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
                    #subprocess.Popen(cmd, shell=True).wait()

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
                text_file_temp_videos = path_temp_parts + "videos.txt"
                with open(text_file_temp_videos, 'a') as the_file:
                    for idx in range(len(seg_start)):
                        tmp_output_file = path_temp_parts + "temp_" + str(idx) + ".mp4"
                        the_file.write('file \'' + os.path.abspath(tmp_output_file) + '\'\n')
                # now render
                print("\t- combining all videos into a single segment!")
                cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
                    + '-f concat -safe 0 ' \
                    + ' -i ' + text_file_temp_videos \
                    + ' -c copy -avoid_negative_ts make_zero -map_chapters -1 ' \
                    + file_path_composite_tmp
                #print(cmd)
                subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
                #subprocess.Popen(cmd, shell=True).wait()

                # end timing and compute debug stats
                t1_big = time.time()
                dur_render = t1_big - t0_big + 1e-6
                print("\t- time to render: " + str(dur_render))
                print("\t- segment durations: " + str(dur_segment_total))
                print("\t- realtime factor: " + str(dur_segment_total / dur_render))
            
            # finally copy temp file to new location
            if not utils.terminated_requested and os.path.exists(file_path_composite_tmp):
                print("\t- renaming temp export file to final filename")
                shutil.move(file_path_composite_tmp, file_path_composite)
            if utils.terminated_requested and os.path.exists(file_path_composite_tmp):
                print("\t- removing half rendered temp file")
                os.remove(file_path_composite_tmp)

        # DESC: description file
        file_path_desc = path_render + video["video"] + "_" + clean_video_title + "_desc.txt"
        if not utils.terminated_requested and not os.path.exists(file_path_desc):
            print("\t- writting info: " + file_path_desc)
            tmp = str(template)
            tmp = tmp.replace("$id", video_info["id"])
            tmp = tmp.replace("$title", video_info["title"])
            # tmp = tmp.replace("$game", video_info["game"])
            tmp = tmp.replace("$views", str(video_info["views"]))
            tmp = tmp.replace("$t_start", video["t_start"])
            tmp = tmp.replace("$t_end", video["t_end"])
            tmp = tmp.replace("$recorded", video_info["recorded_at"])
            tmp = tmp.replace("$file", video["video"] + ".mp4")
            tmp = tmp.replace("$url", video_info["url"])
            if "description" in video:
                tmp = video["description"] + "\n\n" + tmp
            tmp = video["title"] + "\n\n" + tmp
            with open(file_path_desc, "w", encoding="utf-8") as text_file:
                text_file.write(tmp)

        # MUTED COMPOSITE: render the composite image
        # if the user has now added details on segments of the vod should be muted then we will
        # these can be copyrited segments that block the video from being viewed
        # this will extra the audio from the existing video, mute it, then re-encode it
        # https://superuser.com/a/1752409
        # https://superuser.com/a/1256052
        file_path_composite_muted = path_render + video["video"] + "_" + clean_video_title + "_muted.mp4"
        file_path_composite_muted_tmp = path_temp + clean_video_title + "_muted.tmp.mp4"
        if not utils.terminated_requested and not os.path.exists(file_path_composite_muted) and os.path.exists(file_path_composite) and "t_youtube_mute" in video:
        
            # get each segment from the list
            seg_to_cut = video["t_youtube_mute"].split(",")
            seg_mute_start = []
            seg_mute_end = []

            # all the youtube times are relative to the start time of the video
            for idx1 in range(0, len(seg_to_cut)):
                segment = seg_to_cut[idx1].split(" - ")
                assert(len(segment) % 2 == 0)
                assert(len(segment[0].split(':')) == 3)
                assert(len(segment[1].split(':')) == 3)
                h2, m2, s2 = segment[0].split(':')
                time2_s = 3600 * int(h2) + 60 * int(m2) + int(s2)
                seg_mute_start.append(time2_s)
                h2, m2, s2 = segment[1].split(':')
                time2_e = 3600 * int(h2) + 60 * int(m2) + int(s2)
                seg_mute_end.append(time2_e)

            # audio output
            file_path_audio = path_temp + clean_video_title + "_audio.aac"
            file_path_audio_muted = path_temp + clean_video_title + "_audio_muted.aac"
            if os.path.exists(file_path_audio):
                print("\t- deleting temp file: " + file_path_audio)
                os.remove(file_path_audio)
            if os.path.exists(file_path_audio_muted):
                print("\t- deleting temp file: " + file_path_audio_muted)
                os.remove(file_path_audio_muted)

            # step 1. extract audio
            if not utils.terminated_requested:
                print("\t- extracting: " + file_path_audio)
                cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
                    + ' -i ' + file_path_composite \
                    + ' -vn -acodec copy ' + file_path_audio
                subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()

            # step 2. mute audio
            if not utils.terminated_requested:
                
                print("\t- muting: " + file_path_audio_muted)

                # how long this video is
                # https://superuser.com/a/945604
                cmd = path_twitch_ffprob \
                    + " -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 " \
                    + file_path_composite
                pipe = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
                vid_length = float(pipe.communicate()[0])

                # generate mute command
                # we seem to need to record the non-muted segments
                cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
                    + ' -i ' + file_path_audio \
                    + ' -af "volume=0:enable=\''
                for idx1 in range(0, len(seg_mute_start)):
                    cmd = cmd + 'between(t,'+str(seg_mute_start[idx1])+','+str(seg_mute_end[idx1])+')'
                    if idx1 < len(seg_mute_start) - 1:
                        cmd = cmd + "+"
                cmd = cmd + '\'" ' + file_path_audio_muted
                subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()

            # step 3. re-encode video
            if not utils.terminated_requested:
                print("\t- rendering: " + file_path_composite_muted)
                cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
                    + ' -i ' + file_path_composite \
                    + ' -i ' + file_path_audio_muted \
                    + ' -c:v copy -c:a aac -map 0:v:0 -map 1:a:0 ' + file_path_composite_muted_tmp
                subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()

            # step 4. done, copy it over!
            if not utils.terminated_requested and os.path.exists(file_path_composite_muted_tmp):
                shutil.move(file_path_composite_muted_tmp, file_path_composite_muted)

            # delete old files
            if os.path.exists(file_path_audio):
                os.remove(file_path_audio)
            if os.path.exists(file_path_audio_muted):
                os.remove(file_path_audio_muted)

        # DESC: description file
        file_path_desc = path_render + video["video"] + "_" + clean_video_title + "_muted_desc.txt"
        if not utils.terminated_requested and not os.path.exists(file_path_desc)and "t_youtube_mute" in video:
            print("\t- writting info: " + file_path_desc)
            tmp = str(template)
            tmp = tmp.replace("$id", video_info["id"])
            tmp = tmp.replace("$title", video_info["title"])
            # tmp = tmp.replace("$game", video_info["game"])
            tmp = tmp.replace("$views", str(video_info["views"]))
            tmp = tmp.replace("$t_start", video["t_start"])
            tmp = tmp.replace("$t_end", video["t_end"])
            tmp = tmp.replace("$recorded", video_info["recorded_at"])
            tmp = tmp.replace("$file", video["video"] + ".mp4")
            tmp = tmp.replace("$url", video_info["url"])

            muted_txt = "Sections of this video has been muted:\n"
            seg_to_cut = video["t_youtube_mute"].split(",")
            for idx1 in range(0, len(seg_to_cut)):
                muted_txt = muted_txt + seg_to_cut[idx1] + "\n"
            tmp = muted_txt + "\n\n" + tmp
            if "description" in video:
                tmp = video["description"] + "\n\n" + tmp
            tmp = video["title"] + "\n\n" + tmp
            with open(file_path_desc, "w", encoding="utf-8") as text_file:
                text_file.write(tmp)

    except Exception as e:
        print("\t- ERROR: " + str(e))

    # clean up our temp parts folder
    if os.path.exists(path_temp_parts) and os.path.isdir(path_temp_parts):
       shutil.rmtree(path_temp_parts)

    # nice split between each segment
    print("")

