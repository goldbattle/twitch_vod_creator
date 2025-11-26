# !/usr/bin/env python3

import sys
import os
import argparse
import json
import time
import logging
import coloredlogs

# Add parent directory to path so we can import utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utilities import extra, config, twitch_api, video_download, chat, audio_transcription, file

# ================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Download a single Twitch VOD')
    parser.add_argument('vod_id', type=int, help='VOD ID to download')
    parser.add_argument('--no-chat', action='store_true', help='Skip chat rendering')
    parser.add_argument('--no-transcribe', action='store_true', help='Skip audio transcription')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from download operations')
    parser.add_argument('--temp-dir', default=config.get_temp_path("single_video"), help='Temporary directory for downloads (default: /tmp/tvc_single_video)')
    return parser.parse_args()


def run_task(args: argparse.Namespace) -> None:
    """Download a single Twitch VOD based on provided arguments."""
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=log_level, fmt='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    
    vod_id = args.vod_id
    should_render_chat = not args.no_chat
    should_transcribe = not args.no_transcribe
    
    config_dict = config.load_config()
    config_dict['temp_path'] = args.temp_dir
    auth = config_dict['auth']
    path_root = config_dict['data_root']
    
    extra.setup_signal_handle()
    
    # Get video info
    logger.debug(f"trying to pull api info for vod {vod_id}")
    videos = list(twitch_api.get_videos(auth["client_id"], auth["client_secret"], video_ids=[vod_id]))
    if len(videos) != 1:
        logger.error(f"Found {len(videos)} videos for ID {vod_id}")
        exit(1)
    
    video_helix = videos[0]
    video_data = twitch_api.create_video_data(auth["client_id"], auth["client_secret"], video_helix)
    
    # Setup paths
    path_data = os.path.join(path_root, video_data['user_name'].lower())
    file.ensure_directory(path_data)
    file.ensure_directory(config_dict['temp_path'])
    logger.info(f"saving into {video_data['user_name'].lower()} user folder")
    
    export_folder = file.get_date_folder(video_data['recorded_at'])
    path_data_folder = os.path.join(path_data, export_folder)
    file.ensure_directory(path_data_folder)
    
    file_path_info = os.path.join(path_data_folder, f"{vod_id}_info.json")
    file_path = os.path.join(path_data_folder, f"{vod_id}.mp4")
    file_path_chat = os.path.join(path_data_folder, f"{vod_id}_chat.json")
    file_path_chat_mp4 = os.path.join(path_data_folder, f"{vod_id}_chat.mp4")
    file_path_webvtt = os.path.join(path_data_folder, f"{vod_id}.vtt")
    
    # Save video info
    if not extra.terminated_requested and not os.path.exists(file_path_info):
        with open(file_path_info, 'w', encoding="utf-8") as f:
            json.dump(video_data, f, indent=4)
        logger.info("saved video info")
        logger.debug(f"  - {file_path_info}")
    
    # Download video
    if not extra.terminated_requested:
        logger.info("starting download video...")
        logger.debug(f"  - {file_path}")
        t0 = time.time()
        video_download.download_vod(config_dict, vod_id, file_path, verbose=args.verbose)
        dur_min = (time.time() - t0) / 60.0
        logger.info(f"download video took {dur_min:.2f} min")
    
    # Download chat
    if not extra.terminated_requested:
        logger.info("starting download chat...")
        logger.debug(f"  - {file_path_chat}")
        t0 = time.time()
        chat.download_chat(config_dict, vod_id, file_path_chat, is_clip=False, verbose=args.verbose)
        dur_min = (time.time() - t0) / 60.0
        logger.info(f"download chat took {dur_min:.2f} min")
    
    # Transcribe audio
    if should_transcribe and not extra.terminated_requested:
        if os.path.exists(file_path) and not os.path.exists(file_path_webvtt):
            logger.info("starting transcribing...")
            logger.debug(f"  - {file_path_webvtt}")
            t0 = time.time()
            audio_transcription.transcribe_video(config_dict, file_path, file_path_webvtt, quiet=False)
            dur_min = (time.time() - t0) / 60.0
            logger.info(f"transcribing took {dur_min:.2f} min")
    
    # Render chat
    if should_render_chat and not extra.terminated_requested:
        if os.path.exists(file_path_chat) and not os.path.exists(file_path_chat_mp4):
            logger.info("starting rendering chat...")
            logger.debug(f"  - {file_path_chat_mp4}")
            t0 = time.time()
            chat.render_chat(config_dict, file_path_chat, file_path_chat_mp4, verbose=args.verbose)
            if not os.path.exists(file_path_chat_mp4):
                logger.warning("Warning: Render file was not created, render may have failed")
            else:
                dur_min = (time.time() - t0) / 60.0
                logger.info(f"rendering chat took {dur_min:.2f} min")


def main() -> None:
    """Main entry point."""
    args = parse_args()
    run_task(args)


if __name__ == "__main__":
    main()
