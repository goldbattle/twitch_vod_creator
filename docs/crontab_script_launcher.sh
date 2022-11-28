#!/bin/bash

# check that we have passed a script name
if [[ $# < 1 ]]
then
	echo "specify what script to launch"
	exit 1
fi

# check if the process is running or not
CWD="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
if pgrep -f "python3 $CWD/../$1" >/dev/null 2>&1 ; 
then
	echo "script already running, skipping"
	exit 1
fi 

# else lets run the script!
DATE=$(date +\%Y-\%m-\%d)
TIME=$(date +\%H-\%M-\%S)
mkdir -p "$CWD/../logs/$DATE/"
#python3 "$CWD/../$1" "${@:2}" &> "$CWD/../logs/$DATE/$TIME-$1.log"
python3 "$CWD/../$1" "${@:2}" 2>&1 | tee "$CWD/../logs/$DATE/$TIME-$1.log"
