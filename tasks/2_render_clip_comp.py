# !/usr/bin/env python3

import sys
import os
import argparse
import re
import json
import time
import datetime
import subprocess
import shutil
import logging
import coloredlogs
from typing import Dict, List, Any

# Add parent directory to path so we can import utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utilities import extra, config, twitch_api, video_download, chat, video_editing, file

# ================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Download and render clip compilation')
    parser.add_argument('--channel', required=True, help='Channel name')
    parser.add_argument('--max-clips', required=True, type=int, help='Maximum number of clips')
    parser.add_argument('--date-start', required=True, help='Start date (ISO format: YYYY-MM-DDTHH:MM:SSZ)')
    parser.add_argument('--date-end', required=True, help='End date (ISO format: YYYY-MM-DDTHH:MM:SSZ)')
    parser.add_argument('--min-view-counts', type=int, default=500, help='Minimum view count (default: 500)')
    parser.add_argument('--clips-to-ignore', nargs='*', default=[], help='List of clip IDs to ignore, or a path to a text file with one ID per line')
    parser.add_argument('--no-download', action='store_true', help='Skip downloading from Twitch')
    parser.add_argument('--no-remove', action='store_true', help='Keep rendered files')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from download operations')
    parser.add_argument('--do-4k', action='store_true', help='Enable upscaling videos to 4K (3840x2160) with 25Mbps bitrate and re-render chat at 4K')
    
    # Get base_path for default values
    config_dict = config.load_config()
    default_data_root = os.path.dirname(config_dict['base_path'])
    
    # Directory arguments
    parser.add_argument('--dir-temp', default=config.get_temp_path("render_clip_comp"), help='Temporary directory for downloads (default: /tmp/tvc_render_clip_comp)')
    parser.add_argument('--dir-data-root', default=default_data_root, help=f'Root directory containing data_clips_new and data_rendered folders (should contain folders like "data_clips_new" and "data_rendered") (default: {default_data_root})')
    return parser.parse_args()


