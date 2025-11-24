# !/usr/bin/env python3

import argparse
import json
import os
import logging
import coloredlogs
import utilities_extra
from utilities_config import load_config, get_temp_path
from utilities_twitch_api import get_videos, create_video_data
from utilities_video_download import download_vod
from utilities_chat import download_chat, render_chat
from utilities_audio_transcription import transcribe_video
from utilities_file import get_date_folder, ensure_directory

# ================================================================

def main():
    parser = argparse.ArgumentParser(description='Download a single Twitch VOD')
    parser.add_argument('vod_id', type=int, help='VOD ID to download')
    parser.add_argument('--no-chat', action='store_true', help='Skip chat rendering')
    parser.add_argument('--no-transcribe', action='store_true', help='Skip audio transcription')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from download operations')
    parser.add_argument('--temp-dir', default=get_temp_path("single_video"), help='Temporary directory for downloads (default: /tmp/tvc_single_video)')
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=log_level, fmt='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    
    vod_id = args.vod_id
    should_render_chat = not args.no_chat
    should_transcribe = not args.no_transcribe
    
    config = load_config()
    config['temp_path'] = args.temp_dir
    auth = config['auth']
    path_root = config['data_root']
    
    utilities_extra.setup_signal_handle()
    
    # Get video info
    logger.debug(f"trying to pull api info for vod {vod_id}")
    videos = list(get_videos(auth["client_id"], auth["client_secret"], video_ids=[vod_id]))
    if len(videos) != 1:
        logger.error(f"Found {len(videos)} videos for ID {vod_id}")
        exit(1)
    
    video_helix = videos[0]
    video_data = create_video_data(auth["client_id"], auth["client_secret"], video_helix)
    
    # Setup paths
    path_data = os.path.join(path_root, video_data['user_name'].lower())
    ensure_directory(path_data)
    ensure_directory(config['temp_path'])
    logger.info(f"saving into {video_data['user_name'].lower()} user folder")
    
    export_folder = get_date_folder(video_data['recorded_at'])
    path_data_folder = os.path.join(path_data, export_folder)
    ensure_directory(path_data_folder)
    
    file_path_info = os.path.join(path_data_folder, f"{vod_id}_info.json")
    file_path = os.path.join(path_data_folder, f"{vod_id}.mp4")
    file_path_chat = os.path.join(path_data_folder, f"{vod_id}_chat.json")
    file_path_chat_mp4 = os.path.join(path_data_folder, f"{vod_id}_chat.mp4")
    file_path_webvtt = os.path.join(path_data_folder, f"{vod_id}.vtt")
    
    # Save video info
    if not utilities_extra.terminated_requested and not os.path.exists(file_path_info):
        with open(file_path_info, 'w', encoding="utf-8") as f:
            json.dump(video_data, f, indent=4)
        logger.info("saved video info")
        logger.debug(f"  - {file_path_info}")
    
    # Download video
    if not utilities_extra.terminated_requested:
        logger.info("starting download video...")
        logger.debug(f"  - {file_path}")
        t0 = time.time()
        download_vod(config, vod_id, file_path, verbose=args.verbose)
        dur_min = (time.time() - t0) / 60.0
        logger.info(f"download video took {dur_min:.2f} min")
    
    # Download chat
    if not utilities_extra.terminated_requested:
        logger.info("starting download chat...")
        logger.debug(f"  - {file_path_chat}")
        t0 = time.time()
        download_chat(config, vod_id, file_path_chat, is_clip=False, verbose=args.verbose)
        dur_min = (time.time() - t0) / 60.0
        logger.info(f"download chat took {dur_min:.2f} min")
    
    # Transcribe audio
    if should_transcribe and not utilities_extra.terminated_requested:
        if os.path.exists(file_path) and not os.path.exists(file_path_webvtt):
            logger.info("starting transcribing...")
            logger.debug(f"  - {file_path_webvtt}")
            t0 = time.time()
            transcribe_video(config, file_path, file_path_webvtt, quiet=False)
            dur_min = (time.time() - t0) / 60.0
            logger.info(f"transcribing took {dur_min:.2f} min")
    
    # Render chat
    if should_render_chat and not utilities_extra.terminated_requested:
        if os.path.exists(file_path_chat) and not os.path.exists(file_path_chat_mp4):
            logger.info("starting rendering chat...")
            logger.debug(f"  - {file_path_chat_mp4}")
            t0 = time.time()
            render_chat(config, file_path_chat, file_path_chat_mp4, verbose=args.verbose)
            if not os.path.exists(file_path_chat_mp4):
                logger.warning("Warning: Render file was not created, render may have failed")
            else:
                dur_min = (time.time() - t0) / 60.0
                logger.info(f"rendering chat took {dur_min:.2f} min")


if __name__ == "__main__":
    main()
