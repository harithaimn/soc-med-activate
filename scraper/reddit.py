# Reddit Scraper by Query
# One Post -> All Comments -> Nested Replies
# Updated 25th May 2026, 12.31 PM

import requests
import json
import time
from datetime import datetime, UTC, timedelta

HEADERS = {
    "User-Agent": "python:reddit.scraper:v2.0 (by /u/anonymous)"
}

QUERIES = [
    '"Rafizi"',
    '"Rafizi Ramli"',
    '"Nik Nazmi"',
    '"Parti Bersama"',
    '"Parti Bersama Malaysia"',
]

POST_LIMIT = 50
MAX_COMMENT_DEPTH = 10

# last 30 days dynamically
END = datetime.now(UTC)
START = END - timedelta(days=30)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_FILE = (
    f"./data/reddit/reddit_output_{timestamp}.json"
)

SEARCH_URL = "https://api.reddit.com/search"

dataset = []
seen_posts = set()


def safe_request(url, params=None, retries=5):

    for attempt in range(retries):

        try:

            time.sleep(2)
            response = requests.get(
                url,
                headers=HEADERS,
                params=params,
                timeout=30
            )

            if response.status_code == 429:
                print("Rate limited. Sleeping 15s...")
                time.sleep(15)
                continue

            if response.status_code != 200:
                print(f"HTTP Error: {response.status_code}")
                return None

            return response.json()

        except requests.exceptions.Timeout:
            print("Timeout. Retrying...")
            time.sleep(5)

        except requests.exceptions.RequestException as e:
            print("Request failed:", e)
            time.sleep(5)

    return None


def get_post_image(post):

    preview = post.get("preview")

    if preview:

        images = preview.get("images")

        if images and len(images) > 0:

            source = images[0].get("source")

            if source:
                return source.get("url")

    thumbnail = post.get("thumbnail")

    if thumbnail and thumbnail.startswith("http"):
        return thumbnail

    url = post.get("url")

    if url:

        image_extensions = (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif"
        )

        if url.lower().endswith(image_extensions):
            return url

    return None


def extract_comment_tree(comment):

    if comment["kind"] != "t1":
        return None

    data = comment["data"]

    replies = data.get("replies")

    children = []

    if isinstance(replies, dict):

        raw_children = replies["data"]["children"]

        for child in raw_children:

            if child["kind"] == "t1":

                child_comment = extract_comment_tree(child)

                if child_comment:
                    children.append(child_comment)

    comment_object = {
        "parent_id":
            str(data.get("parent_id")).split("_")[-1],

        "parent_type":
            "post"
            if str(data.get("parent_id")).startswith("t3_")
            else "comment",

        "comment_id": data.get("id"),

        "author": data.get("author"),

        "author_url":
            f"https://www.reddit.com/user/{data.get('author')}",

        "body": data.get("body"),

        "score": data.get("score"),

        "reply_count": len(children),

        "created_time": datetime.fromtimestamp(
            data.get("created_utc"),
            UTC
        ).strftime("%Y-%m-%d %H:%M:%S UTC"),

        "comment_permalink":
            f"https://reddit.com{data.get('permalink', '')}",

        "replies": children
    }

    return comment_object


for query in QUERIES:

    print(f"\n=== SEARCHING QUERY: {query} ===")

    after = None

    while True:

        params = {
            "q": query,
            "sort": "new",
            "limit": POST_LIMIT,
            "raw_json": 1,
            "type": "link",
        }

        if after:
            params["after"] = after

        data = safe_request(
            SEARCH_URL,
            params
        )

        if not data:
            break

        posts = data["data"]["children"]

        if not posts:
            break

        all_before_start = True

        for p in posts:

            post = p["data"]

            post_id = post["id"]

            # avoid duplicate posts across queries
            if post_id in seen_posts:
                continue

            seen_posts.add(post_id)

            post_date = datetime.fromtimestamp(
                post["created_utc"],
                UTC
            )

            if post_date >= START:
                all_before_start = False

            # skip newer than range
            if post_date >= END:
                continue

            # skip older than range
            if post_date < START:
                continue

            print(
                f"Processing: {post['title']} "
                f"| {post_date.strftime('%Y-%m-%d')}"
            )

            comments_url = (
                f"https://api.reddit.com/comments/{post_id}"
            )

            comments_data = safe_request(
                comments_url,
                {
                    "raw_json": 1,
                    "depth": MAX_COMMENT_DEPTH,
                    "limit": 500,
                    "sort": "top",
                }
            )

            comments_tree = []

            if comments_data:

                try:

                    top_comments = (
                        comments_data[1]["data"]["children"]
                    )

                    for c in top_comments:

                        parsed_comment = extract_comment_tree(c)

                        if parsed_comment:
                            comments_tree.append(parsed_comment)

                except Exception as e:

                    print("Failed extracting comments:", e)

            post_metadata = {

                "query": query,

                "subreddit": f"r/{post.get('subreddit')}",

                "post_id": post_id,

                "flair": post.get("link_flair_text"),

                "title": post.get("title"),

                "text": post.get("selftext"),

                "author": post.get("author"),

                "author_url":
                    f"https://www.reddit.com/user/{post.get('author')}",

                "score": post.get("score"),

                "upvote_ratio": post.get("upvote_ratio"),

                "num_comments": post.get("num_comments"),

                "created_time": datetime.fromtimestamp(
                    post.get("created_utc"),
                    UTC
                ).strftime("%Y-%m-%d %H:%M:%S UTC"),

                "date": post_date.strftime("%d-%m-%Y"),

                "permalink":
                    f"https://reddit.com{post.get('permalink')}",

                "url": post.get("url"),

                "image_url": get_post_image(post),
            }

            dataset.append({

                "post": post_metadata,

                "comments": comments_tree
            })

            time.sleep(2)

        if all_before_start:
            print("Reached older posts than START date.")
            break

        after = data["data"].get("after")

        if not after:
            break


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

print(f"\nCollected {len(dataset)} posts")
print(f"Saved to: {OUTPUT_FILE}")