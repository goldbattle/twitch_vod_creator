# !/usr/bin/env python3

import argparse
import json
import os
import time
import datetime
import logging
import coloredlogs
import utilities_extra
from utilities_config import load_config, get_temp_path
from utilities_twitch_api import get_users_by_login, get_clips, create_clip_data, get_clip_data
from utilities_video_download import download_clip
from utilities_chat import download_chat
from utilities_file import get_date_folder, ensure_directory

# ================================================================

def main():
    parser = argparse.ArgumentParser(description='Download Twitch clips')
    parser.add_argument('--channels', required=True, nargs='+', help='List of channel names to download clips from')
    parser.add_argument('--min-view-counts', required=True, type=int, nargs='+', help='Minimum view counts for each channel (must match number of channels)')
    parser.add_argument('--num-days', required=True, type=int, help='Number of days to query back from today')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from download operations')
    parser.add_argument('--temp-dir', default=get_temp_path("main_clips"), help='Temporary directory for downloads (default: /tmp/tvc_main_clips)')
    args = parser.parse_args()
    
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
    
    config = load_config()
    config['temp_path'] = args.temp_dir
    auth = config['auth']
    path_root = config['clips_root']
    
    date_start = (datetime.datetime.now() - datetime.timedelta(days=num_days_to_query)).strftime('%Y-%m-%dT%H:%M:%SZ')
    date_end = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
    logger.info(f"Start Day: {date_start}")
    logger.info(f"End Day: {date_end}")
    
    utilities_extra.setup_signal_handle()
    
    # Get users
    logger.debug(f"Fetching user info for channels: {channels}")
    users_tmp = get_users_by_login(auth["client_id"], auth["client_secret"], channels)
    users = []
    min_view_counts_tmp = []
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
    game_cache = {}
    count_total_clips_checked = 0
    count_total_clips_downloaded = 0
    
    # Process each user
    for idx, user in enumerate(users):
        if utilities_extra.terminated_requested:
            logger.info('terminate requested, not looking at any more users...')
            break
        
        path_data = os.path.join(path_root, user["login"])
        ensure_directory(path_data)
        ensure_directory(config['temp_path'])
        
        try:
            logger.info(f"getting clips for -> {user['login']}")
            logger.info(f"  - Id {user['id']}")
            vid_iter = get_clips(auth["client_id"], auth["client_secret"], user["id"], 
                                 started_at=date_start, ended_at=date_end, page_size=100)
            
            for video in vid_iter:
                if utilities_extra.terminated_requested:
                    logger.info('terminate requested, not downloading any more..')
                    break
                
                count_total_clips_checked += 1
                
                # Stop if below view count threshold (clips are sorted by view count)
                if video['view_count'] < min_view_counts[idx]:
                    logger.debug(f"Stopping at clip with {video['view_count']} views (threshold: {min_view_counts[idx]})")
                    break
                
                logger.info(f"processing {video['url']}")
                logger.info(f"  - {video['view_count']} views")
                
                # Setup paths
                export_folder = get_date_folder(video['created_at'].strftime('%Y-%m-%dT%H:%M:%SZ'))
                path_data_folder = os.path.join(path_data, export_folder)
                ensure_directory(path_data_folder)
                
                file_path_info = os.path.join(path_data_folder, f"{video['id']}_info.json")
                file_path = os.path.join(path_data_folder, f"{video['id']}.mp4")
                file_path_chat = os.path.join(path_data_folder, f"{video['id']}_chat.json")
                
                # Save/update clip info
                if not utilities_extra.terminated_requested:
                    if not os.path.exists(file_path_info):
                        clip_data = create_clip_data(auth["client_id"], auth["client_secret"], video, game_cache)
                        with open(file_path_info, 'w', encoding="utf-8") as f:
                            json.dump(clip_data, f, indent=4)
                        logger.info(f"  - saved clip info: {video['id']}")
                        logger.debug(f"  - {file_path_info}")
                    else:
                        with open(file_path_info) as f:
                            video_info = json.load(f)
                        video_info["view_count"] = video['view_count']
                        if video_info.get("video_offset") == -1:
                            clip_data = get_clip_data(video['id'])
                            if clip_data['offset'] != -1:
                                video_info["video_offset"] = clip_data['offset']
                                video_info["duration"] = clip_data['duration']
                        with open(file_path_info, 'w', encoding="utf-8") as f:
                            json.dump(video_info, f, indent=4)
                        logger.info(f"  - updated clip info: {video['view_count']} views")
                        logger.debug(f"  - {file_path_info}")
                
                # Download clip
                if not utilities_extra.terminated_requested and not os.path.exists(file_path):
                    logger.info("  - starting download clip...")
                    logger.debug(f"  - {file_path}")
                    t0 = time.time()
                    if download_clip(config, video['id'], file_path, verbose=args.verbose):
                        count_total_clips_downloaded += 1
                        dur_min = (time.time() - t0) / 60.0
                        logger.info(f"  - download clip took {dur_min:.2f} min")
                    else:
                        logger.error("  - VIDEO DOWNLOAD FAILED!!!!")
                
                # Download chat
                try:
                    if not utilities_extra.terminated_requested and not os.path.exists(file_path_chat):
                        logger.info("  - starting download chat...")
                        logger.debug(f"  - {file_path_chat}")
                        t0 = time.time()
                        download_chat(config, video['id'], file_path_chat, is_clip=True, verbose=args.verbose)
                        dur_min = (time.time() - t0) / 60.0
                        logger.info(f"  - download chat took {dur_min:.2f} min")
                except Exception as e:
                    logger.warning(f"  - not able to download any chat... {e}")
        
        except Exception as e:
            logger.error(f"Error processing user {user['login']}: {e}")
    
    t1 = time.time()
    logger.info(f"number of checked clips: {count_total_clips_checked}")
    logger.info(f"number of downloaded clips: {count_total_clips_downloaded}")
    logger.info(f"total execution time: {t1 - t0:.1f}")


if __name__ == "__main__":
    main()
