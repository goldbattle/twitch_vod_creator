# !/usr/bin/env python3
import subprocess
import requests
import datetime
import time
import utils


channel = "sodapoppin"
date_start = "2020-01-01" # 2020-08-22, 2020-01-01
date_end = "2020-12-31" # 2020-08-28, 2021-05-01


# get all the videos for this user
url = "https://api.twitcharchives.com/videos?channel_name="+channel+"&offset=0&limit=99999"
print("trying to pull api info")
print(url)
data_raw = requests.get(url)
videos = data_raw.json()
print("found "+str(len(videos))+" videos")


# list of ids we will download
video_ids = []
datetime_start = datetime.datetime.strptime(date_start, "%Y-%m-%d")
datetime_end = datetime.datetime.strptime(date_end, "%Y-%m-%d")
for video in videos:
  datetime_video = datetime.datetime.fromtimestamp(video['created'])
  date = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.localtime(video['created']))
  # print(str(video['id']) + " has date " + str(date))
  if datetime_video > datetime_start and datetime_video < datetime_end:
    video_ids.append(str(video['id']))
video_ids.reverse()
print("total of "+str(len(video_ids))+" videos in date range")


# loop through each id to try to download it!
utils.setup_signal_handle()
for idtmp in video_ids:
  if not utils.terminated_requested:
    subprocess.call("python3 ../0_single_video_twitcharchives.py "+str(idtmp), shell=True)
    print("====================================================")
    print("====================================================")
    time.sleep(10)




