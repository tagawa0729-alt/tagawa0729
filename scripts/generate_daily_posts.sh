#!/bin/bash
# ============================================================
# 毎晩23時 デイリーパイプライン
# 実行順：
#   STEP 0: スーパーバイザー（事前診断）
#   STEP 1: フェッチャー（エンゲージメントデータ取得）
#   STEP 2: アナリスト（パフォーマンス分析 → next-topics.md）
#   STEP 3a: X リサーチ（バズ投稿50本取得）
#   STEP 3b: Instagram リサーチ（バズリール取得）
#   STEP 4: ライター（next-topics.md + リサーチ → post-queue.md に30本追加）
#   STEP 5: スーパーバイザー（最終確認）
#   STEP 6: 投稿スケジューラー起動（8時まで待機 → 22時まで投稿）
# cron: 0 23 * * * /Users/akiharutagawa/Desktop/クロード１/scripts/generate_daily_posts.sh
# ============================================================

PROJ=/Users/akiharutagawa/Desktop/クロード１
LOG=$PROJ/scripts/schedule_posts_log.txt
CLAUDE=/Users/akiharutagawa/.local/bin/claude
TODAY=$(date '+%Y-%m-%d')

# PATH を明示
export PATH=/Users/akiharutagawa/.local/bin:/usr/local/bin:/usr/bin:/bin

# 環境変数を読み込む
if [ -f "$PROJ/.env" ]; then
    export $(grep -v '^#' "$PROJ/.env" | xargs) 2>/dev/null
fi

# ログ関数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M')] $1" | tee -a "$LOG"
}

cd "$PROJ" || exit 1

log ""
log "============================================================"
log "🌙 デイリーパイプライン開始 ($TODAY)"
log "============================================================"


# ─────────────────────────────────────────
# STEP 0: スーパーバイザー（事前診断）
# ─────────────────────────────────────────
log "STEP0: スーパーバイザー事前診断..."

$CLAUDE --print --dangerously-skip-permissions \
"作業ディレクトリ: $PROJ

以下のファイルを全て読んで、自動運用の現状を診断してください。

【チェックするファイル】
- knowledge/post-history.md（投稿履歴）
- post-queue.md（現在のキュー）
- knowledge/next-topics.md（ネタストック）
- knowledge/analysis-latest.md（最新分析）
- account/haruoo/01_profile.md〜08_strategy.md（ナレッジ8ファイル）

【チェック項目】
1. 投稿が2日以上止まっていないか（止まっていれば⚠️）
2. post-queue.md のキューが5件以上溜まりすぎていないか
3. next-topics.md のテーマが1件以下に枯渇していないか
4. engagement_fetched: false が5件以上残っていないか
5. ナレッジファイル8つに空・不備がないか

結果を $PROJ/supervisor-report.md に保存してください（上書き）。" >> "$LOG" 2>&1

log "✅ STEP0完了"


# ─────────────────────────────────────────
# STEP 1: フェッチャー（エンゲージメントデータ取得）
# ─────────────────────────────────────────
log "STEP1: エンゲージメントデータ取得中..."

python3 "$PROJ/scripts/fetch_metrics.py" >> "$LOG" 2>&1
STATUS=$?

if [ $STATUS -eq 0 ]; then
    log "✅ STEP1完了"
else
    log "⚠️  STEP1: フェッチャーエラー（続行します）"
fi


# ─────────────────────────────────────────
# STEP 2: アナリスト（パフォーマンス分析）
# ─────────────────────────────────────────
log "STEP2: アナリスト分析中..."

$CLAUDE --print --dangerously-skip-permissions \
"作業ディレクトリ: $PROJ

$(cat $PROJ/analyst-agent-prompt.md)

【注意】
- knowledge/post-history.md の全投稿データを使うこと
- engagement_fetched: true のデータのみ分析対象
- 分析結果は knowledge/analysis-latest.md に上書き保存
- 次回テーマ提案は knowledge/next-topics.md に上書き保存
- 各テーマには「どんな切り口で書くか」「1行目の案」を必ずセットで書くこと" >> "$LOG" 2>&1

log "✅ STEP2完了"


# ─────────────────────────────────────────
# STEP 3a: X リサーチ
# ─────────────────────────────────────────
log "STEP3a: X バズ投稿リサーチ中（50本）..."

python3 "$PROJ/scripts/x_fetch_buzz.py" --min-likes 1000 --max-results 50 >> "$LOG" 2>&1
X_STATUS=$?

if [ $X_STATUS -ne 0 ]; then
    log "⚠️  STEP3a: Xリサーチ失敗（続行します）"
else
    # 日付確認
    RESEARCH_DATE=$(grep "X バズ投稿リサーチ結果" "$PROJ/knowledge/research-knowledge.md" | tail -1 | grep -o '[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}')
    if [ "$RESEARCH_DATE" != "$TODAY" ]; then
        log "⚠️  STEP3a: リサーチデータが今日付きでない（$RESEARCH_DATE）"
    else
        log "✅ STEP3a完了（日付確認OK: $RESEARCH_DATE）"
    fi
fi


# ─────────────────────────────────────────
# STEP 3b: Instagram リサーチ
# ─────────────────────────────────────────
log "STEP3b: Instagram バズリールリサーチ中..."

