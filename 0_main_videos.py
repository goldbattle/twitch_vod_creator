# !/usr/bin/env python3

import argparse
import json
import os
import time
import utilities_extra
from utilities_config import load_config, get_temp_path
from utilities_twitch_api import get_users_by_login, is_user_live, get_videos, create_video_data, get_vod_moments
from utilities_video_download import download_vod
from utilities_chat import download_chat, render_chat
from utilities_audio_transcription import transcribe_video
from utilities_file import get_date_folder, ensure_directory

# parameters
channels = [
    'sodapoppin'#, 'skippypoppin', 'nmplol',
    # 'moonmoon', 'clintstevens', 'sevadus',
    # 'jerma985', 'heydoubleu', 'vei', 'squeex',
    # 'goldbattle', 'j_blow'
    # 'mindcrack'
]
max_videos = 1
render_chat_flags = [
    True#, False, False,
    # False, True, False,
    # False, False, False, False,
    # False, False,
    # False
]
render_webvtt = [
    True#, True, True,
    # False, True, False,
    # False, False, True, False,
    # False, False,
    # False
]

# ================================================================

def main():
    parser = argparse.ArgumentParser(description='Download and process Twitch VODs')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from download operations')
    parser.add_argument('--temp-dir', default=get_temp_path("main_videos"), help='Temporary directory for downloads (default: /tmp/tvc_main_videos)')
    args = parser.parse_args()
    
    config = load_config()
    config['temp_path'] = args.temp_dir
    auth = config['auth']
    path_root = config['data_root']
    
    utilities_extra.setup_signal_handle()
    
    if len(channels) != len(render_chat_flags) or len(channels) != len(render_webvtt):
        print('number of channels and render settings do not match!!')
        exit(-1)
    
    # Get users
    users_tmp = get_users_by_login(auth["client_id"], auth["client_secret"], channels)
    users = []
    render_chat_flags_filtered = []
    render_webvtt_filtered = []
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
            print(f"streamer {channel} wasn't found, are they banned???")
    
    # Process each user
    for idx, user in enumerate(users):
        if utilities_extra.terminated_requested:
            print('terminate requested, not looking at any more users...')
            break
        
        path_data = os.path.join(path_root, user["login"].lower())
        ensure_directory(path_data)
        ensure_directory(config['temp_path'])
        
        # Check if live
        stream_is_live = is_user_live(auth["client_id"], auth["client_secret"], user["id"])
        
        # Get videos
        print(f"getting videos for -> {user['login'].lower()} (id {user['id']})")
        vid_iter = get_videos(auth["client_id"], auth["client_secret"], user_id=user["id"], page_size=100)
        arr_archive = []
        arr_highlight = []
        arr_upload = []
        ct_added = [0, 0, 0]
        seen_first_video = False
        
        for video in vid_iter:
            if not seen_first_video and stream_is_live:
                print(f"skipping video {video['id']} since stream is live...")
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
        
        print(f"\t- found {len(arr_archive)} archives")
        print(f"\t- found {len(arr_highlight)} highlights")
        print(f"\t- found {len(arr_upload)} uploads")
        
        # Process each archive video
        for video in arr_archive:
            if utilities_extra.terminated_requested:
                print('terminate requested, not downloading any more..')
                break
            
            t0_start = time.time()
            video_data = create_video_data(auth["client_id"], auth["client_secret"], video['helix'])
            
            # Get file paths
            export_folder = get_date_folder(video_data['recorded_at'])
            path_data_folder = os.path.join(path_data, export_folder)
            ensure_directory(path_data_folder)
            
            file_path_info = os.path.join(path_data_folder, f"{video['helix']['id']}_info.json")
            file_path = os.path.join(path_data_folder, f"{video['helix']['id']}.mp4")
            file_path_chat = os.path.join(path_data_folder, f"{video['helix']['id']}_chat.json")
            file_path_chat_mp4 = os.path.join(path_data_folder, f"{video['helix']['id']}_chat.mp4")
            file_path_webvtt = os.path.join(path_data_folder, f"{video['helix']['id']}.vtt")
            
            # Save/update video info
            print(f"\t- saving video info: {file_path_info}")
            if not utilities_extra.terminated_requested:
                if not os.path.exists(file_path_info):
                    with open(file_path_info, 'w', encoding="utf-8") as f:
                        json.dump(video_data, f, indent=4)
                else:
                    print(f"\t- updating video info: {file_path_info}")
                    with open(file_path_info) as f:
                        video_info = json.load(f)
                    if len(video_info.get("moments", [])) == 0:
                        moments = get_vod_moments(video['helix']['id'])
                        if len(moments) != 0:
                            video_info["moments"] = moments
                    with open(file_path_info, 'w', encoding="utf-8") as f:
                        json.dump(video_info, f, indent=4)
            
            # Download video
            print(f"\t- download video: {file_path}")
            if not utilities_extra.terminated_requested and not os.path.exists(file_path):
                t0 = time.time()
                success = download_vod(config, video['helix']['id'], file_path, verbose=args.verbose)
                if success:
                    print(f"\t- done in {time.time() - t0:.1f} seconds")
                else:
                    print(f"\t- ERROR: Video download failed!")
            
            # Download chat
            print(f"\t- download chat: {file_path_chat}")
            if not utilities_extra.terminated_requested and not os.path.exists(file_path_chat):
                t0 = time.time()
                download_chat(config, video['helix']['id'], file_path_chat, is_clip=False, verbose=args.verbose)
                print(f"\t- done in {time.time() - t0:.1f} seconds")
            
            # Transcribe audio
            if render_webvtt_filtered[idx] and not utilities_extra.terminated_requested:
                if os.path.exists(file_path) and not os.path.exists(file_path_webvtt):
                    print(f"\t- transcribing: {file_path_webvtt}")
                    t0 = time.time()
                    transcribe_video(config, file_path, file_path_webvtt)
                    print(f"\t- done in {time.time() - t0:.1f} seconds")
            
            # Render chat
            if render_chat_flags_filtered[idx] and not utilities_extra.terminated_requested:
                if os.path.exists(file_path_chat) and not os.path.exists(file_path_chat_mp4):
                    print(f"\t- rendering chat: {file_path_chat_mp4}")
                    t0 = time.time()
                    render_chat(config, file_path_chat, file_path_chat_mp4, verbose=args.verbose)
                    print(f"\t- done in {time.time() - t0:.1f} seconds")
                    
                    # Send pushover notification
                    text = (f"{video['helix']['user_name']} vod {video['helix']['id']} "
                           f"ready to edit ({int((time.time() - t0_start)/60.0)} min to prepare)")
                    utilities_extra.send_pushover_message(auth, text)


if __name__ == "__main__":
    main()
