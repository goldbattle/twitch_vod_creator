

# youtube-video-upload

Upload videos starting from a yaml file.

https://github.com/remorses/youtube-video-upload


```
pip3 install youtube-video-upload
python -m youtube_video_upload example.yaml
```




example.yaml file:
```yaml
local_server: true # use a local server instead of a url to get credentials
                   # this is necessary when using this script from localhost
videos:
    -
        title: test video 4
        file: ../testing/output - Copy.mp4
        description: another example video
#        category: Gaming
        privacy: public
        tags:
            - testing
            - gaming
            - sodapoppin

secrets_path: ../profiles/sodapoppin_secrets.json
credentials_path: ../profiles/sodapoppin_creds.json
```


This seems to have all videos fail due to invalid "Terms and Conditions" after uploading.
Not sure how to fix, for now hand uploads are what are used.