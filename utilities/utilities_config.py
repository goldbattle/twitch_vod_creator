# !/usr/bin/env python3

"""
Configuration and path loader module.
Returns a configuration dictionary with all paths and auth info.
"""

import os
import yaml


def load_config(base_path=None):
    """
    Load configuration and return as dictionary.
    
    Args:
        base_path: Base path of the project. If None, uses the directory of this file.
        
    Returns:
        Dictionary with all configuration paths and auth info
    """
    if base_path is None:
        # Get project root (parent of utilities directory)
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    auth_config = os.path.join(base_path, "config", "auth.yaml")
    with open(auth_config) as f:
        auth = yaml.load(f, Loader=yaml.FullLoader)
    
    font_path = os.path.join(base_path, "thirdparty", "bebas_neue", "BebasNeue-Regular.ttf")
    # Windows path escaping for ffmpeg
    font_path_escaped = font_path.replace("\\", "/").replace(":", "\\\\:")
    
    return {
        'base_path': base_path,
        'auth': auth,
        'twitch_cli': os.path.join(base_path, "thirdparty", "Twitch_Downloader_1.56.2", "TwitchDownloaderCLI"),
        'ffmpeg': os.path.join(base_path, "thirdparty", "ffmpeg-4.3.1-amd64-static", "ffmpeg"),
        'ffprobe': os.path.join(base_path, "thirdparty", "ffmpeg-4.3.1-amd64-static", "ffprobe"),
        'vosk_model': os.path.join(base_path, "thirdparty", "vosk-model-small-en-us-0.15"),
        'font': font_path_escaped,
        'data_root': os.path.join(os.path.dirname(base_path), "data"),
        'clips_root': os.path.join(os.path.dirname(base_path), "data_clips_new"),
        'render_root': os.path.join(os.path.dirname(base_path), "data_rendered"),
    }


def get_temp_path(name="default"):
    """Get temporary directory path for a specific operation."""
    return os.path.join("/tmp", f"tvc_{name}")

