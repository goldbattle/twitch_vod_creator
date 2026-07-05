# !/usr/bin/env python3

"""
Video editing operations module.
Handles video rendering, muting, combining, and other editing operations.
"""

import logging
import os
import subprocess
import shutil
import hashlib
from . import utilities_extra

logger = logging.getLogger(__name__)


def has_nvenc_support(config):
    """Check if ffmpeg supports NVENC encoding and GPU is available."""
    # First check if ffmpeg has NVENC encoder compiled in
    # Note: ffmpeg sends encoder list to stderr, not stdout
    has_encoder = False
    try:
        ffmpeg_path = config.get('ffmpeg', 'ffmpeg')
        result = subprocess.run(
            [ffmpeg_path, '-encoders'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        if result.returncode != 0:
            logger.debug("GPU support: ffmpeg -encoders command failed")
            return False
        
        # Check both stdout and stderr (ffmpeg behavior can vary)
        # Search in both outputs - Python's 'in' operator handles multi-line strings correctly
        output = result.stdout.decode('utf-8', errors='ignore') + result.stderr.decode('utf-8', errors='ignore')
        if 'h264_nvenc' not in output:
            logger.debug("GPU support: h264_nvenc encoder not found in ffmpeg output")
            return False
        has_encoder = True
        logger.debug("GPU support: h264_nvenc encoder found in ffmpeg")
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug(f"GPU support: Error checking ffmpeg encoders: {e}")
        return False
    
    # Also check if GPU is actually available
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        if result.returncode == 0 and len(result.stdout.strip()) > 0:
            gpu_name = result.stdout.decode('utf-8', errors='ignore').strip().split('\n')[0]
            logger.debug(f"GPU support: NVIDIA GPU detected - {gpu_name}")
            return True
        else:
            logger.debug("GPU support: nvidia-smi returned no GPU")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        # If nvidia-smi is not available, we can't verify GPU presence
        # Return False to fall back to software encoding
        logger.debug(f"GPU support: nvidia-smi not available or failed: {e}")
        if has_encoder:
            logger.debug("GPU support: Encoder present but GPU not verified, falling back to software encoding")
        return False


def get_video_encoder_params(config, preset="slow", use_gpu=None):
    """
    Get video encoder parameters, using NVENC if supported.
    
    Args:
        config: Configuration dictionary with ffmpeg path
        preset: Encoding preset ('slow', 'fast', 'veryfast')
        use_gpu: Force GPU usage (True/False). If None, auto-detect.
    
    Returns:
        Tuple of (codec, encoding_params_string)
    """
    if use_gpu is None:
        use_gpu = has_nvenc_support(config)
    
    # Quality defaults tuned for YouTube uploads with text-heavy overlays:
    # - Lower cq/crf than previous default (23) to preserve chat readability.
    # - Keep preset fast to avoid slowing render pipelines too much.
    if use_gpu:
        logger.debug(f"GPU support: Using NVENC (h264_nvenc) with preset {preset}")
        # NVENC preset mapping: slow -> p7 (best quality), fast -> p4, veryfast -> p1
        nvenc_presets = {
            'slow': 'p7',
            'fast': 'p4',
            'veryfast': 'p1'
        }
        nvenc_preset = nvenc_presets.get(preset, 'p4')
        # NVENC uses -cq for constant quality (similar to CRF).
        # vbr_hq generally preserves quality better than strict CBR for YouTube uploads.
        return 'h264_nvenc', f'-rc vbr_hq -cq 19 -maxrate 20M -bufsize 40M -preset {nvenc_preset}'
    else:
        logger.debug(f"GPU support: Using software encoding (libx264) with preset {preset}")
        # CRF 19 is a better quality/speed tradeoff than CRF 23 for small text details.
        return 'libx264', f'-crf 19 -preset {preset}'


def time_string_to_seconds(time_str):
    """Convert time string (HH:MM:SS) to seconds."""
    h, m, s = time_str.split(':')
    return 3600 * int(h) + 60 * int(m) + int(s)


def render_segment_with_chat(config, video_path, chat_path, output_path,
                              start_time, end_time, chat_offset=0,
                              video_scale="1646x926", verbose=False, is_4k=False):
    """Render a video segment with chat overlay."""
    if os.path.exists(output_path) or utilities_extra.terminated_requested:
        return False
    
    # Calculate chat start time with offset
    h1, m1, s1 = start_time.split(':')
    time1_s = 3600 * int(h1) + 60 * int(m1) + int(s1) + chat_offset
    m, s = divmod(time1_s, 60)
    h, m = divmod(m, 60)
    seg_start_chat = f"{h:02d}:{m:02d}:{s:02d}"
    
    # Get encoder parameters (NVENC if GPU available, otherwise libx264)
    if is_4k:
        codec, encoder_params = get_video_encoder_params(config, preset="fast")
        # For 4K: video 3292x2160, chat 548x2160, total 3840x2160
        # Apply upscaling with noise reduction: hqdn3d + lanczos scaling
        cmd = (
            f'{config["ffmpeg"]} '
            f' -ss {start_time} -i {video_path} -to {end_time}'
            f' -ss {seg_start_chat} -i {chat_path}'
            f' -filter_complex "[0:v] hqdn3d=luma_spatial=2,scale=3292:2160:flags=lanczos+accurate_rnd+full_chroma_int [tmp1];'
            f' [1:v] scale=548:2160 [tmp2];'
            f' [tmp1][tmp2]hstack=inputs=2:shortest=1[stack]"'
            f' -shortest -map "[stack]" -map 0:a'
            f' -vcodec {codec} {encoder_params}'
            f' -avoid_negative_ts make_zero -r 60 -vsync 2'
            f' -map_chapters -1 -c:a copy'
            f' {output_path}'
        )
    else:
        codec, encoder_params = get_video_encoder_params(config, preset="fast")
        cmd = (
            f'{config["ffmpeg"]} '
            f' -ss {start_time} -i {video_path} -to {end_time}'
            f' -ss {seg_start_chat} -i {chat_path}'
            f' -filter_complex "[0:v] scale={video_scale} [tmp1];'
            f' [tmp1][1:v]hstack=inputs=2:shortest=1[stack]"'
            f' -shortest -map "[stack]" -map 0:a'
            f' -vcodec {codec} {encoder_params}'
            f' -avoid_negative_ts make_zero -r 60 -vsync 2'
            f' -map_chapters -1 -c:a copy'
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
                                 start_time, end_time, scale="1920:1080", verbose=False, is_4k=False):
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
    if is_4k:
        # For 4K: 3840x2160 with upscaling (hqdn3d + lanczos scaling)
        codec, encoder_params = get_video_encoder_params(config, preset="fast")
        cmd = (
            f'{config["ffmpeg"]} -hide_banner -loglevel {loglevel} -stats'
            f' -ss {start_time} -i {video_path} -t {seg_length}'
            f' -vf hqdn3d=luma_spatial=2,scale=3840:2160:flags=lanczos+accurate_rnd+full_chroma_int'
            f' -c:a copy -vcodec {codec} {encoder_params}'
            f' -avoid_negative_ts make_zero -vsync 2 -map_chapters -1'
            f' {output_path}'
        )
    else:
        codec, encoder_params = get_video_encoder_params(config, preset="fast")
        cmd = (
            f'{config["ffmpeg"]} -hide_banner -loglevel {loglevel} -stats'
            f' -ss {start_time} -i {video_path} -t {seg_length}'
            f' -vf scale=w={scale.split(":")[0]}:h={scale.split(":")[1]}'
            f' -c:a copy -vcodec {codec} {encoder_params}'
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
    # Use hash of full output path to ensure unique temp files for parallel processing
    output_hash = hashlib.md5(output_path.encode()).hexdigest()[:12]
    temp_audio = os.path.join(temp_path, f"{output_hash}_audio.aac")
    temp_audio_muted = os.path.join(temp_path, f"{output_hash}_audio_muted.aac")
    temp_basename = f"{output_hash}_{os.path.basename(output_path)}"
    temp_output = os.path.join(temp_path, temp_basename)
    
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
        f' -c:v copy -c:a copy -map 0:v:0 -map 1:a:0'
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


def upscale_video_to_4k(config, video_path, output_path, verbose=False):
    """Upscale a video to 4K (3840x2160) with CRF 15."""
    if os.path.exists(output_path) or utilities_extra.terminated_requested:
        return False
    
    temp_path = config.get('temp_path', '/tmp')
    # Use hash of full output path to ensure unique temp files for parallel processing
    output_hash = hashlib.md5(output_path.encode()).hexdigest()[:12]
    temp_basename = f"{output_hash}_{os.path.basename(output_path)}"
    temp_output = os.path.join(temp_path, temp_basename)
    
    loglevel = "error" if verbose else "quiet"
    codec, encoder_params = get_video_encoder_params(config, preset="fast")
    
    # Build video filter chain
    # https://ffmpeg.org/ffmpeg-filters.html#sr-1
    # https://ffmpeg.org/ffmpeg-filters.html#dnn_005fprocessing
    USE_SR_UPSCALE = False
    vf_parts = []
    
    # Add light temporal noise reduction (hqdn3d: spatial_luma, spatial_chroma, temporal_luma, temporal_chroma)
    # Light setting (default is 4), lets ffmpeg solve for the remaining terms via its defaults
    vf_parts.append('hqdn3d=luma_spatial=2')
    
    superres_model = config.get('superres_model')
    if USE_SR_UPSCALE and superres_model and os.path.exists(superres_model):
        # sr filter (libplacebo super resolution) with TensorFlow backend
        vf_parts.append(f'sr=dnn_backend=tensorflow:model={superres_model}:scale_factor=2:input=x:output=y')

    # Always final step is Lanczos scaling
    # accurate_rnd: accurate rounding
    # full_chroma_int: full chroma interpolation
    vf_parts.append('scale=3840:2160:flags=lanczos+accurate_rnd+full_chroma_int')
    vf_string = ','.join(vf_parts) if len(vf_parts) > 1 else vf_parts[0]
    logger.debug(f"Upscaling: SR={USE_SR_UPSCALE}, filter: {vf_string}")
    
    cmd = (
        f'{config["ffmpeg"]} -hide_banner -loglevel {loglevel} -stats'
        f' -i {video_path}'
        f' -vf {vf_string}'
        f' -c:a copy'
        f' -vcodec {codec} {encoder_params}'
        f' -avoid_negative_ts make_zero -vsync 2 -map_chapters -1'
        f' {temp_output}'
    )
    
    stdout = None if verbose else subprocess.DEVNULL
    stderr = None if verbose else subprocess.DEVNULL
    
    process = subprocess.Popen(cmd, shell=True, stdout=stdout, stderr=stderr)
    return_code = process.wait()
    
    if return_code != 0:
        logger.error(f"Error: ffmpeg returned exit code {return_code}")
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return False
    
    if os.path.exists(temp_output):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.move(temp_output, output_path)
        return True
    return False


def render_clip_with_title(config, video_path, chat_path, output_path, title_text, quiet=True, is_4k=False):
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
    
    codec, encoder_params = get_video_encoder_params(config, preset="fast")
    
    # For 4K: scale video to 3292x2160, chat to 548x2160, total 3840x2160
    # Scale title text proportionally: 85 * (2160/926) ≈ 198
    # Scale position: 25 * (2160/926) ≈ 58
    # Scale border: 5 * (2160/926) ≈ 12
    if is_4k:
        codec, encoder_params = get_video_encoder_params(config, preset="fast")
        if chat_path and os.path.exists(chat_path):
            cmd = (
                f'{config["ffmpeg"]} -hide_banner -loglevel quiet -stats '
                f' -i {video_path}'
                f' -i {chat_path}'
                f' -filter_complex "[0:v] hqdn3d=luma_spatial=2,scale=3292:2160:flags=lanczos+accurate_rnd+full_chroma_int [tmp0];'
                f' [tmp0]drawtext=text=\'{title_clean}\':x=58:y=58:fontfile={config["font"]}:fontsize=198:fontcolor=white:bordercolor=black:borderw=12'
                f':alpha=\'if(lt(t,0),0,if(lt(t,0),(t-0)/0,if(lt(t,4),1,if(lt(t,4.5),(0.5-(t-4))/0.5,0))))\'[tmp1]; '
                f' [1:v] scale=548:2160 [tmp2];'
                f' [tmp1][tmp2] hstack=inputs=2:shortest=1" -shortest '
                f' -c:a copy -vcodec {codec} {encoder_params} '
                f' -video_track_timescale 90000 -avoid_negative_ts make_zero -map_chapters -1 -fflags +genpts -r 60 '
                f' {output_path}'
            )
        else:
            cmd = (
                f'{config["ffmpeg"]} -hide_banner -loglevel quiet -stats '
                f' -i {video_path}'
                f' -vf "hqdn3d=luma_spatial=2,scale=3292:2160:flags=lanczos+accurate_rnd+full_chroma_int,pad=3840:2160:0:0:black,'
                f'drawtext=text=\'{title_clean}\':x=58:y=58:fontfile={config["font"]}:fontsize=198:fontcolor=white:bordercolor=black:borderw=12'
                f':alpha=\'if(lt(t,0),0,if(lt(t,0),(t-0)/0,if(lt(t,4),1,if(lt(t,4.5),(0.5-(t-4))/0.5,0))))\' "'
                f' -c:a copy -vcodec {codec} {encoder_params} '
                f' -video_track_timescale 90000 -avoid_negative_ts make_zero -map_chapters -1 -fflags +genpts -r 60 '
                f' {output_path}'
            )
    else:
        if chat_path and os.path.exists(chat_path):
            cmd = (
                f'{config["ffmpeg"]} -hide_banner -loglevel quiet -stats '
                f' -i {video_path}'
                f' -i {chat_path}'
                f' -filter_complex "scale=1646x926,pad=1920:926:0:90:black [tmp0];'
                f' [tmp0]drawtext=text=\'{title_clean}\':x=25:y=25:fontfile={config["font"]}:fontsize=85:fontcolor=white:bordercolor=black:borderw=5'
                f':alpha=\'if(lt(t,0),0,if(lt(t,0),(t-0)/0,if(lt(t,4),1,if(lt(t,4.5),(0.5-(t-4))/0.5,0))))\'[tmp1]; '
                f' [tmp1][1:v] overlay=shortest=0:x=1646:y=0:eof_action=endall" -shortest '
                f' -c:a copy -vcodec {codec} {encoder_params} '
                f' -video_track_timescale 90000 -avoid_negative_ts make_zero -map_chapters -1 -fflags +genpts -r 60 '
                f' {output_path}'
            )
        else:
            cmd = (
                f'{config["ffmpeg"]} -hide_banner -loglevel quiet -stats '
                f' -i {video_path}'
                f' -vf "scale=1646x926,pad=1920:926:0:90:black,'
                f'drawtext=text=\'{title_clean}\':x=25:y=25:fontfile={config["font"]}:fontsize=85:fontcolor=white:bordercolor=black:borderw=5'
                f':alpha=\'if(lt(t,0),0,if(lt(t,0),(t-0)/0,if(lt(t,4),1,if(lt(t,4.5),(0.5-(t-4))/0.5,0))))\' "'
                f' -c:a copy -vcodec {codec} {encoder_params} '
                f' -video_track_timescale 90000 -avoid_negative_ts make_zero -map_chapters -1 -fflags +genpts -r 60 '
                f' {output_path}'
            )
    
    subprocess.Popen(cmd, shell=True, stdout=stdout, stderr=stderr).wait()
    return os.path.exists(output_path)

