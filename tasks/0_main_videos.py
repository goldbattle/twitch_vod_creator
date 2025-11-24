# !/usr/bin/env python3

import sys
import os
import argparse
import json
import time
import logging
import coloredlogs
from typing import Dict, List, Any

# Add parent directory to path so we can import utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utilities import extra, config, twitch_api, video_download, chat, audio_transcription, file

# ================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Download and process Twitch VODs')
    parser.add_argument('--channels', required=True, nargs='+', help='List of channel names to download videos from')
    parser.add_argument('--max-videos', required=True, type=int, help='Maximum number of videos to download per type (archive/highlight/upload)')
    parser.add_argument('--render-chat', required=True, nargs='+', help='Whether to render chat for each channel (true/false, must match number of channels)')
    parser.add_argument('--render-webvtt', required=True, nargs='+', help='Whether to generate WebVTT transcriptions for each channel (true/false, must match number of channels)')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from download operations')
    parser.add_argument('--temp-dir', default=config.get_temp_path("main_videos"), help='Temporary directory for downloads (default: /tmp/tvc_main_videos)')
    return parser.parse_args()


def run_task(args: argparse.Namespace) -> None:
    """Download and process Twitch VODs based on provided arguments."""
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=log_level, fmt='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    
    channels = args.channels
    max_videos = args.max_videos
    render_chat_flags = [x.lower() in ('true', '1', 'yes') for x in args.render_chat]
    render_webvtt = [x.lower() in ('true', '1', 'yes') for x in args.render_webvtt]
    
    config_dict = config.load_config()
    config_dict['temp_path'] = args.temp_dir
    auth = config_dict['auth']
    path_root = config_dict['data_root']
    
    extra.setup_signal_handle()
    
    if len(channels) != len(render_chat_flags) or len(channels) != len(render_webvtt):
        logger.error(f'Number of channels ({len(channels)}) must match number of render-chat ({len(render_chat_flags)}) and render-webvtt ({len(render_webvtt)}) flags')
        exit(-1)
    
    # Get users
    logger.debug(f"Fetching user info for channels: {channels}")
    users_tmp = twitch_api.get_users_by_login(auth["client_id"], auth["client_secret"], channels)
    users: List[Dict[str, Any]] = []
    render_chat_flags_filtered: List[bool] = []
    render_webvtt_filtered: List[bool] = []
    for idx, channel in enumerate(channels):
        found = False
        for user in users_tmp:
            if user["login"].lower() == channel.lower():
                users.append(user)
                render_chat_flags_filtered.append(render_chat_flags[idx])
                render_webvtt_filtered.append(render_webvtt[idx])
                found = True
                break
        if not found:
            logger.warning(f"streamer {channel} wasn't found, are they banned???")
    
    # Process each user
    for idx, user in enumerate(users):
        if extra.terminated_requested:
            logger.info('terminate requested, not looking at any more users...')
            break
        
        path_data = os.path.join(path_root, user["login"].lower())
        file.ensure_directory(path_data)
        file.ensure_directory(config_dict['temp_path'])
        
        # Check if live
        stream_is_live = twitch_api.is_user_live(auth["client_id"], auth["client_secret"], user["id"])
        
        # Get videos
        logger.info(f"getting videos for -> {user['login'].lower()}")
        logger.info(f"  - Id {user['id']}")
        vid_iter = twitch_api.get_videos(auth["client_id"], auth["client_secret"], user_id=user["id"], page_size=100)
        arr_archive: List[Dict[str, Any]] = []
        arr_highlight: List[Dict[str, Any]] = []
        arr_upload: List[Dict[str, Any]] = []
        ct_added = [0, 0, 0]
        seen_first_video = False
        
        for video in vid_iter:
            if not seen_first_video and stream_is_live:
                logger.debug(f"skipping video {video['id']} since stream is live...")
                seen_first_video = True
                continue
            seen_first_video = True
            
            if video['type'] == 'archive' and ct_added[0] < max_videos:
                arr_archive.append({'helix': video})
                ct_added[0] += 1
            elif video['type'] == 'highlight' and ct_added[1] < max_videos:
                arr_highlight.append({'helix': video})
                ct_added[1] += 1
            elif video['type'] == 'upload' and ct_added[2] < max_videos:
                arr_upload.append({'helix': video})
                ct_added[2] += 1
        
        logger.info(f"  - found {len(arr_archive)} archives, {len(arr_highlight)} highlights, {len(arr_upload)} uploads")
        
        # Process each archive video
        for video in arr_archive:
            if extra.terminated_requested:
                logger.info('terminate requested, not downloading any more..')
                break
            
            logger.info(f"processing video {video['helix']['id']}")
            t0_start = time.time()
            video_data = twitch_api.create_video_data(auth["client_id"], auth["client_secret"], video['helix'])
            
            # Get file paths
            export_folder = file.get_date_folder(video_data['recorded_at'])
            path_data_folder = os.path.join(path_data, export_folder)
            file.ensure_directory(path_data_folder)
            
            file_path_info = os.path.join(path_data_folder, f"{video['helix']['id']}_info.json")
            file_path = os.path.join(path_data_folder, f"{video['helix']['id']}.mp4")
            file_path_chat = os.path.join(path_data_folder, f"{video['helix']['id']}_chat.json")
            file_path_chat_mp4 = os.path.join(path_data_folder, f"{video['helix']['id']}_chat.mp4")
            file_path_webvtt = os.path.join(path_data_folder, f"{video['helix']['id']}.vtt")
            
            # Save/update video info
            if not extra.terminated_requested:
                if not os.path.exists(file_path_info):
                    with open(file_path_info, 'w', encoding="utf-8") as f:
                        json.dump(video_data, f, indent=4)
                    logger.info("  - saved video info")
                    logger.debug(f"  - {file_path_info}")
                else:
                    logger.info("  - updated video info")
                    logger.debug(f"  - {file_path_info}")
                    with open(file_path_info) as f:
                        video_info = json.load(f)
                    if len(video_info.get("moments", [])) == 0:
                        moments = twitch_api.get_vod_moments(video['helix']['id'])
                        if len(moments) != 0:
                            video_info["moments"] = moments
                    with open(file_path_info, 'w', encoding="utf-8") as f:
                        json.dump(video_info, f, indent=4)
            
            # Download video
            if not extra.terminated_requested and not os.path.exists(file_path):
                logger.info("  - starting download video...")
                logger.debug(f"  - {file_path}")
                t0 = time.time()
                success = video_download.download_vod(config_dict, video['helix']['id'], file_path, verbose=args.verbose)
                if success:
                    dur_min = (time.time() - t0) / 60.0
                    logger.info(f"  - download video took {dur_min:.2f} min")
                else:
                    logger.error("  - ERROR: Video download failed!")
            
            # Download chat
            if not extra.terminated_requested and not os.path.exists(file_path_chat):
                logger.info("  - starting download chat...")
                logger.debug(f"  - {file_path_chat}")
                t0 = time.time()
                chat.download_chat(config_dict, video['helix']['id'], file_path_chat, is_clip=False, verbose=args.verbose)
                dur_min = (time.time() - t0) / 60.0
                logger.info(f"  - download chat took {dur_min:.2f} min")
            
            # Transcribe audio
            if render_webvtt_filtered[idx] and not extra.terminated_requested:
                if os.path.exists(file_path) and not os.path.exists(file_path_webvtt):
                    logger.info("  - starting transcribing...")
                    logger.debug(f"  - {file_path_webvtt}")
                    t0 = time.time()
                    audio_transcription.transcribe_video(config_dict, file_path, file_path_webvtt)
                    dur_min = (time.time() - t0) / 60.0
                    logger.info(f"  - transcribing took {dur_min:.2f} min")
            
            # Render chat
            if render_chat_flags_filtered[idx] and not extra.terminated_requested:
                if os.path.exists(file_path_chat) and not os.path.exists(file_path_chat_mp4):
                    logger.info("  - starting rendering chat...")
                    logger.debug(f"  - {file_path_chat_mp4}")
                    t0 = time.time()
                    chat.render_chat(config_dict, file_path_chat, file_path_chat_mp4, verbose=args.verbose)
                    dur_min = (time.time() - t0) / 60.0
                    logger.info(f"  - rendering chat took {dur_min:.2f} min")
                    
                    # Send pushover notification
                    text = (f"{video['helix']['user_name']} vod {video['helix']['id']} "
                           f"ready to edit ({int((time.time() - t0_start)/60.0)} min to prepare)")
                    extra.send_pushover_message(auth, text)


def main() -> None:
    """Main entry point."""
    args = parse_args()
    run_task(args)


if __name__ == "__main__":
    main()
