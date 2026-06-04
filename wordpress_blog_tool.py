#!/usr/bin/env python3
"""Create WordPress-ready blog drafts and optionally publish them.

This tool is intentionally dependency-free so it can run in a fresh checkout.
It generates WordPress block-editor compatible HTML from a topic, title,
keywords, and audience. If WordPress credentials are provided, it can also
create a draft or published post through the WordPress REST API.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_OUTPUT_DIR = Path("drafts")
DEFAULT_STATUS = "draft"
WORDPRESS_STATUSES = {"draft", "publish", "pending", "private", "future"}


@dataclass(frozen=True)
class BlogDraft:
    """WordPress blog draft metadata and body."""

    title: str
    slug: str
    excerpt: str
    keywords: list[str]
    audience: str
    html: str
    created_at: str


def split_keywords(raw_keywords: str | Sequence[str] | None) -> list[str]:
    """Normalize comma-separated or repeated keyword input."""

    if raw_keywords is None:
        return []

    if isinstance(raw_keywords, str):
        candidates: Iterable[str] = raw_keywords.split(",")
    else:
        candidates = []
        for item in raw_keywords:
            candidates = [*candidates, *str(item).split(",")]

    seen: set[str] = set()
    keywords: list[str] = []
    for keyword in candidates:
        normalized = keyword.strip()
        dedupe_key = normalized.casefold()
        if normalized and dedupe_key not in seen:
            keywords.append(normalized)
            seen.add(dedupe_key)
    return keywords


def slugify(value: str) -> str:
    """Create a URL-safe slug while preserving ASCII words and numbers."""

    normalized = re.sub(r"[^\w\s-]", "", value.lower(), flags=re.UNICODE)
    normalized = re.sub(r"[\s_-]+", "-", normalized, flags=re.UNICODE).strip("-")
    return normalized or "wordpress-blog-draft"


def sentence_case(value: str) -> str:
    """Return a readable sentence fragment for headings and summaries."""

    stripped = value.strip()
    if not stripped:
        return "WordPress blog"
    return stripped[0].upper() + stripped[1:]


def build_excerpt(topic: str, audience: str, keywords: Sequence[str]) -> str:
    """Build a concise search snippet for the post."""

    keyword_phrase = ", ".join(keywords[:3]) if keywords else "実践ポイント"
    return (
        f"{sentence_case(topic)}について、{audience}に向けて{keyword_phrase}を中心に"
        "わかりやすく整理したWordPress投稿用の下書きです。"
    )


def wp_paragraph(text: str) -> str:
    return f"<!-- wp:paragraph -->\n<p>{escape(text)}</p>\n<!-- /wp:paragraph -->"


def wp_heading(text: str, level: int = 2) -> str:
    safe_level = min(max(level, 2), 4)
    return (
        f"<!-- wp:heading {{\"level\":{safe_level}}} -->\n"
        f"<h{safe_level}>{escape(text)}</h{safe_level}>\n"
        "<!-- /wp:heading -->"
    )


def wp_list(items: Sequence[str]) -> str:
    body = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f"<!-- wp:list -->\n<ul>{body}</ul>\n<!-- /wp:list -->"


def generate_blog_draft(
    *,
    title: str,
    topic: str,
    audience: str,
    keywords: Sequence[str] | None = None,
) -> BlogDraft:
    """Generate a WordPress-ready blog draft from basic planning inputs."""

    clean_title = sentence_case(title)
    clean_topic = sentence_case(topic)
    clean_audience = audience.strip() or "読者"
    clean_keywords = split_keywords(keywords)
    excerpt = build_excerpt(clean_topic, clean_audience, clean_keywords)

    keyword_text = "、".join(clean_keywords) if clean_keywords else "重要なポイント"
    checklist = [
        f"{clean_topic}で最初に押さえる目的を明確にする",
        f"{clean_audience}がつまずきやすい点を具体例で補足する",
        "導入・本文・まとめの流れで読みやすく整理する",
        "最後に次の行動がわかるチェックリストを入れる",
    ]
    if clean_keywords:
        checklist.insert(1, f"SEOキーワード（{keyword_text}）を自然な文脈で使う")

    sections = [
        wp_paragraph(excerpt),
        wp_heading(f"{clean_topic}の概要"),
        wp_paragraph(
            f"この記事では、{clean_topic}について{clean_audience}が短時間で理解し、"
            "実際の行動に移せるように要点を整理します。"
        ),
        wp_heading("記事で伝えるべきポイント"),
        wp_list(checklist),
        wp_heading("本文の構成案"),
        wp_paragraph(
            "1つ目の段落では背景と課題、2つ目の段落では解決策、3つ目の段落では"
            "実践時の注意点を説明します。必要に応じて画像、表、FAQを追加してください。"
        ),
        wp_heading("まとめ"),
        wp_paragraph(
            f"{clean_topic}は、{clean_audience}にとって継続的な改善につながるテーマです。"
            "公開前にタイトル、メタディスクリプション、内部リンク、アイキャッチ画像を確認しましょう。"
        ),
    ]

    html = f"<!-- wp:post-title /-->\n\n" + "\n\n".join(sections) + "\n"
    return BlogDraft(
        title=clean_title,
        slug=slugify(clean_title),
        excerpt=excerpt,
        keywords=clean_keywords,
        audience=clean_audience,
        html=html,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def save_draft(draft: BlogDraft, output_dir: Path = DEFAULT_OUTPUT_DIR) -> tuple[Path, Path]:
    """Save HTML and JSON metadata files for a draft."""

    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / f"{draft.slug}.html"
    json_path = output_dir / f"{draft.slug}.json"
    html_path.write_text(draft.html, encoding="utf-8")
    json_path.write_text(json.dumps(asdict(draft), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return html_path, json_path


def load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def create_wordpress_post(
    *,
    site_url: str,
    username: str,
    app_password: str,
    draft: BlogDraft,
    status: str = DEFAULT_STATUS,
    timeout: int = 30,
) -> dict:
    """Create a WordPress post through the REST API."""

    if status not in WORDPRESS_STATUSES:
        raise ValueError(f"Unsupported WordPress status: {status}")

    endpoint = site_url.rstrip("/") + "/wp-json/wp/v2/posts"
    payload = json.dumps(
        {
            "title": draft.title,
            "content": draft.html,
            "excerpt": draft.excerpt,
            "slug": draft.slug,
            "status": status,
        }
    ).encode("utf-8")
    token = base64.b64encode(f"{username}:{app_password}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "User-Agent": "ryouiku-dev-blog-tool/1.0",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"WordPress API error {error.code}: {body}") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate WordPress-ready blog drafts and optionally publish them.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              python wordpress_blog_tool.py --title "療育の始め方" --topic "療育" --keyword "発達支援,家庭療育"
              WP_URL=https://example.com WP_USERNAME=editor WP_APP_PASSWORD='xxxx xxxx xxxx xxxx' \\
                python wordpress_blog_tool.py --title "療育の始め方" --topic "療育" --publish
            """
        ),
    )
    parser.add_argument("--title", required=True, help="Post title")
    parser.add_argument("--topic", required=True, help="Main topic to explain")
    parser.add_argument("--audience", default="保護者・支援者", help="Target readers")
    parser.add_argument(
        "--keyword",
        "--keywords",
        action="append",
        default=[],
        help="SEO keyword. Repeat or pass comma-separated values.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for local drafts")
    parser.add_argument("--publish", action="store_true", help="Create a WordPress post via REST API")
    parser.add_argument("--site-url", default=os.getenv("WP_URL"), help="WordPress site URL or WP_URL")
    parser.add_argument("--username", default=os.getenv("WP_USERNAME"), help="WordPress username or WP_USERNAME")
    parser.add_argument(
        "--app-password",
        default=os.getenv("WP_APP_PASSWORD"),
        help="WordPress application password or WP_APP_PASSWORD",
    )
    parser.add_argument(
        "--status",
        default=DEFAULT_STATUS,
        choices=sorted(WORDPRESS_STATUSES),
        help="WordPress post status when publishing",
    )
    parser.add_argument("--timeout", type=int, default=30, help="WordPress API timeout in seconds")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    draft = generate_blog_draft(
        title=args.title,
        topic=args.topic,
        audience=args.audience,
        keywords=split_keywords(args.keyword),
    )
    html_path, json_path = save_draft(draft, args.output_dir)
    print(f"Saved HTML draft: {html_path}")
    print(f"Saved metadata: {json_path}")

    if args.publish:
        missing = [
            name
            for name, value in (
                ("--site-url/WP_URL", args.site_url),
                ("--username/WP_USERNAME", args.username),
                ("--app-password/WP_APP_PASSWORD", args.app_password),
            )
            if not value
        ]
        if missing:
            print("Missing WordPress credentials: " + ", ".join(missing), file=sys.stderr)
            return 2
        response = create_wordpress_post(
            site_url=args.site_url,
            username=args.username,
            app_password=args.app_password,
            draft=draft,
            status=args.status,
            timeout=args.timeout,
        )
        print("Created WordPress post:")
        print(json.dumps({"id": response.get("id"), "link": response.get("link")}, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
