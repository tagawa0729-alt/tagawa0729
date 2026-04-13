#!/bin/bash
# 投稿プロセス監視スクリプト（ウォッチドッグ）
# 毎時0分に実行。8〜23時の間に1時間以上投稿がなければ自動再起動。

PROJ=/Users/akiharutagawa/Desktop/クロード１
LOG="$PROJ/scripts/schedule_posts_log.txt"
STDOUT="$PROJ/scripts/schedule_posts_stdout.txt"
STATE="$PROJ/scripts/posting_state.json"

HOUR=$(date '+%H' | sed 's/^0*//' )
[ -z "$HOUR" ] && HOUR=0

# 8時〜22時以外は何もしない
if [ "$HOUR" -lt 8 ] || [ "$HOUR" -ge 23 ]; then
    exit 0
fi

# 全投稿完了済みなら何もしない
if [ -f "$STATE" ]; then
    TODAY_CHECK=$(date '+%Y-%m-%d')
    STATE_DATE=$(python3 -c "import json; d=json.load(open('$STATE')); print(d.get('date',''))" 2>/dev/null)
    COMPLETED=$(python3 -c "import json; d=json.load(open('$STATE')); print(len(d.get('completed',[])))" 2>/dev/null)
    if [ "$STATE_DATE" = "$TODAY_CHECK" ] && [ "${COMPLETED:-0}" -ge 30 ]; then
        exit 0
    fi
fi

# 今日の投稿ファイルが存在するか確認
TODAY=$(date '+%Y-%m-%d')
QUEUE_FILE="$PROJ/posts/post-queue-${TODAY}.md"
if [ ! -f "$QUEUE_FILE" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️  watchdog: 投稿ファイルなし。スキップ。" >> "$LOG"
    exit 1
fi

# 最後の投稿から1時間以上経過しているか確認
LAST_POST_SEC=$(grep "✅ 完了 post_id" "$LOG" | tail -1 | grep -o '\[.*\]' | tr -d '[]' | xargs -I{} date -j -f "%Y-%m-%d %H:%M:%S" "{}" '+%s' 2>/dev/null)
NOW_SEC=$(date '+%s')

if [ -n "$LAST_POST_SEC" ]; then
    DIFF=$((NOW_SEC - LAST_POST_SEC))
    if [ "$DIFF" -lt 3600 ]; then
        # 1時間以内に投稿あり → 正常
        exit 0
    fi
fi

# プロセスが生きていても念のため確認
PROC=$(ps aux | grep "schedule_posts.py" | grep "$PROJ" | grep -v grep)
if [ -n "$PROC" ]; then
    # プロセス生存中だが投稿が止まっている → 強制再起動
    kill $(echo "$PROC" | awk '{print $2}') 2>/dev/null
    sleep 2
fi

# 再起動
echo "" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🔄 watchdog: 1時間以上投稿なし → 自動再起動します..." >> "$LOG"

cd "$PROJ" && nohup python3 scripts/schedule_posts.py >> "$STDOUT" 2>&1 &
NEW_PID=$!

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ watchdog: 再起動完了 PID=$NEW_PID" >> "$LOG"
