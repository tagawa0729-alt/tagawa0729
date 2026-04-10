#!/usr/bin/env python3
"""
Threads 連投スクリプト
post-queue.md から投稿を取り出して10分間隔でThreadsに投稿する
"""

import requests
import time
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent.parent
QUEUE_FILE = BASE_DIR / "posts" / "post-queue.md"
HISTORY_FILE = BASE_DIR / "knowledge" / "post-history.md"

USER_ID = "26245972698403230"
ACCESS_TOKEN = "THAAZAKkxyW4IVBUVNRQjRITlY3WlJ5dVFpUmJhVVJjdG8xZAVFYamdZAblJNYi1kUmxHWk1xSjhxekp2Q0daYXRUUm5TVzlTckcyNW5TVmlZAMW9WMnAxeUxKc0k1RmFwaHluVDNtbkx3R3dSOE93bkdzcEtkMEIzSkFRSUI0ZAzQ0d0JKRmJpODFDeTM4ZA3dKRlEZD"

# ── 投稿テキスト3本 ──────────────────────────────────────────
POSTS = [
    {
        "id": 1,
        "text": """¥980で角栓が"自己崩壊"する時代が来てる

鼻の黒ずみ、ずっとゴシゴシこするしかないと思ってたんよ。
でもビオレの新作ウォッシュに変えたら、完全にコンセプトブレイクした。

「トロメタミン」って成分（角栓の奥まで届く界面活性剤みたいなやつ）が浸透して、ミクロパウダーが内側から崩壊させる仕組み。
スクラブで削るんじゃなくて、セルフデストラクション（自己崩壊）させるのが正解けん。

敏感肌の僕が1週間続けたら、黒ずみが体感7割フェイドアウトした。
¥980でこのスペック、控えめに言ってアンビリバボーよ。

使い方のコツはコメントに👇"""
    },
    {
        "id": 2,
        "text": """洗顔後に「なんか顔つっぱるな」って感じてる人へ

それ、肌が傷んでるサインかもしれんばい。

洗顔料が強すぎて、必要な油分まで根こそぎ落としてる状態。
ファンケルのやわ肌ミルク洗顔（¥1,650）に変えた翌朝、つっぱりがほぼ消えた。

ミルクが洗いながら同時に保湿してくれる設計けん、洗ったのに肌が柔らかくなる。
これに変えてから、化粧水を塗ったときに「あ、ちゃんと入ってる」って実感できるようになったばい。

「洗顔って全部同じじゃないの？」って思ってた昔の僕に教えてやりたい。

まず2週間だけ試してみてよかよ👇"""
    },
    {
        "id": 3,
        "text": """スキンケア初心者はまず1本だけ買えばよか

200万使ってわかったのは「全部買う必要ない」ってこと。
自分の一番の悩みに合わせて1本だけ選べばいいけん。

毛穴の黒ずみが気になる
→ ビオレ角栓崩壊洗顔（¥1,000以下）

洗顔後につっぱる・乾燥が気になる
→ ファンケルやわ肌ミルク洗顔（¥1,650）

なんか顔が暗い・くすんで見える
→ キュレル泡ジェル洗顔（¥2,090）

全部ドラッグストアで買えるばい。
「自分がどれかわからん」って人は、コメントに一番気になる悩みを書いてくれたら答えるけん👇"""
    },
]

INTERVAL_SECONDS = 600  # 10分


def post_to_threads(text: str) -> dict:
    """Threads APIで投稿する。{'post_id': str} または {'error': str} を返す"""
    base = f"https://graph.threads.net/v1.0/{USER_ID}"

    # Step 1: コンテナ作成
    r1 = requests.post(
        f"{base}/threads",
        data={"media_type": "TEXT", "text": text, "access_token": ACCESS_TOKEN},
        timeout=30,
    )
    if r1.status_code != 200:
        return {"error": f"container: {r1.status_code} {r1.text}"}
    creation_id = r1.json().get("id")
    if not creation_id:
        return {"error": f"no id: {r1.text}"}

    time.sleep(3)  # 公開前に少し待つ

    # Step 2: 公開
    r2 = requests.post(
        f"{base}/threads_publish",
        data={"creation_id": creation_id, "access_token": ACCESS_TOKEN},
        timeout=30,
    )
    if r2.status_code != 200:
        return {"error": f"publish: {r2.status_code} {r2.text}"}
    post_id = r2.json().get("id")
    if not post_id:
        return {"error": f"no post_id: {r2.text}"}

    return {"post_id": post_id}


def append_history(post: dict, post_id: str, posted_at: str):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = f"""
---
post_id: {post_id}
queue_id: post-{post['id']:03d}
account_id: 1
account_name: ハルオ/美容の実験者
platform: Threads
posted_at: {posted_at}
post: |
{chr(10).join('  ' + line for line in post['text'].splitlines())}
pattern: {'問題提起型' if post['id']==1 else '逆説体験談型' if post['id']==2 else 'リスト型'}
cta: コメント誘導👇
affiliate_hint: null
engagement_fetched: false
likes: null
reposts: null
replies: null
impressions: null
"""
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


def main():
    log_path = BASE_DIR / "scripts" / "post_log.txt"

    def log(msg):
        ts = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    log("=== 連投再開（②③・10分間隔）===")

    for i, post in enumerate(POSTS[1:], start=1):  # ①は投稿済みのためスキップ
        log(f"[{i+1}/3] 投稿中: {post['text'][:30].strip()}...")

        result = post_to_threads(post["text"])

        if "error" in result:
            log(f"  ❌ エラー: {result['error']}")
            log("  自動リトライは実行しません（二重投稿防止）")
            continue

        posted_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
        log(f"  ✅ 投稿完了 post_id={result['post_id']}")
        append_history(post, result["post_id"], posted_at)

        if i < len(POSTS) - 1:
            log(f"  ⏳ 次の投稿まで {INTERVAL_SECONDS//60} 分待機...")
            time.sleep(INTERVAL_SECONDS)

    log("=== 全投稿完了 ===")


if __name__ == "__main__":
    main()
