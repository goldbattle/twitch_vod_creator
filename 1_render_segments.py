# !/usr/bin/env python3

import argparse
import yaml
import os
import time
import json
import shutil
import utilities_extra
from utilities_config import load_config, get_temp_path
from utilities_video_editing import render_segment_with_chat, render_segment_without_chat, combine_videos, mute_audio_segments, time_string_to_seconds
from utilities_chat import render_chat
from utilities_file import get_valid_filename

# video file we wish to render
video_file = "config/soda_2025_videos.yaml"
config_file = "config/soda_config_youtube.yaml"

# ================================================================

def main():
    parser = argparse.ArgumentParser(description='Render video segments')
    parser.add_argument('--video-file', default=video_file, help='Video YAML file')
    parser.add_argument('--config-file', default=config_file, help='Config YAML file')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from operations')
    parser.add_argument('--temp-dir', default=get_temp_path("render_segments"), help='Temporary directory for downloads (default: /tmp/tvc_render_segments)')
    args = parser.parse_args()
    
    config = load_config()
    config['temp_path'] = args.temp_dir
    
    video_file_path = os.path.join(config['base_path'], args.video_file)
    config_file_path = os.path.join(config['base_path'], args.config_file)
    
    # Load config
    with open(config_file_path) as f:
        yaml_config = yaml.load(f, Loader=yaml.FullLoader)
    print(f"loaded config file: {config_file_path}")
    
    # Load template
    template_file = os.path.join(config['base_path'], "config", yaml_config["yt_template"])
    with open(template_file, "r") as f:
        template = f.read()
    print(f"loaded template file: {template_file}")
    
    utilities_extra.setup_signal_handle()
    
    # Load videos
    with open(video_file_path) as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    print(f"loaded {len(data)} videos to render")
    
    # Setup paths
    path_root = os.path.dirname(config['base_path'])
    path_render = os.path.join(path_root, "data_rendered")
    
    # Process each video
    for video in data:
        if utilities_extra.terminated_requested:
            print('terminate requested, not downloading any more..')
            break
        
        print(f"processing {video['video']}")
        
        # Check video exists
        file_path_video = os.path.join(path_root, video["video"] + ".mp4")
        if not os.path.exists(file_path_video):
            print(f"\t- ERROR: could not find the video file!")
            print(f"\t- {file_path_video}")
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
                    print(f"\t- rendering chat: {file_path_chat}")
                    render_chat(config, file_path_chat, file_path_chat_mp4, verbose=args.verbose)
                
                # Render composite
                print(f"\t- rendering composite: {file_path_composite}")
                os.makedirs(os.path.dirname(file_path_composite), exist_ok=True)
                
                if os.path.exists(file_path_composite_tmp):
                    print(f"\t- deleting temp file: {file_path_composite_tmp}")
                    os.remove(file_path_composite_tmp)
                
                # Render segments
                seg_start = video["t_start"].split(",")
                seg_end = video["t_end"].split(",")
                assert len(seg_start) == len(seg_end)
                
                dur_segment_total = 0
                t0_big = time.time()
                segment_files = []
                
                for idx in range(len(seg_start)):
                    if utilities_extra.terminated_requested:
                        print('terminate requested, not rendering more segments..')
                        break
                    
                    tmp_output_file = os.path.join(path_temp_parts, f"temp_{idx}.mp4")
                    if len(seg_start) == 1:
                        tmp_output_file = file_path_composite_tmp
                    
                    t0 = time.time()
                    chat_offset = int(video.get("t_chat_offset", 0))
                    
                    if should_render_chat and os.path.exists(file_path_chat_mp4):
                        print(f"\t- rendering with chat overlay {seg_start[idx]} to {seg_end[idx]}")
                        if chat_offset != 0:
                            print(f"\t- chat has offset of {chat_offset} seconds")
                        success = render_segment_with_chat(
                            config, file_path_video, file_path_chat_mp4, tmp_output_file,
                            seg_start[idx], seg_end[idx], chat_offset, verbose=args.verbose
                        )
                        if not success:
                            print(f"\t- ERROR: Failed to render segment! Check if input files exist and run with --verbose for details.")
                            break
                    else:
                        print(f"\t- rendering *without* chat overlay {seg_start[idx]} to {seg_end[idx]}")
                        success = render_segment_without_chat(
                            config, file_path_video, tmp_output_file,
                            seg_start[idx], seg_end[idx], verbose=args.verbose
                        )
                        if not success:
                            print(f"\t- ERROR: Failed to render segment! Check if input files exist and run with --verbose for details.")
                            break
                    
                    if not os.path.exists(tmp_output_file):
                        print(f"\t- ERROR: Output file was not created: {tmp_output_file}")
                        break
                    
                    t1 = time.time()
                    h1, m1, s1 = seg_start[idx].split(':')
                    h2, m2, s2 = seg_end[idx].split(':')
                    dur_segment = (int(h2) - int(h1)) * 3600 + (int(m2) - int(m1)) * 60 + (int(s2) - int(s1))
                    dur_render = t1 - t0 + 1e-6
                    dur_segment_total += dur_segment
                    print(f"\t- time to render: {dur_render:.1f}")
                    print(f"\t- segment duration: {dur_segment}")
                    if dur_render > 0.1:  # Only show realtime factor if it took more than 0.1 seconds
                        print(f"\t- realtime factor: {dur_segment / dur_render:.2f}")
                    else:
                        print(f"\t- WARNING: Render completed too quickly - likely failed!")
                    
                    if len(seg_start) > 1:
                        segment_files.append(tmp_output_file)
                
                # Combine segments if multiple
                if not utilities_extra.terminated_requested and len(seg_start) != 1:
                    print("\t- combining all videos into a single segment!")
                    combine_videos(config, segment_files, file_path_composite_tmp)
                    
                    t1_big = time.time()
                    dur_render = t1_big - t0_big + 1e-6
                    print(f"\t- time to render: {dur_render:.1f}")
                    print(f"\t- segment durations: {dur_segment_total}")
                    print(f"\t- realtime factor: {dur_segment_total / dur_render:.2f}")
                
                # Move temp to final
                if not utilities_extra.terminated_requested and os.path.exists(file_path_composite_tmp):
                    print("\t- renaming temp export file to final filename")
                    shutil.move(file_path_composite_tmp, file_path_composite)
                elif utilities_extra.terminated_requested and os.path.exists(file_path_composite_tmp):
                    print("\t- removing half rendered temp file")
                    os.remove(file_path_composite_tmp)
            
            # Description file
            file_path_desc = os.path.join(path_render, f"{video['video']}_{clean_video_title}_desc.txt")
            if not utilities_extra.terminated_requested and not os.path.exists(file_path_desc):
                print(f"\t- writting info: {file_path_desc}")
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
                
                print(f"\t- muting audio segments: {file_path_composite_muted}")
                mute_audio_segments(config, file_path_composite, file_path_composite_muted, mute_segments)
            
            # Muted description file
            file_path_desc_muted = os.path.join(path_render, f"{video['video']}_{clean_video_title}_muted_desc.txt")
            if not utilities_extra.terminated_requested and not os.path.exists(file_path_desc_muted) and seg_to_cut is not None:
                print(f"\t- writting info: {file_path_desc_muted}")
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
        
        except Exception as e:
            print(f"\t- ERROR: {e}")
        
        # Cleanup
        if os.path.exists(path_temp_parts):
            shutil.rmtree(path_temp_parts)
        print("")


if __name__ == "__main__":
    main()
