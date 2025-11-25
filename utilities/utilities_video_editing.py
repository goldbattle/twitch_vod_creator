# !/usr/bin/env python3

"""
Video editing operations module.
Handles video rendering, muting, combining, and other editing operations.
"""

import logging
import os
import subprocess
import shutil
from . import utilities_extra

logger = logging.getLogger(__name__)


def time_string_to_seconds(time_str):
    """Convert time string (HH:MM:SS) to seconds."""
    h, m, s = time_str.split(':')
    return 3600 * int(h) + 60 * int(m) + int(s)


def render_segment_with_chat(config, video_path, chat_path, output_path,
                              start_time, end_time, chat_offset=0,
                              video_scale="1646x926", verbose=False):
    """Render a video segment with chat overlay."""
    if os.path.exists(output_path) or utilities_extra.terminated_requested:
        return False
    
    # Calculate chat start time with offset
    h1, m1, s1 = start_time.split(':')
    time1_s = 3600 * int(h1) + 60 * int(m1) + int(s1) + chat_offset
    m, s = divmod(time1_s, 60)
    h, m = divmod(m, 60)
    seg_start_chat = f"{h:02d}:{m:02d}:{s:02d}"
    
    cmd = (
        f'{config["ffmpeg"]} '
        f' -ss {start_time} -i {video_path} -to {end_time}'
        f' -ss {seg_start_chat} -i {chat_path}'
        f' -filter_complex "[0:v] scale={video_scale} [tmp1];'
        f' [tmp1][1:v]hstack=inputs=2:shortest=1[stack]"'
        f' -shortest -map "[stack]" -map 0:a'
        f' -vcodec libx264 -crf 10 -preset veryfast'
        f' -avoid_negative_ts make_zero -framerate 60 -vsync 2'
        f' -map_chapters -1 -c:a aac'
        f' {output_path}'
    )
    
    stdout = None if verbose else subprocess.DEVNULL
    stderr = None if verbose else subprocess.DEVNULL
    
    process = subprocess.Popen(cmd, shell=True, stdout=stdout, stderr=stderr)
    return_code = process.wait()
    
    if return_code != 0:
        logger.error(f"Error: ffmpeg returned exit code {return_code}")
        return False
    
    return os.path.exists(output_path)


def render_segment_without_chat(config, video_path, output_path,
                                 start_time, end_time, scale="1920:1080", verbose=False):
    """Render a video segment without chat overlay."""
    if os.path.exists(output_path) or utilities_extra.terminated_requested:
        return False
    
    # Calculate segment length
    h1, m1, s1 = start_time.split(':')
    h2, m2, s2 = end_time.split(':')
    time1_s = 3600 * int(h1) + 60 * int(m1) + int(s1)
    time2_s = 3600 * int(h2) + 60 * int(m2) + int(s2)
    m, s = divmod(time2_s - time1_s, 60)
    h, m = divmod(m, 60)
    seg_length = f"{h:02d}:{m:02d}:{s:02d}"
    
    loglevel = "error" if verbose else "quiet"
    cmd = (
        f'{config["ffmpeg"]} -hide_banner -loglevel {loglevel} -stats'
        f' -ss {start_time} -i {video_path} -t {seg_length}'
        f' -vf scale=w={scale.split(":")[0]}:h={scale.split(":")[1]}'
        f' -c:a aac -vcodec libx264 -crf 10 -preset fast'
        f' -avoid_negative_ts make_zero -vsync 2 -map_chapters -1'
        f' {output_path}'
    )
    
    stdout = None if verbose else subprocess.DEVNULL
    stderr = None if verbose else subprocess.DEVNULL
    
    process = subprocess.Popen(cmd, shell=True, stdout=stdout, stderr=stderr)
    return_code = process.wait()
    
    if return_code != 0:
        logger.error(f"Error: ffmpeg returned exit code {return_code}")
        return False
    
    return os.path.exists(output_path)


def combine_videos(config, video_paths, output_path, quiet=True):
    """Combine multiple video files into one."""
    if os.path.exists(output_path) or utilities_extra.terminated_requested:
        return False
    
    temp_path = config.get('temp_path', '/tmp')
    concat_file = os.path.join(temp_path, "concat_list.txt")
    with open(concat_file, 'w') as f:
        for video_path in video_paths:
            if os.path.exists(video_path):
                f.write(f"file '{os.path.abspath(video_path)}'\n")
    
    cmd = (
        f'{config["ffmpeg"]} -hide_banner -loglevel quiet -stats'
        f' -f concat -safe 0 -i {concat_file}'
        f' -c copy -avoid_negative_ts make_zero -map_chapters -1'
        f' {output_path}'
    )
    
    stdout = subprocess.DEVNULL if quiet else None
    stderr = subprocess.DEVNULL if quiet else None
    
    subprocess.Popen(cmd, shell=True, stdout=stdout, stderr=stderr).wait()
    
    if os.path.exists(concat_file):
        os.remove(concat_file)
    
    return os.path.exists(output_path)


