# !/usr/bin/env python3

import sys
import os
import argparse
import time
import logging
import coloredlogs
import threading
from typing import List, Tuple, Optional, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to path so we can import utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utilities import extra, config, audio_transcription, chat, video_editing

# ================================================================
# Worker Functions
# ================================================================

def process_vtt(video_path: str, vtt_path: str, config_dict: Dict[str, Any], args: argparse.Namespace, logger: logging.Logger) -> Tuple[bool, float]:
    """Process a single VTT transcription."""
    worker_id = threading.current_thread().name
    if extra.terminated_requested:
        return (False, 0.0)
    
    # Check if old enough to process
    oldness = time.time() - os.path.getmtime(video_path)
    if oldness < args.min_age:
        return (False, 0.0)
    
    # Transcribe if not exists
    if os.path.exists(video_path) and not os.path.exists(vtt_path):
        logger.info(f"[{worker_id}] starting transcribing {os.path.basename(video_path)}...")
        logger.debug(f"[{worker_id}]   - {vtt_path}")
        t0 = time.time()
        success = audio_transcription.transcribe_video(config_dict, video_path, vtt_path, quiet=not args.verbose)
        dur_min = (time.time() - t0) / 60.0
        if success:
            logger.info(f"[{worker_id}] transcribing {os.path.basename(video_path)} took {dur_min:.2f} min")
            return (True, dur_min)
        else:
            logger.error(f"[{worker_id}] ERROR: Failed to transcribe {video_path}")
            return (False, dur_min)
    return (False, 0.0)


def process_chat(chat_json_path: str, chat_mp4_path: str, config_dict: Dict[str, Any], args: argparse.Namespace, logger: logging.Logger) -> Tuple[bool, float]:
    """Process a single chat render."""
    worker_id = threading.current_thread().name
    if extra.terminated_requested:
        return (False, 0.0)
    
    # Check if old enough to process
    oldness = time.time() - os.path.getmtime(chat_json_path)
    if oldness < args.min_age:
        return (False, 0.0)
    
    # Render chat if not exists
    if os.path.exists(chat_json_path) and not os.path.exists(chat_mp4_path):
        logger.info(f"[{worker_id}] starting rendering chat {os.path.basename(chat_json_path)}...")
        logger.debug(f"[{worker_id}]   - {chat_mp4_path}")
        t0 = time.time()
        success = chat.render_chat(config_dict, chat_json_path, chat_mp4_path, verbose=args.verbose, is_4k=args.do_4k)
        dur_min = (time.time() - t0) / 60.0
        if success:
            logger.info(f"[{worker_id}] rendering chat {os.path.basename(chat_json_path)} took {dur_min:.2f} min")
            return (True, dur_min)
        else:
            logger.error(f"[{worker_id}] ERROR: Failed to render chat {chat_json_path}")
            return (False, dur_min)
    return (False, 0.0)


def process_4k(video_path: str, video_4k_path: str, config_dict: Dict[str, Any], args: argparse.Namespace, logger: logging.Logger) -> Tuple[bool, float]:
    """Process a single 4K upscale."""
    worker_id = threading.current_thread().name
    if extra.terminated_requested:
        return (False, 0.0)
    
    # Check if old enough to process
    oldness = time.time() - os.path.getmtime(video_path)
    if oldness < args.min_age:
        return (False, 0.0)
    
    # Upscale if not exists
    if os.path.exists(video_path) and not os.path.exists(video_4k_path):
        logger.info(f"[{worker_id}] starting upscaling to 4K {os.path.basename(video_path)}...")
        logger.debug(f"[{worker_id}]   - {video_4k_path}")
        t0 = time.time()
        success = video_editing.upscale_video_to_4k(config_dict, video_path, video_4k_path, verbose=args.verbose)
        dur_min = (time.time() - t0) / 60.0
        if success:
            logger.info(f"[{worker_id}] upscaling to 4K {os.path.basename(video_path)} took {dur_min:.2f} min")
            return (True, dur_min)
        else:
            logger.error(f"[{worker_id}] ERROR: Failed to upscale {video_path} to 4K!")
            return (False, dur_min)
    return (False, 0.0)


