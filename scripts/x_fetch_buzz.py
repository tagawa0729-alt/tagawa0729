#!/usr/bin/env python3
"""
X バズ投稿フェッチャー（Playwright版・無料）
Playwrightを使ってXにログインし、メンズスキンケア関連の
バズ投稿（いいね数上位）を取得して research-knowledge.md に追記する。

使い方:
  python3 scripts/x_fetch_buzz.py
  python3 scripts/x_fetch_buzz.py --min-likes 3000 --max-results 15
  python3 scripts/x_fetch_buzz.py --dry-run

必要な環境変数（.envに記載）:
  X_USERNAME  — Xのユーザー名（@なし）
  X_PASSWORD  — Xのパスワード
"""

import os
import sys
import re
import time
import json
import argparse
import warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).parent.parent
RESEARCH_FILE = BASE_DIR / "knowledge" / "research-knowledge.md"
SESSION_FILE = BASE_DIR / "scripts" / ".x_session.json"

# 検索クエリ一覧（順番に実行）
SEARCH_QUERIES = [
    {
        "label": "スキンケア全般バズ投稿",
        "url": "https://x.com/search?q=%E3%82%B9%E3%82%AD%E3%83%B3%E3%82%B1%E3%82%A2+lang%3Aja+-filter%3Aretweets&src=typed_query&f=top",
    },
    {
        "label": "メンズスキンケア",
        "url": "https://x.com/search?q=%E3%83%A1%E3%83%B3%E3%82%BA%E3%82%B9%E3%82%AD%E3%83%B3%E3%82%B1%E3%82%A2+OR+%E7%94%B7%E3%81%AE%E8%82%8C+lang%3Aja+-filter%3Aretweets&src=typed_query&f=top",
    },
    {
        "label": "洗顔・肌荒れ・ニキビ",
        "url": "https://x.com/search?q=%E6%B4%97%E9%A1%94+OR+%E8%82%8C%E8%8D%92%E3%82%8C+OR+%E3%83%8B%E3%82%AD%E3%83%93%E8%82%8C+lang%3Aja+-filter%3Aretweets&src=typed_query&f=top",
    },
    {
        "label": "美容・保湿バズ",
        "url": "https://x.com/search?q=%E4%BF%9D%E6%B9%BF+OR+%E7%BE%8E%E5%AE%B9+%E3%82%B9%E3%82%AD%E3%83%B3%E3%82%B1%E3%82%A2+lang%3Aja+-filter%3Aretweets&src=typed_query&f=top",
    },
]


def load_env():
    """~/Desktop/クロード１/.env から環境変数を読み込む"""
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def parse_likes(text: str) -> int:
    """いいね数テキストを数値に変換（例: "1.2万" → 12000）"""
    text = text.strip().replace(",", "").replace("，", "")
    try:
        if "万" in text:
            return int(float(text.replace("万", "")) * 10000)
        elif "千" in text:
            return int(float(text.replace("千", "")) * 1000)
        elif "K" in text.upper():
            return int(float(text.upper().replace("K", "")) * 1000)
        elif "M" in text.upper():
            return int(float(text.upper().replace("M", "")) * 1000000)
        else:
            digits = re.sub(r"[^\d]", "", text)
            return int(digits) if digits else 0
    except Exception:
        return 0


def analyze_buzz_pattern(text: str) -> str:
    """バズパターンを分析"""
    patterns = []
    if any(w in text for w in ["？", "?", "なぜ", "理由", "原因", "知ってる", "気づい", "実は"]):
        patterns.append("問題提起型")
    if any(w in text for w in ["やめたら", "やめると", "逆に", "むしろ"]):
        patterns.append("逆説型")
    if any(c.isdigit() for c in text) and any(w in text for w in ["選", "つ", "ステップ", "方法", "コツ", "個"]):
        patterns.append("リスト型")
    if any(w in text for w in ["日間", "週間", "ヶ月", "試した", "やってみた", "続けた"]):
        patterns.append("体験談型")
    return " / ".join(patterns) if patterns else "その他"


