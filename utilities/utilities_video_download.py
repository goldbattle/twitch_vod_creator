# !/usr/bin/env python3

"""
Video download operations module.
Handles downloading videos and clips from Twitch.
"""

import os
import subprocess
import shutil
from . import utilities_extra


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
        if verbose:
            print(f"Error: TwitchDownloaderCLI returned exit code {return_code}")
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
        if verbose:
            print(f"Error: TwitchDownloaderCLI returned exit code {return_code}")
        return False
    
    if os.path.exists(temp_output):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.move(temp_output, output_path)
        return True
    return False

