# !/usr/bin/env python3

import argparse
import json
import os
import time
import datetime
import utilities_extra
from utilities_config import load_config, get_temp_path
from utilities_twitch_api import get_users_by_login, get_clips, create_clip_data, get_clip_data
from utilities_video_download import download_clip
from utilities_chat import download_chat
from utilities_file import get_date_folder, ensure_directory

# parameters
channels = ['xqc', 'moonmoon', 'sodapoppin', 'clintstevens', 'pokelawls', 'forsen', 'nmplol', 'jerma985', 'vei']
min_view_counts = [6000, 1000, 300, 100, 1000, 5000, 100, 500, 500]
num_days_to_query = 120

# ================================================================

def main():
    parser = argparse.ArgumentParser(description='Download Twitch clips')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from download operations')
    parser.add_argument('--temp-dir', default=get_temp_path("main_clips"), help='Temporary directory for downloads (default: /tmp/tvc_main_clips)')
    args = parser.parse_args()
    
    config = load_config()
    config['temp_path'] = args.temp_dir
    auth = config['auth']
    path_root = config['clips_root']
    
    date_start = (datetime.datetime.now() - datetime.timedelta(days=num_days_to_query)).strftime('%Y-%m-%dT%H:%M:%SZ')
    date_end = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
    print(f"Start Day: {date_start}")
    print(f"End Day: {date_end}")
    
    utilities_extra.setup_signal_handle()
    
    # Get users
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
            print(f"streamer {channel} wasn't found, are they banned???")
    min_view_counts = min_view_counts_tmp
    
    t0 = time.time()
    game_cache = {}
    count_total_clips_checked = 0
    count_total_clips_downloaded = 0
    
    # Process each user
    for idx, user in enumerate(users):
        if utilities_extra.terminated_requested:
            print('terminate requested, not looking at any more users...')
            break
        
        path_data = os.path.join(path_root, user["login"])
        ensure_directory(path_data)
        ensure_directory(config['temp_path'])
        
        try:
            print(f"getting clips for -> {user['login']} (id {user['id']})")
            vid_iter = get_clips(auth["client_id"], auth["client_secret"], user["id"], 
                                 started_at=date_start, ended_at=date_end, page_size=100)
            
            for video in vid_iter:
                if utilities_extra.terminated_requested:
                    print('terminate requested, not downloading any more..')
                    break
                
                count_total_clips_checked += 1
                
                # Stop if below view count threshold (clips are sorted by view count)
                if video['view_count'] < min_view_counts[idx]:
                    break
                
                print(f"processing {video['url']} ({video['view_count']} views)")
                
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
                        print(f"\t- saving clip info: {video['id']}_info.json")
                        clip_data = create_clip_data(auth["client_id"], auth["client_secret"], video, game_cache)
                        with open(file_path_info, 'w', encoding="utf-8") as f:
                            json.dump(clip_data, f, indent=4)
                    else:
                        print(f"\t- updating clip info: {video['view_count']} views")
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
                    if download_clip(config, video['id'], file_path, verbose=args.verbose):
                        count_total_clips_downloaded += 1
                    else:
                        print("\t- VIDEO DOWNLOAD FAILED!!!!")
                
                # Download chat
                try:
                    if not utilities_extra.terminated_requested and not os.path.exists(file_path_chat):
                        print(f"\t- download chat: {video['id']}_chat.json")
                        download_chat(config, video['id'], file_path_chat, is_clip=True, verbose=args.verbose)
                except Exception as e:
                    print(f"\t- not able to download any chat... {e}")
        
        except Exception as e:
            print(e)
    
    t1 = time.time()
    print(f"number of checked clips: {count_total_clips_checked}")
    print(f"number of downloaded clips: {count_total_clips_downloaded}")
    print(f"total execution time: {t1 - t0:.1f}")


if __name__ == "__main__":
    main()
