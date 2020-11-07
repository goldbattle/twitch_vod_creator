# Import general libraries
import re
import os
import codecs
import requests
import json
import time
import signal

# global variable which sets if we should terminate
terminated_requested = False


def signal_handler(sig, frame):
    global terminated_requested
    terminated_requested = True
    print('terminate requested!!!!!')


def setup_signal_handle():
    signal.signal(signal.SIGINT, signal_handler)


def get_vod_moments(void_id):
    # get response
    try:
        gql_response = get_vod_graphql_info(void_id)
        gql_obj = json.loads(gql_response)
        moments = []
        for moment in gql_obj["data"]["video"]["moments"]["edges"]:
            data = {
                "id": moment["node"]["details"]["game"]["id"],
                "name": moment["node"]["details"]["game"]["displayName"],
                "duration": int(moment["node"]["durationMilliseconds"] / 1000.0),
                "offset": int(moment["node"]["positionMilliseconds"] / 1000.0),
            }
            moments.append(data)
        return moments
    except Exception as e:
        # print(e)
        return []


def get_vod_graphql_info(vod_id):
    # seems to just be a default client id
    # https://dev.twitch.tv/docs/authentication
    client_id = "kimne78kx3ncx6brgo4mv6wki5h1ko"
    # auth = "xxxxxx"

    # formulate the graphql query format
    # https://graphiql-online.com/graphiql
    # https://api.twitch.tv/gql
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
              }
            }
          }
        }
      }
    '''
    variables = {'videoId': vod_id}
    url = 'https://api.twitch.tv/gql'
    response = requests.post(
        url,
        json={'query': query, 'variables': variables},
        # headers={"Client-ID": client_id, "Authorization": "OAuth "+auth}
        headers={"Client-ID": client_id}
    )
    return response.text