def extract_tweets_from_page(page, min_likes: int, max_results: int) -> list:
    """ページ上のツイートを抽出してフィルタ"""
    results = []
    seen_texts = set()

    # スクロールして投稿を読み込む
    for scroll_i in range(6):
        page.evaluate("window.scrollBy(0, 1200)")
        page.wait_for_timeout(1500)

        tweets_data = page.evaluate("""
        () => {
            const articles = document.querySelectorAll('article[data-testid="tweet"]');
            return Array.from(articles).map(article => {
                // テキスト
                const textEl = article.querySelector('[data-testid="tweetText"]');
                const text = textEl ? textEl.innerText : '';

                // いいね数（aria-labelから取得: "1,234 Likes. Like" → "1234"）
                const likeBtn = article.querySelector('[data-testid="like"]');
                let likeText = '0';
                if (likeBtn) {
                    const ariaLabel = likeBtn.getAttribute('aria-label') || '';
                    const match = ariaLabel.match(/^[\d,\.万千]+/);
                    if (match) {
                        likeText = match[0].replace(/,/g, '');
                    } else {
                        const span = likeBtn.querySelector('span[data-testid="app-text-transition-container"]');
                        likeText = span ? span.innerText : '0';
                    }
                }

                // RT数
                const rtEl = article.querySelector('[data-testid="retweet"] span[data-testid="app-text-transition-container"]');
                const rtText = rtEl ? rtEl.innerText : '0';

                // 返信数
                const replyEl = article.querySelector('[data-testid="reply"] span[data-testid="app-text-transition-container"]');
                const replyText = replyEl ? replyEl.innerText : '0';

                // ユーザー名
                const userLink = article.querySelector('a[href*="/"] [data-testid="User-Name"]');
                const username = userLink ? userLink.innerText : '';

                // URL（投稿リンク）
                const timeEl = article.querySelector('time');
                const linkEl = timeEl ? timeEl.closest('a') : null;
                const url = linkEl ? 'https://x.com' + linkEl.getAttribute('href') : '';

                // 日時
                const datetime = timeEl ? timeEl.getAttribute('datetime') : '';

                return { text, likeText, rtText, replyText, username, url, datetime };
            });
        }
        """)

        for t in tweets_data:
            txt = t.get("text", "").strip()
            if not txt or txt in seen_texts:
                continue
            seen_texts.add(txt)

            likes = parse_likes(t.get("likeText", "0"))
            if likes < min_likes:
                continue

            rts = parse_likes(t.get("rtText", "0"))
            replies = parse_likes(t.get("replyText", "0"))

            # ユーザー名を@から抽出
            uname_raw = t.get("username", "")
            uname_match = re.search(r"@([\w]+)", uname_raw)
            username = uname_match.group(1) if uname_match else uname_raw.split("\n")[-1]

            results.append({
                "text": txt,
                "likes": likes,
                "retweets": rts,
                "replies": replies,
                "username": username,
                "url": t.get("url", ""),
                "created_at": t.get("datetime", "")[:10],
            })

        if len(results) >= max_results:
            break

    results.sort(key=lambda x: x["likes"], reverse=True)
    return results[:max_results]


def click_and_type(page, selector: str, value: str, timeout: int = 10000) -> bool:
    """
    Reactフォーム対応の入力：
    JS getBoundingClientRect → mouse.click → keyboard.type で入力する。
    Playwright bounding_box() がNoneになる場合のフォールバックつき。
    """
    try:
        el = page.locator(selector).first
        el.wait_for(state="visible", timeout=timeout)

        # JS経由で座標取得（Playwrightのbounding_boxはdialog内でNoneになることがある）
        rect = page.evaluate(f"""
        () => {{
            const el = document.querySelector('{selector}');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {{x: r.x, y: r.y, w: r.width, h: r.height}};
        }}
        """)

        if not rect or rect["w"] == 0:
            return False

        cx = rect["x"] + rect["w"] / 2
        cy = rect["y"] + rect["h"] / 2
        page.mouse.click(cx, cy)
        page.wait_for_timeout(400)
        page.keyboard.press("Meta+A")
        page.keyboard.press("Backspace")
        page.keyboard.type(value, delay=60)
        return True
    except Exception:
        return False


