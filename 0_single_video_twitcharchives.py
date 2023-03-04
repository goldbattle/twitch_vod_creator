# !/usr/bin/env python3

import yaml  # pip install PyYAML

# Old non-working version for very large files!
# from youtube_dl import YoutubeDL # pip install youtube_dl
# from ./thirdparty/google_drive_downloader import GoogleDriveDownloader as gdd # (broken?) pip install googledrivedownloader
# import gdown # pip install gdown

# This seems to work for really big files
# Need to install globally on the system to use
# https://github.com/architdate/drivedl
# pip install drivedl

import os
import sys
import json
import time
import requests
import subprocess
import shutil
import progressbar
from datetime import datetime
import urllib.request
import utils


# the vod which we wish to download
if len(sys.argv) != 2:
    print("please pass at least a single vod id (twitch archive) to download...")
    exit(-1)
vod_id_to_download = int(sys.argv[1])

quiet_gdown = False
use_backblaze = False
youtube_for_video = False

# ================================================================
# ================================================================

# paths of the cli and data
path_base = os.path.dirname(os.path.abspath(__file__))
# path_twitch_ffmpeg = path_base + "/thirdparty/Twitch_Downloader_1.40.7/ffmpeg.exe"
path_twitch_ffmpeg = path_base + "/thirdparty/ffmpeg-4.3.1-amd64-static/ffmpeg"
path_root = path_base + "/../data/"
path_temp = "/tmp/tvc_single_video_twitcharchives/"

# ================================================================
# ================================================================

# progress bar helper
# https://stackoverflow.com/a/46825841/7718197
pbar = None
def show_progress(block_num, block_size, total_size):
    global pbar
    if pbar is None:
        pbar = progressbar.ProgressBar(maxval=total_size)
        pbar.start()
    downloaded = block_num * block_size
    if downloaded < total_size:
        pbar.update(downloaded)
    else:
        pbar.finish()
        pbar = None

# set default user agents we will use
opener = urllib.request.build_opener()
opener.addheaders = [('User-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36')]
urllib.request.install_opener(opener)

# setup control+c handler
utils.setup_signal_handle()

# query their api endpoint
print("trying to pull api info for vod " + str(vod_id_to_download))
data_raw = requests.get("https://api.twitcharchives.com/videos?id="+str(vod_id_to_download))
videos = data_raw.json()
assert (len(videos) == 1)
video = videos[0]

# check if the temp directory is created
if os.path.exists(path_temp) and os.path.isdir(path_temp):
    shutil.rmtree(path_temp)
if not os.path.exists(path_temp):
    os.makedirs(path_temp)

# if invalid vod id then replace it with the twitch archive one
if str(video['vodId']) == "0":
    print("invalid video id of " + str(video['vodId']) + " will try to get metadata")
    if video["metadataFile"]:

        # try to download the meta data file that is recorded
        # https://b2.twitcharchives.com/file/twitch-archives/41440005979/final.mp4
        # https://b2.twitcharchives.com/file/twitch-archives/41440005979/metadata.json
        file_path_tmp = path_temp + str(vod_id_to_download) + "_meta.json"
        if use_backblaze:
            url = "https://b2.twitcharchives.com/file/twitch-archives/" + str(vod_id_to_download) + "/metadata.json"
            urllib.request.urlretrieve(url, file_path_tmp, show_progress)
        else:
            print("GDRIVE: downloading metadata " + str(video["metadataFile"]))
            # gdd.download_file_from_google_drive(file_id=video["metadataFile"], dest_path=file_path_tmp)
            # gdown.download(id=str(video["metadataFile"]), output=file_path_tmp, quiet=quiet_gdown, use_cookies=True)
            tmp_path = '/tmp/drivedl_download/'
            cmd = 'rm -rf /tmp/drivedl_download/ && drivedl ' + video["metadataFile"] + ' ' + tmp_path
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL).wait()
            file_download = tmp_path + os.listdir(tmp_path)[0]
            if os.path.exists(file_download):
                shutil.move(file_download, file_path_tmp)


        # check that we have the metadata file downloaded
        if not os.path.exists(file_path_tmp):
            print("unable to download metadata file.... can't do anything!")
            sys.exit()

        # finally open the file and try to parse the data from it
        # seems that the id can have a "v" prefix on it, so we should strip to get raw twitch id
        with open(file_path_tmp) as f:
            video_info = json.load(f)
            if (video_info["_id"][0] == "v"):
                video['vodId'] = video_info["_id"][1:]
            else:
                video['vodId'] = video_info["_id"]
            video['views'] = video_info["views"]
            print("found vod id of "+str(video['vodId']))
        os.remove(file_path_tmp)
    else:
        print("no metadata file id found.... can't do anything!")
        sys.exit()

