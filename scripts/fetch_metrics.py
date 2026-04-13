#!/usr/bin/env python3
"""
フェッチャー — Threads エンゲージメントデータ取得
post-history.md の engagement_fetched: false かつ投稿から24時間以上の投稿を対象に
Threads API でいいね・リプライ・リポスト・閲覧数を取得して追記する。
"""
import os
import re
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST          = timezone(timedelta(hours=9))
BASE_DIR     = Path(__file__).parent.parent
HISTORY_FILE = BASE_DIR / "knowledge" / "post-history.md"

ACCESS_TOKEN = os.environ.get(
    "THREADS_ACCESS_TOKEN",
    "THAAZAKkxyW4IVBUVNRQjRITlY3WlJ5dVFpUmJhVVJjdG8xZAVFYamdZAblJNYi1kUmxHWk1xSjhxekp2Q0daYXRUUm5TVzlTckcyNW5TVmlZAMW9WMnAxeUxKc0k1RmFwaHluVDNtbkx3R3dSOE93bkdzcEtkMEIzSkFRSUI0ZAzQ0d0JKRmJpODFDeTM4ZA3dKRlEZD"
)
BASE_URL = "https://graph.threads.net/v1.0"


def load_env():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def parse_history(path: Path) -> list:
    """post-history.md からエントリを解析して返す"""
    if not path.exists():
        return []

    text    = path.read_text(encoding="utf-8")
    # `---` ブロックで分割
    blocks  = re.split(r"\n---\n", text)
    entries = []

    for block in blocks:
        block = block.strip()
        if not block or "post_id:" not in block:
            continue

        def extract(key):
            m = re.search(rf"^{key}:\s*(.+)$", block, re.MULTILINE)
            return m.group(1).strip() if m else ""

        entries.append({
            "raw":              block,
            "post_id":          extract("post_id"),
            "posted_at":        extract("posted_at"),
            "engagement_fetched": extract("engagement_fetched").lower() == "true",
        })

    return entries


def fetch_metrics(post_id: str) -> dict:
    """Threads API でメトリクスを取得"""
    url    = f"{BASE_URL}/{post_id}"
    params = {
        "fields": "likes,replies,reposts,quotes,views",
        "access_token": ACCESS_TOKEN,
    }
    r = requests.get(url, params=params, timeout=15)
    if r.status_code != 200:
        return {"error": f"{r.status_code}: {r.text[:100]}"}
    return r.json()


def fetch_replies(post_id: str) -> list:
    """Threads API でリプライを取得"""
    url    = f"{BASE_URL}/{post_id}/replies"
    params = {
        "fields": "text,timestamp",
        "access_token": ACCESS_TOKEN,
    }
    r = requests.get(url, params=params, timeout=15)
    if r.status_code != 200:
        return []
    data = r.json()
    return data.get("data", [])


def is_question(text: str) -> bool:
    return any(kw in text for kw in ["？", "?", "教えて", "どうしたら", "教えてください", "どうすれば"])


def update_history(path: Path, post_id: str, metrics: dict, replies: list):
    """post-history.md の該当エントリを更新する"""
    text = path.read_text(encoding="utf-8")

    # likes
    likes   = metrics.get("likes", {})
    if isinstance(likes, dict):
        likes_count = likes.get("summary", {}).get("total_count", "--")
    else:
        likes_count = likes if likes is not None else "--"

    replies_count = metrics.get("replies", "--")
    reposts_count = metrics.get("reposts", "--")
    views_count   = metrics.get("views",   "--")

    # コメント一覧
    comments_md = ""
    if replies:
        comments_md = "comments:\n"
        for r in replies[:20]:
            txt   = r.get("text", "").strip().replace("\n", " ")[:100]
            ts    = r.get("timestamp", "")[:16]
            q_flag = " [質問]" if is_question(r.get("text", "")) else ""
            comments_md += f"  - \"{txt}\" ({ts}){q_flag}\n"

    def replace_field(field, value):
        return re.sub(
            rf"(^{field}:\s*).*$",
            rf"\g<1>{value}",
            text,
            flags=re.MULTILINE,
        )

    # post_id が含まれるブロック内だけ更新
    # 対象ブロックを抽出して更新
    block_pattern = re.compile(
        r"(---\n(?:(?!---\n).)*?post_id: " + re.escape(post_id) + r"(?:(?!---\n).)*?)"
        r"(engagement_fetched: false)",
        re.DOTALL
    )

    def replace_block(m):
        block = m.group(1)
        block = re.sub(r"^engagement_fetched: false", "engagement_fetched: true", block, flags=re.MULTILINE)
        block = re.sub(r"^likes: .*$",         f"likes: {likes_count}",    block, flags=re.MULTILINE)
        block = re.sub(r"^replies_count: .*$", f"replies_count: {replies_count}", block, flags=re.MULTILINE)
        block = re.sub(r"^reposts: .*$",       f"reposts: {reposts_count}",  block, flags=re.MULTILINE)
        block = re.sub(r"^views: .*$",         f"views: {views_count}",     block, flags=re.MULTILINE)
        if comments_md:
            block = block.rstrip() + "\n" + comments_md
        return block + "engagement_fetched: true"

    new_text, count = block_pattern.subn(replace_block, text)

    if count == 0:
        # シンプルな文字列置換にフォールバック
        new_text = text.replace(
            f"post_id: {post_id}\n",
            f"post_id: {post_id}\n",
        )
        new_text = re.sub(
            r"(post_id: " + re.escape(post_id) + r".*?engagement_fetched: )false",
            r"\g<1>true",
            new_text,
            flags=re.DOTALL,
        )
        new_text = re.sub(
            r"(post_id: " + re.escape(post_id) + r".*?likes: )--",
            rf"\g<1>{likes_count}",
            new_text,
            flags=re.DOTALL,
        )

    path.write_text(new_text, encoding="utf-8")


def main():
    load_env()
    token = os.environ.get("THREADS_ACCESS_TOKEN", ACCESS_TOKEN)

    if not HISTORY_FILE.exists():
        print("post-history.md が見つかりません。スキップ。")
        return

    entries = parse_history(HISTORY_FILE)
    now     = datetime.now(JST)

    targets = []
    for e in entries:
        if e["engagement_fetched"]:
            continue
        if not e["post_id"] or not e["posted_at"]:
            continue
        try:
            posted = datetime.strptime(e["posted_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
        except Exception:
            continue
        if (now - posted) < timedelta(hours=24):
            continue  # 24時間未満はスキップ
        targets.append(e)

    if not targets:
        print("✅ 取得対象なし（全て取得済みor24時間未満）")
        return

    print(f"📊 エンゲージメント取得対象: {len(targets)}件")

    for e in targets:
        post_id = e["post_id"]
        print(f"  取得中: {post_id} (投稿日時: {e['posted_at']})")

        metrics = fetch_metrics(post_id)
        if "error" in metrics:
            print(f"  ❌ メトリクス取得失敗: {metrics['error']} → スキップ")
            continue

        replies = fetch_replies(post_id)
        update_history(HISTORY_FILE, post_id, metrics, replies)

        questions = [r for r in replies if is_question(r.get("text", ""))]
        print(f"  ✅ 取得完了 | likes={metrics.get('likes','--')} replies={len(replies)} (質問:{len(questions)}件)")
        time.sleep(1)

    print(f"\n✅ フェッチャー完了 ({len(targets)}件処理)")


if __name__ == "__main__":
    main()
