#!/bin/bash
# Example commands with current defaults for all main scripts
# These commands show what parameters were previously hardcoded

# ================================================================
# 0_main_clips.py
# ================================================================
# Downloads clips from multiple channels with view count thresholds
# Default channels: xqc moonmoon sodapoppin clintstevens pokelawls forsen nmplol jerma985 vei
# Default min-view-counts: 6000 1000 300 100 1000 5000 100 500 500
# Default num-days: 120
python3 0_main_clips.py \
    --channels xqc moonmoon sodapoppin clintstevens pokelawls forsen nmplol jerma985 vei \
    --min-view-counts 6000 1000 300 100 1000 5000 100 500 500 \
    --num-days 120

# Example with fewer channels:
# python3 0_main_clips.py \
#     --channels sodapoppin xqc \
#     --min-view-counts 300 6000 \
#     --num-days 30

# ================================================================
# 0_main_videos.py
# ================================================================
# Downloads videos from a single channel
# Default channel: sodapoppin
# Default max-videos: 1
# Default render-chat: true
# Default render-webvtt: true
python3 0_main_videos.py \
    --channels sodapoppin \
    --max-videos 1 \
    --render-chat true \
    --render-webvtt true

# Example with multiple channels (previously commented out in code):
# python3 0_main_videos.py \
#     --channels sodapoppin skippypoppin nmplol \
#     --max-videos 1 \
#     --render-chat true false false \
#     --render-webvtt true true true

# Example with more channels (all previously commented out):
# python3 0_main_videos.py \
#     --channels sodapoppin moonmoon clintstevens sevadus jerma985 heydoubleu vei squeex goldbattle j_blow mindcrack \
#     --max-videos 1 \
#     --render-chat true false false false false false false false false false false false \
#     --render-webvtt true true true false true false false false true false false false

# ================================================================
# 1_render_clip_comp.py
# ================================================================
# Renders a clip compilation from a date range
# Default channel: sodapoppin
# Default max-clips: 10
# Default date-start: 2024-12-01T00:00:00Z
# Default date-end: 2024-12-31T00:00:00Z
# Default min-views: 500 (optional, can be omitted)
# Default get_latest_from_twitch: true (use --no-download to disable)
# Default remove_rendered: true (use --no-remove to disable)
# Default clips-to-ignore: (list below, optional)
# Option 1: List clip IDs directly (min-views can be omitted to use default 500)
python3 1_render_clip_comp.py \
    --channel sodapoppin \
    --max-clips 10 \
    --date-start 2024-12-01T00:00:00Z \
    --date-end 2024-12-31T00:00:00Z \
    --clips-to-ignore \
        ScaryBrainyEyeballArsonNoSexy-0Jn0wz5mZ1bRMyGk \
        EasyFairLlamaHoneyBadger-rxZed8PoO1MR3PgL \
        ShinyDependableSharkKappaPride-Qjf4VS7pe6TumUY6 \
        MoralSaltyHabaneroDatSheffy-3uKETXph5PWyF8w6 \
        PricklyCheerfulShallotKeyboardCat-h8Knl5UZGEphTpn7 \
        BoredHedonisticMilkCorgiDerp-kzChRQAEuGS0xNcM

# Example with custom min-views:
# python3 1_render_clip_comp.py \
#     --channel sodapoppin \
#     --max-clips 10 \
#     --date-start 2024-12-01T00:00:00Z \
#     --date-end 2024-12-31T00:00:00Z \
#     --min-view-counts 1000

# Option 2: Use a file with one ID per line
# python3 1_render_clip_comp.py \
#     --channel sodapoppin \
#     --max-clips 10 \
#     --date-start 2024-12-01T00:00:00Z \
#     --date-end 2024-12-31T00:00:00Z \
#     --clips-to-ignore config/clips_to_ignore.txt

