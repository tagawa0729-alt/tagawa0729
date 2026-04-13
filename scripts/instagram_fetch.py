#!/usr/bin/env python3
"""
Instagram バズリール フェッチャー（Playwright版）

やること：
1. 自分のフォロー一覧を開いて美容系アカウントをリストアップ
2. 各アカウントのタイムラインをスクロールして10万再生以上のリールをピックアップ
3. フォロー中のアカウントがフォローしているアカウントも同様にチェック
4. リールのキャプション・コメントを取得してresearch-knowledge.mdに保存

必要な環境変数（.env）:
  INSTAGRAM_USERNAME  — Instagramのユーザー名
  INSTAGRAM_PASSWORD  — Instagramのパスワード

オプション:
  --min-views   最低再生数（デフォルト: 100000）
  --max-reels   取得するリール最大数（デフォルト: 30）
  --dry-run     保存せずに結果を表示するだけ
  --show-browser ブラウザを表示してデバッグ
"""

import os
import re
import sys
import time
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR      = Path(__file__).parent.parent
RESEARCH_FILE = BASE_DIR / "knowledge" / "research-knowledge.md"

# 美容系アカウント判定キーワード（bio・username・displayname）
BEAUTY_KEYWORDS = [
    "スキンケア", "美容", "コスメ", "化粧", "肌", "保湿", "メンズビューティ",
    "beauty", "skincare", "cosmetic", "makeup", "skin", "ビューティ",
    "韓国コスメ", "プチプラ", "デパコス", "メンズスキン"
]

MIN_VIEWS_DEFAULT = 100_000


def load_env():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def is_beauty_account(bio: str, username: str, display_name: str) -> bool:
    text = f"{bio} {username} {display_name}".lower()
    return any(kw.lower() in text for kw in BEAUTY_KEYWORDS)


def parse_view_count(text: str) -> int:
    """'12万' '1.2M' '105K' などを数値に変換"""
    text = text.strip().replace(",", "").replace(" ", "")
    try:
        if "万" in text:
            return int(float(text.replace("万", "")) * 10_000)
        elif "億" in text:
            return int(float(text.replace("億", "")) * 100_000_000)
        elif text.upper().endswith("M"):
            return int(float(text[:-1]) * 1_000_000)
        elif text.upper().endswith("K"):
            return int(float(text[:-1]) * 1_000)
        else:
            digits = re.sub(r"[^\d]", "", text)
            return int(digits) if digits else 0
    except Exception:
        return 0


def login_instagram(page, username: str, password: str):
    """Instagramにログイン"""
    print("  Instagramにログイン中...")
    page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    # ユーザー名入力
    for sel in ['input[name="username"]', 'input[aria-label*="ユーザーネーム"]', 'input[type="text"]']:
        try:
            el = page.locator(sel).first
            el.wait_for(state="visible", timeout=8000)
            el.fill(username)
            break
        except Exception:
            continue

    page.wait_for_timeout(500)

    # パスワード入力
    for sel in ['input[name="password"]', 'input[type="password"]']:
        try:
            el = page.locator(sel).first
            el.wait_for(state="visible", timeout=8000)
            el.fill(password)
            break
        except Exception:
            continue

    page.wait_for_timeout(500)

    # ログインボタン
    for sel in ['button[type="submit"]', 'button:has-text("ログイン")', 'button:has-text("Log in")']:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=3000):
                btn.click()
                break
        except Exception:
            continue

    page.wait_for_timeout(5000)

    # 「後で」「後でやる」ボタンがあればクリック（通知許可ダイアログ）
    for text in ["後で", "後でやる", "Not Now", "後にする"]:
        try:
            btn = page.get_by_text(text).first
            if btn.is_visible(timeout=2000):
                btn.click()
                page.wait_for_timeout(1000)
        except Exception:
            pass

    if "instagram.com" in page.url and "login" not in page.url:
        print("  ✅ ログイン成功")
    else:
        print(f"  ⚠️  ログイン確認中... URL: {page.url}")


