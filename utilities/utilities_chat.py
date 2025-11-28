# !/usr/bin/env python3

"""
Chat operations module.
Handles chat downloading and rendering.
"""

import logging
import os
import subprocess
import shutil
import hashlib
from . import utilities_extra

logger = logging.getLogger(__name__)


def download_chat(config, content_id, output_path, is_clip=False, verbose=False):
    """Download chat for a VOD or clip."""
    if os.path.exists(output_path):
        return True
    
    if utilities_extra.terminated_requested:
        return False
    
    temp_path = config.get('temp_path', '/tmp')
    # Use hash of full output path to ensure unique temp files for parallel processing
    output_hash = hashlib.md5(output_path.encode()).hexdigest()[:12]
    temp_basename = f"{output_hash}_{os.path.basename(output_path)}"
    temp_output = os.path.join(temp_path, temp_basename)
    
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
        logger.error(f"Error: TwitchDownloaderCLI chatdownload returned exit code {return_code}")
        return False
    
    if os.path.exists(temp_output):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.move(temp_output, output_path)
        return True
    return False


def render_chat(config, chat_json_path, output_path, 
                height=926, width=274, update_rate=0.1, framerate=60,
                font_size=15, verbose=False, is_4k=False):
    """Render chat JSON to video."""
    if os.path.exists(output_path):
        return True
    
    if utilities_extra.terminated_requested:
        return False
    
    # For 4K, scale chat proportionally: 274x926 -> 548x2160
    if is_4k:
        height = 2160
        width = 548
        # Scale font size proportionally: 15 * (2160/926) ≈ 35
        font_size = int(font_size * (2160 / 926))
    
    temp_path = config.get('temp_path', '/tmp')
    # Use hash of full output path to ensure unique temp files for parallel processing
    output_hash = hashlib.md5(output_path.encode()).hexdigest()[:12]
    temp_basename = f"{output_hash}_{os.path.basename(output_path)}"
    temp_output = os.path.join(temp_path, temp_basename)
    
    cmd = (
        f'{config["twitch_cli"]} chatrender'
        f' -i {chat_json_path} -o {temp_output}'
        f' --ffmpeg-path "{config["ffmpeg"]}"'
        f' -h {height} -w {width}'
        f' --update-rate {update_rate} --framerate {framerate} --font-size {font_size}'
        f' --bttv true --ffz true --stv true'
        f' --sub-messages true --badges true --sharpening true --dispersion true'
        f' --collision Overwrite --banner false'
        f' --temp-path "{temp_path}"'
    )
    
    stdout = None if verbose else subprocess.DEVNULL
    stderr = None if verbose else subprocess.DEVNULL
    
    process = subprocess.Popen(cmd, shell=True, stdout=stdout, stderr=stderr)
    return_code = process.wait()
    
    if return_code != 0:
        logger.error(f"Error: TwitchDownloaderCLI chatrender returned exit code {return_code}")
        return False
    
    if os.path.exists(temp_output):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.move(temp_output, output_path)
        return True
    return False

