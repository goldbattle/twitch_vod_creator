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
from typing import Dict, Any, List

# Add parent directory to path so we can import utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utilities import extra, config, file

# ================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Upload video segments to YouTube')
    parser.add_argument('--video-file', required=True, help='Video YAML file (relative to config directory)')
    parser.add_argument('--history-file', required=True, help='History YAML file (relative to config directory)')
    parser.add_argument('--config-file', required=True, help='Config YAML file (relative to config directory)')
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
    
    video_file = os.path.join(path_base, "config", args.video_file)
    history_file = os.path.join(path_base, "config", args.history_file)
    config_file = os.path.join(path_base, "config", args.config_file)
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
    
    # load the yaml from file
    with open(video_file) as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    logger.info(f"loaded {len(data)} videos to upload")

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
            logger.info(f"processing {video['video']}")
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
                hist_uploads[video_id] = {
                    'title': video["title"],
                    'file': file_path_composite,
                    'link': new_options
                }

                # finally write the updated history file
                if not os.path.exists(os.path.dirname(history_file)):
                    os.makedirs(os.path.dirname(history_file))
                with open(history_file, 'w') as yaml_file:
                    yaml.dump(hist_uploads, yaml_file)

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
