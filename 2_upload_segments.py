# !/usr/bin/env python3

import yaml  # pip install PyYAML
# sudo pip install --upgrade google-api-python-client oauth2client progressbar2
# pip install youtube-video-upload
from youtube_video_upload import upload_from_options, upload_video

import os
import time
import utils

# video file we wish to render
path_base = os.path.dirname(os.path.abspath(__file__))
video_file = path_base + "/config/soda_2024_videos.yaml"
history_file = path_base + "/config/soda_2024_uploads.yaml"
config_file = path_base + "/config/soda_config_youtube.yaml"

display_missing = False

# load the yaml from file
with open(config_file) as f:
    config = yaml.load(f, Loader=yaml.FullLoader)
print("loaded config file: " + config_file)

# paths of the cli and data
path_root = path_base + "/../data/"
path_render = path_base + "/../data_rendered/"

# youtube credential location
path_yt_creds = path_base + "/../profiles/" + config["yt_creds"]
path_yt_secrets = path_base + "/../profiles/" + config["yt_secrets"]

# ================================================================
# ================================================================

# setup control+c handler
utils.setup_signal_handle()

# load the yaml from file
with open(video_file) as f:
    data = yaml.load(f, Loader=yaml.FullLoader)
print("loaded " + str(len(data)) + " videos to upload")

# load our historical uploads file
hist_uploads = {}
if os.path.exists(history_file):
    with open(history_file) as f:
        hist_uploads = yaml.load(f, Loader=yaml.FullLoader)

# loop through each video and render each segment
# we will want to first ensure chat is rendered
# from there we will render the full segmented video
for suffix in ["", "_muted"]:
    for video in data:

        # check if we should download any more
        if utils.terminated_requested:
            print('terminate requested, not downloading any more..')
            break

        # nice debug print
        print("processing " + video["video"] + ", suffix = \"" + suffix + "\"")

        # check if the files are there
        clean_video_title = utils.get_valid_filename(video["title"])
        file_path_composite = path_render + video["video"] + "_" + clean_video_title + suffix + ".mp4"
        file_path_desc = path_render + video["video"] + "_" + clean_video_title + suffix + "_desc.txt"
        if not os.path.exists(file_path_composite) or not os.path.exists(file_path_desc):
            if display_missing:
                print("\t- ERROR video has not been rendered yet...")
                print("\t- " + video["video"] + "_" + clean_video_title + ".mp4")
                print("\t- " + video["video"] + "_" + clean_video_title + "_desc.txt")
            continue

        # unique video id
        video_id = video["video"].replace(' ', '_') + "_" + video["title"].lower().replace(' ', '_') + suffix
        if video_id in hist_uploads:
            print("\t- skipping video, has already been uploaded")
            print("\t- link: " + hist_uploads[video_id]['link'])
            continue

        # load the description file
        with open(file_path_desc, "r") as myfile:
            video_description = ''.join(myfile.readlines()[2:])

        # combine our tags
        tags = config["tags"]
        if "tags" in video:
            tags.append(video["tags"])

        # upload options
        options = {
            'local_server': True,
            'videos': [
                {
                    'title': video['title'],
                    'file': file_path_composite,
                    'description': video_description,
                    'category': 'Entertainment',
                    'privacy': 'private',
                    'tags': tags
                }
            ],
            'secrets_path': path_yt_secrets,
            'credentials_path': path_yt_creds
        }

        # now upload the video!
        print("\t- starting video upload...")
        try:
            t0 = time.time()
            upload_video.MAX_RETRIES = 2
            new_options = upload_from_options(options)
            t1 = time.time()
            print("\t- done performing video upload!")
            print("\t- link: " + new_options)
            print("\t- upload time: " + str(t1 - t0 + 1e-6))
            hist_uploads[video_id] = {
                'title': video["title"],
                'file': file_path_composite,
                'link': new_options
            }

            # finally write the updated history file
            if not os.path.exists(os.path.dirname(history_file)):
                os.makedirs(os.path.dirname(history_file))
            with open(history_file, 'w') as yaml_file:
                yaml.dump(hist_uploads, yaml_file)

        except Exception as e:
            print("\t- ERROR unable to complete the upload!")
            print(e)
            break
