# !/usr/bin/env python3

import sys
import os
import argparse
import yaml
import time
import json
import shutil
import logging
import coloredlogs
import glob
from typing import List, Tuple, Dict, Any, Optional

# Add parent directory to path so we can import utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utilities import extra, config, video_editing, chat, file

# ================================================================

def find_segments_files(directory: str) -> List[str]:
    """Recursively find all *_segments.yaml files in the given directory."""
    pattern = os.path.join(directory, '**', '*_segments.yaml')
    files = glob.glob(pattern, recursive=True)
    return sorted(files)


def load_all_segments(segments_files: List[str], logger: logging.Logger) -> List[Dict[str, Any]]:
    """Load all segments from multiple YAML files and combine them into a single list."""
    all_segments = []
    for file_path in segments_files:
        try:
            with open(file_path) as f:
                data = yaml.load(f, Loader=yaml.FullLoader)
                if data:
                    all_segments.extend(data)
                    logger.debug(f"Loaded {len(data)} segments from {file_path}")
        except Exception as e:
            logger.error(f"Error loading segments from {file_path}: {e}")
    return all_segments


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Render video segments')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file-segments', help='YAML file with all video segments (relative to config directory)')
    group.add_argument('--dir-segments', help='Directory to recursively scan for *_segments.yaml files')
    parser.add_argument('--file-config', required=True, help='Config YAML file (relative to config directory)')
    parser.add_argument('--file-history', help='History YAML file (relative to config directory)')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from operations')
    parser.add_argument('--temp-dir', default=config.get_temp_path("render_segments"), help='Temporary directory for downloads (default: /tmp/tvc_render_segments)')
    parser.add_argument('--do-4k', action='store_true', help='Upscale videos to 4K (3840x2160) with 25Mbps bitrate and re-render chat at 4K')
    return parser.parse_args()


