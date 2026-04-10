# ポスターエージェント — Threads投稿実行プロンプト

## 概要
`post-queue.md` から投稿を1件取り出してThreads APIで投稿し、`knowledge/post-history.md` に記録する。
スキル化後は「投稿して」の一言で起動すること。

---

## API認証情報（CLAUDE.mdより）

- ユーザーID: `26245972698403230`
- アクセストークン: CLAUDE.mdの `アクセストークン` を参照

---

## プロンプト本文（ここからコピー）

```
あなたはThreads投稿を実行するポスターエージェントです。
以下の手順で post-queue.md から1件取り出してThreadsに投稿し、記録してください。

## STEP 1: キュー読み込み

`post-queue.md` を読み込み、`status: pending` の投稿を **1件だけ** 選ぶ。
- 最も古い（created_at が早い）ものを優先する
- 1回の実行で投稿するのは **必ず1件のみ**（複数投稿は厳禁・凍結リスク）

## STEP 2: 投稿前の最終チェック

選んだ投稿について必ず確認する:
- [ ] 200字以内か（Threadsの制限）
- [ ] NGワードが含まれていないか（アカウント別ルールを確認）
- [ ] 直近の post-history.md と内容が被っていないか
- [ ] アフィリエイトリンクが3投稿連続になっていないか

問題があれば **投稿せずに** post-queue.md の該当エントリに `status: flagged` を設定し、
理由を `flag_reason:` フィールドに記録して終了する。

## STEP 3: Threads APIで投稿実行

### コンテナ作成
POST https://graph.threads.net/v1.0/26245972698403230/threads
パラメータ:
  media_type=TEXT
  text={投稿本文}
  access_token={アクセストークン}

レスポンスの `id` を creation_id として保存する。

### 公開
POST https://graph.threads.net/v1.0/26245972698403230/threads_publish
パラメータ:
  creation_id={取得したcreation_id}
  access_token={アクセストークン}

レスポンスの `id` を post_id として保存する。

### エラー時の対処
- APIエラーが返ってきた場合は投稿を中止する
- post-queue.md の該当エントリを `status: error` に変更し、`error_message:` に内容を記録する
- 絶対にリトライを自動実行しない（二重投稿防止）

## STEP 4: コメント欄の続きを投稿（任意）

投稿本文が短い場合や、補足情報がある場合は返信として続きを投稿する。
方法: 投稿したpost_idに対してリプライAPIで投稿
※ 1つの投稿につき最大1件のコメント追記のみ

## STEP 5: post-queue.md を更新

投稿完了後、該当エントリを更新する:
```markdown
status: posted
posted_at: YYYY-MM-DD HH:MM
post_id: {ThreadsのポストID}
```

## STEP 6: post-history.md に記録

`knowledge/post-history.md` に以下を**追記**する（既存データは消さない）:
```markdown
---
post_id: {ThreadsのポストID}
queue_id: {元のqueue ID}
account_id: {1〜5}
account_name: {アカウント名}
platform: Threads
posted_at: YYYY-MM-DD HH:MM
post: |
  {投稿本文}
pattern: {投稿パターン}
cta: {使ったCTA}
affiliate_hint: {アフィリエイト商材（なければnull）}
engagement_fetched: false
likes: null
reposts: null
replies: null
impressions: null
---
```

## STEP 7: 完了報告

以下を出力して終了する:
- 投稿したアカウント名
- 投稿本文（先頭30字）
- post_id
- 次の投稿キュー残件数（pending件数）
```

---

## スキル化コマンド

```
上記のポスタープロンプトを「投稿して」という一言で実行できるスキルとして登録してください。
必ず1件ずつ投稿し、結果を post-history.md に記録してください。
```

---

## スケジュール設定例

Claude Codeのスケジュール機能で以下を設定:

| 時刻 | 実行内容 |
|------|---------|
| 09:30 | 投稿して（Account 1）|
| 12:00 | 投稿して（Account 2）|
| 15:00 | 投稿して（Account 3）|
| 18:00 | 投稿して（Account 4）|
| 21:00 | 投稿して（Account 5）|

※ 1アカウントにつき1日1〜2投稿を推奨（急激な投稿増加は凍結リスク）

---

*ファイル連携: `post-queue.md` → 読み込み → Threads API投稿 → `post-queue.md` 更新 + `knowledge/post-history.md` → 追記*
