# !/usr/bin/env python3

import sys
import os
import argparse
import yaml  # pip install PyYAML
# sudo pip install --upgrade google-api-python-client oauth2client progressbar2
# pip install youtube-video-upload
from youtube_video_upload import upload_from_options, upload_video

import time
import logging
import coloredlogs
import glob
from typing import Dict, Any, List

# Add parent directory to path so we can import utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utilities import extra, config, file

# ================================================================

def find_segments_files(directory: str) -> List[str]:
    """Recursively find all *_segments.yaml files in the given directory."""
    pattern = os.path.join(directory, '**', '*_segments.yaml')
    files = glob.glob(pattern, recursive=True)
    return sorted(files)


def load_all_segments(segments_files: List[str], logger: logging.Logger) -> List[Dict[str, Any]]:
    """Load all segments from multiple YAML files and combine them into a single list."""
    all_segments = []
    for file_path in segments_files:
        try:
            with open(file_path) as f:
                data = yaml.load(f, Loader=yaml.FullLoader)
                if data:
                    all_segments.extend(data)
                    logger.debug(f"Loaded {len(data)} segments from {file_path}")
        except Exception as e:
            logger.error(f"Error loading segments from {file_path}: {e}")
    return all_segments


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Upload video segments to YouTube')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file-segments', help='YAML file with all video segments (relative to config directory)')
    group.add_argument('--dir-segments', help='Directory to recursively scan for *_segments.yaml files')
    parser.add_argument('--history-file', required=True, help='Full path to history YAML file')
    parser.add_argument('--file-config', required=True, help='Full path to config YAML file')
    parser.add_argument('--display-missing', action='store_true', help='Display missing video files')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from operations')
    return parser.parse_args()


def run_task(args: argparse.Namespace) -> None:
    """Upload video segments to YouTube based on provided arguments."""
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=log_level, fmt='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    
    config_base = config.load_config()
    path_base = config_base['base_path']
    
    history_file = args.history_file
    config_file = args.file_config
    display_missing = args.display_missing
    
    # load the yaml from file
    with open(config_file) as f:
        yaml_config = yaml.load(f, Loader=yaml.FullLoader)
    logger.debug(f"loaded config file: {config_file}")
    
    # paths of the cli and data
    path_root = config_base['data_root']
    path_render = config_base['render_root']
    
    # youtube credential location
    path_yt_creds = os.path.join(os.path.dirname(path_base), "profiles", yaml_config["yt_creds"])
    path_yt_secrets = os.path.join(os.path.dirname(path_base), "profiles", yaml_config["yt_secrets"])
    
    # setup control+c handler
    extra.setup_signal_handle()
    
    # Load segments from either a single file or directory scan
    if args.file_segments:
        # Single file mode
        video_file = os.path.join(path_base, "config", args.file_segments)
        with open(video_file) as f:
            data = yaml.load(f, Loader=yaml.FullLoader)
        logger.info(f"loaded {len(data)} videos to upload from {args.file_segments}")
    else:
        # Directory scan mode
        segments_dir = args.dir_segments
        if not os.path.isabs(segments_dir):
            segments_dir = os.path.join(path_base, segments_dir)
        
        # Find and load all segments files
        segments_files = find_segments_files(segments_dir)
        if not segments_files:
            logger.warning(f"No *_segments.yaml files found in {segments_dir}")
            return
        
        logger.info(f"Found {len(segments_files)} segments file(s):")
        for file_path in segments_files:
            logger.info(f"  - {file_path}")
        
        # Load all segments from all files
        data = load_all_segments(segments_files, logger)
        logger.info(f"Loaded {len(data)} total segments to upload")

    # load our historical uploads file
    hist_uploads: Dict[str, Any] = {}
    if os.path.exists(history_file):
        with open(history_file) as f:
            hist_uploads = yaml.load(f, Loader=yaml.FullLoader)

    # loop through each video and render each segment
    # we will want to first ensure chat is rendered
    # from there we will render the full segmented video
    for suffix in ["", "_muted"]:
        for video in data:

            # check if we should download any more
            if extra.terminated_requested:
                logger.info('terminate requested, not downloading any more..')
                break

            # nice debug print
            logger.info(f"processing {video['video']} - '{video['title']}'")
            logger.info(f"  - Suffix: \"{suffix}\"")

            # check if the files are there
            clean_video_title = file.get_valid_filename(video["title"])
            file_path_composite = os.path.join(path_render, video["video"] + "_" + clean_video_title + suffix + ".mp4")
            file_path_desc = os.path.join(path_render, video["video"] + "_" + clean_video_title + suffix + "_desc.txt")
            if not os.path.exists(file_path_composite) or not os.path.exists(file_path_desc):
                if display_missing:
                    logger.warning("video has not been rendered yet...")
                    logger.warning(f"{video['video']}_{clean_video_title}.mp4")
                    logger.warning(f"{video['video']}_{clean_video_title}_desc.txt")
                continue

            # unique video id
            video_id = video["video"].replace(' ', '_') + "_" + video["title"].lower().replace(' ', '_') + suffix
            if video_id in hist_uploads:
                logger.debug(f"skipping video, has already been uploaded: {hist_uploads[video_id]['link']}")
                continue

            # load the description file
            with open(file_path_desc, "r") as myfile:
                video_description = ''.join(myfile.readlines()[2:])

            # combine our tags
            tags: List[str] = yaml_config["tags"]
            if "tags" in video:
                tags.append(video["tags"])

            # upload options
            options = {
                'local_server': True,
                'videos': [
                    {
                        'title': video['title'],
                        'file': file_path_composite,
                        'description': video_description,
                        'category': 'Entertainment',
                        'privacy': 'private',
                        'tags': tags
                    }
                ],
                'secrets_path': path_yt_secrets,
                'credentials_path': path_yt_creds
            }

            # now upload the video!
            logger.info("starting video upload...")
            try:
                t0 = time.time()
                upload_video.MAX_RETRIES = 2
                new_options = upload_from_options(options)
                t1 = time.time()
                logger.info("done performing video upload!")
                logger.info(f"link: {new_options}")
                logger.debug(f"upload time: {t1 - t0 + 1e-6}")
                entry = {
                    'title': video["title"],
                    'file': file_path_composite,
                    'uploaded_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'link': new_options
                }
                
                # finally write the updated history file with locking
                extra.update_history_file(history_file, video_id, entry, logger)
                # Update in-memory copy as well (merge with existing if any)
                if video_id not in hist_uploads:
                    hist_uploads[video_id] = {}
                hist_uploads[video_id].update(entry)

            except Exception as e:
                logger.error("unable to complete the upload!")
                logger.error(f"{e}")
                break


def main() -> None:
    """Main entry point."""
    args = parse_args()
    run_task(args)


if __name__ == "__main__":
    main()
