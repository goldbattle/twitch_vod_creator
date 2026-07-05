#!/usr/bin/env python3

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from typing import Optional

import coloredlogs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

API_URL = "https://api.github.com/repos/lay295/TwitchDownloader/releases/latest"
ASSET_PREFIX = "TwitchDownloaderCLI-"
ASSET_SUFFIX = "-Linux-x64.zip"
_DIR_RE = re.compile(r'^Twitch_Downloader_(\d+\.\d+(?:\.\d+)?)$')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Check for and install TwitchDownloaderCLI updates')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output')
    return parser.parse_args()


def _version_key(version: str) -> tuple:
    return tuple(int(x) for x in version.lstrip('v').split('.'))


def _installed_version(thirdparty: str) -> Optional[str]:
    versions = []
    for name in os.listdir(thirdparty):
        m = _DIR_RE.match(name)
        if m and os.path.isdir(os.path.join(thirdparty, name)):
            versions.append(m.group(1))
    if not versions:
        return None
    return max(versions, key=_version_key)


def _fetch_latest_version() -> str:
    with urllib.request.urlopen(API_URL, timeout=30) as resp:
        return json.load(resp)['tag_name'].lstrip('v')


def _is_up_to_date(current: Optional[str], latest: str) -> bool:
    if not current:
        return False
    return _version_key(current) >= _version_key(latest)


def run_task(args: argparse.Namespace) -> None:
    log_level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=log_level, fmt='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)

    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    thirdparty = os.path.join(base_path, "thirdparty")
    config_path = os.path.join(base_path, "utilities", "utilities_config.py")

    current = _installed_version(thirdparty)
    latest = _fetch_latest_version()

    logger.info("TwitchDownloader")
    logger.info("  installed: %s", current or 'none')
    logger.info("  latest:    %s", latest)

    if _is_up_to_date(current, latest):
        logger.info("Already up to date (%s).", current)
        return

    ans = input(f"Update to {latest}? [y/N] ").strip().lower()
    if ans not in ('y', 'yes'):
        logger.info("Skipped.")
        return

    asset = f"{ASSET_PREFIX}{latest}{ASSET_SUFFIX}"
    url = f"https://github.com/lay295/TwitchDownloader/releases/download/{latest}/{asset}"
    dest = os.path.join(thirdparty, f"Twitch_Downloader_{latest}")

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, asset)
        logger.info("Downloading %s ...", asset)
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest)

    cli = os.path.join(dest, "TwitchDownloaderCLI")
    os.chmod(cli, 0o755)

    with open(config_path, encoding='utf-8') as f:
        text = f.read()
    new_text = re.sub(r'Twitch_Downloader_[0-9][0-9.]*', f'Twitch_Downloader_{latest}', text)
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(new_text)

    if current and current != latest:
        old_dir = os.path.join(thirdparty, f"Twitch_Downloader_{current}")
        if os.path.isdir(old_dir):
            shutil.rmtree(old_dir)
            logger.info("Removed old thirdparty/Twitch_Downloader_%s", current)

    result = subprocess.run([cli, '--version'], capture_output=True, text=True)
    version_out = (result.stdout or result.stderr).strip()
    if version_out:
        logger.info(version_out)
    logger.info("Updated utilities/utilities_config.py -> Twitch_Downloader_%s", latest)


def main() -> None:
    run_task(parse_args())


if __name__ == "__main__":
    main()
