# website editor

This website aims to increase speed while editing locally downloaded VOD files.
Ideally, most interactions should come from the keyboard and should generate a compatible config file for use.
If you want to run it locally, download [nginx](http://nginx.org/en/download.html) and edit the included config to correctly point to your directories.
If there is a video transcript, we leverage this to enable fast editing.
For example, the text can be clicked to jump to that timestamp in the video, and thus should remove the need for seeking in the video.


![](../docs/website_example.png)


## keyboard actions

- `a` - create a new video segment
- `up / down arrows` - switch between active segments
- `s` - append a start time to the current segment
- `d` - append an end time to the current segment
- `left / right arrows` - advance forward 10 seconds into the video 
- `ctrl + left / right arrows` - advance forward 30 seconds into the video 
- `alt + left / right arrows` - advance forward 60 seconds into the video 


## known limitations

- no undo button, need to add this to improve usability
- no way to delete a segment
- can be laggy on load / usage for long VODs due to number of transcript words



## nginx on ubuntu


```
sudo apt install nginx
sudo systemctl enable nginx
sudo rm /etc/nginx/sites-enabled/default
sudo sh -c "echo -n 'YOUR_USERNAME:' >> /etc/nginx/.htpasswd"
sudo sh -c "openssl passwd -apr1 >> /etc/nginx/.htpasswd"
cat /etc/nginx/.htpasswd
sudo ln -s /mnt/twitchvods2/twitch_vod_creator/website/twitch_vod_editor.conf /etc/nginx/sites-enabled/
sudo service nginx restart
```

