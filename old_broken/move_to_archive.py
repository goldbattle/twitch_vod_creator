import os
import datetime
import subprocess


# disable dry run
disable_dry_run = True

# main data array, and then the location we wish to archive into
path_main = "/mnt/twitchvods/"
path_archive = "/mnt/twitchvods_archive/"
directories = ["data", "data_live", "data_clips_new"]
# directories = ["data_live"]

# if the folder is older then this many days, then archive it!
archive_if_older = 2 * 365
date_threshold = datetime.datetime.now()-datetime.timedelta(days=archive_if_older)

# loop through each directory which we will try to see if any channels need to be archived
for directory in directories:
    channels = [ f.path for f in os.scandir(os.path.join(path_main, directory)) if f.is_dir() ]
    for channel_path in channels:
        print(f"====================================================")
        print(f"====================================================")
        print(f"processing: {channel_path}")

        date_folders = [ os.path.basename(f.path) for f in os.scandir(channel_path) if f.is_dir() ]
        date_folders.sort()
        dates = [ datetime.datetime.strptime(d, "%Y-%m") for d in date_folders ]

        # loop through each folder and see if this folder should rsync'ed over to the new location
        for i, date_str in enumerate(date_folders):
            if dates[i] > date_threshold:
                print(f"skipping {date_str} -> {dates[i]} since it isn't old enough")
                continue
            path_old = channel_path + "/" + date_str + "/"
            path_new = channel_path.replace(path_main, path_archive) + "/" + date_str + "/"
            print(f"will move folder '{path_old}' to '{path_new}'!")
            if not os.path.exists(path_new):
                os.makedirs(path_new, exist_ok=True)

            # lets actually do the copy now!
            # https://explainshell.com/explain?cmd=rsync+--dry-run+--remove-source-files+-avzPh
            dryrun = "--dry-run"
            if disable_dry_run:
                dryrun = ""
            cmd = "rsync -avzPh --itemize-changes --remove-source-files " + dryrun + " " + path_old + " " + path_new
            print(cmd)
            # subprocess.call(["rsync", "-avzPh", "--itemize-changes", "--remove-source-files", dryrun, path_old, path_new], shell=True)
            subprocess.call(cmd, shell=True)
            print("")
        print("")
            







