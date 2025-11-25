# !/usr/bin/env python3

"""
Twitch API operations module.
Centralizes all Twitch API interactions including users, videos, clips, games, and moments.
"""

import json
import logging
import requests
import twitch

logger = logging.getLogger(__name__)


def get_client(client_id, client_secret):
    """Get authenticated Twitch Helix client."""
    client = twitch.TwitchHelix(client_id=client_id, client_secret=client_secret)
    client.get_oauth()
    return client


def get_users_by_login(client_id, client_secret, login_names):
    """Get user information by login names."""
    client = get_client(client_id, client_secret)
    return client.get_users(login_names=login_names)


def get_user_by_login(client_id, client_secret, login_name):
    """Get a single user by login name."""
    users = get_users_by_login(client_id, client_secret, [login_name])
    for user in users:
        if user["login"].lower() == login_name.lower():
            return user
    return None


def get_videos(client_id, client_secret, user_id=None, video_ids=None, page_size=100):
    """Get videos for a user or by video IDs."""
    client = get_client(client_id, client_secret)
    if video_ids:
        return client.get_videos(video_ids=video_ids)
    elif user_id:
        return client.get_videos(user_id=user_id, page_size=page_size)
    else:
        raise ValueError("Either user_id or video_ids must be provided")


def get_clips(client_id, client_secret, broadcaster_id, started_at=None, ended_at=None, page_size=100):
    """Get clips for a broadcaster."""
    client = get_client(client_id, client_secret)
    kwargs = {"broadcaster_id": broadcaster_id, "page_size": page_size}
    if started_at:
        kwargs["started_at"] = started_at
    if ended_at:
        kwargs["ended_at"] = ended_at
    return client.get_clips(**kwargs)


def get_streams(client_id, client_secret, user_ids):
    """Get stream information for users."""
    client = get_client(client_id, client_secret)
    return client.get_streams(user_ids=user_ids)


def is_user_live(client_id, client_secret, user_id):
    """Check if a user is currently live."""
    streams = get_streams(client_id, client_secret, [user_id])
    return len(streams) == 1


def get_games(client_id, client_secret, game_ids):
    """Get game information by game IDs."""
    client = get_client(client_id, client_secret)
    return client.get_games(game_ids=game_ids)


def _get_vod_graphql_info(vod_id):
    """Get VOD GraphQL information."""
    client_id = "kimne78kx3ncx6brgo4mv6wki5h1ko"
    query = '''
    query Query($videoId: ID) {
        video(id: $videoId) {
          moments(momentRequestType: VIDEO_CHAPTER_MARKERS, types: GAME_CHANGE) {
            pageInfo {
              hasNextPage
            }
            edges {
              node {
                details {
                  ... on GameChangeMomentDetails {
                    game {
                      id
                      displayName
                      name
                    }
                  }
                }
                positionMilliseconds
                durationMilliseconds
                type
              }
            }
          }
        }
      }
    '''
    variables = {'videoId': vod_id}
    url = 'https://gql.twitch.tv/gql'
    response = requests.post(
        url,
        json={'query': query, 'variables': variables},
        headers={"Client-ID": client_id}
    )
    return response.text


def get_vod_moments(vod_id):
    """Get VOD moments (game changes) for a video."""
    try:
        gql_response = _get_vod_graphql_info(vod_id)
        gql_obj = json.loads(gql_response)
        moments = []
        for moment in gql_obj["data"]["video"]["moments"]["edges"]:
            data = {
                "duration": int(moment["node"]["durationMilliseconds"] / 1000.0),
                "offset": int(moment["node"]["positionMilliseconds"] / 1000.0),
            }
            if "details" in moment["node"] and "game" in moment["node"]["details"]:
                data["id"] = moment["node"]["details"]["game"]["id"]
                data["name"] = moment["node"]["details"]["game"]["displayName"]
            else:
                data["id"] = "-1"
                data["name"] = "Unknown"
            if "type" in moment["node"]:
                data["type"] = moment["node"]["type"]
            moments.append(data)
        return moments
    except Exception as e:
        logger.error(f"Error getting VOD moments: {e}")
        return []


