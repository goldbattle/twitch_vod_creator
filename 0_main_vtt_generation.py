# !/usr/bin/env python3

import argparse
import os
import time
import logging
import coloredlogs
import utilities_extra
from utilities_config import load_config, get_temp_path
from utilities_audio_transcription import transcribe_video

# parameters
channel = "sodapoppin"
min_age_seconds = 60

# ================================================================

def main():
    parser = argparse.ArgumentParser(description='Generate WebVTT transcriptions for videos')
    parser.add_argument('--channel', default=channel, help='Channel name to process')
    parser.add_argument('--min-age', type=int, default=min_age_seconds, help='Minimum file age in seconds')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from operations')
    parser.add_argument('--temp-dir', default=get_temp_path("vtt_generation"), help='Temporary directory for downloads (default: /tmp/tvc_vtt_generation)')
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=log_level, fmt='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    
    config = load_config()
    config['temp_path'] = args.temp_dir
    path_root = config['data_root']
    
    utilities_extra.setup_signal_handle()
    
    # Find video files
    files_to_process = []
    channel_path = os.path.join(path_root, args.channel)
    
    if not os.path.exists(channel_path):
        logger.error(f"Channel directory not found: {channel_path}")
        return
    
    logger.debug(f"Scanning channel directory: {channel_path}")
    for subdir, dirs, files in os.walk(channel_path):
        if utilities_extra.terminated_requested:
            break
        for file in files:
            if utilities_extra.terminated_requested:
                break
            ext = file.split(os.extsep)
            if len(ext) != 2:
                continue
            if ext[1] == "mp4" and "_" not in file:
                video_path = os.path.join(subdir, file)
                vtt_path = os.path.join(subdir, ext[0] + ".vtt")
                files_to_process.append((video_path, vtt_path))
    
    logger.info(f"found {len(files_to_process)} videos to process")
    
    # Process each video
    for video_path, vtt_path in files_to_process:
        if utilities_extra.terminated_requested:
            logger.info('terminate requested, not processing any more..')
            break
        
        # Check if old enough to process
        oldness = time.time() - os.path.getmtime(video_path)
        if oldness < args.min_age:
            logger.debug(f"skipping {video_path} since it is only {oldness:.1f} sec old")
            continue
        
        # Transcribe if not exists
        if os.path.exists(video_path) and not os.path.exists(vtt_path):
            logger.info("starting transcribing...")
            logger.debug(f"  - {vtt_path}")
            t0 = time.time()
            transcribe_video(config, video_path, vtt_path)
            dur_min = (time.time() - t0) / 60.0
            logger.info(f"transcribing took {dur_min:.2f} min")


if __name__ == "__main__":
    main()
