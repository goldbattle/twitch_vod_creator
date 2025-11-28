# !/usr/bin/env python3

import sys
import os
import argparse
import time
import logging
import coloredlogs
from typing import List, Tuple, Optional

# Add parent directory to path so we can import utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utilities import extra, config, audio_transcription, chat, video_editing

# ================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Post-process videos: generate WebVTT transcriptions, render chat, and/or upscale to 4K')
    parser.add_argument('--channel', required=True, help='Channel name to process')
    parser.add_argument('--min-age', type=int, default=60, help='Minimum file age in seconds')
    parser.add_argument('--do-vtt', action='store_true', help='Generate WebVTT transcriptions for videos')
    parser.add_argument('--do-chat-render', action='store_true', help='Render chat JSON files to video')
    parser.add_argument('--do-4k', action='store_true', help='Upscale videos to 4K')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from operations')
    parser.add_argument('--temp-dir', default=config.get_temp_path("videos_post"), help='Temporary directory for operations (default: /tmp/tvc_videos_post)')
    return parser.parse_args()


def run_task(args: argparse.Namespace) -> None:
    """Post-process videos: generate WebVTT transcriptions, render chat, and/or upscale to 4K."""
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=log_level, fmt='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    
    config_dict = config.load_config()
    config_dict['temp_path'] = args.temp_dir
    path_root = config_dict['data_root']
    
    extra.setup_signal_handle()
    
    channel_path = os.path.join(path_root, args.channel)
    
    if not os.path.exists(channel_path):
        logger.error(f"Channel directory not found: {channel_path}")
        return
    
    # Find video files for VTT and 4K processing
    videos_to_process: List[Tuple[str, str, Optional[str]]] = []  # (video_path, vtt_path, 4k_path)
    # Find chat JSON files for chat rendering
    chats_to_process: List[Tuple[str, str]] = []  # (chat_json_path, chat_mp4_path)
    
    logger.debug(f"Scanning channel directory: {channel_path}")
    for subdir, dirs, files in os.walk(channel_path):
        if extra.terminated_requested:
            break
        for filename in files:
            if extra.terminated_requested:
                break
            
            # Find video files (mp4 without underscore) for VTT and 4K
            if args.do_vtt or args.do_4k:
                ext = filename.split(os.extsep)
                if len(ext) == 2 and ext[1] == "mp4" and "_" not in filename:
                    video_path = os.path.join(subdir, filename)
                    vtt_path = os.path.join(subdir, ext[0] + ".vtt") if args.do_vtt else None
                    video_4k_path = os.path.join(subdir, ext[0] + "_4k.mp4") if args.do_4k else None
                    videos_to_process.append((video_path, vtt_path, video_4k_path))
            
            # Find chat JSON files for chat rendering
            if args.do_chat_render:
                if filename.endswith("_chat.json"):
                    chat_json_path = os.path.join(subdir, filename)
                    # Use _chat_4k.mp4 if --do-4k is specified, otherwise _chat.mp4
                    if args.do_4k:
                        chat_mp4_path = chat_json_path.replace("_chat.json", "_chat_4k.mp4")
                    else:
                        chat_mp4_path = chat_json_path.replace("_chat.json", "_chat.mp4")
                    chats_to_process.append((chat_json_path, chat_mp4_path))
    
    logger.info(f"found {len(videos_to_process)} videos to process")
    if args.do_chat_render:
        logger.info(f"found {len(chats_to_process)} chat files to process")
    
    # Process VTT generation
    if args.do_vtt and not extra.terminated_requested:
        logger.info("Processing WebVTT transcriptions...")
        for video_path, vtt_path, _ in videos_to_process:
            if vtt_path is None:
                continue
            if extra.terminated_requested:
                logger.warning('terminate requested, not processing any more..')
                break
            
            # Check if old enough to process
            oldness = time.time() - os.path.getmtime(video_path)
            if oldness < args.min_age:
                logger.debug(f"skipping {video_path} since it is only {oldness:.1f} sec old")
                continue
            
            # Transcribe if not exists
            if os.path.exists(video_path) and not os.path.exists(vtt_path):
                logger.info(f"starting transcribing {os.path.basename(video_path)}...")
                logger.debug(f"  - {vtt_path}")
                t0 = time.time()
                audio_transcription.transcribe_video(config_dict, video_path, vtt_path, quiet=not args.verbose)
                dur_min = (time.time() - t0) / 60.0
                logger.info(f"transcribing took {dur_min:.2f} min")
    
    # Process chat rendering
    if args.do_chat_render and not extra.terminated_requested:
        logger.info("Processing chat rendering...")
        for chat_json_path, chat_mp4_path in chats_to_process:
            if extra.terminated_requested:
                logger.warning('terminate requested, not processing any more..')
                break
            
            # Check if old enough to process
            oldness = time.time() - os.path.getmtime(chat_json_path)
            if oldness < args.min_age:
                logger.debug(f"skipping {chat_json_path} since it is only {oldness:.1f} sec old")
                continue
            
            # Render chat if not exists
            if os.path.exists(chat_json_path) and not os.path.exists(chat_mp4_path):
                logger.info(f"starting rendering chat {os.path.basename(chat_json_path)}...")
                logger.debug(f"  - {chat_mp4_path}")
                t0 = time.time()
                chat.render_chat(config_dict, chat_json_path, chat_mp4_path, verbose=args.verbose, is_4k=args.do_4k)
                dur_min = (time.time() - t0) / 60.0
                logger.info(f"rendering chat took {dur_min:.2f} min")
    
    # Process 4K upscaling
    if args.do_4k and not extra.terminated_requested:
        logger.info("Processing 4K upscaling...")
        for video_path, _, video_4k_path in videos_to_process:
            if video_4k_path is None:
                continue
            if extra.terminated_requested:
                logger.warning('terminate requested, not processing any more..')
                break
            
            # Check if old enough to process
            oldness = time.time() - os.path.getmtime(video_path)
            if oldness < args.min_age:
                logger.debug(f"skipping {video_path} since it is only {oldness:.1f} sec old")
                continue
            
            # Upscale if not exists
            if os.path.exists(video_path) and not os.path.exists(video_4k_path):
                logger.info(f"starting upscaling to 4K {os.path.basename(video_path)}...")
                logger.debug(f"  - {video_4k_path}")
                t0 = time.time()
                success = video_editing.upscale_video_to_4k(config_dict, video_path, video_4k_path, verbose=args.verbose)
                dur_min = (time.time() - t0) / 60.0
                if success:
                    logger.info(f"upscaling to 4K took {dur_min:.2f} min")
                else:
                    logger.error(f"ERROR: Failed to upscale {video_path} to 4K!")


def main() -> None:
    """Main entry point."""
    args = parse_args()
    run_task(args)


if __name__ == "__main__":
    main()

