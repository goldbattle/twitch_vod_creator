#!/bin/bash

# Script to ensure all third-party dependencies are executable
# This is useful after cloning the repository or when permissions are lost

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THIRDPARTY_DIR="${SCRIPT_DIR}/thirdparty"

# Check if thirdparty directory exists
if [ ! -d "$THIRDPARTY_DIR" ]; then
    echo "Error: thirdparty directory not found at $THIRDPARTY_DIR"
    exit 1
fi

echo "Making third-party dependencies executable..."
echo "Searching in: $THIRDPARTY_DIR"
echo ""

# Counter for files made executable
count=0

# Make ffmpeg binaries executable
echo "Processing ffmpeg binaries..."
find "$THIRDPARTY_DIR" -type f \( -name "ffmpeg" -o -name "ffprobe" -o -name "qt-faststart" \) 2>/dev/null | while IFS= read -r file; do
    if [ -f "$file" ]; then
        chmod +x "$file"
        echo "  Made executable: $file"
        count=$((count + 1))
    fi
done

# Make TwitchDownloaderCLI executables
echo "Processing TwitchDownloaderCLI executables..."
find "$THIRDPARTY_DIR" -type f -name "TwitchDownloaderCLI" 2>/dev/null | while IFS= read -r file; do
    if [ -f "$file" ]; then
        chmod +x "$file"
        echo "  Made executable: $file"
        count=$((count + 1))
    fi
done

# Make Python scripts executable
echo "Processing Python scripts..."
find "$THIRDPARTY_DIR" -type f -name "*.py" 2>/dev/null | while IFS= read -r file; do
    if [ -f "$file" ]; then
        chmod +x "$file"
        echo "  Made executable: $file"
        count=$((count + 1))
    fi
done

# Count files separately since while loop runs in subshell
total_count=$(find "$THIRDPARTY_DIR" -type f \( -name "ffmpeg" -o -name "ffprobe" -o -name "qt-faststart" -o -name "TwitchDownloaderCLI" -o -name "*.py" \) 2>/dev/null | wc -l)

echo ""
echo "Done! Made $total_count file(s) executable."

