# !/usr/bin/env python3

import sys
import os
import argparse
import json
import time
import datetime
import logging
import coloredlogs
from typing import Dict, List, Any

# Add parent directory to path so we can import utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utilities import extra, config, twitch_api, video_download, chat, file

# ================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Download Twitch clips')
    parser.add_argument('--channels', required=True, nargs='+', help='List of channel names to download clips from')
    parser.add_argument('--min-view-counts', required=True, type=int, nargs='+', help='Minimum view counts for each channel (must match number of channels)')
    parser.add_argument('--num-days', required=True, type=int, help='Number of days to query back from today')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from download operations')
    
    # Get base_path for default values
    config_dict = config.load_config()
    default_clips_dir = os.path.join(os.path.dirname(config_dict['base_path']), "data_clips_new")
    
    # Directory arguments
    parser.add_argument('--dir-temp', default=config.get_temp_path("main_clips"), help='Temporary directory for downloads (default: /tmp/tvc_main_clips)')
    parser.add_argument('--dir-clips', default=default_clips_dir, help=f'Clips directory (default: {default_clips_dir})')
    return parser.parse_args()


def run_task(args: argparse.Namespace) -> None:
    """Download Twitch clips based on provided arguments."""
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=log_level, fmt='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    
    channels = args.channels
    min_view_counts = args.min_view_counts
    num_days_to_query = args.num_days
    
    if len(channels) != len(min_view_counts):
        logger.error(f"Number of channels ({len(channels)}) must match number of min-view-counts ({len(min_view_counts)})")
        exit(1)
    
    config_dict = config.load_config()
    config_dict['temp_path'] = args.dir_temp
    auth = config_dict['auth']
    path_root = args.dir_clips
    
    date_start = (datetime.datetime.now() - datetime.timedelta(days=num_days_to_query)).strftime('%Y-%m-%dT%H:%M:%SZ')
    date_end = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
    logger.info(f"Start Day: {date_start}")
    logger.info(f"End Day: {date_end}")
    
    extra.setup_signal_handle()
    
    # Get users
    logger.debug(f"Fetching user info for channels: {channels}")
    users_tmp = twitch_api.get_users_by_login(auth["client_id"], auth["client_secret"], channels)
    users: List[Dict[str, Any]] = []
    min_view_counts_tmp: List[int] = []
    for idx, channel in enumerate(channels):
        found = False
        for user in users_tmp:
            if user["login"].lower() == channel.lower():
                users.append(user)
                min_view_counts_tmp.append(min_view_counts[idx])
                found = True
                break
        if not found:
            logger.warning(f"streamer {channel} wasn't found, are they banned???")
    min_view_counts = min_view_counts_tmp
    
    t0 = time.time()
    game_cache: Dict[str, Any] = {}
    count_total_clips_checked = 0
    count_total_clips_downloaded = 0
    
    # Process each user
    for idx, user in enumerate(users):
        if extra.terminated_requested:
            logger.info('terminate requested, not looking at any more users...')
            break
        
        path_data = os.path.join(path_root, user["login"])
        file.ensure_directory(path_data)
        file.ensure_directory(config_dict['temp_path'])
        
        try:
            logger.info(f"getting clips for -> {user['login']}")
            logger.info(f"  - Id {user['id']}")
            vid_iter = twitch_api.get_clips(auth["client_id"], auth["client_secret"], user["id"], 
                                 started_at=date_start, ended_at=date_end, page_size=100)
            
            # Collect all clips first (iterator will fetch all pages automatically)
            all_clips = []
            for video in vid_iter:
                count_total_clips_checked += 1
                # Stop if below view count threshold (clips are sorted by view count)
                if video['view_count'] < min_view_counts[idx]:
                    logger.debug(f"Stopping at clip with {video['view_count']} views (threshold: {min_view_counts[idx]})")
                    break
                all_clips.append(video)
            
            # Sort by created_at to process older clips first (oldest to newest)
            all_clips.sort(key=lambda x: x['created_at'])
            for video in all_clips:
                if extra.terminated_requested:
                    logger.info('terminate requested, not downloading any more..')
                    break
                
                clip_date = video['created_at'].strftime('%Y-%m-%d')
                logger.info(f"processing {video['url']}")
                logger.info(f"  - {clip_date} - {video['view_count']} views")
                
                # Setup paths
                export_folder = file.get_date_folder(video['created_at'].strftime('%Y-%m-%dT%H:%M:%SZ'))
                path_data_folder = os.path.join(path_data, export_folder)
                
                # Download complete clip (info, video, chat)
                result = video_download.download_complete_clip(
                    config_dict, video, path_data_folder, game_cache, logger, verbose=args.verbose
                )
                
                if result['video_downloaded']:
                    count_total_clips_downloaded += 1
        
        except Exception as e:
            logger.error(f"Error processing user {user['login']}: {e}")
    
    t1 = time.time()
    logger.info(f"number of checked clips: {count_total_clips_checked}")
    logger.info(f"number of downloaded clips: {count_total_clips_downloaded}")
    logger.info(f"total execution time: {t1 - t0:.1f}")


def main() -> None:
    """Main entry point."""
    args = parse_args()
    run_task(args)


if __name__ == "__main__":
    main()