def click_button_robust(page, names: list) -> bool:
    """ボタンをテキスト名で探してクリック（JS座標方式）"""
    for name in names:
        try:
            btn = page.get_by_role("button", name=name).first
            btn.wait_for(state="visible", timeout=3000)
            rect = page.evaluate(f"""
            () => {{
                const btns = Array.from(document.querySelectorAll('button'));
                const btn = btns.find(b => b.innerText.trim().includes('{name}'));
                if (!btn) return null;
                const r = btn.getBoundingClientRect();
                return {{x: r.x, y: r.y, w: r.width, h: r.height}};
            }}
            """)
            if rect and rect["w"] > 0:
                page.mouse.click(rect["x"] + rect["w"]/2, rect["y"] + rect["h"]/2)
                return True
        except Exception:
            pass
    # フォールバック: Enter
    page.keyboard.press("Enter")
    return False


def login_to_x(page, username: str, password: str):
    """Xにログインする（堅牢版・JS座標方式）"""
    print("  Xにログイン中...")
    page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)
    page.screenshot(path=str(BASE_DIR / "scripts" / "debug_login_start.png"))

    # --- STEP 1: ユーザー名入力 ---
    # まず入力欄が出るまで待つ
    username_sel = None
    for sel in ['input[autocomplete="username"]', 'input[name="text"]', 'input[type="text"]']:
        try:
            page.wait_for_selector(sel, state="visible", timeout=10000)
            username_sel = sel
            break
        except Exception:
            pass

    if not username_sel:
        page.screenshot(path=str(BASE_DIR / "scripts" / "debug_login.png"))
        raise Exception("ユーザー名入力欄が見つかりません。debug_login.png を確認してください。")

    ok = click_and_type(page, username_sel, username, timeout=10000)
    if not ok:
        # JS直接入力フォールバック
        page.evaluate(f"""
        () => {{
            const el = document.querySelector('{username_sel}');
            if (el) {{
                el.focus();
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                nativeInputValueSetter.call(el, '{username}');
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
        }}
        """)
        page.wait_for_timeout(300)

    page.wait_for_timeout(500)
    page.screenshot(path=str(BASE_DIR / "scripts" / "debug_after_username.png"))

    # 「次へ」クリック
    click_button_robust(page, ["次へ", "Next"])
    page.wait_for_timeout(4000)
    page.screenshot(path=str(BASE_DIR / "scripts" / "debug_after_next.png"))

    # --- STEP 2: 追加確認（電話/メール）が出た場合スキップ ---
    verify_val = os.environ.get("X_VERIFY", "")
    try:
        verify_el = page.locator('input[data-testid="ocfEnterTextTextInput"]').first
        if verify_el.is_visible(timeout=2000):
            print("  ⚠️  追加確認が求められました")
            if verify_val:
                click_and_type(page, 'input[data-testid="ocfEnterTextTextInput"]', verify_val)
                click_button_robust(page, ["次へ", "Next"])
                page.wait_for_timeout(3000)
    except Exception:
        pass

    # --- STEP 3: パスワード入力 ---
    # パスワード欄が現れるまで明示的に待つ
    pw_sel = None
    for sel in ['input[name="password"]', 'input[type="password"]', 'input[autocomplete="current-password"]']:
        try:
            page.wait_for_selector(sel, state="visible", timeout=15000)
            pw_sel = sel
            print(f"  パスワード欄確認: {sel}")
            break
        except Exception:
            pass

    if not pw_sel:
        page.screenshot(path=str(BASE_DIR / "scripts" / "debug_password.png"))
        raise Exception("パスワード入力欄が見つかりません。debug_password.png を確認してください。")

    pw_ok = click_and_type(page, pw_sel, password, timeout=10000)
    if not pw_ok:
        # JS直接入力フォールバック
        page.evaluate(f"""
        () => {{
            const el = document.querySelector('{pw_sel}');
            if (el) {{
                el.focus();
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                nativeInputValueSetter.call(el, arguments[0]);
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
        }}
        """, password)
        page.wait_for_timeout(300)

    page.wait_for_timeout(600)
    page.screenshot(path=str(BASE_DIR / "scripts" / "debug_after_password.png"))

    # 「ログイン」クリック
    click_button_robust(page, ["ログイン", "Log in"])
    page.wait_for_timeout(8000)

    current_url = page.url
    print(f"  ログイン後URL: {current_url}")
    page.screenshot(path=str(BASE_DIR / "scripts" / "debug_after_login.png"))
    if any(k in current_url for k in ["home", "/home", "twitter.com"]):
        print("  ✅ ログイン成功")
    else:
        print("  ⚠️  ログイン結果を確認中（続行します）")


