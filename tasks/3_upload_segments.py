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
    parser.add_argument('--file-config', required=True, help='Config YAML file (relative to config directory)')
    parser.add_argument('--file-history', required=True, help='History YAML file (relative to config directory)')
    parser.add_argument('--display-missing', action='store_true', help='Display missing video files')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output from operations')
    
    # Get base_path for default values
    config_base = config.load_config()
    default_data_root = os.path.dirname(config_base['base_path'])
    
    # Directory and segment file arguments
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file-segments', help='YAML file with all video segments (relative to config directory)')
    group.add_argument('--dir-segments', help='Directory to recursively scan for *_segments.yaml files')
    parser.add_argument('--dir-data-root', default=default_data_root, help=f'Root directory containing data and data_rendered folders (should contain folders like "data" and "data_rendered") (default: {default_data_root})')
    return parser.parse_args()


def run_task(args: argparse.Namespace) -> None:
    """Upload video segments to YouTube based on provided arguments."""
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=log_level, fmt='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    
    config_base = config.load_config()
    path_base = config_base['base_path']
    
    config_file_path = os.path.join(config_base['base_path'], args.file_config)
    display_missing = args.display_missing
    
    # load the yaml from file
    with open(config_file_path) as f:
        yaml_config = yaml.load(f, Loader=yaml.FullLoader)
    logger.debug(f"loaded config file: {config_file_path}")
    
    # Load history file
    history_file = os.path.join(config_base['base_path'], args.file_history)
    logger.debug(f"history file: {history_file}")
    
    # Setup paths - dir_data_root is the parent directory, YAMLs include data/ or data_live/ prefix
    path_root = args.dir_data_root
    path_render = os.path.join(args.dir_data_root, "data_rendered")
    
    # youtube credential location
    path_yt_creds = os.path.join(path_root, "profiles", yaml_config["yt_creds"])
    path_yt_secrets = os.path.join(path_root, "profiles", yaml_config["yt_secrets"])
    
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
        
        logger.info(f"Found {len(segments_files)} segments yaml file(s)")
        for file_path in segments_files:
            logger.debug(f"  - {file_path}")
        
        # Load all segments from all files
        data = load_all_segments(segments_files, logger)
        logger.info(f"Loaded {len(data)} total segments to upload")

    # load our historical uploads file
    hist_uploads: Dict[str, Any] = {}
    if os.path.exists(history_file):
        with open(history_file) as f:
            hist_uploads = yaml.load(f, Loader=yaml.FullLoader)
        logger.debug(f"loaded history file: {history_file}")
    else:
        logger.debug(f"history file does not exist, will create: {history_file}")

    # loop through each video and render each segment
    # we will want to first ensure chat is rendered
    # from there we will render the full segmented video
    # For _4k, use the base description file (no suffix), otherwise use suffix
    for suffix, suffix_desc in zip(["", "_muted", "_4k"], ["", "_muted", ""]):
        if extra.terminated_requested:
            logger.info('terminate requested, not uploading any more..')
            break
        
        for video in data:

            # check if we should download any more
            if extra.terminated_requested:
                logger.info('terminate requested, not uploading any more..')
                break

            # check if the files are there
            clean_video_title = file.get_valid_filename(video["title"])
            file_path_composite = os.path.join(path_render, video["video"] + "_" + clean_video_title + suffix + ".mp4")
            file_path_desc = os.path.join(path_render, video["video"] + "_" + clean_video_title + suffix_desc + "_desc.txt")
            if not os.path.exists(file_path_composite) or not os.path.exists(file_path_desc):
                if display_missing:
                    logger.warning(f"processing {video['video']} - '{video['title']}'")
                    logger.warning(f"  - suffix: \"{suffix}\"")
                    logger.warning("   - video has not been rendered yet...")
                    logger.warning(f"  - {video['video']}_{clean_video_title}{suffix}.mp4")
                    logger.warning(f"  - {video['video']}_{clean_video_title}{suffix_desc}_desc.txt")
                continue

            # nice print (only print when we're actually processing)
            logger.info(f"processing {video['video']} - '{video['title']}'")
            logger.info(f"  - suffix: \"{suffix}\"")

            # unique video id
            video_id = video["video"].replace(' ', '_') + "_" + video["title"].lower().replace(' ', '_') + suffix
            if video_id in hist_uploads:
                logger.info(f"  - skipping video, has already been uploaded: {hist_uploads[video_id]['link']}")
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
            logger.info("  - starting video upload...")
            try:
                t0 = time.time()
                upload_video.MAX_RETRIES = 2
                new_options = upload_from_options(options)
                t1 = time.time()
                
                # Check if upload was successful (returns a valid link/result)
                if new_options is None:
                    logger.error("  - upload failed: upload_from_options returned None")
                    continue
                
                logger.info(f"  - upload took {t1 - t0 + 1e-6:.2f} seconds!")
                logger.info(f"  - link: {new_options}")
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

            except KeyboardInterrupt:
                logger.info('terminate requested (KeyboardInterrupt), stopping uploads...')
                extra.terminated_requested = True
                break
            except Exception as e:
                if extra.terminated_requested:
                    logger.info('terminate requested, stopping uploads...')
                    break
                logger.error("  - unable to complete the upload!")
                logger.error(f"  - {e}")
                break


def main() -> None:
    """Main entry point."""
    args = parse_args()
    run_task(args)


if __name__ == "__main__":
    main()
