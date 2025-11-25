#!/usr/bin/env python3
"""
Twitch VOD Creator - Main CLI entry point.
"""

import sys
import os
import argparse
import importlib.util
from typing import Dict, Callable, Any, Tuple

# Add current directory to path so we can import tasks
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_task_module(module_name: str):
    """Dynamically load a task module by name."""
    module_path = os.path.join(os.path.dirname(__file__), 'tasks', f'{module_name}.py')
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module {module_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Task module mapping (lazy loaded)
TASK_MODULE_MAP = {
    'download_clips': '0_main_clips',
    'download_videos': '0_main_videos',
    'download_single_video': '0_single_video',
    'generate_vtt': '0_main_vtt_generation',
    'web': '1_editor_website',
    'render_clip_comp': '2_render_clip_comp',
    'render_4way': '2_render_4way',
    'render_segments': '2_render_segments',
    'upload_segments': '3_upload_segments',
}

# Command descriptions for help output
COMMAND_DESCRIPTIONS = {
    'download_clips': 'Download Twitch clips (video+chat)from a given set of channels',
    'download_videos': 'Download Twitch VODs (video+chat) for a given set of channels, optionally rendering chat and WebVTT transcriptions',
    'download_single_video': 'Download a single Twitch VOD (video+chat) by ID',
    'generate_vtt': 'Generate any missing WebVTT transcriptions for videos for a given channel',
    'render_clip_comp': 'Download and render clip compilation into single video',
    'render_4way': 'Render 4-way video composite into single video',
    'render_segments': 'Render video segments from created YAML editing file',
    'upload_segments': 'Upload video segments to YouTube via YouTube API',
    'web': 'Host a web server for the video editor interface',
}


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        description='Twitch VOD Creator - Download, process, and render Twitch VODs and clips',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(
        dest='command',
        help='Command to run',
        metavar='<command>'
    )
    
    # Add subcommands with descriptions
    subparsers.add_parser(
        'download_clips',
        help=COMMAND_DESCRIPTIONS['download_clips'],
        description='Download Twitch clips from specified channels'
    )
    
    subparsers.add_parser(
        'download_videos',
        help=COMMAND_DESCRIPTIONS['download_videos'],
        description='Download and process Twitch VODs from specified channels'
    )
    
    subparsers.add_parser(
        'download_single_video',
        help=COMMAND_DESCRIPTIONS['download_single_video'],
        description='Download a single Twitch VOD by its ID'
    )
    
    subparsers.add_parser(
        'generate_vtt',
        help=COMMAND_DESCRIPTIONS['generate_vtt'],
        description='Generate WebVTT transcriptions for videos in a channel'
    )
    
    subparsers.add_parser(
        'render_clip_comp',
        help=COMMAND_DESCRIPTIONS['render_clip_comp'],
        description='Download and render a compilation of clips'
    )
    
    subparsers.add_parser(
        'render_4way',
        help=COMMAND_DESCRIPTIONS['render_4way'],
        description='Render a 4-way video composite with chat overlay'
    )
    
    subparsers.add_parser(
        'render_segments',
        help=COMMAND_DESCRIPTIONS['render_segments'],
        description='Render video segments from a YAML configuration'
    )
    
    subparsers.add_parser(
        'upload_segments',
        help=COMMAND_DESCRIPTIONS['upload_segments'],
        description='Upload rendered video segments to YouTube'
    )
    
    subparsers.add_parser(
        'web',
        help=COMMAND_DESCRIPTIONS['web'],
        description='Host a web server for the video editor interface'
    )
    
    return parser


def main() -> None:
    """Main entry point."""
    parser = create_parser()
    
    # If no arguments provided, show help
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    
    # Check if first argument is a valid command
    first_arg = sys.argv[1] if len(sys.argv) > 1 else None
    
    # If first argument is --help or -h, show help
    if first_arg in ('--help', '-h'):
        parser.print_help()
        sys.exit(0)
    
    # Parse arguments to get the command
    args = parser.parse_args(sys.argv[1:2])
    
    # If first argument is not a valid command, show error
    if first_arg not in TASK_MODULE_MAP:
        if first_arg and not first_arg.startswith('-'):
            # Looks like they tried to use a command that doesn't exist
            print(f"Error: Unknown command '{first_arg}'", file=sys.stderr)
            print(f"\nAvailable commands:", file=sys.stderr)
            for cmd in sorted(TASK_MODULE_MAP.keys()):
                desc = COMMAND_DESCRIPTIONS.get(cmd, '')
                print(f"  {cmd:<25} {desc}", file=sys.stderr)
            sys.exit(1)
        else:
            # They provided arguments without a command
            print("Error: No command specified", file=sys.stderr)
            print(f"\nUsage: {sys.argv[0]} <command> [options]", file=sys.stderr)
            print(f"\nAvailable commands:", file=sys.stderr)
            for cmd in sorted(TASK_MODULE_MAP.keys()):
                desc = COMMAND_DESCRIPTIONS.get(cmd, '')
                print(f"  {cmd:<25} {desc}", file=sys.stderr)
            print(f"\nUse '{sys.argv[0]} --help' for more information.", file=sys.stderr)
            sys.exit(1)
    
    # This should always be set now, but double-check
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    # Check if command exists
    if args.command not in TASK_MODULE_MAP:
        print(f"Error: Unknown command '{args.command}'", file=sys.stderr)
        parser.print_help()
        sys.exit(1)
    
    # Load the task module lazily
    try:
        task_module = load_task_module(TASK_MODULE_MAP[args.command])
    except Exception as e:
        print(f"Error loading task module: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Handle help request
    if len(sys.argv) > 2 and (sys.argv[2] == '--help' or sys.argv[2] == '-h'):
        # Temporarily replace sys.argv to let the task's parser handle --help
        original_argv = sys.argv
        try:
            # Remove the command name, keep --help
            sys.argv = [sys.argv[0]] + sys.argv[2:]
            task_module.parse_args()
        except SystemExit:
            pass
        finally:
            sys.argv = original_argv
        return
    
    # Run the task
    original_argv = sys.argv
    try:
        # Remove the command name from argv
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        # Parse arguments using the task's parser
        task_args = task_module.parse_args()
        # Run the task
        task_module.run_task(task_args)
    finally:
        sys.argv = original_argv


if __name__ == '__main__':
    main()
