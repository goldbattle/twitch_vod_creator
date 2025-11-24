# !/usr/bin/env python3

import argparse
import yaml
import os
import time
import json
import shutil
import logging
import coloredlogs
import utilities_extra
from utilities_config import load_config, get_temp_path
from utilities_video_editing import render_segment_with_chat, render_segment_without_chat, combine_videos, mute_audio_segments, time_string_to_seconds
from utilities_chat import render_chat
from utilities_file import get_valid_filename

# ================================================================

def main():
    parser = argparse.ArgumentParser(description='Render video segments')
    parser.add_argument('--video-file', required=True, help='Video YAML file (relative to config directory)')
    parser.add_argument('--config-file', required=True, help='Config YAML file (relative to config directory)')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from operations')
    parser.add_argument('--temp-dir', default=get_temp_path("render_segments"), help='Temporary directory for downloads (default: /tmp/tvc_render_segments)')
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=log_level, fmt='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    
    config = load_config()
    config['temp_path'] = args.temp_dir
    
    video_file_path = os.path.join(config['base_path'], args.video_file)
    config_file_path = os.path.join(config['base_path'], args.config_file)
    
    # Load config
    with open(config_file_path) as f:
        yaml_config = yaml.load(f, Loader=yaml.FullLoader)
    logger.debug(f"loaded config file: {config_file_path}")
    
    # Load template
    template_file = os.path.join(config['base_path'], "config", yaml_config["yt_template"])
    with open(template_file, "r") as f:
        template = f.read()
    logger.debug(f"loaded template file: {template_file}")
    
    utilities_extra.setup_signal_handle()
    
    # Load videos
    with open(video_file_path) as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    logger.info(f"loaded {len(data)} videos to render")
    
    # Setup paths
    path_root = os.path.dirname(config['base_path'])
    path_render = os.path.join(path_root, "data_rendered")
    
    # Process each video
    for video in data:
        if utilities_extra.terminated_requested:
            logger.info('terminate requested, not downloading any more..')
            break
        
        logger.info(f"processing {video['video']}")
        
        # Check video exists
        file_path_video = os.path.join(path_root, video["video"] + ".mp4")
        if not os.path.exists(file_path_video):
            logger.error(f"could not find the video file: {file_path_video}")
            continue
        
        # Load video info
        file_path_info = os.path.join(path_root, video["video"] + "_info.json")
        with open(file_path_info) as f:
            video_info = json.load(f)
        
        # Setup paths
        clean_video_title = get_valid_filename(video["title"])
        path_temp_parts = os.path.join(config['temp_path'], "parts", clean_video_title)
        if os.path.exists(path_temp_parts):
            shutil.rmtree(path_temp_parts)
        os.makedirs(path_temp_parts, exist_ok=True)
        
        try:
            # Composite video
            file_path_composite = os.path.join(path_render, f"{video['video']}_{clean_video_title}.mp4")
            file_path_composite_tmp = os.path.join(config['temp_path'], f"{clean_video_title}.tmp.mp4")
            
            if not utilities_extra.terminated_requested and not os.path.exists(file_path_composite):
                should_render_chat = video.get("with_chat", True)
                
                # Render chat if needed
                file_path_chat = os.path.join(path_root, video["video"] + "_chat.json")
                file_path_chat_mp4 = os.path.join(path_root, video["video"] + "_chat.mp4")
                
                if should_render_chat and os.path.exists(file_path_chat) and not os.path.exists(file_path_chat_mp4):
                    logger.info("  - starting rendering chat...")
                    logger.debug(f"  - {file_path_chat_mp4}")
                    t0 = time.time()
                    render_chat(config, file_path_chat, file_path_chat_mp4, verbose=args.verbose)
                    dur_min = (time.time() - t0) / 60.0
                    logger.info(f"  - rendering chat took {dur_min:.2f} min")
                
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
                segment_files = []
                
                logger.info("  - starting rendering segments...")
                for idx in range(len(seg_start)):
                    if utilities_extra.terminated_requested:
                        logger.info('terminate requested, not rendering more segments..')
                        break
                    
                    tmp_output_file = os.path.join(path_temp_parts, f"temp_{idx}.mp4")
                    if len(seg_start) == 1:
                        tmp_output_file = file_path_composite_tmp
                    
                    t0 = time.time()
                    chat_offset = int(video.get("t_chat_offset", 0))
                    
                    if should_render_chat and os.path.exists(file_path_chat_mp4):
                        logger.info(f"  - starting rendering segment {seg_start[idx]} to {seg_end[idx]}...")
                        logger.debug(f"  - {tmp_output_file}")
                        if chat_offset != 0:
                            logger.debug(f"  - chat offset: {chat_offset} seconds")
                        success = render_segment_with_chat(
                            config, file_path_video, file_path_chat_mp4, tmp_output_file,
                            seg_start[idx], seg_end[idx], chat_offset, verbose=args.verbose
                        )
                        if not success:
                            logger.error("  - ERROR: Failed to render segment! Check if input files exist and run with --verbose for details.")
                            break
                    else:
                        logger.info(f"  - starting rendering segment {seg_start[idx]} to {seg_end[idx]}...")
                        logger.debug(f"  - {tmp_output_file}")
                        success = render_segment_without_chat(
                            config, file_path_video, tmp_output_file,
                            seg_start[idx], seg_end[idx], verbose=args.verbose
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
                if not utilities_extra.terminated_requested and len(seg_start) != 1:
                    logger.info("  - starting merging segments...")
                    logger.debug(f"  - {file_path_composite_tmp}")
                    combine_videos(config, segment_files, file_path_composite_tmp)
                    
                    dur_min = (time.time() - t0_big) / 60.0
                    logger.info(f"  - merging segments took {dur_min:.2f} min")
                    logger.debug(f"  - segment durations: {dur_segment_total}")
                    dur_render_total = time.time() - t0_big
                    logger.debug(f"  - realtime factor: {dur_segment_total / dur_render_total:.2f}")
                
                # Move temp to final
                if not utilities_extra.terminated_requested and os.path.exists(file_path_composite_tmp):
                    logger.debug("  - renaming temp export file to final filename")
                    shutil.move(file_path_composite_tmp, file_path_composite)
                elif utilities_extra.terminated_requested and os.path.exists(file_path_composite_tmp):
                    logger.debug("  - removing half rendered temp file")
                    os.remove(file_path_composite_tmp)
            
            # Description file
            file_path_desc = os.path.join(path_render, f"{video['video']}_{clean_video_title}_desc.txt")
            if not utilities_extra.terminated_requested and not os.path.exists(file_path_desc):
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
            
            # Muted composite
            file_path_composite_muted = os.path.join(path_render, f"{video['video']}_{clean_video_title}_muted.mp4")
            seg_to_cut = None
            if "t_youtube_mute" in video:
                seg_to_cut = video["t_youtube_mute"].split(",")
            
            if (not utilities_extra.terminated_requested and not os.path.exists(file_path_composite_muted) and
                os.path.exists(file_path_composite) and seg_to_cut is not None):
                
                # Parse mute segments
                mute_segments = []
                for seg in seg_to_cut:
                    parts = seg.split(" - ")
                    assert len(parts) == 2
                    start_seconds = time_string_to_seconds(parts[0])
                    end_seconds = time_string_to_seconds(parts[1])
                    mute_segments.append((start_seconds, end_seconds))
                
                logger.info("  - starting muting audio segments...")
                logger.debug(f"  - {file_path_composite_muted}")
                t0 = time.time()
                mute_audio_segments(config, file_path_composite, file_path_composite_muted, mute_segments)
                dur_min = (time.time() - t0) / 60.0
                logger.info(f"  - muting audio segments took {dur_min:.2f} min")
            
            # Muted description file
            file_path_desc_muted = os.path.join(path_render, f"{video['video']}_{clean_video_title}_muted_desc.txt")
            if not utilities_extra.terminated_requested and not os.path.exists(file_path_desc_muted) and seg_to_cut is not None:
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
            logger.error(f"{e}")
        
        # Cleanup
        if os.path.exists(path_temp_parts):
            shutil.rmtree(path_temp_parts)


if __name__ == "__main__":
    main()
