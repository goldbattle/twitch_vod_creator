#!/usr/bin/env python3
"""
Web server task for hosting the video editor interface.
"""

import sys
import os
import argparse
import logging
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, unquote
from typing import Optional, Dict, List
import re
import mimetypes
import json
import time
from pathlib import Path
from tqdm import tqdm
import coloredlogs


class CustomHTTPRequestHandler(SimpleHTTPRequestHandler):
    """Custom HTTP request handler that serves files from different directories."""
    
    # Class-level cache for listings (shared across all instances)
    # Key: cache_key (e.g., "dir_username_month" or "videos_all"), Value: (data, timestamp)
    _list_cache: Dict[str, tuple] = {}
    _cache_ttl: float = 300.0  # Cache for 5 minutes
    
    def __init__(self, *args, website_root: str, data_path: str, data_live_path: Optional[str] = None, **kwargs):
        self.website_root = website_root
        self.data_path = data_path
        self.data_live_path = data_live_path
        # Ensure mimetypes are properly initialized
        mimetypes.init()
        super().__init__(*args, **kwargs)
    
    def guess_type(self, path: str) -> str:
        """Override to ensure proper MIME types for video files."""
        # Get base type from parent
        content_type = super().guess_type(path)
        
        # Ensure video files get proper MIME types
        if path.endswith('.mp4'):
            return 'video/mp4'
        elif path.endswith('.webm'):
            return 'video/webm'
        elif path.endswith('.ogg') or path.endswith('.ogv'):
            return 'video/ogg'
        elif path.endswith('.vtt'):
            return 'text/vtt'
        elif path.endswith('.json'):
            return 'application/json'
        
        return content_type or 'application/octet-stream'
    
    def do_GET(self):
        """Handle GET requests with proper error handling for unconfigured endpoints and range requests."""
        # Check if data_live is requested but not configured
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query_params = parsed.query
        
        # Handle API endpoints
        if path == '/api/videos':
            # Parse query parameters
            filepath = None
            if query_params:
                params = dict(param.split('=') for param in query_params.split('&') if '=' in param)
                filepath = params.get('filepath')
                if filepath:
                    filepath = unquote(filepath)
            self.handle_videos_api(filepath=filepath)
            return
        
        if path.startswith('/data_live/') and self.data_live_path is None:
            self.send_error(404, "data_live endpoint not configured")
            return
        
        # Get the translated file path
        file_path = self.translate_path(self.path)
        
        # Check if it's a file (not a directory)
        if os.path.isfile(file_path):
            self.handle_file_request(file_path)
        else:
            # Use default behavior for directories and other files
            super().do_GET()
    
    def handle_file_request(self, file_path: str):
        """Handle file requests with Range request support for video streaming."""
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                self.send_error(404, "File not found")
                return
            
            file_size = os.path.getsize(file_path)
            
            # Parse Range header if present
            range_header = self.headers.get('Range')
            if range_header:
                # Handle Range request (for video streaming)
                byte_range = self.parse_range_header(range_header, file_size)
                if byte_range:
                    start, end = byte_range
                    self.send_range_response(file_path, start, end, file_size)
                    return
                else:
                    # Invalid range - send 416 Range Not Satisfiable
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{file_size}')
                    self.end_headers()
                    return
            
            # No range request - send full file
            self.send_full_file(file_path, file_size)
            
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Client disconnected - this is normal, especially for large files
            # Just ignore the error
            pass
        except Exception as e:
            try:
                self.send_error(500, f"Internal server error: {str(e)}")
            except (BrokenPipeError, ConnectionResetError, OSError):
                # Client already disconnected, can't send error
                pass
    
    def parse_range_header(self, range_header: str, file_size: int) -> Optional[tuple]:
        """Parse Range header and return (start, end) tuple or None if invalid."""
        # Range header format: "bytes=start-end" or "bytes=start-" or "bytes=-suffix"
        match = re.match(r'bytes=(\d*)-(\d*)', range_header)
        if not match:
            return None
        
        start_str = match.group(1)
        end_str = match.group(2)
        
        # Handle suffix range: "bytes=-500" means last 500 bytes
        if not start_str and end_str:
            suffix = int(end_str)
            if suffix <= 0 or suffix > file_size:
                return None
            start = file_size - suffix
            end = file_size - 1
        # Handle range with start: "bytes=500-" or "bytes=500-1000"
        elif start_str:
            start = int(start_str)
            if start < 0:
                start = 0
            if start >= file_size:
                return None  # Start beyond file size
            
            if end_str:
                end = int(end_str)
                # Clamp end to file size
                if end >= file_size:
                    end = file_size - 1
            else:
                end = file_size - 1
            
            if start > end:
                return None
        else:
            return None
        
        return (start, end)
    
    def send_range_response(self, file_path: str, start: int, end: int, file_size: int):
        """Send a 206 Partial Content response for range requests."""
        content_length = end - start + 1
        
        try:
            self.send_response(206)
            self.send_header('Content-Type', self.guess_type(file_path))
            self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
            self.send_header('Content-Length', str(content_length))
            self.send_header('Accept-Ranges', 'bytes')
            self.end_headers()
            
            # Stream the file in chunks
            with open(file_path, 'rb') as f:
                f.seek(start)
                remaining = content_length
                chunk_size = 8192  # 8KB chunks
                
                while remaining > 0:
                    try:
                        chunk = f.read(min(chunk_size, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        # Client disconnected during streaming
                        break
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Client disconnected before or during response
            pass
    
    def send_full_file(self, file_path: str, file_size: int):
        """Send a full file response (200 OK) with streaming support."""
        try:
            self.send_response(200)
            self.send_header('Content-Type', self.guess_type(file_path))
            self.send_header('Content-Length', str(file_size))
            self.send_header('Accept-Ranges', 'bytes')
            self.end_headers()
            
            # Stream the file in chunks
            with open(file_path, 'rb') as f:
                chunk_size = 8192  # 8KB chunks
                while True:
                    try:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        # Client disconnected during streaming
                        break
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Client disconnected before or during response
            pass
    
    def translate_path(self, path: str) -> str:
        """Translate URL path to filesystem path."""
        # Remove query string and fragment
        parsed = urlparse(path)
        path = unquote(parsed.path)
        
        # Handle /data/ endpoint
        if path.startswith('/data/'):
            relative_path = path[6:]  # Remove '/data/' prefix
            if not relative_path:
                relative_path = ''
            full_path = os.path.join(self.data_path, relative_path)
            return os.path.normpath(full_path)
        
        # Handle /data_live/ endpoint
        if path.startswith('/data_live/'):
            # This should only be reached if data_live_path is configured
            # (do_GET handles the unconfigured case)
            relative_path = path[11:]  # Remove '/data_live/' prefix
            if not relative_path:
                relative_path = ''
            full_path = os.path.join(self.data_live_path, relative_path)
            return os.path.normpath(full_path)
        
        # Default: serve from website root
        # Remove leading slash
        if path.startswith('/'):
            path = path[1:]
        
        # If path is empty, serve index.html
        if not path:
            path = 'index.html'
        
        full_path = os.path.join(self.website_root, path)
        return os.path.normpath(full_path)
    
    def end_headers(self):
        """Add CORS headers to allow cross-origin requests."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Range, Content-Range')
        super().end_headers()
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Range, Content-Range')
        self.send_header('Access-Control-Max-Age', '86400')
        self.end_headers()
    
    def do_HEAD(self):
        """Handle HEAD requests (used by browsers to check file info)."""
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path.startswith('/data_live/') and self.data_live_path is None:
            self.send_error(404, "data_live endpoint not configured")
            return
        
        file_path = self.translate_path(self.path)
        if os.path.isfile(file_path):
            try:
                file_size = os.path.getsize(file_path)
                self.send_response(200)
                self.send_header('Content-Type', self.guess_type(file_path))
                self.send_header('Content-Length', str(file_size))
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()
            except Exception as e:
                self.send_error(500, f"Internal server error: {str(e)}")
        else:
            super().do_HEAD()
    
    def log_message(self, format, *args):
        """Override to use a cleaner log format and suppress BrokenPipeError logs."""
        # Suppress logging for BrokenPipeError (normal client disconnects)
        if 'Broken pipe' not in str(args):
            logger = logging.getLogger(__name__)
            logger.info(f"{format % args}")
    
    def handle_one_request(self):
        """Override to catch and suppress BrokenPipeError exceptions."""
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            # Client disconnected - this is normal, especially for large files
            # Don't log these as errors
            pass
    
    @staticmethod
    def scan_videos(data_path: str, show_progress: bool = False) -> List[Dict]:
        """Scan data directory for videos and return list with metadata."""
        videos = []
        data_path_obj = Path(data_path)
        
        if not data_path_obj.exists():
            return []
        
        # Find all *_info.json files first to get count
        info_files = list(data_path_obj.rglob('*_info.json'))
        total_files = len(info_files)
        
        # Use tqdm for progress bar if requested
        file_iterator = tqdm(info_files, desc="Scanning videos", unit="file", disable=not show_progress) if show_progress else info_files
        
        # Recursively find all *_info.json files
        for info_file in file_iterator:
            try:
                # Read the info.json file
                with open(info_file, 'r', encoding='utf-8') as f:
                    info_data = json.load(f)
                
                # Get the relative path from data_path
                relative_path = info_file.relative_to(data_path_obj)
                # Remove _info.json suffix to get the base path
                base_path = str(relative_path)[:-10]  # Remove '_info.json'
                # Convert to forward slashes for URL
                url_path = base_path.replace(os.sep, '/')
                
                # Check if corresponding video file exists
                video_file = info_file.parent / f"{info_file.stem[:-5]}.mp4"  # Remove '_info' from stem
                if not video_file.exists():
                    continue
                
                # Extract metadata
                video_info = {
                    'path': f"data/{url_path}",
                    'title': info_data.get('title', 'Unknown Title'),
                    'recorded_at': info_data.get('recorded_at', ''),
                    'duration': info_data.get('duration', ''),
                    'user_name': info_data.get('user_name', ''),
                    'id': info_data.get('id', ''),
                }
                
                videos.append(video_info)
            except (json.JSONDecodeError, IOError, OSError) as e:
                # Skip files that can't be read or parsed
                continue
        
        # Sort by recorded_at date (newest first)
        videos.sort(key=lambda x: x.get('recorded_at', ''), reverse=True)
        
        return videos
    
    def get_list_directory(self, username: Optional[str] = None, month: Optional[str] = None) -> List[Dict]:
        """Get list of directories (users, months, or videos) depending on path depth."""
        # Create cache key based on parameters
        cache_key = f"dir_{username or ''}_{month or ''}"
        current_time = time.time()
        
        # Check if cache is still valid
        if cache_key in CustomHTTPRequestHandler._list_cache:
            cached_data, cache_timestamp = CustomHTTPRequestHandler._list_cache[cache_key]
            if (current_time - cache_timestamp) < CustomHTTPRequestHandler._cache_ttl:
                return cached_data
        
        # Cache miss or expired - build the list
        data_path_obj = Path(self.data_path)
        
        if not data_path_obj.exists():
            items = []
            CustomHTTPRequestHandler._list_cache[cache_key] = (items, current_time)
            return items
        
        items = []
        
        if month and username:
            # Get videos in a specific month folder
            month_path = data_path_obj / username.lower() / month
            if month_path.exists() and month_path.is_dir():
                # Find all *_info.json files in this month folder
                for info_file in month_path.glob('*_info.json'):
                    try:
                        # Read the info.json file
                        with open(info_file, 'r', encoding='utf-8') as f:
                            info_data = json.load(f)
                        
                        # Get the relative path from data_path
                        relative_path = info_file.relative_to(data_path_obj)
                        # Remove _info.json suffix to get the base path
                        base_path = str(relative_path)[:-10]  # Remove '_info.json'
                        # Convert to forward slashes for URL
                        url_path = base_path.replace(os.sep, '/')
                        
                        # Check if corresponding video file exists
                        video_file = info_file.parent / f"{info_file.stem[:-5]}.mp4"  # Remove '_info' from stem
                        if not video_file.exists():
                            continue
                        
                        # Check for additional files
                        base_name = info_file.stem[:-5]  # Remove '_info' from stem
                        chat_json_file = info_file.parent / f"{base_name}_chat.json"
                        chat_mp4_file = info_file.parent / f"{base_name}_chat.mp4"
                        vtt_file = info_file.parent / f"{base_name}.vtt"
                        
                        # Extract metadata
                        items.append({
                            'path': f"data/{url_path}",
                            'title': info_data.get('title', 'Unknown Title'),
                            'recorded_at': info_data.get('recorded_at', ''),
                            'duration': info_data.get('duration', ''),
                            'user_name': info_data.get('user_name', ''),
                            'id': info_data.get('id', ''),
                            'has_vod': video_file.exists(),
                            'has_chat_json': chat_json_file.exists(),
                            'has_chat_render': chat_mp4_file.exists(),
                            'has_vtt': vtt_file.exists(),
                        })
                    except (json.JSONDecodeError, IOError, OSError):
                        continue
                
                # Sort by recorded_at date (newest first)
                items.sort(key=lambda x: x.get('recorded_at', ''), reverse=True)
        
        elif username:
            # Get months for a specific user
            user_path = data_path_obj / username.lower()
            if user_path.exists() and user_path.is_dir():
                for item in user_path.iterdir():
                    if item.is_dir():
                        # Count video files in this directory
                        video_files = list(item.glob('*_info.json'))
                        num_files = len(video_files)
                        if num_files > 0:
                            items.append({
                                'path': f"data/{username.lower()}/{item.name}/",
                                'title': f"{item.name} - {num_files} files",
                                'recorded_at': '',
                                'duration': '',
                                'user_name': username,
                                'id': '',
                            })
                
                # Sort in reverse alphabetical order (newest first for date-based folders)
                items.sort(key=lambda x: x['title'].lower(), reverse=True)
        
        else:
            # Get all user directories (top level)
            for item in data_path_obj.iterdir():
                if item.is_dir():
                    # Count subdirectories (month folders) - don't search for files to avoid HDD wakeup
                    subdirs = [d for d in item.iterdir() if d.is_dir()]
                    num_folders = len(subdirs)
                    if num_folders > 0:
                        items.append({
                            'path': f"data/{item.name}/",
                            'title': f"{item.name} - {num_folders} folders",
                            'recorded_at': '',
                            'duration': '',
                            'user_name': item.name,
                            'id': '',
                        })
            
            # Sort alphabetically by folder name
            items.sort(key=lambda x: x['title'].lower())
        
        # Update cache
        CustomHTTPRequestHandler._list_cache[cache_key] = (items, current_time)
        
        return items
    
    def handle_videos_api(self, filepath: Optional[str] = None):
        """Handle /api/videos endpoint to return list of available videos, months, or user folders."""
        try:
            # Parse filepath to determine what to return
            username = None
            month = None
            
            if filepath:
                # Extract parts from path like "data/username/month/" or "data/username/"
                parts = [p for p in filepath.split('/') if p]  # Remove empty parts
                if len(parts) >= 2 and (parts[0] == 'data' or parts[0] == 'data_live'):
                    username = parts[1]
                    if len(parts) >= 3:
                        month = parts[2]
            
            # Determine what to return based on path depth
            if month and username:
                # Path is data/username/month/ - return videos in that month
                items = self.get_list_directory(username=username, month=month)
            elif username:
                # Path is data/username/ - return months for that user
                items = self.get_list_directory(username=username)
            else:
                # No path or just data/ - return user directories
                items = self.get_list_directory()
            
            response_data = json.dumps(items, indent=2).encode('utf-8')
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response_data)))
            self.end_headers()
            self.wfile.write(response_data)
        except Exception as e:
            try:
                error_msg = json.dumps({'error': str(e)}).encode('utf-8')
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(error_msg)))
                self.end_headers()
                self.wfile.write(error_msg)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Host a web server for the video editor interface'
    )
    parser.add_argument(
        '--data',
        type=str,
        required=True,
        help='Local filesystem path to serve at /data/ endpoint'
    )
    parser.add_argument(
        '--data-live',
        type=str,
        default=None,
        help='Local filesystem path to serve at /data_live/ endpoint (optional)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='Port to run the web server on (default: 8000)'
    )
    parser.add_argument(
        '--host',
        type=str,
        default='127.0.0.1',
        help='Host to bind the server to (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    return parser.parse_args()


def run_task(args: argparse.Namespace) -> None:
    """Run the web server."""
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    coloredlogs.install(level=log_level, fmt='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger(__name__)
    
    # Get the website directory (relative to this script)
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    website_root = os.path.join(script_dir, 'website')
    
    # Validate paths
    if not os.path.isdir(website_root):
        logger.error(f"Website directory not found: {website_root}")
        sys.exit(1)
    
    if not os.path.isdir(args.data):
        logger.error(f"Data directory not found: {args.data}")
        sys.exit(1)
    
    if args.data_live is not None and not os.path.isdir(args.data_live):
        logger.error(f"Data live directory not found: {args.data_live}")
        sys.exit(1)
    
    # Create handler class with the paths
    def handler_factory(*args_factory, **kwargs):
        return CustomHTTPRequestHandler(
            *args_factory,
            website_root=website_root,
            data_path=os.path.abspath(args.data),
            data_live_path=os.path.abspath(args.data_live) if args.data_live else None,
            **kwargs
        )
    
    # Create and start server
    server = HTTPServer((args.host, args.port), handler_factory)
    
    data_path_abs = os.path.abspath(args.data)
    
    logger.info(f"Starting web server on http://{args.host}:{args.port}")
    logger.info(f"  Website root: {website_root}")
    logger.info(f"  /data/ -> {data_path_abs}")
    if args.data_live:
        logger.info(f"  /data_live/ -> {os.path.abspath(args.data_live)}")
    logger.info("Press Ctrl+C to stop the server")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()