def get_following_list(page, own_username: str) -> list:
    """自分のフォロー一覧を取得"""
    print("  フォロー一覧を取得中...")
    page.goto(f"https://www.instagram.com/{own_username}/following/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    following = []
    # モーダルをスクロールしてユーザー名を収集
    for _ in range(10):
        usernames = page.evaluate("""
        () => {
            const links = document.querySelectorAll('a[href*="/"]');
            return Array.from(links)
                .map(a => a.href.match(/instagram\.com\/([^/?]+)/)?.[1])
                .filter(u => u && !['p', 'reel', 'explore', 'accounts', 'direct'].includes(u));
        }
        """)
        for u in usernames:
            if u and u not in following and u != own_username:
                following.append(u)

        page.evaluate("window.scrollBy(0, 500)")
        page.wait_for_timeout(800)

    print(f"  フォロー中: {len(following)}アカウント")
    return list(set(following))


def get_account_bio(page, username: str) -> dict:
    """アカウントのbio・display_nameを取得"""
    try:
        page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1500)

        bio = page.evaluate("""
        () => {
            const el = document.querySelector('span._ap3a') || document.querySelector('div.-vDIg span');
            return el ? el.innerText : '';
        }
        """) or ""

        display_name = page.evaluate("""
        () => {
            const el = document.querySelector('h2._aacl') || document.querySelector('span.x1lliihq');
            return el ? el.innerText : '';
        }
        """) or ""

        return {"username": username, "bio": bio, "display_name": display_name}
    except Exception:
        return {"username": username, "bio": "", "display_name": ""}


