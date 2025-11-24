# !/usr/bin/env python3

"""
File and path utility functions.
Handles file path generation, folder creation, and date-based organization.
"""

import os
import string
from datetime import datetime


def get_date_folder(date_str):
    """
    Get date-based folder name from ISO date string.
    
    Args:
        date_str: ISO date string (e.g., '2021-05-07T12:00:00Z')
        
    Returns:
        Folder name in format 'YYYY-MM/' or 'unknown/' if parsing fails
    """
    try:
        date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%SZ')
        return f"{date.year:02d}-{date.month:02d}/"
    except:
        try:
            # Try alternative format
            date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%SZ')
            return f"{date.year:02d}-{date.month:02d}/"
        except:
            return "unknown/"


def ensure_directory(path):
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        path: Directory path to ensure exists
    """
    if not os.path.exists(path):
        os.makedirs(path)


def get_valid_filename(filename):
    """
    Convert a string to a valid filename.
    
    Args:
        filename: Original filename string
        
    Returns:
        Valid filename with only allowed characters
    """
    valid_chars = "-_%s%s" % (string.ascii_letters, string.digits)
    filename = filename.lower().replace(' ', '_')
    return ''.join(c for c in filename if c in valid_chars)


def get_video_paths(base_path, user_name, video_id, date_str, suffix=""):
    """
    Get standard file paths for a video.
    
    Args:
        base_path: Base data directory path
        user_name: User/channel name
        video_id: Video ID
        date_str: Date string for folder organization
        suffix: Optional suffix for filename (e.g., "_chat", "_rendered")
        
    Returns:
        Dictionary with paths:
        - folder: Full folder path
        - info: Info JSON file path
        - video: Video MP4 file path
        - chat_json: Chat JSON file path
        - chat_mp4: Rendered chat MP4 file path
        - vtt: WebVTT transcription file path
    """
    folder_name = get_date_folder(date_str)
    user_folder = os.path.join(base_path, user_name.lower())
    export_folder = os.path.join(user_folder, folder_name)
    
    base_filename = str(video_id) + suffix
    
    return {
        'folder': export_folder,
        'info': os.path.join(export_folder, base_filename + "_info.json"),
        'video': os.path.join(export_folder, base_filename + ".mp4"),
        'chat_json': os.path.join(export_folder, base_filename + "_chat.json"),
        'chat_mp4': os.path.join(export_folder, base_filename + "_chat.mp4"),
        'vtt': os.path.join(export_folder, base_filename + ".vtt"),
    }


def get_clip_paths(base_path, user_name, clip_id, date_str, suffix=""):
    """
    Get standard file paths for a clip.
    
    Args:
        base_path: Base data directory path
        user_name: User/channel name
        clip_id: Clip ID
        date_str: Date string for folder organization
        suffix: Optional suffix for filename (e.g., "_rendered")
        
    Returns:
        Dictionary with paths (same structure as get_video_paths)
    """
    return get_video_paths(base_path, user_name, clip_id, date_str, suffix)