def process_video_batch(video_path: Optional[str], vtt_path: Optional[str], video_4k_path: Optional[str],
                        chat_json_path: Optional[str], chat_mp4_path: Optional[str],
                        config_dict: Dict[str, Any], args: argparse.Namespace, logger: logging.Logger) -> Dict[str, Any]:
    """Process all operations (VTT, chat, 4K) for a single video+chat combo."""
    worker_id = threading.current_thread().name
    batch_name = os.path.basename(video_path) if video_path else (os.path.basename(chat_json_path) if chat_json_path else "unknown")
    results = {
        'video': batch_name,
        'vtt': None,
        'chat': None,
        '4k': None
    }
    
    if extra.terminated_requested:
        return results
    
    logger.debug(f"[{worker_id}] Processing batch for {batch_name}")
    
    # Process VTT if requested and we have a video
    if args.do_vtt and video_path is not None and vtt_path is not None:
        success, dur_min = process_vtt(video_path, vtt_path, config_dict, args, logger)
        results['vtt'] = {'success': success, 'duration': dur_min}
    
    # Process chat if requested
    if args.do_chat_render and chat_json_path is not None and chat_mp4_path is not None:
        success, dur_min = process_chat(chat_json_path, chat_mp4_path, config_dict, args, logger)
        results['chat'] = {'success': success, 'duration': dur_min}
    
    # Process 4K if requested and we have a video
    if args.do_4k and video_path is not None and video_4k_path is not None:
        success, dur_min = process_4k(video_path, video_4k_path, config_dict, args, logger)
        results['4k'] = {'success': success, 'duration': dur_min}
    
    return results


# ================================================================
# Parallel Execution Helper
# ================================================================

def run_parallel_tasks(tasks: List[Any], worker_func: Callable, description: str,
                       config_dict: Dict[str, Any], args: argparse.Namespace, logger: logging.Logger,
                       result_handler: Optional[Callable[[Any, Any], None]] = None) -> int:
    """
    Run tasks in parallel using ThreadPoolExecutor.
    
    Args:
        tasks: List of task arguments (will be unpacked and passed to worker_func)
        worker_func: Function to call for each task
        description: Description for logging
        config_dict: Configuration dictionary
        args: Command line arguments
        logger: Logger instance
        result_handler: Optional function to handle results (future, task_args) -> None
    
    Returns:
        Number of completed tasks
    """
    if not tasks or extra.terminated_requested:
        return 0
    
    logger.info(f"Processing {description} with {args.parallel} parallel workers...")
    
    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        # Submit all tasks
        futures = {}
        for task_args in tasks:
            if isinstance(task_args, tuple):
                future = executor.submit(worker_func, *task_args, config_dict, args, logger)
            else:
                future = executor.submit(worker_func, task_args, config_dict, args, logger)
            futures[future] = task_args
        
        # Process completed tasks
        completed = 0
        for future in as_completed(futures):
            task_args = futures[future]
            try:
                if result_handler:
                    result_handler(future, task_args)
                else:
                    future.result()  # Just wait for completion
                completed += 1
            except Exception as e:
                # Try to get a meaningful name for the error
                task_name = str(task_args)
                if isinstance(task_args, tuple) and len(task_args) > 0:
                    if isinstance(task_args[0], str):
                        task_name = os.path.basename(task_args[0])
                logger.error(f"Error processing {description} for {task_name}: {e}")
            
            # Check for termination after processing current future
            if extra.terminated_requested:
                logger.warning('terminate requested, cancelling remaining tasks...')
                for f in futures:
                    if not f.done():
                        f.cancel()
                break
    
    logger.info(f"Completed {completed}/{len(tasks)} {description}")
    return completed