def get_reels_from_account(page, username: str, min_views: int, max_reels: int) -> list:
    """アカウントのリールタブから高再生数リールを取得"""
    reels = []
    try:
        page.goto(f"https://www.instagram.com/{username}/reels/", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        for _ in range(5):
            reel_data = page.evaluate("""
            () => {
                const items = document.querySelectorAll('div._aagw, article, div[class*="reel"]');
                return Array.from(items).map(item => {
                    const link = item.querySelector('a');
                    const viewEl = item.querySelector('span[class*="view"], span._aacl');
                    const viewText = viewEl ? viewEl.innerText : '0';
                    const url = link ? link.href : '';
                    return { url, viewText };
                }).filter(r => r.url && r.url.includes('/reel/'));
            }
            """)

            for r in reel_data:
                views = parse_view_count(r.get("viewText", "0"))
                url   = r.get("url", "")
                if views >= min_views and url not in [x["url"] for x in reels]:
                    reels.append({"url": url, "views": views, "username": username})

            if len(reels) >= max_reels:
                break
            page.evaluate("window.scrollBy(0, 1200)")
            page.wait_for_timeout(1000)

    except Exception as e:
        print(f"  ⚠️  {username} のリール取得失敗: {e}")

    return reels


def get_reel_details(page, reel_url: str) -> dict:
    """リールのキャプション・コメントを取得"""
    try:
        page.goto(reel_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        caption = page.evaluate("""
        () => {
            const el = document.querySelector('div._a9zs span') ||
                       document.querySelector('h1._aacl') ||
                       document.querySelector('span[class*="caption"]');
            return el ? el.innerText : '';
        }
        """) or ""

        comments = page.evaluate("""
        () => {
            const els = document.querySelectorAll('span._aacl:not([class*="follow"])');
            return Array.from(els).slice(0, 20).map(el => el.innerText.trim()).filter(t => t.length > 5);
        }
        """) or []

        return {"caption": caption, "comments": comments[:15]}
    except Exception:
        return {"caption": "", "comments": []}


def format_research_output(reels_with_details: list, now: datetime) -> str:
    """research-knowledge.md 追記用Markdownを生成"""
    lines = [
        f"\n## {now.strftime('%Y-%m-%d %H:%M')} Instagram バズリール リサーチ結果（美容系）",
        f"\n> 取得方法: Playwright（ブラウザ自動化）",
        f"> 取得件数: {len(reels_with_details)}件",
        f"> 対象: 10万再生以上のリール\n",
        "### バズリール一覧（再生数順）\n",
        "| 再生数 | アカウント | URL |",
        "|--------|-----------|-----|",
    ]

    for r in sorted(reels_with_details, key=lambda x: x.get("views", 0), reverse=True):
        lines.append(f"| {r['views']:,} | @{r['username']} | {r['url']} |")

    lines.append("\n### キャプション詳細（バズ投稿の1行目・構成パターン）\n")
    for i, r in enumerate(reels_with_details[:20], 1):
        caption = r.get("caption", "").replace("\n", " ")[:200]
        if not caption:
            continue
        first_line = caption.split("。")[0].split("\\n")[0][:80]
        lines.append(f"**{i}. @{r['username']} — {r['views']:,}再生**")
        lines.append(f"> 1行目: 「{first_line}」")
        lines.append(f"> キャプション全文: {caption[:150]}\n")

    lines.append("### コメント欄の悩みワード（読者のリアルな声）\n")
    all_comments = []
    for r in reels_with_details:
        all_comments.extend(r.get("comments", []))

    pain_words = ["ニキビ", "乾燥", "毛穴", "テカリ", "くすみ", "肌荒れ", "敏感肌",
                  "黒ずみ", "シミ", "たるみ", "目の下", "クマ", "脂性", "混合肌"]
    found = {}
    for c in all_comments:
        for w in pain_words:
            if w in c:
                found[w] = found.get(w, 0) + 1

    for w, cnt in sorted(found.items(), key=lambda x: -x[1]):
        lines.append(f"- 「{w}」— {cnt}件のコメントで言及")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Instagram バズリール フェッチャー")
    parser.add_argument("--min-views",   type=int,  default=MIN_VIEWS_DEFAULT)
    parser.add_argument("--max-reels",   type=int,  default=30)
    parser.add_argument("--dry-run",     action="store_true")
    parser.add_argument("--show-browser", action="store_true")
    args = parser.parse_args()

    load_env()

    ig_user = os.environ.get("INSTAGRAM_USERNAME", "")
    ig_pass = os.environ.get("INSTAGRAM_PASSWORD", "")

    if not ig_user or not ig_pass:
        print("エラー: INSTAGRAM_USERNAME と INSTAGRAM_PASSWORD を .env に設定してください。")
        sys.exit(1)

    now     = datetime.now(timezone(timedelta(hours=9)))
    headless = not args.show_browser

    print(f"📸 Instagram バズリールフェッチ開始 ({now.strftime('%Y-%m-%d %H:%M')} JST)")
    print(f"   条件: {args.min_views:,}再生以上 / 最大{args.max_reels}件\n")

    from playwright.sync_api import sync_playwright

    all_reels = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            locale="ja-JP",
        )
        page = context.new_page()

        # ログイン
        login_instagram(page, ig_user, ig_pass)

        # フォロー一覧取得
        following = get_following_list(page, ig_user)

        # 美容系アカウントをフィルタリング
        beauty_accounts = []
        print(f"  美容系アカウントを判定中（{len(following)}件）...")
        for i, uname in enumerate(following[:50]):  # 最大50アカウントチェック
            info = get_account_bio(page, uname)
            if is_beauty_account(info["bio"], info["username"], info["display_name"]):
                beauty_accounts.append(uname)
                print(f"  ✅ 美容系: @{uname}")
            if i % 10 == 9:
                print(f"  ({i+1}/{min(50, len(following))}件チェック済み...)")

        print(f"\n  美容系アカウント: {len(beauty_accounts)}件")

        # 拡張: 美容系アカウントのフォロイーも探索（最大3アカウント）
        extended_accounts = list(beauty_accounts)
        for uname in beauty_accounts[:3]:
            try:
                page.goto(f"https://www.instagram.com/{uname}/following/", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2000)
                sub_following = page.evaluate("""
                () => {
                    const links = document.querySelectorAll('a[href*="/"]');
                    return Array.from(links)
                        .map(a => a.href.match(/instagram\.com\/([^/?]+)/)?.[1])
                        .filter(u => u && !['p', 'reel', 'explore', 'accounts'].includes(u));
                }
                """) or []
                for sub in sub_following[:20]:
                    if sub not in extended_accounts:
                        info = get_account_bio(page, sub)
                        if is_beauty_account(info["bio"], info["username"], info["display_name"]):
                            extended_accounts.append(sub)
                            print(f"  🔍 発見: @{sub} (via @{uname})")
            except Exception:
                pass

        print(f"\n  調査対象アカウント合計: {len(extended_accounts)}件")

        # 各アカウントからリール取得
        reels_with_details = []
        for uname in extended_accounts:
            print(f"  リール取得中: @{uname}...")
            reels = get_reels_from_account(page, uname, args.min_views, 10)
            print(f"    → {len(reels)}件のリール（{args.min_views:,}再生以上）")

            for reel in reels[:5]:
                details = get_reel_details(page, reel["url"])
                reel.update(details)
                reels_with_details.append(reel)

            if len(reels_with_details) >= args.max_reels:
                break

        context.close()
        browser.close()

    # 結果出力
    reels_with_details.sort(key=lambda x: x.get("views", 0), reverse=True)
    print(f"\n📊 取得結果: {len(reels_with_details)}件のリール")
    for r in reels_with_details[:5]:
        print(f"  {r['views']:,}再生 | @{r['username']} | {r['url'][:60]}")

    content = format_research_output(reels_with_details, now)

    if args.dry_run:
        print("\n--- DRY RUN ---")
        print(content)
    else:
        RESEARCH_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RESEARCH_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + content + "\n")
        print(f"\n✅ {RESEARCH_FILE} に追記しました。")

    print("✅ Instagramフェッチ完了")


if __name__ == "__main__":
    main()
