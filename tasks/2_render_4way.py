# !/usr/bin/env python3

import sys
import os
import argparse
import subprocess
import shutil
import time
import logging
import coloredlogs
from typing import List

# Add parent directory to path so we can import utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utilities import extra, config, file

# ================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Render 4-way video composite')
    parser.add_argument('--title', required=True, help='Video title')
    parser.add_argument('--sync-offset', required=True, help='Sync offset time (HH:MM:SS)')
    parser.add_argument('--duration', required=True, help='Video duration (HH:MM:SS)')
    parser.add_argument('--video0', required=True, help='Path to first video (relative to data root, without .mp4)')
    parser.add_argument('--starttime0', required=True, help='Start time for video0 (HH:MM:SS)')
    parser.add_argument('--video1', required=True, help='Path to second video (relative to data root, without .mp4)')
    parser.add_argument('--starttime1', required=True, help='Start time for video1 (HH:MM:SS)')
    parser.add_argument('--video2', required=True, help='Path to third video (relative to data root, without .mp4)')
    parser.add_argument('--starttime2', required=True, help='Start time for video2 (HH:MM:SS)')
    parser.add_argument('--video3', required=True, help='Path to fourth video (relative to data root, without .mp4)')
    parser.add_argument('--starttime3', required=True, help='Start time for video3 (HH:MM:SS)')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from operations')
    parser.add_argument('--temp-dir', default=config.get_temp_path("render_4way"), help='Temporary directory for downloads (default: /tmp/tvc_render_4way)')
    return parser.parse_args()