def mute_audio_segments(config, video_path, output_path, mute_segments, quiet=True):
    """Mute specific time segments in a video."""
    if os.path.exists(output_path) or utilities_extra.terminated_requested:
        return False
    
    temp_path = config.get('temp_path', '/tmp')
    temp_audio = os.path.join(temp_path, "audio.aac")
    temp_audio_muted = os.path.join(temp_path, "audio_muted.aac")
    temp_output = os.path.join(temp_path, os.path.basename(output_path))
    
    # Clean up temp files
    for f in [temp_audio, temp_audio_muted]:
        if os.path.exists(f):
            os.remove(f)
    
    # Step 1: Extract audio
    cmd = (
        f'{config["ffmpeg"]} -hide_banner -loglevel quiet -stats'
        f' -i {video_path} -vn -acodec copy {temp_audio}'
    )
    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
    
    if not os.path.exists(temp_audio):
        return False
    
    # Step 2: Mute segments
    enable_expr = "+".join([f"between(t,{start},{end})" for start, end in mute_segments])
    cmd = (
        f'{config["ffmpeg"]} -hide_banner -loglevel quiet -stats'
        f' -i {temp_audio}'
        f' -af "volume=0:enable=\'{enable_expr}\'"'
        f' {temp_audio_muted}'
    )
    subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
    
    if not os.path.exists(temp_audio_muted):
        return False
    
    # Step 3: Re-encode with muted audio
    stdout = subprocess.DEVNULL if quiet else None
    stderr = subprocess.DEVNULL if quiet else None
    cmd = (
        f'{config["ffmpeg"]} -hide_banner -loglevel quiet -stats'
        f' -i {video_path} -i {temp_audio_muted}'
        f' -c:v copy -c:a aac -map 0:v:0 -map 1:a:0'
        f' {temp_output}'
    )
    subprocess.Popen(cmd, shell=True, stdout=stdout, stderr=stderr).wait()
    
    # Clean up and move
    for f in [temp_audio, temp_audio_muted]:
        if os.path.exists(f):
            os.remove(f)
    
    if os.path.exists(temp_output):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.move(temp_output, output_path)
        return True
    
    return False


def get_video_duration(config, video_path):
    """Get video duration in seconds using ffprobe."""
    if not config.get("ffprobe") or not os.path.exists(video_path):
        return None
    
    cmd = (
        f'{config["ffprobe"]}'
        f' -v error -show_entries format=duration'
        f' -of default=noprint_wrappers=1:nokey=1'
        f' {video_path}'
    )
    try:
        pipe = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        duration = float(pipe.communicate()[0])
        return duration
    except:
        return None


def render_clip_with_title(config, video_path, chat_path, output_path, title_text, quiet=True):
    """Render a clip with title overlay and optional chat."""
    if os.path.exists(output_path) or utilities_extra.terminated_requested:
        return False
    
    # Clean title text
    import re
    title_clean = re.sub(r'http\S+', '', title_text)
    title_clean = re.sub(r'www\S+', '', title_clean)
    title_clean = re.sub(r"[^a-zA-Z0-9'.?: ]", '', title_clean)
    title_clean = title_clean.replace("'", "\u2019")
    if len(title_clean.split()) > 8:
        title_clean = ""
    
    stdout = subprocess.DEVNULL if quiet else None
    stderr = subprocess.DEVNULL if quiet else None
    
    if chat_path and os.path.exists(chat_path):
        cmd = (
            f'{config["ffmpeg"]} -hide_banner -loglevel quiet -stats '
            f' -i {video_path}'
            f' -i {chat_path}'
            f' -filter_complex "scale=1646x926,pad=1920:926:0:90:black [tmp0];'
            f' [tmp0]drawtext=text=\'{title_clean}\':x=25:y=25:fontfile={config["font"]}:fontsize=85:fontcolor=white:bordercolor=black:borderw=5'
            f':alpha=\'if(lt(t,0),0,if(lt(t,0),(t-0)/0,if(lt(t,4),1,if(lt(t,4.5),(0.5-(t-4))/0.5,0))))\'[tmp1]; '
            f' [tmp1][1:v] overlay=shortest=0:x=1646:y=0:eof_action=endall" -shortest '
            f' -c:a aac -ar 48k -ac 2 -vcodec libx264 -crf 19 -preset fast '
            f' -video_track_timescale 90000 -avoid_negative_ts make_zero -map_chapters -1 -fflags +genpts -framerate 60 '
            f' {output_path}'
        )
    else:
        cmd = (
            f'{config["ffmpeg"]} -hide_banner -loglevel quiet -stats '
            f' -i {video_path}'
            f' -vf "scale=1646x926,pad=1920:926:0:90:black,'
            f'drawtext=text=\'{title_clean}\':x=25:y=25:fontfile={config["font"]}:fontsize=85:fontcolor=white:bordercolor=black:borderw=5'
            f':alpha=\'if(lt(t,0),0,if(lt(t,0),(t-0)/0,if(lt(t,4),1,if(lt(t,4.5),(0.5-(t-4))/0.5,0))))\' "'
            f' -c:a aac -ar 48k -ac 2 -vcodec libx264 -crf 19 -preset fast '
            f' -video_track_timescale 90000 -avoid_negative_ts make_zero -map_chapters -1 -fflags +genpts -framerate 60 '
            f' {output_path}'
        )
    
    subprocess.Popen(cmd, shell=True, stdout=stdout, stderr=stderr).wait()
    return os.path.exists(output_path)

