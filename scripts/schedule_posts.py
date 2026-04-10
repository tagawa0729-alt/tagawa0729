#!/usr/bin/env python3
"""
post-queue-30.md の30本を 2026-04-10 08:00〜23:00 に不規則な間隔で投稿するスクリプト
最低間隔: 20分 / コメント誘導CTA付き投稿には1分後に種コメントを返信
"""

import re
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent.parent
QUEUE_FILE = BASE_DIR / "posts" / "post-queue-30.md"
LOG_FILE   = BASE_DIR / "scripts" / "schedule_posts_log.txt"

USER_ID      = "26245972698403230"
ACCESS_TOKEN = "THAAZAKkxyW4IVBUVNRQjRITlY3WlJ5dVFpUmJhVVJjdG8xZAVFYamdZAblJNYi1kUmxHWk1xSjhxekp2Q0daYXRUUm5TVzlTckcyNW5TVmlZAMW9WMnAxeUxKc0k1RmFwaHluVDNtbkx3R3dSOE93bkdzcEtkMEIzSkFRSUI0ZAzQ0d0JKRmJpODFDeTM4ZA3dKRlEZD"

# ── スケジュール（2026-04-10、JST）───────────────────────────────────
SCHEDULE_TIMES = [
    "08:00", "08:23", "08:52", "09:22", "09:57",   # 朝 (+23, +29, +30, +35)
    "10:32", "11:05", "11:45", "12:05", "12:25",   # 午前 (+35, +33, +40, +20, +20)
    "13:00", "13:20", "13:40", "14:15", "14:55",   # 昼 (+35, +20, +20, +35, +40)
    "15:28", "16:05", "16:42", "17:15", "17:50",   # 午後 (+33, +37, +37, +33, +35)
    "18:25", "19:00", "19:35", "20:08", "20:42",   # 夕方 (+35, +35, +35, +33, +34)
    "21:15", "21:45", "22:10", "22:32", "22:52",   # 夜 (+33, +30, +25, +22, +20)
]

# ── コメント誘導CTA付き投稿への種コメント（post_index: 0始まり）──────────
# 対象: 投稿04(3), 06(5), 09(8), 13(12), 16(15), 25(24)
SEED_REPLIES = {
    3: (
        "ちなみに朝ぬるま湯だけにしたの、最初は「本当に大丈夫？」って不安やった。\n"
        "でも1週間でテカリが落ち着いてきて確信したけん。\n"
        "みんなの肌のテカり方、教えてよかよ👇"
    ),
    5: (
        "ちなみに僕はどっちも2週間ずつ交互に使ったけん。\n"
        "日常使いはナチュリエのコスパが最強やったばい。\n"
        "でも特別ケアの日だけSK-IIを使う「使い分け」が今のスタイルけん。\n"
        "あなたはどっち派？"
    ),
    8: (
        "CeraVeのクレンジングジェル、Amazonか楽天で買うのが安いけん。\n"
        "あと「洗顔回数を1日2回→1回に減らした」だけでニキビが減った人も多いから、\n"
        "まずそこだけ試してみてよかよ。\n"
        "気になることあれば何でも聞いてよかよ👇"
    ),
    12: (
        "ちなみに僕は乾燥肌＋毛穴が悩みやったけん、\n"
        "最初はセラミド（キュレル）から入ったばい。\n"
        "3ヶ月でバリアが整って、その後ナイアシンアミド（無印）を追加した。\n"
        "悩みが複数ある人はまず一番気になるものから始めてよかよ。"
    ),
    15: (
        "ちなみに今の僕のルーティンはこんな感じけん。\n"
        "洗顔：ファンケル（日本）\n"
        "化粧水：COSRX（韓国）\n"
        "日焼け止め：アネッサ（日本）\n"
        "目的で選んだら自然に混在になったばい。みんなはどっち派？"
    ),
    24: (
        "参考までに僕の体感をシェアするばい。\n"
        "ビオレ → 毛穴の黒ずみに即効性あり\n"
        "ファンケル → 乾燥肌の朝ケアに最強\n"
        "キュレル → 週2回の集中ケア用\n"
        "全部持っておくと肌の調子で使い分けられるけん、参考にしてよかよ。"
    ),
}


def log(msg: str):
    ts = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def parse_posts(md_path: Path) -> list:
    """Markdownから各投稿本文を抽出（## 投稿NN ヘッダーを持つブロックのみ）"""
    text = md_path.read_text(encoding="utf-8")
    blocks = re.split(r"\n---\n", text)
    posts = []
    for block in blocks:
        lines = block.strip().splitlines()
        header_idx = None
        for idx, line in enumerate(lines):
            if re.match(r"^## 投稿\d+", line):
                header_idx = idx
                break
        if header_idx is None:
            continue
        body = "\n".join(lines[header_idx + 1:]).strip()
        if body:
            posts.append(body)
    return posts


