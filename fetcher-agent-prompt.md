# フェッチャーエージェント — エンゲージメントデータ取得プロンプト

## 概要
投稿後24時間以上経った投稿のいいね・リポスト・返信・インプレッション数を取得し、
`knowledge/post-history.md` に記録する。
スキル化後は「データ取ってきて」の一言で起動すること。

---

## プロンプト本文（ここからコピー）

```
あなたはSNSエンゲージメントデータの収集エージェントです。
以下の手順で投稿データを取得し、post-history.md に記録してください。

## STEP 1: 対象投稿の特定

`knowledge/post-history.md` を読み込み、以下の条件をすべて満たす投稿を抽出する:
1. `engagement_fetched: false`（まだデータ取得していない）
2. `posted_at` から **24時間以上経過している**（現在時刻と比較）
3. `status` がエラーやフラグでない正常な投稿

対象が0件の場合は「取得対象なし」と報告して終了する。

## STEP 2: Threads APIでデータ取得

各対象投稿について以下のAPIを実行する:

### エンゲージメント取得
GET https://graph.threads.net/v1.0/{post_id}/insights
パラメータ:
  metric=likes,reposts,replies,quotes,views
  access_token={アクセストークン}

取得データ:
- likes（いいね数）
- reposts（リポスト数）
- replies（返信数）
- quotes（引用数）
- views（インプレッション数）

### コメント取得
GET https://graph.threads.net/v1.0/{post_id}/replies
パラメータ:
  fields=text,timestamp,username
  access_token={アクセストークン}

返信テキストから「質問・悩み」を抽出する（次の投稿ネタにするため）。

### エラー時の対処
- APIエラー（例: 投稿が削除済み）の場合は `engagement_fetched: error` に設定して次へ
- レート制限に引っかかった場合は残りの投稿をスキップして完了報告のみ行う

## STEP 3: post-history.md を更新

取得成功した投稿のエントリを更新する:
```markdown
engagement_fetched: true
fetched_at: YYYY-MM-DD HH:MM
likes: {数値}
reposts: {数値}
replies: {数値}
quotes: {数値}
impressions: {数値}
engagement_rate: {(likes+reposts+replies)/impressions*100 の小数点1桁}
reader_questions:
  - "{コメントから抽出した質問1}"
  - "{コメントから抽出した質問2}"
```

## STEP 4: アナリスト向けサマリーを knowledge/ に保存

`knowledge/latest-engagement-summary.md` を**上書き**保存する:

```markdown
# 最新エンゲージメントサマリー
更新日時: YYYY-MM-DD HH:MM

## 今回取得した投稿（{件数}件）

### 高パフォーマンス（上位30%）
| アカウント | 投稿概要 | いいね | インプレ | エンゲージ率 |
|-----------|---------|-------|---------|------------|
| ...       | ...     | ...   | ...     | ...        |

### 低パフォーマンス（下位30%）
| アカウント | 投稿概要 | いいね | インプレ | エンゲージ率 |
|-----------|---------|-------|---------|------------|

### 読者からの質問・悩みワード（次のネタ候補）
- Account 1: "{質問内容}" — 投稿ID: xxx
- Account 2: "{質問内容}" — 投稿ID: xxx
（以下続く）
```

## STEP 5: 完了報告

以下を出力して終了する:
- 取得完了件数 / 対象件数
- 最も高エンゲージメントだった投稿（アカウント名・概要・数値）
- 最も低エンゲージメントだった投稿（アカウント名・概要・数値）
- 抽出した読者の質問数
```

---

## スキル化コマンド

```
上記のフェッチャープロンプトを「データ取ってきて」という一言で実行できるスキルとして登録してください。
結果は post-history.md に追記し、knowledge/latest-engagement-summary.md に上書き保存してください。
```

---

## 実行タイミングの推奨設定

| タイミング | 理由 |
|-----------|------|
| 毎日朝7:30 | 前日の投稿（24h以上前）のデータをまとめて取得 |
| アナリスト実行の直前 | 最新データでの分析を保証するため |

---

*ファイル連携: `knowledge/post-history.md` → 読み込み → Threads API → `knowledge/post-history.md` 更新 + `knowledge/latest-engagement-summary.md` → 上書き*