def run_task(args: argparse.Namespace) -> None:
    """Render 4-way video composite based on provided arguments."""
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=log_level, fmt='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    
    config_dict = config.load_config()
    config_dict['temp_path'] = args.temp_dir
    path_root = config_dict['data_root']
    path_render = config_dict['render_root']
    path_temp = config_dict['temp_path']
    
    title = args.title
    syncoffset = args.sync_offset
    duration = args.duration
    video0 = args.video0
    starttime0 = args.starttime0
    video1 = args.video1
    starttime1 = args.starttime1
    video2 = args.video2
    starttime2 = args.starttime2
    video3 = args.video3
    starttime3 = args.starttime3
    
    # setup control+c handler
    extra.setup_signal_handle()
    
    if not os.path.exists(path_temp):
        os.makedirs(path_temp)

    # VIDEO: check that we have the video
    videos = [video0, video1, video2, video3]
    videopaths: List[str] = []
    for video in videos:
        file_path_video = os.path.join(path_root, video + ".mp4")
        videopaths.append(file_path_video)
        if not os.path.exists(file_path_video):
            logger.error(f"could not find the video file: {file_path_video}")
            exit(1)

    # CHAT: check that we have video0 chat
    file_path_chat = os.path.join(path_root, video0 + "_chat.json")
    file_path_render = os.path.join(path_root, video0 + "_chat.mp4")
    if not os.path.exists(file_path_chat):
        logger.error(f"could not find the chat file: {file_path_chat}")
        exit(1)

    # CHAT: actually make sure we render it
    file_path_render_tmp = os.path.join(path_temp, os.path.basename(video0) + "_chat.mp4")
    if not os.path.exists(file_path_render):
        logger.info("starting rendering chat...")
        logger.debug(f"  - {file_path_chat}")
        t0 = time.time()
        cmd = config_dict['twitch_cli'] + ' chatrender' \
            + ' -i ' + file_path_chat + ' -o ' + file_path_render_tmp \
            + ' --ffmpeg-path "' + config_dict['ffmpeg'] + '"' \
            + ' -h 926 -w 274 --update-rate 0.1 --framerate 60 --font-size 15' \
            + ' --bttv true --ffz true --stv true --sub-messages true --badges true' \
            + ' --temp-path "' + path_temp + '" '
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL if not args.verbose else None, 
                         stderr=subprocess.DEVNULL if not args.verbose else None).wait()
        shutil.move(file_path_render_tmp, file_path_render)
        dur_min = (time.time() - t0) / 60.0
        logger.info(f"rendering chat took {dur_min:.2f} min")

    # COMPOSITE: render the composite image
    clean_video_title = file.get_valid_filename(title)
    file_path_composite = os.path.join(path_render, "4WAY", clean_video_title + ".mp4")
    file_path_composite_tmp = os.path.join(path_render, "4WAY", clean_video_title + ".tmp.mp4")

    # Create our export folder if needed
    dir_path_composite = os.path.dirname(os.path.abspath(file_path_composite))
    if not os.path.exists(dir_path_composite):
        os.makedirs(dir_path_composite)
    if os.path.exists(file_path_composite):
        logger.error(f"rendered video file already exists: {file_path_composite}")
        exit(1)

    # for each video construct the start / end times
    synctimes = [starttime0, starttime1, starttime2, starttime3]
    starttimes: List[str] = []
    endtimes: List[str] = []
    for synctime in synctimes:
        h0, m0, s0 = syncoffset.split(':')
        h1, m1, s1 = synctime.split(':')
        h2, m2, s2 = duration.split(':')
        time0_s = 3600 * int(h0) + 60 * int(m0) + int(s0)
        time1_s = 3600 * int(h1) + 60 * int(m1) + int(s1)
        time2_s = 3600 * int(h2) + 60 * int(m2) + int(s2)
        m, s = divmod(time1_s - time0_s, 60)
        h, m = divmod(m, 60)
        starttime = format(h, '02') + ':' + format(m, '02') + ':' + format(s, '02')
        m, s = divmod(time1_s + time2_s, 60)
        h, m = divmod(m, 60)
        endtime = format(h, '02') + ':' + format(m, '02') + ':' + format(s, '02')
        logger.debug(f"segment video{len(endtimes)}: {starttime} -> {endtime}")
        starttimes.append(starttime)
        endtimes.append(endtime)

    # RENDER: actually render the video
    #   - main video is 1646x926
    #   - small videos are 823x463
    #   - chat render is 274x926
    logger.info("starting rendering composite...")
    logger.debug(f"  - {file_path_composite}")
    cmd = config_dict['ffmpeg'] + ' -hide_banner -loglevel quiet -stats ' \
          + ' -ss ' + starttimes[0] + ' -to ' + endtimes[0] + ' -i ' + videopaths[0] \
          + ' -ss ' + starttimes[1] + ' -to ' + endtimes[1] + ' -i ' + videopaths[1] \
          + ' -ss ' + starttimes[2] + ' -to ' + endtimes[2] + ' -i ' + videopaths[2] \
          + ' -ss ' + starttimes[3] + ' -to ' + endtimes[3] + ' -i ' + videopaths[3] \
          + ' -ss ' + starttimes[0] + ' -i ' + file_path_render \
          + ' -filter_complex "' \
          + ' [0:v] scale=823x463 [tmp0];[1:v] scale=823x463 [tmp1];' \
          + ' [2:v] scale=823x463 [tmp2];[3:v] scale=823x463 [tmp3];' \
          + ' [tmp0][tmp1]hstack=inputs=2:shortest=1[top]; ' \
          + ' [tmp2][tmp3]hstack=inputs=2:shortest=1[bottom]; ' \
          + ' [top][bottom]vstack=inputs=2:shortest=1[main]; ' \
          + ' [main][4:v]hstack=inputs=2:shortest=1[stack]" -shortest -map "[stack]" -map 0:a ' \
          + ' -vcodec libx264 -crf 18 -preset veryfast -avoid_negative_ts make_zero -map_chapters -1 -framerate 60 ' \
          + ' -c:a aac ' \
          + file_path_composite_tmp
    logger.debug(f"  - ffmpeg command: {cmd}")
    t0 = time.time()
    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL if not args.verbose else None, 
                     stderr=subprocess.DEVNULL if not args.verbose else None).wait()
    dur_min = (time.time() - t0) / 60.0
    logger.info(f"rendering composite took {dur_min:.2f} min")

    # finally copy temp file to new location
    logger.debug("renaming temp export file to final filename")
    if not extra.terminated_requested and os.path.exists(file_path_composite_tmp):
        os.rename(file_path_composite_tmp, file_path_composite)


def main() -> None:
    """Main entry point."""
    args = parse_args()
    run_task(args)


if __name__ == "__main__":
    main()