# ================================================================
# ================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Post-process videos: generate WebVTT transcriptions, render chat, and/or upscale to 4K')
    parser.add_argument('--directory', required=True, help='Directory to search recursively for videos and chat files')
    parser.add_argument('--min-age', type=int, default=60, help='Minimum file age in seconds')
    parser.add_argument('--do-vtt', action='store_true', help='Generate WebVTT transcriptions for videos')
    parser.add_argument('--do-chat-render', action='store_true', help='Render chat JSON files to video')
    parser.add_argument('--do-4k', action='store_true', help='Upscale videos to 4K')
    parser.add_argument('--parallel', type=int, default=6, help='Number of parallel tasks to run (default: 6)')
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
    
    extra.setup_signal_handle()
    
    # Use the provided directory directly (can be absolute or relative)
    search_directory = os.path.abspath(args.directory)
    if not os.path.exists(search_directory):
        logger.error(f"Directory not found: {search_directory}")
        return
    if not os.path.isdir(search_directory):
        logger.error(f"Path is not a directory: {search_directory}")
        return
    
    # Find video files for VTT and 4K processing
    videos_to_process: List[Tuple[str, str, Optional[str]]] = []  # (video_path, vtt_path, 4k_path)
    # Find chat JSON files for chat rendering
    chats_to_process: List[Tuple[str, str]] = []  # (chat_json_path, chat_mp4_path)
    
    logger.debug(f"Scanning directory recursively: {search_directory}")
    for subdir, dirs, files in os.walk(search_directory):
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
    
    # Create a mapping of video ID to chat files
    chat_map: Dict[str, Tuple[str, str]] = {}
    if args.do_chat_render:
        for chat_json_path, chat_mp4_path in chats_to_process:
            # Extract video ID from chat filename (e.g., "12345_chat.json" -> "12345")
            chat_basename = os.path.basename(chat_json_path)
            video_id = chat_basename.replace("_chat.json", "")
            chat_map[video_id] = (chat_json_path, chat_mp4_path)
    
    # Create batches: group videos with their corresponding chat files
    batches: List[Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]] = []
    processed_chat_ids = set()
    
    # Process videos (with or without chat)
    for video_path, vtt_path, video_4k_path in videos_to_process:
        # Extract video ID from video filename (e.g., "12345.mp4" -> "12345")
        video_basename = os.path.basename(video_path)
        video_id = os.path.splitext(video_basename)[0]
        
        # Find corresponding chat files
        chat_json_path, chat_mp4_path = chat_map.get(video_id, (None, None))
        if chat_json_path is not None:
            processed_chat_ids.add(video_id)
        
        batches.append((video_path, vtt_path, video_4k_path, chat_json_path, chat_mp4_path))
    
    # Process chat files that don't have corresponding videos
    if args.do_chat_render:
        for chat_json_path, chat_mp4_path in chats_to_process:
            # Extract video ID from chat filename (e.g., "12345_chat.json" -> "12345")
            chat_basename = os.path.basename(chat_json_path)
            video_id = chat_basename.replace("_chat.json", "")
            
            # Only add if we haven't already processed this chat with a video
            if video_id not in processed_chat_ids:
                batches.append((None, None, None, chat_json_path, chat_mp4_path))
    
    # Track statistics for processing
    stats = {
        'vtt_completed': 0,
        'vtt_failed': 0,
        'chat_completed': 0,
        'chat_failed': 0,
        'upscale_completed': 0,
        'upscale_failed': 0
    }
    
    # Count total tasks that will be attempted
    vtt_total = sum(1 for video_path, vtt_path, _, _, _ in batches 
                    if args.do_vtt and video_path is not None and vtt_path is not None)
    chat_total = sum(1 for _, _, _, chat_json_path, chat_mp4_path in batches 
                    if args.do_chat_render and chat_json_path is not None and chat_mp4_path is not None)
    upscale_total = sum(1 for video_path, _, video_4k_path, _, _ in batches 
                        if args.do_4k and video_path is not None and video_4k_path is not None)
    
    def batch_result_handler(future, task_args):
        video_path, vtt_path, video_4k_path, chat_json_path, chat_mp4_path = task_args
        try:
            results = future.result()
            
            if results['vtt'] is not None:
                if results['vtt']['success']:
                    stats['vtt_completed'] += 1
                else:
                    stats['vtt_failed'] += 1
            if results['chat'] is not None:
                if results['chat']['success']:
                    stats['chat_completed'] += 1
                else:
                    stats['chat_failed'] += 1
            if results['4k'] is not None:
                if results['4k']['success']:
                    stats['upscale_completed'] += 1
                else:
                    stats['upscale_failed'] += 1
        except Exception as e:
            batch_name = os.path.basename(video_path) if video_path else (os.path.basename(chat_json_path) if chat_json_path else "unknown")
            logger.error(f"Error processing batch for {batch_name}: {e}")
            # Try to determine which operations failed
            if args.do_vtt and vtt_path is not None:
                stats['vtt_failed'] += 1
            if args.do_chat_render and chat_json_path is not None:
                stats['chat_failed'] += 1
            if args.do_4k and video_4k_path is not None:
                stats['upscale_failed'] += 1
    
    completed = run_parallel_tasks(batches, process_video_batch, "video batches",
                                    config_dict, args, logger, batch_result_handler)
    
    # Log detailed statistics with uniform format
    if args.do_vtt:
        logger.info(f"  - VTT: {stats['vtt_completed']}/{vtt_total} completed ({stats['vtt_failed']} failed)")
    if args.do_chat_render:
        logger.info(f"  - Chat: {stats['chat_completed']}/{chat_total} completed ({stats['chat_failed']} failed)")
    if args.do_4k:
        logger.info(f"  - 4K: {stats['upscale_completed']}/{upscale_total} completed ({stats['upscale_failed']} failed)")


def main() -> None:
    """Main entry point."""
    args = parse_args()
    run_task(args)


if __name__ == "__main__":
    main()