# create the video object with all our information
# DATA: api data of this vod
m, s = divmod(video['length'], 60)
h, m = divmod(m, 60)
durationstr = format(h, '02') + 'h' + format(m, '02') + 'm' + format(s, '02') + 's'
video_data = {
    'id': str(video['vodId']),
    'user_id': str(video['channelId']),
    'user_name': video['channelName'],
    'title': video['title'],
    'duration': durationstr,
    'url': "https://www.twitch.tv/videos/"+str(video['vodId']),
    'views': (video['views'] if "views" in video else -1),
    'moments': utils.get_vod_moments_from_twitcharchive_string(video['chapters']),
    'muted_segments': [],
    'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.localtime(video['created'])),
    'twitcharchives': {
        "id": video['id'],
        "gdriveVideo": video['videoFile'],
        "gdriveChat": video['chatFile'],
        "gdriveMeta": video["metadataFile"],
        "youtubeVideo": video['videoYoutubeId'],
        "youtubeChat": video['chatYoutubeId'],
    }
}


# create the save directory for this user!
path_data = path_root + "/" + video_data['user_name'].lower() + "/"
if not os.path.exists(path_data):
    os.makedirs(path_data)
print("saving into " + video_data['user_name'].lower() + " user folder")
print("video id of "+str(video_data["id"])+" recorded on "+str(video_data["recorded_at"]))

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
file_path_info = path_data + export_folder + str(video_data['id']) + "_info.json"
print("saving video info: " + file_path_info)
if not utils.terminated_requested and not os.path.exists(file_path_info):
    with open(file_path_info, 'w', encoding="utf-8") as file:
        json.dump(video_data, file, indent=4)

# VIDEO: check if the file exists
file_path = path_data + export_folder + str(video_data['id']) + ".mp4"
file_path_tmp = path_temp + str(video_data['id']) + ".tmp.mp4"
file_path_tmp_ytdl = path_temp + str(video_data['id']) + ".tmp.%(ext)s"


#====================================================================================================
#====================================================================================================
#====================================================================================================

# youtube will be multiple parts, thus we will parse all of them and download each one
# then we will merge them all together into a single video which is the final.mp4 result
if youtube_for_video and not utils.terminated_requested and not os.path.exists(file_path):

    # split video into the parts (if over 10 hours it splits)
    parts = video_data["twitcharchives"]["youtubeVideo"].split(",")

    # first lets see if we need to download multiple parts
    # example: sZ6u0r-SHNs,fTn4eIGpOQE
    for idx, part in enumerate(parts):
        # create filename if needed
        tmp_output_file_ytdl = path_temp + str(video_data['id']) + "_" + str(idx) + ".%(ext)s"
        if len(parts) == 1:
            tmp_output_file_ytdl = file_path_tmp_ytdl
        # download the youtube video
        youtube_url = 'https://youtu.be/'+part
        print("part "+str(idx)+": downloading from youtube: "+youtube_url)
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
            'recodevideo': 'mp4',
            'outtmpl': tmp_output_file_ytdl,
        }
        ydl = YoutubeDL(ydl_opts)
        retcode = ydl.download([youtube_url])
        print("\npart "+str(idx)+": return code: "+str(retcode))


    # if there are multiple parts lets stitch it all together into a single video
    # otherwise we just need to move it to the file location
    # https://stackoverflow.com/a/36045659
    if not utils.terminated_requested and len(parts) != 1:
        # text file will all segments
        text_file_temp_videos = path_temp + "videos.txt"
        with open(text_file_temp_videos, 'w') as the_file:
            for idx, part in enumerate(parts):
                tmp_output_file = path_temp + str(video_data['id']) + "_" + str(idx) + ".mp4"
                the_file.write('file \'' + os.path.abspath(tmp_output_file) + '\'\n')
        # now render
        t0 = time.time()
        print("\t- combining all videos into a single segment!")
        cmd = path_twitch_ffmpeg + ' -hide_banner -loglevel quiet -stats ' \
              + '-f concat -safe 0 ' \
              + ' -i ' + text_file_temp_videos \
              + ' -c copy -avoid_negative_ts make_zero ' \
              + file_path_tmp
        #print(cmd)
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
        #subprocess.Popen(cmd, shell=True).wait()

        # end timing
        print("\t- time to render: " + str(time.time()-t0))

    # finally copy temp file to new location
    if not utils.terminated_requested and os.path.exists(file_path_tmp):
        print("\t- renaming temp export file to final filename")
        shutil.move(file_path_tmp, file_path)

#====================================================================================================
#====================================================================================================
#====================================================================================================


