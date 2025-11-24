# !/usr/bin/env python3

"""
Audio transcription module.
Handles audio-to-text transcription using Vosk.
"""

import os
import json
import subprocess
from webvtt import WebVTT, Caption
from vosk import Model, KaldiRecognizer, SetLogLevel
from . import utilities_extra

# Global model cache
_model_cache = None
_rec_cache = None
_sample_rate = 16000


def webvtt_time_string(seconds):
    """Convert seconds to WebVTT time string format."""
    minutes = seconds / 60
    seconds = seconds % 60
    hours = int(minutes / 60)
    minutes = int(minutes % 60)
    return '%i:%02i:%06.3f' % (hours, minutes, seconds)


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
    for res in results:
        words = json.loads(res).get('result')
        if not words:
            continue
        for word in words:
            start = webvtt_time_string(word['start'])
            end = webvtt_time_string(word['end'])
            vtt.captions.append(Caption(start, end, word['word']))
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    vtt.save(output_path)
    return os.path.exists(output_path)

