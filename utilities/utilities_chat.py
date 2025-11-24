# !/usr/bin/env python3

"""
Chat operations module.
Handles chat downloading and rendering.
"""

import os
import subprocess
import shutil
from . import utilities_extra


def download_chat(config, content_id, output_path, is_clip=False, verbose=False):
    """Download chat for a VOD or clip."""
    if os.path.exists(output_path):
        return True
    
    if utilities_extra.terminated_requested:
        return False
    
    temp_path = config.get('temp_path', '/tmp')
    temp_output = os.path.join(temp_path, os.path.basename(output_path))
    
    cmd = (
        f'{config["twitch_cli"]} chatdownload'
        f' --id {content_id}'
        f' --embed-images true --threads 6'
        f' --bttv true --ffz true --stv true'
        f' --collision Overwrite --banner false'
        f' -o {temp_output}'
    )
    
    stdout = None if verbose else subprocess.DEVNULL
    stderr = None if verbose else subprocess.DEVNULL
    
    process = subprocess.Popen(cmd, shell=True, stdout=stdout, stderr=stderr)
    return_code = process.wait()
    
    if return_code != 0:
        if verbose:
            print(f"Error: TwitchDownloaderCLI chatdownload returned exit code {return_code}")
        return False
    
    if os.path.exists(temp_output):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.move(temp_output, output_path)
        return True
    return False


def render_chat(config, chat_json_path, output_path, 
                height=926, width=274, update_rate=0.1, framerate=60,
                font_size=15, verbose=False):
    """Render chat JSON to video."""
    if os.path.exists(output_path):
        return True
    
    if utilities_extra.terminated_requested:
        return False
    
    temp_path = config.get('temp_path', '/tmp')
    temp_output = os.path.join(temp_path, os.path.basename(output_path))
    
    cmd = (
        f'{config["twitch_cli"]} chatrender'
        f' -i {chat_json_path} -o {temp_output}'
        f' --ffmpeg-path "{config["ffmpeg"]}"'
        f' -h {height} -w {width}'
        f' --update-rate {update_rate} --framerate {framerate} --font-size {font_size}'
        f' --bttv true --ffz true --stv true'
        f' --sub-messages true --badges true --sharpening true --dispersion true'
        f' --temp-path "{temp_path}"'
    )
    
    stdout = None if verbose else subprocess.DEVNULL
    stderr = None if verbose else subprocess.DEVNULL
    
    process = subprocess.Popen(cmd, shell=True, stdout=stdout, stderr=stderr)
    return_code = process.wait()
    
    if return_code != 0:
        if verbose:
            print(f"Error: TwitchDownloaderCLI chatrender returned exit code {return_code}")
        return False
    
    if os.path.exists(temp_output):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.move(temp_output, output_path)
        return True
    return False