def run_task(args: argparse.Namespace) -> None:
    """Download and render clip compilation based on provided arguments."""
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=log_level, fmt='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    
    get_latest_from_twitch = not args.no_download
    remove_rendered = not args.no_remove
    
    # Handle clips-to-ignore: if single argument and it's a file, read from file; otherwise use as list
    clips_to_ignore = []
    if args.clips_to_ignore:
        if len(args.clips_to_ignore) == 1 and os.path.isfile(args.clips_to_ignore[0]):
            # Single argument is a file path - read IDs from file
            try:
                with open(args.clips_to_ignore[0], 'r') as f:
                    clips_to_ignore = [line.strip() for line in f if line.strip()]
                logger.debug(f"Loaded {len(clips_to_ignore)} clip IDs to ignore from {args.clips_to_ignore[0]}")
            except Exception as e:
                logger.error(f"Could not read clips-to-ignore file {args.clips_to_ignore[0]}: {e}")
                exit(1)
        else:
            # Multiple arguments or single non-file argument - treat as list of IDs
            clips_to_ignore = args.clips_to_ignore
    
    # Validate date formats before proceeding
    try:
        datetime_start = datetime.datetime.strptime(args.date_start, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        logger.error(f"Invalid date format for --date-start: {args.date_start}")
        logger.error(f"Expected format: YYYY-MM-DDTHH:MM:SSZ (e.g., 2024-01-01T00:00:00Z)")
        exit(1)
    try:
        datetime_end = datetime.datetime.strptime(args.date_end, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        logger.error(f"Invalid date format for --date-end: {args.date_end}")
        logger.error(f"Expected format: YYYY-MM-DDTHH:MM:SSZ (e.g., 2024-12-31T00:00:00Z)")
        exit(1)
    
    if datetime_start >= datetime_end:
        logger.error(f"--date-start ({args.date_start}) must be before --date-end ({args.date_end})")
        exit(1)
    
    config_dict = config.load_config()
    config_dict['temp_path'] = args.dir_temp
    auth = config_dict['auth']
    
    # Setup paths - dir_data_root is the parent directory
    path_root = os.path.join(args.dir_data_root, "data_clips_new")
    path_render = os.path.join(args.dir_data_root, "data_rendered")
    
    extra.setup_signal_handle()
    
    # Check if final composite already exists (either MP4 or description file)
    file_path_composite = os.path.join(path_render, "CLIPS", f"{args.channel}_{args.date_start[:10]}_{args.date_end[:10]}.mp4")
    file_path_desc = os.path.join(path_render, "CLIPS", f"{args.channel}_{args.date_start[:10]}_{args.date_end[:10]}_desc.txt")
    if os.path.exists(file_path_composite) or os.path.exists(file_path_desc):
        logger.error("Final composite video or description file already exists. Skipping individual clip rendering. Delete the existing files to re-render.")
        exit(-1)
    
    path_data = os.path.join(path_root, args.channel)
    os.makedirs(path_data, exist_ok=True)
    os.makedirs(config_dict['temp_path'], exist_ok=True)
    
    # Download new clips if enabled
    if not args.no_download and get_latest_from_twitch:
        user = twitch_api.get_user_by_login(auth["client_id"], auth["client_secret"], args.channel)
        if not user:
            logger.error(f"User {args.channel} not found")
            exit(1)
        
        game_cache = {}
        logger.info(f"getting clips for -> {user['login']}")
        logger.info(f"  - Id {user['id']}")
        vid_iter = twitch_api.get_clips(auth["client_id"], auth["client_secret"], user["id"],
                            started_at=args.date_start, ended_at=args.date_end, page_size=100)
        try:
            for video in vid_iter:
                if extra.terminated_requested:
                    logger.info('terminate requested, not looking at any more clips...')
                    exit(-1)
                
                if video['view_count'] < args.min_view_counts:
                    logger.debug(f"skipping {video['url']} (only {video['view_count']} views)")
                    break
                
                created_date = video['created_at'].strftime('%Y-%m-%d')
                logger.info(f"clip {video['url']}")
                logger.info(f"  - {video['view_count']} views, created: {created_date}")
                
                # Setup paths
                export_folder = file.get_date_folder(video['created_at'].strftime('%Y-%m-%dT%H:%M:%SZ'))
                path_data_folder = os.path.join(path_data, export_folder)
                
                # Download complete clip (info, video, chat)
                video_download.download_complete_clip(
                    config_dict, video, path_data_folder, game_cache, logger, verbose=args.verbose
                )
        
        except Exception as e:
            logger.error("twitch api failure.... stopping querying....")
            logger.error(f"{e}")
            exit(-1)
    
    # Load clips from disk
    arr_clips = []
    # Dates already validated at the top
    for root, dirs, files in os.walk(path_data):
        for filename in files:
            if not filename.endswith('_info.json'):
                continue
            with open(os.path.join(root, filename)) as f:
                video_info = json.load(f)
            
            datetime_created = datetime.datetime.strptime(video_info['created_at'], "%Y-%m-%d %H:%M:%SZ")
            export_folder = f"{datetime_created.year:02d}-{datetime_created.month:02d}/"
            file_path = os.path.join(path_data, export_folder, f"{video_info['id']}.mp4")
            
            if not os.path.exists(file_path):
                logger.warning(f"{video_info['id']} is missing its main video file!!!!")
                continue
            
            filesize = os.path.getsize(file_path)
            if filesize < 1:
                logger.warning(f"{video_info['id']} clip is invalid!!!!")
                continue
            
            if datetime_created < datetime_start or datetime_created > datetime_end:
                continue
            
            if video_info["id"] in clips_to_ignore:
                logger.debug(f"{video_info['id']} clip has been IGNORED!!!!")
                continue
            
            arr_clips.append(video_info)
    
    # Remove overlapping clips
    arr_clips_no_common = []
    arr_clips.sort(key=lambda x: x.get('duration', -1), reverse=True)
    for id1, video1 in enumerate(arr_clips):
        if "video_id" not in video1 or video1['video_id'] == "":
            arr_clips_no_common.append(id1)
            continue
        if "video_offset" not in video1 or video1['video_offset'] == -1:
            arr_clips_no_common.append(id1)
            continue
        if "duration" not in video1 or video1['duration'] == -1:
            arr_clips_no_common.append(id1)
            continue
        
        id_common = []
        for id2, video2 in enumerate(arr_clips):
            if id1 == id2:
                continue
            if "video_id" not in video2 or video2['video_id'] == "":
                continue
            if "video_offset" not in video2 or video2['video_offset'] == -1:
                continue
            if "duration" not in video2 or video2['duration'] == -1:
                continue
            if video1['video_id'] != video2['video_id']:
                continue
            
            start1 = video1['video_offset']
            end1 = video1['video_offset'] + video1['duration']
            start2 = video2['video_offset']
            end2 = video2['video_offset'] + video2['duration']
            if start1 < end2 and start2 < end1:
                id_common.append(id2)
        
        if len(id_common) == 0:
            arr_clips_no_common.append(id1)
            continue
        
        num_added = sum(1 for id3 in id_common if id3 in arr_clips_no_common)
        if num_added == 0:
            arr_clips_no_common.append(id1)
    
    arr_clips = [arr_clips[id1] for id1 in arr_clips_no_common]
    
    # Sort by view count, then by date
    logger.debug(f"sorting {len(arr_clips)} clips by viewcount")
    arr_clips.sort(key=lambda x: x['view_count'])
    start_id = max(0, len(arr_clips) - args.max_clips)
    arr_clips = arr_clips[start_id:]
    logger.debug(f"sorting {len(arr_clips)} clips by date")
    arr_clips.sort(key=lambda x: x['created_at'])
    
    if len(arr_clips) < args.max_clips:
        logger.error("unable to find enough requested clips....")
        logger.error("either decrease the min view count or number of requested clips..")
        exit(-1)
    
    # Render individual clips
    for video in arr_clips:
        logger.info(f"clip {video['url']}")
        logger.info(f"  - {video['view_count']} views, clipped at {video['created_at']}")
        
        datetime_created = datetime.datetime.strptime(video['created_at'], "%Y-%m-%d %H:%M:%SZ")
        export_folder = f"{datetime_created.year:02d}-{datetime_created.month:02d}/"
        
        file_path_chat = os.path.join(path_data, export_folder, f"{video['id']}_chat.json")
        file_path_chat_mp4 = os.path.join(path_data, export_folder, f"{video['id']}_chat.mp4")
        
        # For 4K mode, we need to re-render chat at 4K resolution
        if args.do_4k and os.path.exists(file_path_chat):
            file_path_chat_mp4_4k = os.path.join(path_data, export_folder, f"{video['id']}_chat_4k.mp4")
            if not os.path.exists(file_path_chat_mp4_4k):
                logger.info("  - starting rendering chat at 4K...")
                logger.debug(f"  - {file_path_chat_mp4_4k}")
                t0 = time.time()
                success = chat.render_chat(config_dict, file_path_chat, file_path_chat_mp4_4k, verbose=args.verbose, is_4k=True)
                dur_min = (time.time() - t0) / 60.0
                if success:
                    logger.info(f"  - rendering chat at 4K took {dur_min:.2f} min")
                else:
                    logger.error("  - ERROR: Failed to render chat at 4K!")
            file_path_chat_mp4 = file_path_chat_mp4_4k
        elif os.path.exists(file_path_chat) and not os.path.exists(file_path_chat_mp4):
            logger.info("  - starting rendering chat...")
            logger.debug(f"  - {file_path_chat_mp4}")
            t0 = time.time()
            chat.render_chat(config_dict, file_path_chat, file_path_chat_mp4, verbose=args.verbose)
            dur_min = (time.time() - t0) / 60.0
            logger.info(f"  - rendering chat took {dur_min:.2f} min")
        
        file_path = os.path.join(path_data, export_folder, f"{video['id']}.mp4")
        
        file_path_composite = os.path.join(path_data, export_folder, f"{video['id']}_rendered.mp4")
        
        if not extra.terminated_requested and not os.path.exists(file_path_composite):
            os.makedirs(os.path.dirname(file_path_composite), exist_ok=True)
            
            logger.info("  - starting rendering composite...")
            logger.debug(f"  - {file_path_composite}")
            t0 = time.time()
            video_editing.render_clip_with_title(config_dict, file_path, file_path_chat_mp4 if os.path.exists(file_path_chat_mp4) else None,
                                  file_path_composite, video["title"], is_4k=args.do_4k)
            
            dur_min = (time.time() - t0) / 60.0
            logger.info(f"  - rendering composite took {dur_min:.2f} min")
    
    # Combine all clips
    text_file_temp_videos = os.path.join(path_render, "CLIPS", f"{args.channel}_{args.date_start[:10]}_{args.date_end[:10]}.txt")
    file_path_composite = os.path.join(path_render, "CLIPS", f"{args.channel}_{args.date_start[:10]}_{args.date_end[:10]}.mp4")

    logger.info("starting to render the composite video (will take a while)...")
    if not extra.terminated_requested and not os.path.exists(file_path_composite):
        os.makedirs(os.path.dirname(file_path_composite), exist_ok=True)
        
        # Create concat file
        with open(text_file_temp_videos, 'w') as f:
            for video in arr_clips:
                datetime_created = datetime.datetime.strptime(video['created_at'], "%Y-%m-%d %H:%M:%SZ")
                export_folder = f"{datetime_created.year:02d}-{datetime_created.month:02d}/"
                tmp_output_file = os.path.join(path_data, export_folder, f"{video['id']}_rendered.mp4")
                if os.path.exists(tmp_output_file):
                    f.write(f"file '{os.path.abspath(tmp_output_file)}'\n")
                else:
                    logger.warning(f"  - WARNING: skipping {os.path.abspath(tmp_output_file)}")
        
        # Combine videos
        logger.info("  - starting merging videos...")
        logger.debug(f"  - {file_path_composite}")
        t0_big = time.time()
        video_paths = []
        with open(text_file_temp_videos) as f:
            for line in f:
                if line.startswith("file "):
                    video_paths.append(line.split("'")[1])
        
        if not video_paths:
            logger.error("  - ERROR: No video files found to combine!")
            os.remove(text_file_temp_videos)
        else:
            logger.debug(f"  - combining {len(video_paths)} video files")
            success = video_editing.combine_videos(config_dict, video_paths, file_path_composite, quiet=not args.verbose)
            os.remove(text_file_temp_videos)
            
            dur_min = (time.time() - t0_big) / 60.0
            if success and os.path.exists(file_path_composite):
                logger.info(f"  - merging videos took {dur_min:.2f} min")
            else:
                logger.error(f"  - ERROR: Failed to create composite video after {dur_min:.2f} min")
                logger.error(f"  - Output file does not exist: {file_path_composite}")
    
    # Create description file (only if composite video was successfully created)
    file_path_desc = os.path.join(path_render, "CLIPS", f"{args.channel}_{args.date_start[:10]}_{args.date_end[:10]}_desc.txt")
    if not extra.terminated_requested and not os.path.exists(file_path_desc) and os.path.exists(file_path_composite):
        tmp = f"Top {args.max_clips} Between {args.date_start[:10]} to {args.date_end[:10]}\n\n"
        
        num_second_into_video = 0
        for video in arr_clips:
            datetime_created = datetime.datetime.strptime(video['created_at'], "%Y-%m-%d %H:%M:%SZ")
            export_folder = f"{datetime_created.year:02d}-{datetime_created.month:02d}/"
            
            file_path_info = os.path.join(path_data, export_folder, f"{video['id']}_info.json")
            tmp_output_file = os.path.join(path_data, export_folder, f"{video['id']}_rendered.mp4")
            if not os.path.exists(tmp_output_file):
                logger.warning(f"skipping {tmp_output_file}")
                continue
            
            with open(file_path_info) as f:
                video_info = json.load(f)
            
            m, s = divmod(int(num_second_into_video), 60)
            h, m = divmod(m, 60)
            timestamp = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
            
            title_clean = re.sub(r"[^a-zA-Z0-9'.?: ]", '', video_info["title"])
            title_clean = title_clean.replace("\\\\", "\\\\\\\\").replace("'", "\u2019")
            tmp += f"{timestamp} \"{title_clean}\" clipped by {video_info['creator_name']}\n"
            
            logger.debug("=============================")
            logger.debug(f"  {timestamp} - {video_info['id']}")
            logger.debug(f"  {title_clean}")
            
            vid_length = video_editing.get_video_duration(config_dict, tmp_output_file)
            if vid_length:
                num_second_into_video += vid_length
        
        with open(file_path_desc, "w", encoding="utf-8") as f:
            f.write(tmp)
        logger.info("  - created description file")
        logger.debug(f"  - {file_path_desc}")
    
    # Remove rendered files if requested
    if not extra.terminated_requested and not args.no_remove and remove_rendered:
        for video in arr_clips:
            logger.debug(f"{video['id']}")
            datetime_created = datetime.datetime.strptime(video['created_at'], "%Y-%m-%d %H:%M:%SZ")
            export_folder = f"{datetime_created.year:02d}-{datetime_created.month:02d}/"
            tmp_output_file = os.path.join(path_data, export_folder, f"{video['id']}_rendered.mp4")
            if os.path.exists(tmp_output_file):
                os.remove(tmp_output_file)
                logger.debug(f"  - removed composite: {tmp_output_file}")
            if args.do_4k:
                file_path_chat_4k = os.path.join(path_data, export_folder, f"{video['id']}_chat_4k.mp4")
                if os.path.exists(file_path_chat_4k):
                    os.remove(file_path_chat_4k)
                    logger.debug(f"  - removed 4K chat render: {file_path_chat_4k}")


def main() -> None:
    """Main entry point."""
    args = parse_args()
    run_task(args)


if __name__ == "__main__":
    main()
