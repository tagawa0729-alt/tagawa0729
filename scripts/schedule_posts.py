#!/usr/bin/env python3
"""翌日分の投稿スクリプト"""
import re, json, time, subprocess, atexit, requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent.parent
QUEUE_FILE = BASE_DIR / "posts" / "post-queue-2026-04-13.md"
LOG_FILE = BASE_DIR / "scripts" / "schedule_posts_log.txt"
STATE_FILE = BASE_DIR / "scripts" / "posting_state.json"

USER_ID = "26245972698403230"
ACCESS_TOKEN = "THAAZAKkxyW4IVBUVNRQjRITlY3WlJ5dVFpUmJhVVJjdG8xZAVFYamdZAblJNYi1kUmxHWk1xSjhxekp2Q0daYXRUUm5TVzlTckcyNW5TVmlZAMW9WMnAxeUxKc0k1RmFwaHluVDNtbkx3R3dSOE93bkdzcEtkMEIzSkFRSUI0ZAzQ0d0JKRmJpODFDeTM4ZA3dKRlEZD"

SCHEDULE_TIMES = [
    "08:05","08:30","08:55","09:22","09:48",
    "10:12","10:35","11:00","11:25","11:52",
    "12:15","12:40","13:05","13:28","13:52",
    "14:18","14:41","15:05","15:30","15:55",
    "16:22","16:47","17:12","17:35","18:00",
    "18:28","18:55","19:22","19:47","20:12",
]

SEED_REPLIES = {}

def log(msg):
    ts = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def load_state():
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text())["completed"])
    return set()

def save_state(completed):
    STATE_FILE.write_text(json.dumps({"completed": sorted(completed)}))

def parse_posts(md_path):
    text = md_path.read_text(encoding="utf-8")
    blocks = re.split(r"\n---\n", text)
    posts = []
    for block in blocks:
        lines = block.strip().splitlines()
        for i, line in enumerate(lines):
            if re.match(r"^## 投稿\d+", line):
                body_lines = [l for l in lines[i+1:] if not l.startswith("<!-- comment_reply:")]
                body = "\n".join(body_lines).strip()
                if body:
                    posts.append(body)
                break
    return posts

def parse_schedule(date_str):
    return [datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H:%M").replace(tzinfo=JST) for t in SCHEDULE_TIMES]

def _create_and_publish(text, reply_to_id=None):
    base = f"https://graph.threads.net/v1.0/{USER_ID}"
    params = {"media_type": "TEXT", "text": text, "access_token": ACCESS_TOKEN}
    if reply_to_id:
        params["reply_to_id"] = reply_to_id
    r1 = requests.post(f"{base}/threads", data=params, timeout=30)
    if r1.status_code != 200:
        return {"error": f"container: {r1.status_code} {r1.text[:200]}"}
    creation_id = r1.json().get("id")
    if not creation_id:
        return {"error": f"no id: {r1.text[:200]}"}
    time.sleep(3)
    r2 = requests.post(f"{base}/threads_publish", data={"creation_id": creation_id, "access_token": ACCESS_TOKEN}, timeout=30)
    if r2.status_code != 200:
        return {"error": f"publish: {r2.status_code} {r2.text[:200]}"}
    post_id = r2.json().get("id")
    return {"post_id": post_id} if post_id else {"error": f"no post_id: {r2.text[:200]}"}

def main():
    _caffeinate = subprocess.Popen(["caffeinate", "-s"])
    atexit.register(_caffeinate.terminate)
    completed = load_state()
    log("=" * 60)
    log(f"スケジュール投稿開始 ({QUEUE_FILE.name}, 30本)")
    if completed:
        log(f"再開モード: {sorted(completed)} スキップ")
    posts = parse_posts(QUEUE_FILE)
    schedule = parse_schedule(QUEUE_FILE.stem.replace("post-queue-", ""))
    if len(posts) != len(schedule):
        log(f"❌ 投稿数({len(posts)})とスケジュール数({len(schedule)})が不一致。終了。")
        return
    MIN_INTERVAL = timedelta(minutes=20)
    now = datetime.now(JST)
    adjusted = []
    last_time = now - MIN_INTERVAL
    for i, scheduled_at in enumerate(schedule):
        if i in completed:
            adjusted.append(None)
            continue
        actual = max(scheduled_at, last_time + MIN_INTERVAL)
        adjusted.append(actual)
        last_time = actual
    log(f"残り: {len(posts) - len(completed)}本 | 終了予定: {[t for t in adjusted if t][-1].strftime('%H:%M') if any(adjusted) else 'N/A'}")
    log("=" * 60)
    for i, (post_text, scheduled_at) in enumerate(zip(posts, adjusted), 1):
        if scheduled_at is None:
            continue
        wait_sec = (scheduled_at - datetime.now(JST)).total_seconds()
        if wait_sec > 60:
            log(f"[{i:02d}/30] {scheduled_at.strftime('%H:%M')} まで待機 ({wait_sec/60:.1f}分後)...")
        while True:
            remaining = (scheduled_at - datetime.now(JST)).total_seconds()
            if remaining <= 0:
                break
            time.sleep(min(30, remaining))
        log(f"[{i:02d}/30] 投稿中: {post_text[:40].replace(chr(10),' ')}...")
        result = _create_and_publish(post_text)
        if "error" in result:
            log(f"  ❌ エラー: {result['error']}")
            continue
        post_id = result["post_id"]
        log(f"  ✅ 完了 post_id={post_id}")
        completed.add(i - 1)
        save_state(completed)
        if (i - 1) in SEED_REPLIES:
            log(f"  ⏳ 種コメント60秒待機...")
            time.sleep(60)
            reply_result = _create_and_publish(SEED_REPLIES[i - 1], reply_to_id=post_id)
            if "error" in reply_result:
                log(f"  ❌ 返信エラー: {reply_result['error']}")
            else:
                log(f"  💬 返信完了 reply_id={reply_result['post_id']}")
    log("=" * 60)
    log("全投稿完了")

if __name__ == "__main__":
    main()
