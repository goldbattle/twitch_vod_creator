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

    # Windows path escaping for ffmpeg
    font_path = os.path.join(base_path, "thirdparty", "bebas_neue", "BebasNeue-Regular.ttf")
    font_path_escaped = font_path.replace("\\", "/").replace(":", "\\\\:")
    
    return {
        'base_path': base_path,
        'vosk_model': os.path.join(base_path, "thirdparty", "vosk-model-small-en-us-0.15"),
        'font': font_path_escaped,
        'auth': auth,
        'twitch_cli': os.path.join(base_path, "thirdparty", "Twitch_Downloader_1.56.2", "TwitchDownloaderCLI"),

        # == FOR SERVER ==
        'ffmpeg': os.path.join(base_path, "thirdparty", "ffmpeg-4.3.1-amd64-static", "ffmpeg"),
        'ffprobe': os.path.join(base_path, "thirdparty", "ffmpeg-4.3.1-amd64-static", "ffprobe"),

        # == FFMPEG ON MY ARCH MACHINE ==
        # 'ffmpeg': os.path.join(base_path, "thirdparty", "ffmpeg-arch", "ffmpeg"),
        # 'ffprobe': os.path.join(base_path, "thirdparty", "ffmpeg-arch", "ffprobe"),
        
        # == FFMPEG WITH SUPER RESOLUTION ==
        # 'ffmpeg': os.path.join(base_path, "thirdparty", "ffmpeg-sr", "bin", "ffmpeg.wrapper"),
        # 'ffprobe': os.path.join(base_path, "thirdparty", "ffmpeg-sr", "bin", "ffprobe.wrapper"),
        # 'superres_model': os.path.join(base_path, "thirdparty", "ffmpeg-sr", "sr", "espcn.pb"),
    }


def get_temp_path(name="default"):
    """Get temporary directory path for a specific operation."""
    return os.path.join("/tmp", f"tvc_{name}")

