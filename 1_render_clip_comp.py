# !/usr/bin/env python3

import argparse
import os
import re
import json
import time
import datetime
import subprocess
import utilities_extra
from utilities_config import load_config, get_temp_path
from utilities_twitch_api import get_user_by_login, get_clips, create_clip_data, get_clip_data
from utilities_video_download import download_clip
from utilities_chat import download_chat, render_chat
from utilities_video_editing import render_clip_with_title, combine_videos, get_video_duration
from utilities_file import get_date_folder

# parameters
channel = 'sodapoppin'
max_clips = 10
date_start = '2024-12-01T00:00:00Z'
date_end = '2024-12-31T00:00:00Z'
min_views_required = 500
get_latest_from_twitch = True
remove_rendered = True
clips_to_ignore = [
    "ScaryBrainyEyeballArsonNoSexy-0Jn0wz5mZ1bRMyGk",
    "EasyFairLlamaHoneyBadger-rxZed8PoO1MR3PgL",
    "ShinyDependableSharkKappaPride-Qjf4VS7pe6TumUY6",
    "MoralSaltyHabaneroDatSheffy-3uKETXph5PWyF8w6",
    "PricklyCheerfulShallotKeyboardCat-h8Knl5UZGEphTpn7",
    "BoredHedonisticMilkCorgiDerp-kzChRQAEuGS0xNcM",
]

# ================================================================

