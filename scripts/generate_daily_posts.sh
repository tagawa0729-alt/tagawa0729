#!/bin/bash
# 毎晩23時の自動パイプライン
# STEP1: Xバズ投稿をリサーチ → STEP2: 投稿3本を生成
# cron: 0 23 * * * /Users/akiharutagawa/Desktop/クロード１/scripts/generate_daily_posts.sh

LOG=/Users/akiharutagawa/Desktop/クロード１/scripts/schedule_posts_log.txt
PROJ=/Users/akiharutagawa/Desktop/クロード１

echo "" >> "$LOG"
echo "========================================" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M')] 🔄 デイリーパイプライン開始" >> "$LOG"
echo "========================================" >> "$LOG"

cd "$PROJ" || exit 1

# .envから環境変数を読み込む
export $(grep -v '^#' .env | xargs) 2>/dev/null

TOMORROW=$(date -v+1d '+%Y-%m-%d')

# ─────────────────────────────────────────
# STEP 1: Xバズ投稿リサーチ
# ─────────────────────────────────────────
echo "[$(date '+%Y-%m-%d %H:%M')] STEP1: Xリサーチ開始..." >> "$LOG"

python3 scripts/x_fetch_buzz.py --min-likes 1000 --max-results 15 >> "$LOG" 2>&1
RESEARCH_STATUS=$?

if [ $RESEARCH_STATUS -eq 0 ]; then
  echo "[$(date '+%Y-%m-%d %H:%M')] ✅ STEP1完了: リサーチデータ更新" >> "$LOG"
else
  echo "[$(date '+%Y-%m-%d %H:%M')] ⚠️  STEP1警告: リサーチに問題あり（既存データで続行）" >> "$LOG"
fi

# ─────────────────────────────────────────
# STEP 2: 投稿3本を生成
# ─────────────────────────────────────────
echo "[$(date '+%Y-%m-%d %H:%M')] STEP2: 投稿生成開始..." >> "$LOG"

/usr/local/bin/claude --print --dangerously-skip-permissions \
"作業ディレクトリ: /Users/akiharutagawa/Desktop/クロード１/

以下の順番で作業してください。

1. account/haruoo/ の01〜08ファイルを全て読む
2. knowledge/research-knowledge.md の末尾（最新のリサーチ結果）を読む
3. 今日取得したXのバズ投稿データをもとに、ハルオ（@haruoo.biyou）のキャラクターで Threads投稿を3本作成する
4. posts/post-queue-${TOMORROW}.md に保存する

投稿の条件：
- 01_profile.md のキャラクター・口調・博多弁・和製英語ルールに従う
- 05_writing.md の文字数・CTA・商品紹介比率ルールに従う
- 07_ng-rules.md のNGルールを守る
- 今日リサーチしたXバズ投稿のネタ・フレーズ・悩みワードを必ず反映させる
- パターンは3本で違うものを選ぶ（問題提起・体験談・リスト・逆説・比較 から）" \
>> "$LOG" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M')] ✅ STEP2完了: posts/post-queue-${TOMORROW}.md を生成" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M')] 🏁 デイリーパイプライン終了" >> "$LOG"