def get_vod_moments_from_twitcharchive_string(data):
    """Get VOD moments from TwitchArchive string data."""
    try:
        gql_obj = json.loads(data)
        moments = []
        for moment in gql_obj:
            data = {
                "duration": int(moment["node"]["durationMilliseconds"] / 1000.0),
                "offset": int(moment["node"]["positionMilliseconds"] / 1000.0),
            }
            if "details" in moment["node"] and "game" in moment["node"]["details"]:
                data["id"] = moment["node"]["details"]["game"]["id"]
                data["name"] = moment["node"]["details"]["game"]["displayName"]
            else:
                data["id"] = "-1"
                data["name"] = "Unknown"
            if "type" in moment["node"]:
                data["type"] = moment["node"]["type"]
            moments.append(data)
        return moments
    except Exception as e:
        logger.error(f"Error parsing VOD moments from string: {e}")
        return []


def _get_clip_graphql_info(clip_id):
    """Get clip GraphQL information."""
    client_id = "kd1unb4b3q4t58fwlpcbzcbnm76a8fp"
    query = '''
    query Query($clip_id: ID!) {
        clip(slug: $clip_id) {
            videoOffsetSeconds
            viewCount
            durationSeconds
            video {
                id
            }
        }
      }
    '''
    variables = {'clip_id': clip_id}
    url = 'https://gql.twitch.tv/gql'
    response = requests.post(
        url,
        json={'query': query, 'variables': variables},
        headers={"Client-ID": client_id}
    )
    return response.text


def get_clip_data(clip_id):
    """Get clip data including VOD offset and duration."""
    try:
        gql_response = _get_clip_graphql_info(clip_id)
        gql_obj = json.loads(gql_response)
        if gql_obj["data"]["clip"]["videoOffsetSeconds"] == None:
            logger.warning("clip's VOD was deleted, unable to find offset...")
            return {
                "vod_id": -1,
                "offset": -1,
                "duration": gql_obj["data"]["clip"]["durationSeconds"],
            }
        return {
            "vod_id": gql_obj["data"]["clip"]["video"]["id"],
            "offset": gql_obj["data"]["clip"]["videoOffsetSeconds"],
            "duration": gql_obj["data"]["clip"]["durationSeconds"],
        }
    except Exception as e:
        return {
            "vod_id": -1,
            "offset": -1,
            "duration": -1,
        }


def create_video_data(client_id, client_secret, video_helix):
    """Create a standardized video data dictionary from Helix video object."""
    return {
        'id': video_helix['id'],
        'user_id': video_helix['user_id'],
        'user_name': video_helix['user_name'],
        'title': video_helix['title'],
        'duration': video_helix['duration'],
        'url': video_helix['url'],
        'views': video_helix['view_count'],
        'moments': get_vod_moments(video_helix['id']),
        'muted_segments': (video_helix['muted_segments'] if video_helix['muted_segments'] is not None else []),
        'recorded_at': video_helix['created_at'].strftime('%Y-%m-%dT%H:%M:%SZ'),
    }


def create_clip_data(client_id, client_secret, clip_helix, game_cache=None):
    """Create a standardized clip data dictionary from Helix clip object."""
    if game_cache is None:
        game_cache = {}
    
    # Get game information
    game_title = ""
    if clip_helix.get('game_id'):
        if clip_helix['game_id'] not in game_cache:
            games = get_games(client_id, client_secret, [clip_helix['game_id']])
            if games and clip_helix['game_id'] == games[0]['id']:
                game_cache[games[0]['id']] = games[0]['name']
                game_title = games[0]['name']
        else:
            game_title = game_cache[clip_helix['game_id']]
    
    # Get clip VOD offset data
    clip_data = get_clip_data(clip_helix['id'])
    
    return {
        'id': clip_helix['id'],
        'video_id': clip_helix['video_id'],
        'video_offset': clip_data['offset'],
        'creator_id': clip_helix['creator_id'],
        'creator_name': clip_helix['creator_name'],
        'title': clip_helix['title'],
        'game_id': clip_helix['game_id'],
        'game': game_title,
        'url': clip_helix['url'],
        'view_count': clip_helix['view_count'],
        'duration': clip_data['duration'],
        'created_at': clip_helix['created_at'].strftime('%Y-%m-%d %H:%M:%SZ'),
    }

