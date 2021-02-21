# Spleeter Audio Extraction

https://github.com/deezer/spleeter
https://gist.github.com/dannguyen/58db5ac1866e8c930b2f2840a455653d

0 - Install spleeter

```
pip install tensorflow
pip install spleeter
```

1 - Extracting the audio from video

```sh
ffmpeg.exe -i SeductiveBelovedEchidnaCoolStoryBob.mp4 -f wav audio_raw.wav
```

2 - Splitting the audio into 2 tracks with spleeter

```sh
spleeter separate -i audio_raw.wav -p spleeter:2stems -o audio_split
```

3 - Strip audio from video

```sh
ffmpeg.exe -i SeductiveBelovedEchidnaCoolStoryBob.mp4 -codec copy -an SeductiveBelovedEchidnaCoolStoryBob_silent.mp4
```

4 - Merge silent video with audio track

```sh
ffmpeg.exe -i SeductiveBelovedEchidnaCoolStoryBob_silent.mp4 -i audio_split/audio_raw/vocals.wav -c:v copy -c:a aac SeductiveBelovedEchidnaCoolStoryBob_clean.mp4
```
