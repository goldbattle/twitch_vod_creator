# !/usr/bin/env python3

"""
Video download operations module.
Handles downloading videos and clips from Twitch.
"""

import logging
import os
import json
import time
import subprocess
import shutil
from . import utilities_extra
from . import utilities_twitch_api as twitch_api
from . import utilities_chat as chat

logger = logging.getLogger(__name__)


def download_vod(config, vod_id, output_path, quality="1080p60", verbose=False):
    """Download a VOD video."""
    if os.path.exists(output_path):
        return True
    
    if utilities_extra.terminated_requested:
        return False
    
    temp_output = os.path.join(config.get('temp_path', '/tmp'), os.path.basename(output_path))
    
    cmd = (
        f'{config["twitch_cli"]} videodownload'
        f' --id {vod_id}'
        f' --ffmpeg-path "{config["ffmpeg"]}"'
        f' --temp-path "{config.get("temp_path", "/tmp")}"'
        f' --quality {quality}'
        f' --collision Overwrite --banner false'
        f' -o {temp_output}'
    )
    
    stdout = None if verbose else subprocess.DEVNULL
    stderr = None if verbose else subprocess.DEVNULL
    
    process = subprocess.Popen(cmd, shell=True, stdout=stdout, stderr=stderr)
    return_code = process.wait()
    
    if return_code != 0:
        logger.error(f"Error: TwitchDownloaderCLI returned exit code {return_code}")
        return False
    
    if os.path.exists(temp_output):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.move(temp_output, output_path)
        return True
    return False


def download_clip(config, clip_id, output_path, verbose=False):
    """Download a clip video."""
    if os.path.exists(output_path):
        return True
    
    if utilities_extra.terminated_requested:
        return False
    
    temp_output = os.path.join(config.get('temp_path', '/tmp'), os.path.basename(output_path))
    
    cmd = (
        f'{config["twitch_cli"]} clipdownload'
        f' --id {clip_id}'
        f' --ffmpeg-path "{config["ffmpeg"]}"'
        f' --collision Overwrite --banner false'
        f' -o {temp_output}'
    )
    
    stdout = None if verbose else subprocess.DEVNULL
    stderr = None if verbose else subprocess.DEVNULL
    
    process = subprocess.Popen(cmd, shell=True, stdout=stdout, stderr=stderr)
    return_code = process.wait()
    
    if return_code != 0:
        logger.error(f"Error: TwitchDownloaderCLI returned exit code {return_code}")
        return False
    
    if os.path.exists(temp_output):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.move(temp_output, output_path)
        return True
    return False


def download_complete_clip(config, video, path_data_folder, game_cache, logger, verbose=False):
    """
    Download a complete clip: info, video, and chat.
    
    Args:
        config: Configuration dictionary
        video: Video/clip object from Twitch API (must have 'id', 'view_count', 'created_at', 'url')
        path_data_folder: Directory where clip files should be saved
        game_cache: Dictionary cache for game information (will be updated)
        logger: Logger instance for logging
        verbose: Whether to show verbose output
        
    Returns:
        Dictionary with download results:
        - info_saved: bool - whether info was saved/updated
        - video_downloaded: bool - whether video was downloaded
        - chat_downloaded: bool - whether chat was downloaded
        - video_path: str - path to video file
        - chat_path: str - path to chat JSON file
        - info_path: str - path to info JSON file
    """
    os.makedirs(path_data_folder, exist_ok=True)
    
    file_path_info = os.path.join(path_data_folder, f"{video['id']}_info.json")
    file_path = os.path.join(path_data_folder, f"{video['id']}.mp4")
    file_path_chat = os.path.join(path_data_folder, f"{video['id']}_chat.json")
    
    result = {
        'info_saved': False,
        'video_downloaded': False,
        'chat_downloaded': False,
        'video_path': file_path,
        'chat_path': file_path_chat,
        'info_path': file_path_info,
    }
    
    # Save/update clip info
    if not utilities_extra.terminated_requested:
        if not os.path.exists(file_path_info):
            clip_data = twitch_api.create_clip_data(
                config['auth']["client_id"], 
                config['auth']["client_secret"], 
                video, 
                game_cache
            )
            with open(file_path_info, 'w', encoding="utf-8") as f:
                json.dump(clip_data, f, indent=4)
            logger.info(f"  - saved clip info: {video['id']}")
            logger.debug(f"  - {file_path_info}")
            result['info_saved'] = True
        else:
            with open(file_path_info) as f:
                video_info = json.load(f)
            video_info["view_count"] = video['view_count']
            if video_info.get("video_offset") == -1:
                clip_data = twitch_api.get_clip_data(video['id'])
                if clip_data['offset'] != -1:
                    video_info["video_offset"] = clip_data['offset']
                    video_info["duration"] = clip_data['duration']
            with open(file_path_info, 'w', encoding="utf-8") as f:
                json.dump(video_info, f, indent=4)
            logger.info("  - updated clip info")
            logger.debug(f"  - {file_path_info}")
            result['info_saved'] = True
    
    # Download clip
    if not utilities_extra.terminated_requested and not os.path.exists(file_path):
        logger.info("  - starting download clip...")
        logger.debug(f"  - {file_path}")
        t0 = time.time()
        if download_clip(config, video['id'], file_path, verbose=verbose):
            dur_min = (time.time() - t0) / 60.0
            logger.info(f"  - download clip took {dur_min:.2f} min")
            result['video_downloaded'] = True
        else:
            logger.error("  - VIDEO DOWNLOAD FAILED!!!!")
    
    # Download chat
    try:
        if not utilities_extra.terminated_requested and not os.path.exists(file_path_chat):
            logger.info("  - starting download chat...")
            logger.debug(f"  - {file_path_chat}")
            t0 = time.time()
            if chat.download_chat(config, video['id'], file_path_chat, is_clip=True, verbose=verbose):
                dur_min = (time.time() - t0) / 60.0
                logger.info(f"  - download chat took {dur_min:.2f} min")
                result['chat_downloaded'] = True
    except Exception as e:
        logger.warning(f"  - not able to download any chat... {e}")
    
    return result

