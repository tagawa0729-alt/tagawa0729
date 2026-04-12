#!/bin/bash
# 毎晩23時の自動パイプライン
# STEP0: スーパーバイザー診断 → STEP1: リサーチ → STEP2: 投稿生成 → STEP3: 完了報告
# cron: 0 23 * * * /Users/akiharutagawa/Desktop/クロード１/scripts/generate_daily_posts.sh

LOG=/Users/akiharutagawa/Desktop/クロード１/scripts/schedule_posts_log.txt
PROJ=/Users/akiharutagawa/Desktop/クロード１
CLAUDE=/Users/akiharutagawa/.local/bin/claude

echo "" >> "$LOG"
echo "========================================" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M')] 🔄 デイリーパイプライン開始" >> "$LOG"
echo "========================================" >> "$LOG"

cd "$PROJ" || exit 1
export $(grep -v '^#' .env | xargs) 2>/dev/null
TOMORROW=$(date -v+1d '+%Y-%m-%d')

# ─────────────────────────────────────────
# STEP 0: スーパーバイザー診断（開始前チェック）
# ─────────────────────────────────────────
echo "[$(date '+%Y-%m-%d %H:%M')] STEP0: スーパーバイザー診断開始..." >> "$LOG"

$CLAUDE --print --dangerously-skip-permissions \
"作業ディレクトリ: /Users/akiharutagawa/Desktop/クロード１/
/チェックして" >> "$LOG" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M')] ✅ STEP0完了: supervisor-report.md を更新" >> "$LOG"

# ─────────────────────────────────────────
# STEP 1: Xバズ投稿リサーチ（新鮮なデータを取得）
# ─────────────────────────────────────────
echo "[$(date '+%Y-%m-%d %H:%M')] STEP1: Xリサーチ開始..." >> "$LOG"

# リサーチ実行
python3 scripts/x_fetch_buzz.py --min-likes 1000 --max-results 15 >> "$LOG" 2>&1
RESEARCH_STATUS=$?

if [ $RESEARCH_STATUS -eq 0 ]; then
  echo "[$(date '+%Y-%m-%d %H:%M')] ✅ STEP1完了: 最新リサーチデータ取得" >> "$LOG"
else
  echo "[$(date '+%Y-%m-%d %H:%M')] 🔴 STEP1失敗: リサーチ取得エラー。投稿生成を中止します。" >> "$LOG"
  # リサーチ失敗したら投稿生成しない（古いデータで投稿しない）
  exit 1
fi

# リサーチデータが本当に今日付きか確認
TODAY=$(date '+%Y-%m-%d')
RESEARCH_DATE=$(grep "Xバズ投稿リサーチ結果" "$PROJ/knowledge/research-knowledge.md" | tail -1 | grep -o '[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}')
if [ "$RESEARCH_DATE" != "$TODAY" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M')] 🔴 STEP1警告: リサーチデータが今日付きでない（$RESEARCH_DATE）。投稿生成を中止。" >> "$LOG"
  exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M')] ✅ リサーチ日付確認OK: $RESEARCH_DATE" >> "$LOG"

# ─────────────────────────────────────────
# STEP 2: 投稿3本を生成（当日リサーチ必須）
# ─────────────────────────────────────────
echo "[$(date '+%Y-%m-%d %H:%M')] STEP2: 投稿生成開始..." >> "$LOG"

$CLAUDE --print --dangerously-skip-permissions \
"作業ディレクトリ: /Users/akiharutagawa/Desktop/クロード１/

以下の順番で作業してください。

1. account/haruoo/ の01〜08ファイルを全て読む
2. knowledge/research-knowledge.md の末尾（最新のリサーチ結果）を読む
   ※ 必ず今日（${TODAY}）付きのデータを使うこと。古いデータは使わない。
3. 今日取得したXのバズ投稿データをもとに、ハルオ（@haruoo.biyou）のキャラクターでThreads投稿を3本作成する
4. posts/post-queue-${TOMORROW}.md に保存する

投稿の条件：
- 01_profile.md のキャラクター・口調・和製英語ルールに従う
- 05_writing.md の文字数・CTA・商品紹介比率ルールに従う
- 07_ng-rules.md のNGルールを守る（20分以内連続投稿NG・矛盾NG）
- 今日リサーチしたXバズ投稿のネタを必ず反映させる（古いネタ禁止）
- パターンは3本で違うものを選ぶ（問題提起・体験談・リスト・逆説・比較 から）" \
>> "$LOG" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M')] ✅ STEP2完了: posts/post-queue-${TOMORROW}.md を生成" >> "$LOG"

# ─────────────────────────────────────────
# STEP 3: スーパーバイザー最終確認
# ─────────────────────────────────────────
echo "[$(date '+%Y-%m-%d %H:%M')] STEP3: スーパーバイザー最終確認..." >> "$LOG"

$CLAUDE --print --dangerously-skip-permissions \
"作業ディレクトリ: /Users/akiharutagawa/Desktop/クロード１/
/チェックして" >> "$LOG" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M')] ✅ STEP3完了: 最終レポート更新" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M')] 🏁 デイリーパイプライン完了" >> "$LOG"