def run_task(args: argparse.Namespace) -> None:
    """Render video segments based on provided arguments."""
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=log_level, fmt='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    
    config_dict = config.load_config()
    config_dict['temp_path'] = args.temp_dir
    
    config_file_path = os.path.join(config_dict['base_path'], args.file_config)
    
    # Load config
    with open(config_file_path) as f:
        yaml_config = yaml.load(f, Loader=yaml.FullLoader)
    logger.debug(f"loaded config file: {config_file_path}")
    
    # Load history file if provided
    hist_renders: Dict[str, Any] = {}
    if args.file_history:
        history_file = os.path.join(config_dict['base_path'], args.file_history)
        if os.path.exists(history_file):
            with open(history_file) as f:
                hist_renders = yaml.load(f, Loader=yaml.FullLoader)
            logger.debug(f"loaded history file: {history_file}")
        else:
            logger.debug(f"history file does not exist, will create: {history_file}")
    
    # Load template
    template_file = os.path.join(config_dict['base_path'], "config", yaml_config["yt_template"])
    with open(template_file, "r") as f:
        template = f.read()
    logger.debug(f"loaded template file: {template_file}")
    
    extra.setup_signal_handle()
    
    # Load segments from either a single file or directory scan
    if args.file_segments:
        # Single file mode
        video_file_path = os.path.join(config_dict['base_path'], args.file_segments)
        with open(video_file_path) as f:
            data = yaml.load(f, Loader=yaml.FullLoader)
        logger.info(f"loaded {len(data)} videos to render from {args.file_segments}")
    else:
        # Directory scan mode
        segments_dir = args.dir_segments
        if not os.path.isabs(segments_dir):
            segments_dir = os.path.join(config_dict['base_path'], segments_dir)
        
        # Find and load all segments files
        segments_files = find_segments_files(segments_dir)
        if not segments_files:
            logger.warning(f"No *_segments.yaml files found in {segments_dir}")
            return
        
        logger.info(f"Found {len(segments_files)} segments file(s):")
        for file_path in segments_files:
            logger.info(f"  - {file_path}")
        
        # Load all segments from all files
        data = load_all_segments(segments_files, logger)
        logger.info(f"Loaded {len(data)} total segments to render")
    
    # Setup paths
    path_root = os.path.dirname(config_dict['base_path'])
    path_render = os.path.join(path_root, "data_rendered")
    
    # Process each video
    for video in data:
        if extra.terminated_requested:
            logger.info('terminate requested, not downloading any more..')
            break
        
        # Setup paths early to check for skip condition
        clean_video_title = file.get_valid_filename(video["title"])
        file_path_desc = os.path.join(path_render, f"{video['video']}_{clean_video_title}_desc.txt")
        
        logger.info(f"processing {video['video']} - '{video['title']}'")
        
        # Check if video is in history file - if so, skip rendering
        # Only skip if it has "rendered_at" field (added by this script, not other scripts)
        if args.file_history:
            video_id = video["video"].replace(' ', '_') + "_" + video["title"].lower().replace(' ', '_')
            if video_id in hist_renders and "rendered_at" in hist_renders[video_id]:
                logger.info(f"  - video already in history file, was rendered at: {hist_renders[video_id]['rendered_at']}")
                logger.debug(f"  - video_id: {video_id}")
                continue
        
        # Check if description file exists - if so, skip rendering
        if os.path.exists(file_path_desc):
            logger.info("  - description file exists, skipping rendering")
            logger.debug(f"  - {file_path_desc}")
            continue
        
        # Check video exists
        file_path_video = os.path.join(path_root, video["video"] + ".mp4")
        if not os.path.exists(file_path_video):
            logger.error(f"could not find the video file: {file_path_video}")
            continue
        
        # Load video info
        file_path_info = os.path.join(path_root, video["video"] + "_info.json")
        try:
            with open(file_path_info) as f:
                video_info = json.load(f)
        except Exception as e:
            logger.error(f"could not load video info file: {file_path_info} - {e}")
            continue
        
        path_temp_parts = os.path.join(config_dict['temp_path'], "parts", clean_video_title)
        if os.path.exists(path_temp_parts):
            shutil.rmtree(path_temp_parts)
        os.makedirs(path_temp_parts, exist_ok=True)
        
        try:
            # Composite video - use 4K temp folder if enabled
            if args.do_4k:
                file_path_composite = os.path.join(path_render, f"{video['video']}_{clean_video_title}_4k.mp4")
            else:
                file_path_composite = os.path.join(path_render, f"{video['video']}_{clean_video_title}.mp4")
            file_path_composite_tmp = os.path.join(config_dict['temp_path'], f"{clean_video_title}.tmp.mp4")
            
            should_render_chat = video.get("with_chat", True)
            if not extra.terminated_requested:
                # Render chat if needed (only if with_chat is True)
                file_path_chat_mp4 = None
                if should_render_chat:
                    file_path_chat = os.path.join(path_root, video["video"] + "_chat.json")
                    file_path_chat_mp4 = os.path.join(path_root, video["video"] + "_chat.mp4")
                    
                    # For 4K mode, we need to re-render chat at 4K resolution
                    if args.do_4k and os.path.exists(file_path_chat):
                        file_path_chat_mp4_4k = os.path.join(path_root, video["video"] + "_chat_4k.mp4")
                        if not os.path.exists(file_path_chat_mp4_4k):
                            # Render to temp first, then copy to data directory
                            file_path_chat_mp4_4k_temp = os.path.join(config_dict['temp_path'], video["video"] + "_chat_4k_temp.mp4")
                            logger.info("  - starting rendering chat at 4K...")
                            logger.debug(f"  - {file_path_chat_mp4_4k}")
                            t0 = time.time()
                            chat.render_chat(config_dict, file_path_chat, file_path_chat_mp4_4k_temp, verbose=args.verbose, is_4k=True)
                            dur_min = (time.time() - t0) / 60.0
                            if os.path.exists(file_path_chat_mp4_4k_temp):
                                # Copy to data directory
                                shutil.copy2(file_path_chat_mp4_4k_temp, file_path_chat_mp4_4k)
                                os.remove(file_path_chat_mp4_4k_temp)
                                logger.info(f"  - rendering chat at 4K took {dur_min:.2f} min")
                            else:
                                logger.error("  - ERROR: Failed to render chat at 4K!")
                                continue
                        file_path_chat_mp4 = file_path_chat_mp4_4k
                    elif os.path.exists(file_path_chat) and not os.path.exists(file_path_chat_mp4):
                        logger.info("  - starting rendering chat...")
                        logger.debug(f"  - {file_path_chat_mp4}")
                        t0 = time.time()
                        chat.render_chat(config_dict, file_path_chat, file_path_chat_mp4, verbose=args.verbose)
                        dur_min = (time.time() - t0) / 60.0
                        logger.info(f"  - rendering chat took {dur_min:.2f} min")
                
                # Upscale video to 4K if enabled
                if args.do_4k:
                    file_path_video_4k = os.path.join(path_root, video["video"] + "_4k.mp4")
                    if not os.path.exists(file_path_video_4k):
                        # Upscale to temp first, then copy to data directory
                        file_path_video_4k_temp = os.path.join(config_dict['temp_path'], video["video"] + "_4k_temp.mp4")
                        logger.info("  - starting upscaling video to 4K...")
                        logger.debug(f"  - {file_path_video_4k}")
                        t0 = time.time()
                        success = video_editing.upscale_video_to_4k(config_dict, file_path_video, file_path_video_4k_temp, verbose=args.verbose)
                        dur_min = (time.time() - t0) / 60.0
                        if success and os.path.exists(file_path_video_4k_temp):
                            # Copy to data directory
                            shutil.copy2(file_path_video_4k_temp, file_path_video_4k)
                            os.remove(file_path_video_4k_temp)
                            logger.info(f"  - upscaling video to 4K took {dur_min:.2f} min")
                            file_path_video = file_path_video_4k
                        else:
                            logger.error("  - ERROR: Failed to upscale video to 4K! Skipping this video.")
                            logger.error("  - Check if input file exists and run with --verbose for details.")
                            if os.path.exists(file_path_video_4k_temp):
                                os.remove(file_path_video_4k_temp)
                            continue  # Skip this video entirely
                    else:
                        file_path_video = file_path_video_4k
                
                # Render composite
                os.makedirs(os.path.dirname(file_path_composite), exist_ok=True)
                
                if os.path.exists(file_path_composite_tmp):
                    logger.debug(f"  - deleting temp file: {file_path_composite_tmp}")
                    os.remove(file_path_composite_tmp)
                
                # Render segments
                seg_start = video["t_start"].split(",")
                seg_end = video["t_end"].split(",")
                assert len(seg_start) == len(seg_end)
                
                dur_segment_total = 0
                t0_big = time.time()
                segment_files: List[str] = []
                
                logger.info("  - starting rendering segments...")
                for idx in range(len(seg_start)):
                    if extra.terminated_requested:
                        logger.info('terminate requested, not rendering more segments..')
                        break
                    
                    tmp_output_file = os.path.join(path_temp_parts, f"temp_{idx}.mp4")
                    if len(seg_start) == 1:
                        tmp_output_file = file_path_composite_tmp
                    
                    t0 = time.time()
                    
                    if should_render_chat and file_path_chat_mp4 and os.path.exists(file_path_chat_mp4):
                        chat_offset = int(video.get("t_chat_offset", 0))
                        logger.info(f"  - starting rendering segment {seg_start[idx]} to {seg_end[idx]}...")
                        logger.debug(f"  - {tmp_output_file}")
                        if chat_offset != 0:
                            logger.debug(f"  - chat offset: {chat_offset} seconds")
                        success = video_editing.render_segment_with_chat(
                            config_dict, file_path_video, file_path_chat_mp4, tmp_output_file,
                            seg_start[idx], seg_end[idx], chat_offset, verbose=args.verbose, is_4k=args.do_4k
                        )
                        if not success:
                            logger.error("  - ERROR: Failed to render segment! Check if input files exist and run with --verbose for details.")
                            break
                    else:
                        logger.info(f"  - starting rendering segment {seg_start[idx]} to {seg_end[idx]}...")
                        logger.debug(f"  - {tmp_output_file}")
                        success = video_editing.render_segment_without_chat(
                            config_dict, file_path_video, tmp_output_file,
                            seg_start[idx], seg_end[idx], verbose=args.verbose, is_4k=args.do_4k
                        )
                        if not success:
                            logger.error("  - ERROR: Failed to render segment! Check if input files exist and run with --verbose for details.")
                            break
                    
                    if not os.path.exists(tmp_output_file):
                        logger.error(f"  - ERROR: Output file was not created: {tmp_output_file}")
                        break
                    
                    t1 = time.time()
                    h1, m1, s1 = seg_start[idx].split(':')
                    h2, m2, s2 = seg_end[idx].split(':')
                    dur_segment = (int(h2) - int(h1)) * 3600 + (int(m2) - int(m1)) * 60 + (int(s2) - int(s1))
                    dur_render = t1 - t0 + 1e-6
                    dur_segment_total += dur_segment
                    dur_min = dur_render / 60.0
                    logger.info(f"  - rendering segment {seg_start[idx]} to {seg_end[idx]} took {dur_min:.2f} min")
                    logger.debug(f"  - segment duration: {dur_segment}")
                    if dur_render > 0.1:  # Only show realtime factor if it took more than 0.1 seconds
                        logger.debug(f"  - realtime factor: {dur_segment / dur_render:.2f}")
                    else:
                        logger.warning("  - WARNING: Render completed too quickly - likely failed!")
                    
                    if len(seg_start) > 1:
                        segment_files.append(tmp_output_file)
                
                # Combine segments if multiple
                if not extra.terminated_requested and len(seg_start) != 1:
                    logger.info("  - starting merging segments...")
                    logger.debug(f"  - {file_path_composite_tmp}")
                    video_editing.combine_videos(config_dict, segment_files, file_path_composite_tmp)
                    
                    dur_min = (time.time() - t0_big) / 60.0
                    logger.info(f"  - merging segments took {dur_min:.2f} min")
                    logger.debug(f"  - segment durations: {dur_segment_total}")
                    dur_render_total = time.time() - t0_big
                    logger.debug(f"  - realtime factor: {dur_segment_total / dur_render_total:.2f}")
                
                # Move temp to final
                if not extra.terminated_requested and os.path.exists(file_path_composite_tmp):
                    logger.debug("  - renaming temp export file to final filename")
                    shutil.move(file_path_composite_tmp, file_path_composite)
                elif extra.terminated_requested and os.path.exists(file_path_composite_tmp):
                    logger.debug("  - removing half rendered temp file")
                    os.remove(file_path_composite_tmp)
            
            # Description file - only create if video was successfully rendered
            if not extra.terminated_requested and not os.path.exists(file_path_desc) and os.path.exists(file_path_composite):
                tmp = str(template)
                tmp = tmp.replace("$id", video_info["id"])
                tmp = tmp.replace("$title", video_info["title"])
                tmp = tmp.replace("$views", str(video_info["views"]))
                tmp = tmp.replace("$t_start", video["t_start"])
                tmp = tmp.replace("$t_end", video["t_end"])
                tmp = tmp.replace("$recorded", video_info["recorded_at"])
                tmp = tmp.replace("$file", video["video"] + ".mp4")
                tmp = tmp.replace("$url", video_info["url"])
                if "description" in video:
                    tmp = video["description"] + "\n\n" + tmp
                tmp = video["title"] + "\n\n" + tmp
                with open(file_path_desc, "w", encoding="utf-8") as f:
                    f.write(tmp)
                logger.info("  - created description file")
                logger.debug(f"  - {file_path_desc}")
                
                # Update history file if provided
                if args.file_history:
                    history_file = os.path.join(config_dict['base_path'], args.file_history)
                    video_id = video["video"].replace(' ', '_') + "_" + video["title"].lower().replace(' ', '_')
                    entry = {
                        'title': video["title"],
                        'file': file_path_composite,
                        'rendered_at': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    extra.update_history_file(history_file, video_id, entry, logger)
                    # Update in-memory copy as well (merge with existing if any)
                    if video_id not in hist_renders:
                        hist_renders[video_id] = {}
                    hist_renders[video_id].update(entry)
                    logger.debug(f"  - updated history file: {history_file}")
            
            # Muted composite
            file_path_composite_muted = os.path.join(path_render, f"{video['video']}_{clean_video_title}_muted.mp4")
            seg_to_cut: Optional[List[str]] = None
            if "t_youtube_mute" in video:
                seg_to_cut = video["t_youtube_mute"].split(",")
            
            if (not extra.terminated_requested and not os.path.exists(file_path_composite_muted) and
                os.path.exists(file_path_composite) and seg_to_cut is not None):
                
                # Parse mute segments
                mute_segments: List[Tuple[float, float]] = []
                for seg in seg_to_cut:
                    parts = seg.split(" - ")
                    assert len(parts) == 2
                    start_seconds = video_editing.time_string_to_seconds(parts[0])
                    end_seconds = video_editing.time_string_to_seconds(parts[1])
                    mute_segments.append((start_seconds, end_seconds))
                
                logger.info("  - starting muting audio segments...")
                logger.debug(f"  - {file_path_composite_muted}")
                t0 = time.time()
                video_editing.mute_audio_segments(config_dict, file_path_composite, file_path_composite_muted, mute_segments)
                dur_min = (time.time() - t0) / 60.0
                logger.info(f"  - muting audio segments took {dur_min:.2f} min")
            
            # Muted description file
            file_path_desc_muted = os.path.join(path_render, f"{video['video']}_{clean_video_title}_muted_desc.txt")
            if not extra.terminated_requested and not os.path.exists(file_path_desc_muted) and seg_to_cut is not None:
                tmp = str(template)
                tmp = tmp.replace("$id", video_info["id"])
                tmp = tmp.replace("$title", video_info["title"])
                tmp = tmp.replace("$views", str(video_info["views"]))
                tmp = tmp.replace("$t_start", video["t_start"])
                tmp = tmp.replace("$t_end", video["t_end"])
                tmp = tmp.replace("$recorded", video_info["recorded_at"])
                tmp = tmp.replace("$file", video["video"] + ".mp4")
                tmp = tmp.replace("$url", video_info["url"])
                
                muted_txt = "Sections of this video has been muted:\n"
                for seg in seg_to_cut:
                    muted_txt += seg + "\n"
                tmp = muted_txt + "\n\n" + tmp
                if "description" in video:
                    tmp = video["description"] + "\n\n" + tmp
                tmp = video["title"] + "\n\n" + tmp
                with open(file_path_desc_muted, "w", encoding="utf-8") as f:
                    f.write(tmp)
                logger.info("  - created muted description file")
                logger.debug(f"  - {file_path_desc_muted}")
        
        except Exception as e:
            logger.error(f"Error processing {video.get('video', 'unknown')} - '{video.get('title', 'unknown')}': {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        # Cleanup
        if os.path.exists(path_temp_parts):
            shutil.rmtree(path_temp_parts)


def main() -> None:
    """Main entry point."""
    args = parse_args()
    run_task(args)


if __name__ == "__main__":
    main()
