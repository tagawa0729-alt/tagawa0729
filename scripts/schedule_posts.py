#!/usr/bin/env python3
"""
post-queue-2026-04-12.md の30本を 2026-04-12 12:10〜22:50 に不規則な間隔で投稿するスクリプト
最低間隔: 20分 / コメント誘導CTA付き投稿には1分後に種コメントを返信
再起動時は posting_state.json で投稿済みインデックスをスキップ
"""

import re
import json
import time
import subprocess
import atexit
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent.parent
QUEUE_FILE  = BASE_DIR / "posts" / "post-queue-2026-04-12.md"
LOG_FILE    = BASE_DIR / "scripts" / "schedule_posts_log.txt"
STATE_FILE  = BASE_DIR / "scripts" / "posting_state.json"

USER_ID      = "26245972698403230"
ACCESS_TOKEN = "THAAZAKkxyW4IVBUVNRQjRITlY3WlJ5dVFpUmJhVVJjdG8xZAVFYamdZAblJNYi1kUmxHWk1xSjhxekp2Q0daYXRUUm5TVzlTckcyNW5TVmlZAMW9WMnAxeUxKc0k1RmFwaHluVDNtbkx3R3dSOE93bkdzcEtkMEIzSkFRSUI0ZAzQ0d0JKRmJpODFDeTM4ZA3dKRlEZD"

# ── スケジュール（2026-04-12、JST）───────────────────────────────────
# 全ペア間隔確認済み: 最小20分、最大25分、全29ペアが20分以上
SCHEDULE_TIMES = [
    "12:10", "12:33", "12:55", "13:19", "13:39",   # (+23,+22,+24,+20)
    "14:01", "14:23", "14:48", "15:08", "15:30",   # (+22,+22,+25,+20,+22)
    "15:51", "16:13", "16:35", "16:57", "17:21",   # (+21,+22,+22,+22,+24)
    "17:41", "18:01", "18:23", "18:45", "19:09",   # (+20,+20,+22,+22,+24)
    "19:31", "19:53", "20:18", "20:38", "21:00",   # (+22,+22,+25,+20,+22)
    "21:22", "21:46", "22:06", "22:28", "22:50",   # (+22,+24,+20,+22,+22)
]

# ── コメント誘導CTA付き投稿への種コメント（post_index: 0始まり）──────────
# 対象: 投稿02(1), 05(4), 07(6), 10(9), 12(11), 18(17), 20(19), 24(23), 27(26), 30(29)
SEED_REPLIES = {
    1: "皮脂テカりに悩んでる人、多いよね。洗顔料の選び方とか保湿の順番とかも関係してくるけん、気になること何でも聞いてよかよ！",
    4: "クリームの量って迷うよね。基本はパール粒1〜2個くらいが目安ばい。でも肌の状態で変えてもOK。なんでも気軽に聞いてよかよ！",
    6: "混合肌かどうかは「洗顔30分後に何もしない状態でどこがテカるか」でチェックできるよ。Tゾーンだけテカる→混合肌の可能性大！",
    9: "剃刀負けがひどい人は、T字カミソリからシェーバー（電動）に変えるだけで改善するケースも多いよ。摩擦が段違いに減るけん、検討してみてよかよ！",
    11: "インナードライの人は「さっぱり系化粧水+ジェルクリーム」の組み合わせが相性いいことが多いよ。油っぽいからってオイルカットしすぎるのが逆効果ばい！",
    17: "成分表示はINCI名（英語）で書いてあることが多くて、レチノールはRetinol、カフェインはCaffeineって表記されてるよ。照らし合わせてみてよかよ！",
    19: "泡立て洗顔派とジェル派どっちも正解やよ。大事なのは「こすらないこと」と「すすぎ残しをしないこと」。ぬるま湯でしっかり流してよかよ！",
    23: "使ってる炭酸洗顔のブランドが気になる人いたら教えるよ。ただし僕が試したのは1種類だけやけん、合う合わないは個人差あるよ！",
    26: "ニキビ跡の種類（赤み・茶色・凸凹）によって有効な成分が変わってくるよ。自分のタイプが気になる人は教えてよかよ、ざっくり解説するよ！",
    29: "何から始めたらいいかわからない人、「今の肌の一番の悩みは何？」ってコメントで教えてね。悩みに合わせた始め方を一緒に考えるよ！",
}


def log(msg: str):
    ts = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state() -> set:
    """投稿済みインデックスをファイルから読み込む"""
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data.get("completed", []))
    return set()


def save_state(completed: set):
    """投稿済みインデックスをファイルに保存"""
    STATE_FILE.write_text(
        json.dumps({"completed": sorted(completed)}, ensure_ascii=False),
        encoding="utf-8"
    )


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
        body_lines = [l for l in lines[header_idx + 1:] if not l.startswith("<!-- comment_reply:")]
        body = "\n".join(body_lines).strip()
        if body:
            posts.append(body)
    return posts


def parse_schedule(date_str: str = "2026-04-12") -> list:
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
    # Macスリープ防止（投稿完了まで維持）
    _caffeinate = subprocess.Popen(["caffeinate", "-s"])
    atexit.register(_caffeinate.terminate)

    # 投稿済みインデックスを読み込む
    completed = load_state()

    log("=" * 60)
    log("スケジュール投稿開始 (post-queue-2026-04-12.md, 30本, 不規則間隔)")
    log(f"コメント返信対象: 投稿 {sorted(i+1 for i in SEED_REPLIES)} （1分後に種コメント）")
    if completed:
        log(f"再開モード: インデックス {sorted(completed)} はスキップ（投稿済み）")

    posts    = parse_posts(QUEUE_FILE)
    schedule = parse_schedule()

    if len(posts) != len(schedule):
        log(f"❌ 投稿数({len(posts)})とスケジュール数({len(schedule)})が不一致。終了。")
        return

    # 起動時に過去分が複数ある場合、20分ずつ後ろ倒しにして連続投稿を防ぐ
    MIN_INTERVAL = timedelta(minutes=20)
    now = datetime.now(JST)
    adjusted = []
    last_time = now - MIN_INTERVAL

    for i, scheduled_at in enumerate(schedule):
        if i in completed:
            adjusted.append(None)
            continue
        if scheduled_at > now:
            earliest = last_time + MIN_INTERVAL
            actual = max(scheduled_at, earliest)
        else:
            earliest = last_time + MIN_INTERVAL
            actual = max(earliest, now)
        adjusted.append(actual)
        last_time = actual

    log(f"投稿数: {len(posts)}本 | 残り: {len(posts) - len(completed)}本")
    log("スケジュール一覧:")
    for i, t in enumerate(adjusted, 1):
        if t is None:
            log(f"  [{i:02d}] ---- (投稿済みスキップ)")
        else:
            reply_mark = " 💬+1min" if (i - 1) in SEED_REPLIES else ""
            orig = schedule[i - 1].strftime('%H:%M')
            mark = f" (元:{orig})" if t != schedule[i - 1] else ""
            log(f"  [{i:02d}] {t.strftime('%H:%M')}{mark}{reply_mark}")
    log("=" * 60)

    for i, (post_text, scheduled_at) in enumerate(zip(posts, adjusted), 1):
        if scheduled_at is None:
            continue

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

        # 投稿済みとして即時保存
        completed.add(i - 1)
        save_state(completed)

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
    log("全30本（＋種コメント）投稿完了")


if __name__ == "__main__":
    main()