# To skip downloading from Twitch (use existing clips):
# python3 1_render_clip_comp.py \
#     --channel sodapoppin \
#     --max-clips 10 \
#     --date-start 2024-12-01T00:00:00Z \
#     --date-end 2024-12-31T00:00:00Z \
#     --no-download

# To keep rendered files:
# python3 1_render_clip_comp.py \
#     --channel sodapoppin \
#     --max-clips 10 \
#     --date-start 2024-12-01T00:00:00Z \
#     --date-end 2024-12-31T00:00:00Z \
#     --no-remove

# ================================================================
# 1_render_4way.py
# ================================================================
# Renders a 4-way video composite
# Default title: "4-Way Puzzle Box with Shroud, AnneMunition, and Sacriel #ad - (sodapoppin) - May 7, 2021"
# Default sync-offset: 00:04:15
# Default duration: 01:31:47
# Default video0: sodapoppin/2021-05/1014588993
# Default starttime0: 01:19:53
# Default video1: annemunition/2021-05/1014683883
# Default starttime1: 00:07:12
# Default video2: sacriel/2021-05/1014237350
# Default starttime2: 06:45:51
# Default video3: shroud/2021-05/1014620817
# Default starttime3: 00:56:46
python3 1_render_4way.py \
    --title "4-Way Puzzle Box with Shroud, AnneMunition, and Sacriel #ad - (sodapoppin) - May 7, 2021" \
    --sync-offset 00:04:15 \
    --duration 01:31:47 \
    --video0 sodapoppin/2021-05/1014588993 \
    --starttime0 01:19:53 \
    --video1 annemunition/2021-05/1014683883 \
    --starttime1 00:07:12 \
    --video2 sacriel/2021-05/1014237350 \
    --starttime2 06:45:51 \
    --video3 shroud/2021-05/1014620817 \
    --starttime3 00:56:46

# ================================================================
# 1_render_segments.py
# ================================================================
# Renders video segments from a YAML configuration file
# Default video-file: config/soda_2025_videos.yaml
# Default config-file: config/soda_config_youtube.yaml
python3 1_render_segments.py \
    --video-file config/soda_2025_videos.yaml \
    --config-file config/soda_config_youtube.yaml

# Example with different config files:
# python3 1_render_segments.py \
#     --video-file config/sevadus_2024_videos.yaml \
#     --config-file config/sevadus_config_youtube.yaml

# ================================================================
# 2_upload_segments.py
# ================================================================
# Uploads video segments to YouTube
# Default video-file: config/soda_2025_videos.yaml
# Default history-file: config/soda_2025_uploads.yaml
# Default config-file: config/soda_config_youtube.yaml
# Default display-missing: false
python3 2_upload_segments.py \
    --video-file config/soda_2025_videos.yaml \
    --history-file config/soda_2025_uploads.yaml \
    --config-file config/soda_config_youtube.yaml

# Example with different config files:
# python3 2_upload_segments.py \
#     --video-file config/sevadus_2024_videos.yaml \
#     --history-file config/sevadus_2024_uploads.yaml \
#     --config-file config/sevadus_config_youtube.yaml

# To display missing video files:
# python3 2_upload_segments.py \
#     --video-file config/soda_2025_videos.yaml \
#     --history-file config/soda_2025_uploads.yaml \
#     --config-file config/soda_config_youtube.yaml \
#     --display-missing

# ================================================================
# 0_main_vtt_generation.py
# ================================================================
# Generates WebVTT transcriptions for videos
# Default channel: sodapoppin
# Default min-age: 60 seconds
python3 0_main_vtt_generation.py \
    --channel sodapoppin \
    --min-age 60

# Example with different channel:
# python3 0_main_vtt_generation.py \
#     --channel xqc \
#     --min-age 120

# ================================================================
# 0_single_video.py
# ================================================================
# Downloads a single VOD by ID
python3 0_single_video.py 1234567890

# To skip chat rendering:
# python3 0_single_video.py 1234567890 --no-chat

# To skip transcription:
# python3 0_single_video.py 1234567890 --no-transcribe