# INSTAGRAM_USERNAME が設定されている場合のみ実行
if [ -n "$INSTAGRAM_USERNAME" ] && [ -n "$INSTAGRAM_PASSWORD" ]; then
    python3 "$PROJ/scripts/instagram_fetch.py" --min-views 100000 --max-reels 30 >> "$LOG" 2>&1
    IG_STATUS=$?
    if [ $IG_STATUS -eq 0 ]; then
        log "✅ STEP3b完了"
    else
        log "⚠️  STEP3b: Instagramリサーチ失敗（続行します）"
    fi
else
    log "⚠️  STEP3b: INSTAGRAM_USERNAME/PASSWORD 未設定のためスキップ"
    log "   → .env に INSTAGRAM_USERNAME=xxx と INSTAGRAM_PASSWORD=xxx を追加してください"
fi


# ─────────────────────────────────────────
# STEP 4: ライター（投稿30本生成 → post-queue.md に追加）
# ─────────────────────────────────────────
log "STEP4: ライター投稿生成中（30本）..."

$CLAUDE --print --dangerously-skip-permissions \
"作業ディレクトリ: $PROJ

以下のファイルを全て読んでください：
1. account/haruoo/01_profile.md（キャラクター・口調）
2. account/haruoo/02_target.md（ターゲット・悩み）
3. account/haruoo/05_writing.md（文章ルール・CTA・文字数）
4. account/haruoo/06_references.md（バズった投稿の実例）
5. account/haruoo/07_ng-rules.md（NGルール）
6. knowledge/next-topics.md（アナリストが提案したテーマ）
7. knowledge/research-knowledge.md の末尾（今日 $TODAY のリサーチデータ）
8. knowledge/post-history.md（過去の投稿内容、重複チェック用）

次に、以下のルールでThreads投稿を30本生成してください：

【生成ルール】
- next-topics.md のテーマを優先的に使う（使い切ったら関連テーマで補完）
- 06_references.md のバズ投稿から「構造だけ」参考にする（丸パクリ禁止）
- 1行目は必ず「有益そう」「意外性」「続きが気になる」のどれかを満たすこと
- 固有名詞か数字を必ず入れること
- 07_ng-rules.md を厳守
- 商品紹介は30本中6本以下（8:2ルール）
- 同じテーマ・商品の連続はNG、30本全体でバランスよく分散
- 各投稿は本文200字以内
- コメント欄用テキスト（reply）がある場合は別途書くこと

【生成後のセルフチェック（30本全部に適用）】
□ 1行目で手が止まるか？
□ AI感のある表現（「〜と言えるでしょう」等）がないか？
□ 07_ng-rules.md に違反していないか？
□ 05_writing.md の口調・文体に合っているか？

【保存先】$PROJ/post-queue.md に以下のYAML形式で追記（既存エントリを消さずに追加）：

---
id: queue-${TODAY}-1
account_id: 1
account_name: ハルオ
platform: Threads
pattern: （問題提起型 / 体験談型 / リスト型 / 逆説型 / 比較型）
status: pending
created_at: ${TODAY} 23:00
post: |
  （本文200字以内）

reply: |
  （コメント欄テキスト、なければこの行ごと省略）
cta: （使ったCTA）
affiliate_hint: （商材名 or null）

---
id: queue-${TODAY}-2
（以下30件まで同様）" >> "$LOG" 2>&1

log "✅ STEP4完了: post-queue.md に30本追加"


# ─────────────────────────────────────────
# STEP 5: スーパーバイザー（最終確認）
# ─────────────────────────────────────────
log "STEP5: スーパーバイザー最終確認..."

$CLAUDE --print --dangerously-skip-permissions \
"作業ディレクトリ: $PROJ

以下のファイルを全て読んで、今夜のパイプライン完了後の状態を最終確認してください。

【チェックするファイル】
- knowledge/post-history.md
- post-queue.md（今追加された30本が入っているか確認）
- knowledge/next-topics.md
- knowledge/analysis-latest.md
- supervisor-report.md（STEP0の診断結果）

【確認項目】
1. post-queue.md に今日（$TODAY）のエントリが30本追加されているか
2. 投稿内容に明らかなNG（07_ng-rules.md 違反）がないか（サンプルチェック）
3. analysis-latest.md が今日の日付で更新されているか
4. 全体として明日の投稿準備が整っているか

結果を $PROJ/supervisor-report.md に追記してください（STEP5最終確認として）。" >> "$LOG" 2>&1

log "✅ STEP5完了"


# ─────────────────────────────────────────
# STEP 6: 投稿スケジューラー起動
# ─────────────────────────────────────────
log "STEP6: 投稿スケジューラー起動..."

if pgrep -f "schedule_posts.py" > /dev/null 2>&1; then
    log "⚠️  schedule_posts.py は既に起動中のためスキップ"
else
    nohup python3 "$PROJ/scripts/schedule_posts.py" >> "$LOG" 2>&1 &
    SCHED_PID=$!
    log "✅ STEP6完了: スケジューラー起動 PID=$SCHED_PID（翌8:00から投稿開始）"
fi


log "============================================================"
log "🏁 デイリーパイプライン完了（翌8:00〜22:00に30本投稿予定）"
log "============================================================"