# try to download the video directly if we have it
# https://b2.twitcharchives.com/file/twitch-archives/41440005979/final.mp4
if use_backblaze and not youtube_for_video and not utils.terminated_requested and not os.path.exists(file_path):
    url = "https://b2.twitcharchives.com/file/twitch-archives/" + str(vod_id_to_download) + "/final.mp4"
    print("BACKBLAZE: download video: " + url)
    urllib.request.urlretrieve(url, file_path, show_progress)


# try to download chat if we have it
# https://b2.twitcharchives.com/file/twitch-archives/41440005979/chat.json
file_path_chat = path_data + export_folder + str(video_data['id']) + "_chat.json"
if use_backblaze and not utils.terminated_requested and not os.path.exists(file_path_chat):
    url = "https://b2.twitcharchives.com/file/twitch-archives/" + str(vod_id_to_download) + "/chat.json"
    print("BACKBLAZE: download chat: " + url)
    urllib.request.urlretrieve(url, file_path_chat, show_progress)


#====================================================================================================
#====================================================================================================
#====================================================================================================

# try to download the video directly if we have it
# https://drive.google.com/uc?id=<id here>
# https://drive.google.com/file/d/1_4q-XR_RVMVRnLDE-etZypqTN3n-LbsT/view?usp=sharing
# https://github.com/wkentaro/gdown/blob/main/gdown/download.py#L64-L75
# Large file problem required a different ID to be used: https://stackoverflow.com/a/65347090/7718197
if not use_backblaze and not youtube_for_video and not utils.terminated_requested and not os.path.exists(file_path) and video_data["twitcharchives"]["gdriveVideo"]:
    print("GDRIVE: download video: " + str(video_data["twitcharchives"]["gdriveVideo"]))
    # gdd.download_file_from_google_drive(file_id=video_data["twitcharchives"]["gdriveVideo"], dest_path=file_path, showsize=True)
    # gdown.download(id=str(video_data["twitcharchives"]["gdriveVideo"])+"&confirm=t", output=file_path, quiet=quiet_gdown, use_cookies=True)
    tmp_path = '/tmp/drivedl_download/'
    cmd = 'rm -rf /tmp/drivedl_download/ && drivedl ' + video_data["twitcharchives"]["gdriveVideo"] + ' ' + tmp_path
    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL).wait()
    file_download = tmp_path + os.listdir(tmp_path)[0]
    if os.path.exists(file_download):
        shutil.move(file_download, file_path)
    if os.path.exists(file_path) and os.path.getsize(file_path) < 1:
        print("GDRIVE: warning downloaded video is invalid size...")
        os.remove(file_path)

# try to download chat if we have it
# https://drive.google.com/uc?id=<id here>
file_path_chat = path_data + export_folder + str(video_data['id']) + "_chat.json"
if not use_backblaze and not utils.terminated_requested and not os.path.exists(file_path_chat) and video_data["twitcharchives"]["gdriveChat"]:
    print("GDRIVE: download chat: " + str(video_data["twitcharchives"]["gdriveChat"]))
    # gdd.download_file_from_google_drive(file_id=video_data["twitcharchives"]["gdriveChat"], dest_path=file_path_chat, showsize=True)
    # gdown.download(id=str(video_data["twitcharchives"]["gdriveChat"]), output=file_path_chat, quiet=quiet_gdown, use_cookies=True)
    tmp_path = '/tmp/drivedl_download/'
    cmd = 'rm -rf /tmp/drivedl_download/ && drivedl ' + video_data["twitcharchives"]["gdriveChat"] + ' ' + tmp_path
    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL).wait()
    file_download = tmp_path + os.listdir(tmp_path)[0]
    if os.path.exists(file_download):
        shutil.move(file_download, file_path_chat)
    if os.path.exists(file_path_chat) and os.path.getsize(file_path_chat) < 1:
        print("GDRIVE: warning downloaded chat is invalid size...")
        os.remove(file_path_chat)


#====================================================================================================
#====================================================================================================
#====================================================================================================


# CHAT VIDEO: check if the file exists
# file_path_render = path_data + export_folder + str(video_data['id']) + "_chat.mp4"
# if os.path.exists(file_path_chat) and not os.path.exists(file_path_render):
#     print("rendering chat: " + file_path_render)
#     cmd = path_twitch_cli + ' -m ChatRender' \
#           + ' -i ' + file_path_chat + ' --ffmpeg-path "' + path_twitch_ffmpeg + '"' \
#           + ' -h 1080 -w 320 --framerate 60 --font-size 13' \
#           + ' -o ' + file_path_render
#     # subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL).wait()
#     subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()


# cleanup temp folder
if os.path.exists(path_temp) and os.path.isdir(path_temp):
    shutil.rmtree(path_temp)

