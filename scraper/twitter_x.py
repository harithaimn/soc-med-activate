# Twitter/X Scraper by Query
# Tweet -> Replies -> Nested Replies
# Updated 26th May 2026

import os
import requests
import json
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# -----------------------------------
# API CONFIG
# -----------------------------------

API_KEY = os.getenv("GETXAPI_KEY")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}"
}

SEARCH_URL = (
    "https://api.getxapi.com/twitter/tweet/advanced_search"
)

TWEET_DETAILS_URL = (
    "https://api.getxapi.com/twitter/tweet/detail"
)

REPLIES_URL = (
    "https://api.getxapi.com/twitter/tweet/replies"
)

# -----------------------------------
# SEARCH QUERIES
# -----------------------------------

QUERIES = [
    '"Rafizi Ramli"',
    '"Nik Nazmi"',
    '"Parti Bersama"',
    '"Parti Bersama Malaysia"',
]

DATES = [
    ("2026-04-25", "2026-05-26"),
]

# -----------------------------------
# SCRAPER CONFIG
# -----------------------------------

SEARCH_PAGES = 1
REPLY_PAGES = 1

MIN_REPLY_COUNT = 3

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_FILE = (
    f"./data/twitter/twitter_output_{timestamp}.json"
)

dataset = []

seen_tweets = set()

# -----------------------------------
# SAFE REQUEST
# -----------------------------------

def safe_request(
    url,
    params=None,
    retries=3,
    sleep_time=2
):

    for attempt in range(retries):

        try:

            time.sleep(sleep_time)

            response = requests.get(
                url,
                headers=HEADERS,
                params=params,
                timeout=30
            )

            if response.status_code == 429:

                print("Rate limited. Sleeping 30s...")
                time.sleep(30)
                continue

            if response.status_code != 200:

                print(
                    "HTTP Error:",
                    response.status_code,
                    response.text
                )

                return None

            return response.json()

        except requests.exceptions.Timeout:

            print("Timeout. Retrying...")
            time.sleep(5)

        except requests.exceptions.RequestException as e:

            print("Request failed:", e)
            time.sleep(5)

    return None

# -----------------------------------
# SEARCH TWEETS
# -----------------------------------

def fetch_tweets(query):

    all_tweets = []

    cursor = None

    for page in range(SEARCH_PAGES):

        params = {
            "q": query,
            "product": "Top"
        }

        if cursor:
            params["cursor"] = cursor

        data = safe_request(
            SEARCH_URL,
            params=params
        )

        if not data:
            break

        tweets = data.get("tweets", [])

        if not tweets:
            break

        all_tweets.extend(tweets)

        if not data.get("has_more"):
            break

        cursor = data.get("next_cursor")

    return all_tweets

# -----------------------------------
# FETCH TWEET
# -----------------------------------

def fetch_tweet(tweet_id):

    params = {
        "id": tweet_id
    }

    data = safe_request(
        TWEET_DETAILS_URL,
        params=params
    )

    if not data:
        return None

    return data.get("data")

# -----------------------------------
# FETCH REPLIES
# -----------------------------------

def fetch_replies(tweet_id):

    all_replies = []

    cursor = None

    for page in range(REPLY_PAGES):

        params = {
            "id": tweet_id
        }

        if cursor:
            params["cursor"] = cursor

        data = safe_request(
            REPLIES_URL,
            params=params
        )

        if not data:
            break

        replies = data.get("replies", [])

        if not replies:
            break

        all_replies.extend(replies)

        if not data.get("has_more"):
            break

        cursor = data.get("next_cursor")

    return all_replies

# -----------------------------------
# BUILD REPLY TREE
# -----------------------------------

def normalize_reply(reply):

    return {

        "tweet_id":
            reply.get("id"),

        "text":
            reply.get("text"),

        "created_at":
            reply.get("createdAt"),

        "lang":
            reply.get("lang"),

        "source":
            reply.get("source"),

        "conversation_id":
            reply.get("conversationId"),

        "in_reply_to_id":
            reply.get("inReplyToId"),

        "is_reply":
            reply.get("isReply"),

        "quoted_tweet":
            reply.get("quoted_tweet"),

        "author": {

            "username":
                reply.get("author", {}).get("userName"),

            "display_name":
                reply.get("author", {}).get("name"),

            "user_id":
                reply.get("author", {}).get("id"),

            "profile_url":
                (
                    "https://x.com/"
                    f"{reply.get('author', {}).get('userName')}"
                ),

            "followers":
                reply.get("author", {}).get("followers"),
        },

        "metrics": {

            "reply_count":
                reply.get("replyCount"),

            "retweet_count":
                reply.get("retweetCount"),

            "like_count":
                reply.get("likeCount"),

            "quote_count":
                reply.get("quoteCount"),

            "bookmark_count":
                reply.get("bookmarkCount"),

            "view_count":
                reply.get("viewCount"),
        },

        "media":
            reply.get("media", []),

        "tweet_url":
            reply.get("url"),

        "replies": []
    }


