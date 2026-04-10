#!/usr/bin/env python3
"""
post-queue-2026-04-11.md の30本を 2026-04-11 08:03〜22:52 に不規則な間隔で投稿するスクリプト
最低間隔: 20分 / コメント誘導CTA付き投稿には1分後に種コメントを返信
"""

import re
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent.parent
QUEUE_FILE = BASE_DIR / "posts" / "post-queue-2026-04-11.md"
LOG_FILE   = BASE_DIR / "scripts" / "schedule_posts_log.txt"

USER_ID      = "26245972698403230"
ACCESS_TOKEN = "THAAZAKkxyW4IVBUVNRQjRITlY3WlJ5dVFpUmJhVVJjdG8xZAVFYamdZAblJNYi1kUmxHWk1xSjhxekp2Q0daYXRUUm5TVzlTckcyNW5TVmlZAMW9WMnAxeUxKc0k1RmFwaHluVDNtbkx3R3dSOE93bkdzcEtkMEIzSkFRSUI0ZAzQ0d0JKRmJpODFDeTM4ZA3dKRlEZD"

# ── スケジュール（2026-04-11、JST）───────────────────────────────────
# 全ペア間隔確認済み: 最小23分、最大40分、全29ペアが20分以上
SCHEDULE_TIMES = [
    "08:03", "08:31", "09:07", "09:42", "10:18",   # 朝 (+28, +36, +35, +36)
    "10:43", "11:15", "11:55", "12:22", "12:48",   # 午前 (+25, +32, +40, +27, +26)
    "13:15", "13:38", "14:05", "14:37", "15:12",   # 昼 (+27, +23, +27, +32, +35)
    "15:43", "16:21", "16:58", "17:25", "17:52",   # 午後 (+31, +38, +37, +27, +27)
    "18:18", "18:52", "19:27", "20:03", "20:35",   # 夕方 (+26, +34, +35, +36, +32)
    "21:08", "21:38", "22:05", "22:28", "22:52",   # 夜 (+33, +30, +27, +23, +24)
]

# ── コメント誘導CTA付き投稿への種コメント（post_index: 0始まり）──────────
# 対象: 投稿05(4), 09(8), 10(9), 12(11), 14(13), 15(14), 20(19), 23(22), 28(27), 30(29)
SEED_REPLIES = {
    4: (
        "ちなみにヒゲ剃り後のケアで一番変わったのは「化粧水をコットンで軽く押さえる」こと。\n"
        "タオルで拭いた直後にすぐやると赤みが引くスピードが全然違うばい。\n"
        "みんなのカミソリ負け対策、教えてよかよ👇"
    ),
    8: (
        "ちなみにアイクリームは「薬指で優しくトントン」が鉄則けん。\n"
        "押し込むのは逆効果で、摩擦が目元の小ジワを作る原因になるばい。\n"
        "目元ケアで気になることがあれば何でも聞いてよかよ👇"
    ),
    9: (
        "補足すると、混合肌が一番多くて一番悩みやすいタイプばい。\n"
        "Tゾーンと頬で使うアイテムを変えるのが正解けん。\n"
        "自分の肌タイプが分からん人は遠慮なくコメントしてよかよ👇"
    ),
    11: (
        "ちなみにニキビ跡には「ナイアシンアミド」が一番効いたばい（無印良品の美白化粧水に入ってる）。\n"
        "炎症が落ち着いたら跡にピンポイントで使うのが効率よかよ。\n"
        "どんな跡で悩んでるか、もっと詳しく教えてよかよ👇"
    ),
    13: (
        "ちなみに僕は今「洗顔→化粧水→日焼け止め」の3ステップだけばい。\n"
        "シンプルにしてから継続率が爆上がりしたけん、まずそこから始めるのがよかよ。\n"
        "ステップを減らして楽になった人、ぜひ教えてよかよ👇"
    ),
    14: (
        "参考までに僕の体感をシェアするけん。\n"
        "脂性肌→キュレル泡ジェル洗顔が最強やったばい\n"
        "乾燥肌→ファンケルやわ肌ミルク洗顔が神\n"
        "混合肌→ビオレ角栓崩壊洗顔でTゾーンを攻める\n"
        "自分のタイプが合ってれば劇的に変わるけん、ぜひ試してよかよ。"
    ),
    19: (
        "ちなみに日焼け止めで一番大事なのは「続けること」けん。\n"
        "SPF30でも毎日塗る人のほうが、SPF50を週1しか塗らない人より絶対肌が綺麗になるばい。\n"
        "今日から始めてみてよかよ👇"
    ),
    22: (
        "敏感肌の人に一番おすすめしたいのはキュレルのシリーズけん。\n"
        "全製品セラミド配合で、バリア機能を守りながら洗えるばい。\n"
        "敏感肌で他に困ってることがあれば教えてよかよ👇"
    ),
    27: (
        "毛穴タイプ別の対処法、もう少し詳しく話すとこんな感じばい。\n"
        "黒ずみ→ビオレ角栓崩壊洗顔（週3回）\n"
        "開き→キュレルで保湿ルーティン構築\n"
        "たるみ→コラーゲン系美容液を夜ケアに追加\n"
        "自分のタイプに合ったケア、一緒に考えるけん気軽に教えてよかよ👇"
    ),
    29: (
        "ちなみに最初の1週間は劇的な変化は出んくて当然けん。\n"
        "ターンオーバーの関係で、体感できるまでに3〜4週間かかるばい。\n"
        "気長に続けて、何か変化を感じたらコメントで教えてよかよ👇"
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


def parse_schedule(date_str: str = "2026-04-11") -> list:
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
    log("スケジュール投稿開始 (post-queue-2026-04-11.md, 30本, 不規則間隔)")
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
    log("全30本（＋種コメント10本）投稿完了")


if __name__ == "__main__":
    main()
