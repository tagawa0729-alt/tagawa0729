#!/usr/bin/env python3
"""
SNS Autopilot 日次レポートをGmailで送信するスクリプト
使い方: python3 scripts/send_report.py
"""

import smtplib
import sys
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent.parent

GMAIL_USER     = "tagawa0729@gmail.com"
GMAIL_PASSWORD = "zlkvazkqhsfhqigm"
TO_ADDRESS     = "tagawa0729@gmail.com"


def read_file(path: Path, fallback: str = "（データなし）") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return fallback


def build_report() -> tuple[str, str]:
    """件名と本文を生成"""
    now = datetime.now(JST)
    date_str = now.strftime("%Y-%m-%d")

    # 各データファイルを読み込む
    engagement = read_file(BASE_DIR / "knowledge" / "latest-engagement-summary.md")
    research   = read_file(BASE_DIR / "knowledge" / "research-knowledge.md")
    # knowledge/next-topics.md を優先、なければルートの next-topics.md
    topics_path = BASE_DIR / "knowledge" / "next-topics.md"
    if not topics_path.exists():
        topics_path = BASE_DIR / "next-topics.md"
    topics = read_file(topics_path)
    log        = read_file(BASE_DIR / "scripts" / "schedule_posts_log.txt")

    # ログから最新の投稿状況を抽出（末尾50行）
    log_tail = "\n".join(log.splitlines()[-50:]) if log else "（ログなし）"

    subject = f"【SNS Autopilot】{date_str} 日次レポート"

    body = f"""SNS Autopilot 日次レポート
生成日時: {now.strftime("%Y-%m-%d %H:%M")} JST
========================================

■ エンゲージメントサマリー
{engagement}

========================================

■ 次回投稿テーマ（next-topics.md）
{topics}

========================================

■ Xリサーチ結果（最新分）
{chr(10).join(research.splitlines()[-80:])}

========================================

■ 本日の投稿ログ（最新50行）
{log_tail}

========================================
SNS Autopilot by Claude
"""
    return subject, body


def send_email(subject: str, body: str) -> bool:
    try:
        msg = MIMEMultipart()
        msg["From"]    = GMAIL_USER
        msg["To"]      = TO_ADDRESS
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, TO_ADDRESS, msg.as_string())
        return True
    except Exception as e:
        print(f"メール送信エラー: {e}", file=sys.stderr)
        return False


def main():
    print("レポート生成中...")
    subject, body = build_report()
    print(f"件名: {subject}")
    print("送信中...")
    if send_email(subject, body):
        print(f"✅ 送信完了 → {TO_ADDRESS}")
    else:
        print("❌ 送信失敗")
        sys.exit(1)


if __name__ == "__main__":
    main()