def main():
    parser = argparse.ArgumentParser(description='Download and render clip compilation')
    parser.add_argument('--channel', default=channel, help='Channel name')
    parser.add_argument('--max-clips', type=int, default=max_clips, help='Maximum number of clips')
    parser.add_argument('--date-start', default=date_start, help=f'Start date (ISO format, default: {date_start})')
    parser.add_argument('--date-end', default=date_end, help=f'End date (ISO format, default: {date_end})')
    parser.add_argument('--min-views', type=int, default=min_views_required, help='Minimum view count')
    parser.add_argument('--no-download', action='store_true', help='Skip downloading from Twitch')
    parser.add_argument('--no-remove', action='store_true', help='Keep rendered files')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from download operations')
    parser.add_argument('--temp-dir', default=get_temp_path("render_clip_comp"), help='Temporary directory for downloads (default: /tmp/tvc_render_clip_comp)')
    args = parser.parse_args()
    
    # Validate date formats before proceeding
    try:
        datetime_start = datetime.datetime.strptime(args.date_start, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as e:
        print(f"Error: Invalid date format for --date-start: {args.date_start}")
        print(f"Expected format: YYYY-MM-DDTHH:MM:SSZ (e.g., 2024-01-01T00:00:00Z)")
        exit(1)
    try:
        datetime_end = datetime.datetime.strptime(args.date_end, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as e:
        print(f"Error: Invalid date format for --date-end: {args.date_end}")
        print(f"Expected format: YYYY-MM-DDTHH:MM:SSZ (e.g., 2024-12-31T00:00:00Z)")
        exit(1)
    
    if datetime_start >= datetime_end:
        print(f"Error: --date-start ({args.date_start}) must be before --date-end ({args.date_end})")
        exit(1)
    
    config = load_config()
    config['temp_path'] = args.temp_dir
    auth = config['auth']
    path_root = config['clips_root']
    path_render = config['render_root']
    
    utilities_extra.setup_signal_handle()
    
    path_data = os.path.join(path_root, args.channel)
    os.makedirs(path_data, exist_ok=True)
    os.makedirs(config['temp_path'], exist_ok=True)
    
    # Download new clips if enabled
    if not args.no_download and get_latest_from_twitch:
        user = get_user_by_login(auth["client_id"], auth["client_secret"], args.channel)
        if not user:
            print(f"Error: User {args.channel} not found")
            exit(1)
        
        game_cache = {}
        print(f"getting clips for -> {user['login']} (id {user['id']})")
        vid_iter = get_clips(auth["client_id"], auth["client_secret"], user["id"],
                            started_at=args.date_start, ended_at=args.date_end, page_size=100)
        try:
            for video in vid_iter:
                if utilities_extra.terminated_requested:
                    print('terminate requested, not looking at any more clips...')
                    exit(-1)
                
                if video['view_count'] < args.min_views:
                    print(f"skipping {video['url']} (only {video['view_count']} views)")
                    break
                
                created_date = video['created_at'].strftime('%Y-%m-%d')
                print(f"clip {video['url']} ({video['view_count']} views, created: {created_date})")
                
                # Setup paths
                export_folder = get_date_folder(video['created_at'].strftime('%Y-%m-%dT%H:%M:%SZ'))
                path_data_folder = os.path.join(path_data, export_folder)
                os.makedirs(path_data_folder, exist_ok=True)
                
                file_path_info = os.path.join(path_data_folder, f"{video['id']}_info.json")
                file_path = os.path.join(path_data_folder, f"{video['id']}.mp4")
                file_path_chat = os.path.join(path_data_folder, f"{video['id']}_chat.json")
                
                # Save/update clip info
                if not utilities_extra.terminated_requested:
                    if not os.path.exists(file_path_info):
                        print(f"\t- saving clip info: {video['id']}")
                        clip_data = create_clip_data(auth["client_id"], auth["client_secret"], video, game_cache)
                        with open(file_path_info, 'w', encoding="utf-8") as f:
                            json.dump(clip_data, f, indent=4)
                    else:
                        print("\t- updating clip info!")
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
                
                # Download clip
                if not utilities_extra.terminated_requested and not os.path.exists(file_path):
                    print(f"\t- download clip: {video['id']}")
                    download_clip(config, video['id'], file_path, verbose=args.verbose)
                    if not os.path.exists(file_path):
                        print("\t- VIDEO DOWNLOAD FAILED!!!!")
                
                # Download chat
                try:
                    if not utilities_extra.terminated_requested and not os.path.exists(file_path_chat):
                        print(f"\t- download chat: {video['id']}")
                        download_chat(config, video['id'], file_path_chat, is_clip=True, verbose=args.verbose)
                except Exception as e:
                    print(f"\t- not able to download any chat... {e}")
        
        except Exception as e:
            print("twitch api failure.... stopping querying....")
            print(e)
            exit(-1)
    
    # Load clips from disk
    arr_clips = []
    # Dates already validated at the top
    for root, dirs, files in os.walk(path_data):
        for file in files:
            if not file.endswith('_info.json'):
                continue
            with open(os.path.join(root, file)) as f:
                video_info = json.load(f)
            
            datetime_created = datetime.datetime.strptime(video_info['created_at'], "%Y-%m-%d %H:%M:%SZ")
            export_folder = f"{datetime_created.year:02d}-{datetime_created.month:02d}/"
            file_path = os.path.join(path_data, export_folder, f"{video_info['id']}.mp4")
            
            if not os.path.exists(file_path):
                print(f"WARNING: {video_info['id']} is missing its main video file!!!!")
                continue
            
            filesize = os.path.getsize(file_path)
            if filesize < 1:
                print(f"WARNING: {video_info['id']} clip is invalid!!!!")
                continue
            
            if datetime_created < datetime_start or datetime_created > datetime_end:
                continue
            
            if video_info["id"] in clips_to_ignore:
                print(f"WARNING: {video_info['id']} clip has been IGNORED!!!!")
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
    print(f"sorting {len(arr_clips)} clips by viewcount")
    arr_clips.sort(key=lambda x: x['view_count'])
    start_id = max(0, len(arr_clips) - args.max_clips)
    arr_clips = arr_clips[start_id:]
    print(f"sorting {len(arr_clips)} clips by date")
    arr_clips.sort(key=lambda x: x['created_at'])
    
    if len(arr_clips) < args.max_clips:
        print("ERROR: unable to find enough requested clips....")
        print("ERROR: either decrease the min view count or number of requested clips..")
        exit(-1)
    print("")
    
    # Render individual clips
    for video in arr_clips:
        print(f"clip has {video['view_count']} views (clipped at {video['created_at']})")
        print(f"\t- {video['url']}")
        
        datetime_created = datetime.datetime.strptime(video['created_at'], "%Y-%m-%d %H:%M:%SZ")
        export_folder = f"{datetime_created.year:02d}-{datetime_created.month:02d}/"
        
        file_path_chat = os.path.join(path_data, export_folder, f"{video['id']}_chat.json")
        file_path_chat_mp4 = os.path.join(path_data, export_folder, f"{video['id']}_chat.mp4")
        
        if not utilities_extra.terminated_requested and os.path.exists(file_path_chat) and not os.path.exists(file_path_chat_mp4):
            print(f"\t- rendering chat: {export_folder}{video['id']}_chat.mp4")
            render_chat(config, file_path_chat, file_path_chat_mp4, verbose=args.verbose)
        
        file_path = os.path.join(path_data, export_folder, f"{video['id']}.mp4")
        file_path_composite = os.path.join(path_data, export_folder, f"{video['id']}_rendered.mp4")
        
        if not utilities_extra.terminated_requested and not os.path.exists(file_path_composite):
            print(f"\t- rendering composite: {export_folder}{video['id']}_rendered.mp4")
            os.makedirs(os.path.dirname(file_path_composite), exist_ok=True)
            
            t0 = time.time()
            render_clip_with_title(config, file_path, file_path_chat_mp4 if os.path.exists(file_path_chat_mp4) else None,
                                  file_path_composite, video["title"])
            
            t1 = time.time()
            dur_render = t1 - t0 + 1e-6
            print(f"\t- time to render: {dur_render:.1f}")
            print()
    
    # Combine all clips
    text_file_temp_videos = os.path.join(path_render, "CLIPS", f"{args.channel}_{args.date_start[:10]}_{args.date_end[:10]}.txt")
    file_path_composite = os.path.join(path_render, "CLIPS", f"{args.channel}_{args.date_start[:10]}_{args.date_end[:10]}.mp4")
    
    print("starting to render the composite video (will take a while)...")
    if not utilities_extra.terminated_requested and not os.path.exists(file_path_composite):
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
                    print(f"\t- WARNING: skipping {os.path.abspath(tmp_output_file)}")
        
        # Combine videos
        t0_big = time.time()
        print("\t- combining all videos into a single segment!")
        video_paths = []
        with open(text_file_temp_videos) as f:
            for line in f:
                if line.startswith("file "):
                    video_paths.append(line.split("'")[1])
        combine_videos(config, video_paths, file_path_composite)
        os.remove(text_file_temp_videos)
        
        t1_big = time.time()
        dur_render = t1_big - t0_big + 1e-6
        print(f"\t- time to render: {dur_render:.1f}")
    
    # Create description file
    file_path_desc = os.path.join(path_render, "CLIPS", f"{args.channel}_{args.date_start[:10]}_{args.date_end[:10]}_desc.txt")
    if not utilities_extra.terminated_requested and not os.path.exists(file_path_desc):
        print(f"\t- writting info: {file_path_desc}")
        tmp = f"Top {args.max_clips} Between {args.date_start[:10]} to {args.date_end[:10]}\n\n"
        
        num_second_into_video = 0
        for video in arr_clips:
            datetime_created = datetime.datetime.strptime(video['created_at'], "%Y-%m-%d %H:%M:%SZ")
            export_folder = f"{datetime_created.year:02d}-{datetime_created.month:02d}/"
            
            file_path_info = os.path.join(path_data, export_folder, f"{video['id']}_info.json")
            tmp_output_file = os.path.join(path_data, export_folder, f"{video['id']}_rendered.mp4")
            if not os.path.exists(tmp_output_file):
                print(f"\t- WARNING: skipping {tmp_output_file}")
                continue
            
            with open(file_path_info) as f:
                video_info = json.load(f)
            
            m, s = divmod(int(num_second_into_video), 60)
            h, m = divmod(m, 60)
            timestamp = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
            
            title_clean = re.sub(r"[^a-zA-Z0-9'.?: ]", '', video_info["title"])
            title_clean = title_clean.replace("\\\\", "\\\\\\\\").replace("'", "\u2019")
            tmp += f"{timestamp} \"{title_clean}\" clipped by {video_info['creator_name']}\n"
            
            print("=============================")
            print(f"  {timestamp} - {video_info['id']}")
            print(f"  {title_clean}")
            
            vid_length = get_video_duration(config, tmp_output_file)
            if vid_length:
                num_second_into_video += vid_length
        
        with open(file_path_desc, "w", encoding="utf-8") as f:
            f.write(tmp)
    
    # Remove rendered files if requested
    if not utilities_extra.terminated_requested and not args.no_remove and remove_rendered:
        for video in arr_clips:
            datetime_created = datetime.datetime.strptime(video['created_at'], "%Y-%m-%d %H:%M:%SZ")
            export_folder = f"{datetime_created.year:02d}-{datetime_created.month:02d}/"
            tmp_output_file = os.path.join(path_data, export_folder, f"{video['id']}_rendered.mp4")
            if os.path.exists(tmp_output_file):
                os.remove(tmp_output_file)


if __name__ == "__main__":
    main()