def parse_schedule(date_str: str = "2026-04-10") -> list:
    return [
        datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H:%M").replace(tzinfo=JST)
        for t in SCHEDULE_TIMES
    ]


def _create_and_publish(text: str, reply_to_id: str = None) -> dict:
    """Threads API: コンテナ作成 → 公開"""
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

    r2 = requests.post(
        f"{base}/threads_publish",
        data={"creation_id": creation_id, "access_token": ACCESS_TOKEN},
        timeout=30,
    )
    if r2.status_code != 200:
        return {"error": f"publish: {r2.status_code} {r2.text[:200]}"}
    post_id = r2.json().get("id")
    return {"post_id": post_id} if post_id else {"error": f"no post_id: {r2.text[:200]}"}


def post_to_threads(text: str) -> dict:
    return _create_and_publish(text)


def reply_to_threads(parent_id: str, text: str) -> dict:
    return _create_and_publish(text, reply_to_id=parent_id)


def main():
    log("=" * 60)
    log("スケジュール投稿開始 (post-queue-30.md, 30本, 不規則間隔)")
    log(f"コメント返信対象: 投稿 {sorted(i+1 for i in SEED_REPLIES)} （1分後に種コメント）")

    posts    = parse_posts(QUEUE_FILE)
    schedule = parse_schedule()

    if len(posts) != len(schedule):
        log(f"❌ 投稿数({len(posts)})とスケジュール数({len(schedule)})が不一致。終了。")
        return

    # 起動時に過去分が複数ある場合、20分ずつ後ろ倒しにして連続投稿を防ぐ
    MIN_INTERVAL = timedelta(minutes=20)
    now = datetime.now(JST)
    adjusted = []
    last_time = now - MIN_INTERVAL  # 初回は即時投稿可能にするための初期値

    for scheduled_at in schedule:
        if scheduled_at > now:
            # 未来の投稿: 元のスケジュールを使いつつ、直前との間隔を保証
            earliest = last_time + MIN_INTERVAL
            actual = max(scheduled_at, earliest)
        else:
            # 過去の投稿: 直前投稿から20分後
            earliest = last_time + MIN_INTERVAL
            actual = max(earliest, now)
        adjusted.append(actual)
        last_time = actual

    log(f"投稿数: {len(posts)}本 | 開始: {adjusted[0].strftime('%H:%M')} → 終了: {adjusted[-1].strftime('%H:%M')}")
    log("スケジュール一覧:")
    for i, t in enumerate(adjusted, 1):
        reply_mark = " 💬+1min" if (i - 1) in SEED_REPLIES else ""
        orig = schedule[i - 1].strftime('%H:%M')
        mark = f" (元:{orig})" if t != schedule[i - 1] else ""
        log(f"  [{i:02d}] {t.strftime('%H:%M')}{mark}{reply_mark}")
    log("=" * 60)

    for i, (post_text, scheduled_at) in enumerate(zip(posts, adjusted), 1):
        wait_sec = (scheduled_at - datetime.now(JST)).total_seconds()

        if wait_sec > 60:
            log(f"[{i:02d}/30] {scheduled_at.strftime('%H:%M')} まで待機 ({wait_sec/60:.1f}分後)...")
        # Macスリープ対策: 30秒刻みでループし、実時刻で判定
        while True:
            remaining = (scheduled_at - datetime.now(JST)).total_seconds()
            if remaining <= 0:
                break
            time.sleep(min(30, remaining))

        log(f"[{i:02d}/30] 投稿中: {post_text[:40].replace(chr(10), ' ')}...")
        result = post_to_threads(post_text)

        if "error" in result:
            log(f"  ❌ エラー: {result['error']}")
            continue

        post_id = result["post_id"]
        log(f"  ✅ 完了 post_id={post_id}")

        # コメント誘導CTA付き投稿 → 1分後に種コメントを返信
        if (i - 1) in SEED_REPLIES:
            log(f"  ⏳ 種コメント投稿まで60秒待機...")
            time.sleep(60)
            reply_text = SEED_REPLIES[i - 1]
            log(f"  💬 返信投稿中...")
            reply_result = reply_to_threads(post_id, reply_text)
            if "error" in reply_result:
                log(f"  ❌ 返信エラー: {reply_result['error']}")
            else:
                log(f"  💬 返信完了 reply_id={reply_result['post_id']}")

    log("=" * 60)
    log("全30本（＋種コメント6本）投稿完了")


if __name__ == "__main__":
    main()