def format_markdown(all_results: list, now: datetime) -> str:
    """research-knowledge.md 追記用Markdownを生成"""
    lines = [
        f"\n## {now.strftime('%Y-%m-%d %H:%M')} X バズ投稿リサーチ結果（メンズスキンケア）",
        f"\n> 取得方法: Playwright（ブラウザ自動化）  ",
        f"> 取得期間: 直近7日間  ",
        f"> 取得件数: {len(all_results)}件\n",
        "### Account 1: メンズスキンケア入門",
        "#### バズコンテンツ一覧（X「トップ」タブ）\n",
        "| いいね | RT | 返信 | ユーザー | 投稿パターン | 投稿日 | URL |",
        "|-------|-----|------|---------|------------|-------|-----|",
    ]

    for t in all_results:
        pattern = analyze_buzz_pattern(t["text"])
        lines.append(
            f"| {t['likes']:,} | {t['retweets']:,} | {t['replies']:,} | "
            f"@{t['username']} | {pattern} | {t['created_at']} | {t['url']} |"
        )

    lines.append("\n#### 投稿テキスト詳細（いいね順）\n")
    for i, t in enumerate(all_results, 1):
        pattern = analyze_buzz_pattern(t["text"])
        lines.append(f"**{i}. @{t['username']} — いいね {t['likes']:,}（{t['created_at']}）**")
        clean_text = t["text"].replace("\n", " ").strip()
        lines.append(f"> {clean_text[:250]}")
        lines.append(f"- バズパターン: {pattern}")
        lines.append(f"- URL: {t['url']}\n")

    lines.append("#### 使えるフックフレーズ（1行目から抽出）\n")
    for t in all_results:
        first = t["text"].split("\n")[0].strip()[:80]
        if first:
            lines.append(f"- 「{first}」（いいね {t['likes']:,}、@{t['username']}）")

    lines.append("\n#### 読者の悩みワード（頻出キーワード）\n")
    pain_keywords = ["ニキビ", "肌荒れ", "乾燥", "テカリ", "毛穴", "ツッパリ",
                     "黒ずみ", "かゆい", "赤み", "ヒリヒリ", "べたつき", "シミ", "くすみ"]
    found = {}
    for t in all_results:
        for kw in pain_keywords:
            if kw in t["text"]:
                found[kw] = found.get(kw, 0) + 1
    for kw, cnt in sorted(found.items(), key=lambda x: -x[1]):
        lines.append(f"- 「{kw}」— {cnt}件の投稿で言及")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="X バズ投稿フェッチャー（Playwright版）")
    parser.add_argument("--min-likes", type=int, default=10000)
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--headless", action="store_true", default=True,
                        help="ヘッドレスモード（デフォルトON）")
    parser.add_argument("--show-browser", action="store_true",
                        help="ブラウザを表示して実行（デバッグ用）")
    args = parser.parse_args()

    load_env()

    x_user = os.environ.get("X_USERNAME", "")
    x_pass = os.environ.get("X_PASSWORD", "")

    if not x_user or not x_pass:
        print("エラー: X_USERNAME と X_PASSWORD を .env に設定してください。")
        print("  X_USERNAME=あなたのXユーザー名")
        print("  X_PASSWORD=あなたのXパスワード")
        sys.exit(1)

    now = datetime.now(timezone(timedelta(hours=9)))
    headless = not args.show_browser

    print(f"🔍 X バズ投稿フェッチ開始 ({now.strftime('%Y-%m-%d %H:%M')} JST)")
    print(f"   条件: いいね {args.min_likes:,}以上 / メンズスキンケア関連")
    print(f"   モード: {'ヘッドレス' if headless else 'ブラウザ表示'}\n")

    from playwright.sync_api import sync_playwright

    all_tweets = []
    seen_texts = set()

    x_auth_token = os.environ.get("X_AUTH_TOKEN", "")
    x_ct0 = os.environ.get("X_CT0", "")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)

        if x_auth_token and x_ct0:
            # Cookieをセットしてログイン不要でアクセス
            print("  Cookie認証でログイン中...")
            context.add_cookies([
                {"name": "auth_token", "value": x_auth_token, "domain": ".x.com", "path": "/"},
                {"name": "ct0",        "value": x_ct0,        "domain": ".x.com", "path": "/"},
            ])
            page = context.new_page()
            # 認証確認
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            if "login" in page.url or "flow" in page.url:
                print("  ⚠️ Cookie認証失敗。Cookieが期限切れの可能性があります。")
                context.close()
                browser.close()
                sys.exit(1)
            print("  ✅ Cookie認証成功")
        else:
            # Cookieがなければ通常ログイン
            page = context.new_page()
            try:
                login_to_x(page, x_user, x_pass)
            except Exception as e:
                print(f"  ログインエラー: {e}")
                context.close()
                browser.close()
                sys.exit(1)

        # 各クエリを検索
        for i, q in enumerate(SEARCH_QUERIES, 1):
            print(f"[{i}/{len(SEARCH_QUERIES)}] 検索中: {q['label']}...")
            try:
                page.goto(q["url"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)

                tweets = extract_tweets_from_page(page, args.min_likes, args.max_results)
                added = 0
                for t in tweets:
                    if t["text"] not in seen_texts:
                        seen_texts.add(t["text"])
                        all_tweets.append(t)
                        added += 1
                print(f"   → {added}件追加（累計: {len(all_tweets)}件）")
            except Exception as e:
                print(f"   → エラー: {e}")

        context.close()
        browser.close()

    # いいね数で再ソート・上限カット
    all_tweets.sort(key=lambda x: x["likes"], reverse=True)
    all_tweets = all_tweets[:args.max_results]

    if not all_tweets:
        print(f"\n⚠️  いいね {args.min_likes:,}以上の投稿が見つかりませんでした。")
        print("   --min-likes を下げて再試行してください。例: --min-likes 1000")
        return

    print(f"\n📊 取得結果: {len(all_tweets)}件")
    print("-" * 65)
    for t in all_tweets:
        preview = t["text"][:45].replace("\n", " ")
        print(f"  いいね {t['likes']:>7,} | @{t['username']:<18} | {preview}...")
    print("-" * 65)

    content = format_markdown(all_tweets, now)

    if args.dry_run:
        print("\n--- DRY RUN ---")
        print(content)
    else:
        RESEARCH_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RESEARCH_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + content + "\n")
        print(f"\n✅ {RESEARCH_FILE} に追記しました。")

    print("✅ フェッチ完了")


if __name__ == "__main__":
    main()
