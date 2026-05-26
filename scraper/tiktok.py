# tiktok.py
# TikTok Scraper by Query
# Video -> Comments -> Nested Replies
# Updated 26th May 2026, 11:21AM

import os
import json
import time
import requests

from datetime import datetime, timezone
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

# -----------------------------------
# API CONFIG
# -----------------------------------

API_TOKEN = os.getenv("TIKTOK_APIFY_TOKEN")

# -----------------------------------
# SEARCH QUERIES
# -----------------------------------

QUERIES = [
    "Rafizi Ramli",
    "Nik Nazmi",
    "Parti Bersama",
    "Parti Bersama Malaysia",
]

# -----------------------------------
# SCRAPER CONFIG
# -----------------------------------

RESULTS_PER_PAGE = 30

TOP_LEVEL_COMMENTS_PER_POST = 20

PROXY_COUNTRY = "MY"

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_FILE = (
    f"./data/tiktok/tiktok_output_{timestamp}.json"
)

dataset = []

seen_videos = set()

# -----------------------------------
# APIFY HELPERS
# -----------------------------------

def start_actor_run(payload):

    url = (
        "https://api.apify.com/v2/acts/"
        "clockworks~tiktok-scraper/runs"
    )

    params = {
        "token": API_TOKEN
    }

    response = requests.post(
        url,
        params=params,
        json=payload
    )

    response.raise_for_status()

    return response.json()["data"]["id"]


def wait_for_run(run_id):

    url = (
        f"https://api.apify.com/v2/actor-runs/{run_id}"
    )

    params = {
        "token": API_TOKEN
    }

    while True:

        response = requests.get(
            url,
            params=params
        )

        response.raise_for_status()

        data = response.json()["data"]

        status = data["status"]

        if status == "SUCCEEDED":

            return data["defaultDatasetId"]

        if status in [
            "FAILED",
            "ABORTED",
            "TIMED-OUT"
        ]:

            raise Exception(
                f"Run failed: {status}"
            )

        time.sleep(3)


def fetch_dataset(dataset_id):

    url = (
        f"https://api.apify.com/v2/datasets/"
        f"{dataset_id}/items"
    )

    params = {
        "token": API_TOKEN
    }

    response = requests.get(
        url,
        params=params
    )

    response.raise_for_status()

    return response.json()


def run_actor(payload):

    run_id = start_actor_run(payload)

    dataset_id = wait_for_run(run_id)

    data = fetch_dataset(dataset_id)

    return data

# -----------------------------------
# COMMENT TREE
# -----------------------------------

def normalize_comment(comment):

    ts = comment.get("createTime")

    create_time = None

    if ts:

        create_time = datetime.fromtimestamp(
            ts,
            tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")

    return {

        "comment_id":
            comment.get("cid"),

        "parent_comment_id":
            comment.get("repliesToId"),

        "text":
            comment.get("text"),

        "user_id":
            comment.get("uid"),

        "username":
            comment.get("uniqueId"),
        
        "user_permalink":
            (
                "https://www.tiktok.com/@"
                f"{comment.get('uid')}"
            ),

        "likes":
            comment.get("diggCount"),

        "reply_count":
            comment.get("replyCommentTotal"),

        "create_time":
            create_time,

        "replies": []
    }


def build_comment_tree(comments):

    comment_map = {}

    root_comments = []

    # normalize
    for comment in comments:

        normalized = normalize_comment(comment)

        comment_map[
            normalized["comment_id"]
        ] = normalized

    # build hierarchy
    for comment_id, comment in comment_map.items():

        parent_id = comment.get(
            "parent_comment_id"
        )

        # top-level comment
        if not parent_id:

            root_comments.append(comment)

        # nested reply
        elif parent_id in comment_map:

            comment_map[parent_id][
                "replies"
            ].append(comment)

    return root_comments

# -----------------------------------
# MAIN PIPELINE
# -----------------------------------

for query in QUERIES:

    print(f"\n=== SEARCHING QUERY ===")
    print(query)

    payload = {

        "searchQueries": [query],

        "resultsPerPage":
            RESULTS_PER_PAGE,

        "proxyCountryCode":
            PROXY_COUNTRY,

        "topLevelCommentsPerPost":
            TOP_LEVEL_COMMENTS_PER_POST,
        
        "maxRepliesPerComment":
            10,
    }

    try:

        videos = run_actor(payload)

    except Exception as e:

        print("Failed query:", query)
        print(e)

        continue

    print(f"Found {len(videos)} videos")

    #for v in tqdm(videos):
    for idx, v in enumerate(
        tqdm(
            videos,
            desc=f"{query}",
            unit="video"
        ),
        start=1
    ):

        video_id = v.get("id")

        if not video_id:
            continue

        # deduplicate
        if video_id in seen_videos:
            continue

        seen_videos.add(video_id)

        ts = v.get("createTime")

        create_time = None

        if ts:

            create_time = datetime.fromtimestamp(
                ts,
                tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S")

        # print(
        #     f"Processing video: {video_id}"
        # )
        video_desc = (
            (v.get("text") or "")
            .replace("\n", " ")
            [:80]
        )

        video_date = "unknown"

        if create_time:
            video_date = create_time

        print(
            f"[{idx}/{len(videos)}] "
            f"{video_date} | "
            f"{video_id} | "
            f"{video_desc}"
        )

        # -----------------------------------
        # COMMENTS
        # -----------------------------------

        raw_comments = []

        comments_url = v.get(
            "commentsDatasetUrl"
        )

        if comments_url:

            try:

                response = requests.get(
                    comments_url
                )

                response.raise_for_status()

                raw_comments = response.json()

            except Exception as e:

                print(
                    f"Failed comments for "
                    f"{video_id}: {e}"
                )

        comments = build_comment_tree(
            raw_comments
        )

        # -----------------------------------
        # VIDEO OBJECT
        # -----------------------------------

        video_object = {

            "query": query,

            "video": {

                "video_id":
                    video_id,

                "video_url":
                    v.get("webVideoUrl"),

                "description":
                    v.get("text"),

                "description_paragraphs": [

                    p.strip()

                    for p in (
                        v.get("text") or ""
                    ).split("\n")

                    if p.strip()
                ],

                "create_time":
                    create_time,

                "author": {

                    "username":
                        v.get(
                            "authorMeta",
                            {}
                        ).get("name"),

                    "display_name":
                        v.get(
                            "authorMeta",
                            {}
                        ).get("nickName"),
                    
                    "user_id":
                        v.get(
                            "authorMeta",
                            {}
                        ).get("id"),

                    "user_permalink":
                        (
                            "https://www.tiktok.com/@"
                            f"{v.get('authorMeta', {}).get('id')}"
                        ),

                },

                "metrics": {

                    "likes":
                        v.get("diggCount"),

                    "comments":
                        v.get("commentCount"),

                    "shares":
                        v.get("shareCount"),

                    "views":
                        v.get("playCount"),

                    "bookmarks":
                        v.get("collectCount"),

                },

                "hashtags":
                    v.get("hashtags", []),

                "mentions":
                    v.get("mentions", []),

                "video_duration":
                    v.get("videoMeta", {}).get(
                        "duration"
                    ),

                "platform":
                    "tiktok",
            },

            "comments": comments
        }

        dataset.append(video_object)

# -----------------------------------
# SAVE
# -----------------------------------

os.makedirs(
    "./data/tiktok",
    exist_ok=True
)

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        dataset,
        f,
        indent=2,
        ensure_ascii=False
    )

print(
    f"\nCollected {len(dataset)} videos"
)

print(
    f"Saved to: {OUTPUT_FILE}"
)