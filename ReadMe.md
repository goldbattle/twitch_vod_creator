# twitch vod creator

The goal of these scripts is to enable both the automatic downloading and fast quick rough editing of twitch vods for archival on youtube.
At the core we leverage lay295's [TwitchDownload](https://github.com/lay295/TwitchDownloader) utility to download both complete vods, clips, and chats.
For all of these we can render the chat such that the twitch experience is preserved along with the original stream on the video-only youtube platform.
Then we can perform specific "cutting" of downloaded videos to select game playthroughs or segments which others might want to watch.
Both the original vod and chat are then render into the same video which can be uploaded to youtube.

Example channels with these video renders:
* Sodapoppin Clips - https://www.youtube.com/channel/UCreuVIdBwFEhf1qFhzyJVKw
* Sevadus Clips - https://www.youtube.com/channel/UCkWuSV5FukUzVLvFnhvPvKQ


### Dependencies & Config

We leverage [python-twitch-client](https://github.com/tsifrer/python-twitch-client) library which recently added oauth support.
You will need at least version 0.7.1 installed to have the correct api support functions.

```
pip install python-twitch-client
pip install PyYAML
pip install youtube-video-upload
```

You will need to make a copy of *[config/auth_example.yaml](config/auth_example.yaml)* and rename it to `config/auth.yaml`.
This should be fill out with a twitch app client information which can be generated from the twitch [developer center](https://dev.twitch.tv/console/apps).
For youtube uploads you will need to generate a oauth json file after you enable Youtube API V3 access in the Google developer console.
Please take a look at the original [youtube-video-upload](https://github.com/remorses/youtube-video-upload) repository for those details if you want to try this.


### Segment Config File Format

The config file format is a yaml file which specifies unique videos which we wish to render of larger vod segments.
A video is defined by the vod which it is cut from and the unique youtube video title which should remain unchanged.
A user can cut multiple segments from a single vod into a video render, but cannot combine multi-vod segments into a single video currently.
The timestamps are specified using `HH:MM:SS` (see ffmpeg docs [here](https://ffmpeg.org/ffmpeg-utils.html#time-duration-syntax)), and are comma seperated.

```
- video: sodapoppin/2020-11/804430123
  title:  "Example Video"
  t_start: "00:00:00,01:00:00"
  t_end: "00:10:00,02:00:00"
```

In this example a video of the 804430123 vod will be rendered with the title "Example Video".
The first 10 minutes will be rendered, afterwhich the video will cut to the 1 hour mark, and render the next hour.
Note that while here we can have as long as possible video, youtube has a max upload length of 12 hours.


### Known Issues

* The youtube uploader does not seem to work for me.
After uploading to youtube successfully, after trying to make the video public the video will be blocked due to "terms and conditions violations".
The script has been left here as a reference for others, but it seems manual upload is still required.

* Ffmpeg rendering still seems to be a bit slow (1.9-2.1x speedup) which I have been unable to increase.
This might be due to the limit of the read speed of my harddrive or tuning of the ffmpeg parameters (which for me do not max out my gpu and cpu).

* Right now this has only been tested with Python 3.7 and on a Windows 10 machine using PyCharm.
Probably all the path handling should be re-done to be more proper to allow for running on different OS platforms.

* There is no detection of two clips being of the same segment of a VOD. This can cause a compilation to have multiple of the same clips in it.
This can be addressed by checking the VOD time offset and seeing if any of the clips have overlapping time segments.
  
