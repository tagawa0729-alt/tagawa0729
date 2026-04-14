"""
post_one.py — pendingから1件だけ投稿する（GitHub Actions用）

ルール:
  - scheduled_at が現在時刻以前のpendingを1件だけ投稿して終了
  - 前回投稿から20分未満なら何もしない
  - 投稿対象がなければ何もしない（exitコード0）
"""
import os, re, time, random, requests, sys
from datetime import datetime, timedelta
import pytz

JST          = pytz.timezone("Asia/Tokyo")
USER_ID      = "26245972698403230"
ACCESS_TOKEN = os.environ["THREADS_ACCESS_TOKEN"]
MIN_GAP      = 20 * 60   # 最低20分間隔
BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE_FILE   = os.path.join(BASE_DIR, "posts", "post-queue.md")
HISTORY_FILE = os.path.join(BASE_DIR, "knowledge", "post-history.md")

def read(p):
    try: return open(p, encoding="utf-8").read()
    except: return ""

def write(p, c): open(p, "w", encoding="utf-8").write(c)
def append(p, c): open(p, "a", encoding="utf-8").write(c)

def parse_next_pending(content, now):
    """scheduled_at <= now のpendingを1件返す（scheduled_at順）"""
    candidates = []
    for entry in re.split(r'\n---\n', content):
        if "status: pending" not in entry:
            continue
        def get(f, e=entry):
            m = re.search(rf'^{f}:\s*(.+)$', e, re.MULTILINE)
            return m.group(1).strip() if m else ""
        def multiline(f, e=entry):
            m = re.search(rf'^{f}: \|\n((?:  .*\n?)*)', e, re.MULTILINE)
            if not m: return ""
            return "\n".join(l[2:] if l.startswith("  ") else l for l in m.group(1).splitlines()).strip()

        pid = get("id"); post = multiline("post")
        if not pid or not post:
            continue

        reply = multiline("reply")
        sched_str = get("scheduled_at")
        sched = None
        if sched_str:
            try: sched = JST.localize(datetime.strptime(sched_str, "%Y-%m-%d %H:%M"))
            except: pass

        # scheduled_atが未設定 or 過去なら対象
        if sched is None or sched <= now:
            candidates.append({
                "id": pid, "post": post,
                "reply": reply if reply and reply.lower() != "null" else None,
                "genre": get("genre"), "pattern": get("pattern"),
                "scheduled_at": sched
            })

    if not candidates:
        return None
    # scheduled_at昇順（古いものから）
    candidates.sort(key=lambda x: x["scheduled_at"] or datetime(1970,1,1,tzinfo=JST))
    return candidates[0]

def get_last_posted_time(history):
    times = re.findall(r'^posted_at:\s*(.+)$', history, re.MULTILINE)
    if not times: return None
    try: return JST.localize(datetime.strptime(times[-1].strip(), "%Y-%m-%d %H:%M"))
    except: return None

def api_post(text, reply_to=None):
    params = {"media_type": "TEXT", "text": text, "access_token": ACCESS_TOKEN}
    if reply_to: params["reply_to_id"] = reply_to
    r = requests.post(f"https://graph.threads.net/v1.0/{USER_ID}/threads", data=params, timeout=30)
    r.raise_for_status()
    cid = r.json()["id"]
    time.sleep(5)
    r2 = requests.post(f"https://graph.threads.net/v1.0/{USER_ID}/threads_publish",
                       data={"creation_id": cid, "access_token": ACCESS_TOKEN}, timeout=30)
    r2.raise_for_status()
    return r2.json()["id"]

def mark_posted(content, pid, post_id, reply_id, now):
    repl = f"status: posted\nposted_at: {now.strftime('%Y-%m-%d %H:%M')}\npost_id: {post_id}\nreply_post_id: {reply_id or 'null'}"
    pattern = rf'(id: {re.escape(pid)}\n(?:.*\n)*?)^status: pending$'
    return re.sub(pattern, rf'\1{repl}', content, count=1, flags=re.MULTILINE)

def main():
    now = datetime.now(JST)
    history = read(HISTORY_FILE)
    last = get_last_posted_time(history)

    # 20分間隔チェック
    if last:
        elapsed = (now - last).total_seconds()
        if elapsed < MIN_GAP:
            remaining = int((MIN_GAP - elapsed) / 60)
            print(f"⏸ 前回投稿から{int(elapsed/60)}分しか経っていません（あと約{remaining}分）。スキップ。")
            sys.exit(0)

    # 次のpendingを取得
    queue_content = read(QUEUE_FILE)
    p = parse_next_pending(queue_content, now)

    if not p:
        print("✅ 投稿対象なし（pendingがないか、まだ時刻ではない）")
        sys.exit(0)

    print(f"📤 投稿: [{p['id']}] {p['post'][:50].replace(chr(10),' ')}...")

    try:
        post_id = api_post(p["post"])
        posted_at = datetime.now(JST)
        print(f"  ✅ post_id={post_id}")

        # リプライ
        reply_id = None
        if p["reply"]:
            rlen = len(p["reply"])
            wsec = random.randint(60,120) if rlen<50 else random.randint(90,180) if rlen<100 else random.randint(120,240)
            print(f"  ⏳ リプライまで{wsec}秒待機...")
            time.sleep(wsec)
            try:
                reply_id = api_post(p["reply"], reply_to=post_id)
                print(f"  💬 reply_id={reply_id}")
            except Exception as e:
                print(f"  ⚠️ リプライ失敗: {e}")

        # キュー更新
        updated = mark_posted(queue_content, p["id"], post_id, reply_id, posted_at)
        write(QUEUE_FILE, updated)

        # 履歴追記
        plines = "\n".join(f"  {l}" for l in p["post"].splitlines())
        append(HISTORY_FILE, (
            f"\n---\npost_id: {post_id}\nreply_post_id: {reply_id or 'null'}\n"
            f"queue_id: {p['id']}\nplatform: Threads\n"
            f"posted_at: {posted_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"genre: {p['genre']}\npattern: {p['pattern']}\n"
            f"metrics_fetched: false\nlikes: null\nreposts: null\nreplies: null\nimpressions: null\n"
            f"post: |\n{plines}\n"
        ))
        print(f"  ✅ 完了")

    except Exception as e:
        print(f"  ❌ 投稿失敗: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