def build_reply_tree(replies, root_tweet_id):

    reply_map = {}

    root_replies = []

    for reply in replies:

        normalized = normalize_reply(reply)

        reply_map[
            normalized["tweet_id"]
        ] = normalized

    for reply_id, reply in reply_map.items():

        parent_id = reply.get("in_reply_to_id")

        # direct reply to root tweet
        if parent_id == root_tweet_id:

            root_replies.append(reply)

        # nested reply
        elif parent_id in reply_map:

            reply_map[parent_id]["replies"].append(reply)

    return root_replies


# -----------------------------------
# MAIN PIPELINE
# -----------------------------------

for query in QUERIES:

    print(f"\n=== SEARCHING QUERY: {query} ===")

    for start_date, end_date in DATES:

        full_query = (
            f"{query} "
            f"since:{start_date} "
            f"until:{end_date}"
        )

        print(full_query)

        tweets = fetch_tweets(full_query)

        print(f"Found {len(tweets)} tweets")

        for tweet in tweets:

            tweet_id = tweet.get("id")

            if not tweet_id:
                continue

            # avoid duplicates
            if tweet_id in seen_tweets:
                continue

            seen_tweets.add(tweet_id)

            print(f"Fetching tweet details: {tweet_id}")

            tweet_data = fetch_tweet(tweet_id)

            if not tweet_data:
                continue

            reply_count = tweet_data.get("replyCount", 0)

            print(
                f"Processing Tweet: "
                f"{tweet_id} "
                f"| replies={reply_count}"
            )

            replies = []

            if reply_count >= MIN_REPLY_COUNT:

                flat_replies = fetch_replies(tweet_id)

                replies = build_reply_tree(
                    flat_replies,
                    tweet_id
                )

            tweet_object = {

                "query": query,

                "tweet": {

                    "tweet_id":
                        tweet_data.get("id"),

                    "text":
                        tweet_data.get("text"),

                    "created_at":
                        tweet_data.get("createdAt"),

                    "lang":
                        tweet_data.get("lang"),

                    "source":
                        tweet_data.get("source"),

                    "conversation_id":
                        tweet_data.get("conversationId"),

                    "in_reply_to_id":
                        tweet_data.get("inReplyToId"),

                    "is_reply":
                        tweet_data.get("isReply"),

                    "quoted_tweet":
                        tweet_data.get("quoted_tweet"),

                    "author": {

                        "username":
                            tweet_data.get("author", {}).get("userName"),

                        "display_name":
                            tweet_data.get("author", {}).get("name"),

                        "user_id":
                            tweet_data.get("author", {}).get("id"),

                        "profile_url":
                            (
                                "https://x.com/"
                                f"{tweet_data.get('author', {}).get('userName')}"
                            ),

                        "followers":
                            tweet_data.get("author", {}).get("followers"),
                    },

                    "metrics": {

                        "reply_count":
                            tweet_data.get("replyCount"),

                        "retweet_count":
                            tweet_data.get("retweetCount"),

                        "like_count":
                            tweet_data.get("likeCount"),

                        "quote_count":
                            tweet_data.get("quoteCount"),

                        "bookmark_count":
                            tweet_data.get("bookmarkCount"),

                        "view_count":
                            tweet_data.get("viewCount"),
                    },

                    "media":
                        tweet_data.get("media", []),

                    "tweet_url":
                        (
                            "https://x.com/"
                            f"{tweet_data.get('author', {}).get('userName')}"
                            f"/status/{tweet_id}"
                        )
                },

                "replies": replies
            }

            dataset.append(tweet_object)

# -----------------------------------
# SAVE
# -----------------------------------

os.makedirs("./data/twitter", exist_ok=True)

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

print(f"\nCollected {len(dataset)} tweets")
print(f"Saved to: {OUTPUT_FILE}")