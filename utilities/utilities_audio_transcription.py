# !/usr/bin/env python3

"""
Audio transcription module.
Handles audio-to-text transcription using Vosk.
"""

import os
import json
import subprocess
import logging
from webvtt import WebVTT, Caption
from vosk import Model, KaldiRecognizer, SetLogLevel
from . import utilities_extra

logger = logging.getLogger(__name__)

# Global model cache
_model_cache = None
_rec_cache = None
_sample_rate = 16000


def webvtt_time_string(seconds):
    """Convert seconds to WebVTT time string format (HH:MM:SS.mmm)."""
    if seconds is None or (isinstance(seconds, float) and (seconds != seconds or seconds < 0)):  # Check for None, NaN, or negative
        raise ValueError(f"Invalid timestamp value: {seconds}")
    
    # Ensure seconds is a float
    total_seconds = float(seconds)
    
    # Calculate hours, minutes, and remaining seconds
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    secs = total_seconds % 60
    
    # Format as HH:MM:SS.mmm
    return '%02d:%02d:%06.3f' % (hours, minutes, secs)


def _load_model(model_path):
    """Load Vosk model (lazy loading with caching)."""
    global _model_cache, _rec_cache
    if _model_cache is None:
        SetLogLevel(-1)
        _model_cache = Model(model_path)
        _rec_cache = KaldiRecognizer(_model_cache, _sample_rate)
        _rec_cache.SetWords(True)
    return _rec_cache


def transcribe_video(config, video_path, output_path, quiet=True):
    """Transcribe audio from video to WebVTT."""
    if os.path.exists(output_path) or utilities_extra.terminated_requested:
        return False
    
    if not os.path.exists(video_path):
        return False
    
    rec = _load_model(config["vosk_model"])
    
    # Extract audio stream using ffmpeg
    command = [
        config["ffmpeg"], '-nostdin', '-loglevel', 'quiet',
        '-i', video_path,
        '-ar', str(_sample_rate), '-ac', '1', '-f', 's16le', '-'
    ]
    
    stderr = subprocess.DEVNULL if quiet else None
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=stderr)
    
    results = []
    while True:
        data = process.stdout.read(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            text = rec.Result()
            results.append(text)
    results.append(rec.FinalResult())
    
    # Convert to WebVTT format
    vtt = WebVTT()
    skipped_count = 0
    for res in results:
        words = json.loads(res).get('result')
        if not words:
            continue
        for word in words:
            try:
                # Validate word data
                if 'start' not in word or 'end' not in word or 'word' not in word:
                    skipped_count += 1
                    continue
                
                # Validate timestamps are valid numbers
                start_val = word.get('start')
                end_val = word.get('end')
                
                if start_val is None or end_val is None:
                    skipped_count += 1
                    continue
                
                try:
                    start_val = float(start_val)
                    end_val = float(end_val)
                except (ValueError, TypeError):
                    skipped_count += 1
                    continue
                
                # Ensure end is not before start
                if end_val < start_val:
                    skipped_count += 1
                    continue
                
                # Format timestamps
                start = webvtt_time_string(start_val)
                end = webvtt_time_string(end_val)
                
                # Create caption with error handling
                vtt.captions.append(Caption(start, end, word['word']))
            except (ValueError, KeyError, TypeError) as e:
                # Log warning but continue processing
                skipped_count += 1
                logger.warning(f"Skipping invalid word entry: {word.get('word', 'unknown')} - {str(e)}")
            except Exception as e:
                # Catch any other errors from webvtt library
                skipped_count += 1
                logger.warning(f"Error creating caption for word '{word.get('word', 'unknown')}': {str(e)}")
    
    if skipped_count > 0:
        logger.warning(f"Skipped {skipped_count} invalid word entries during transcription")
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    vtt.save(output_path)
    return os.path.exists(output_path)

