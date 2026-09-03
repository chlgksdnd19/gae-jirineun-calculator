#!/usr/bin/env python3
"""Build the public department-store information feed without paid services."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urljoin, urlparse


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "docs" / "shopping-info.json"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
)

SOURCES = {
    "hyundai": "https://ehyundai.com/newPortal/EV/EV000001_L.do?page=1",
    "lotte": "https://www.lotteshopping.com/shopnow/cntsList?cstrCd=0005",
    "shinsegae": "https://deptmapp.shinsegae.com/shopping/event/list.do",
}

SOURCE_HOSTS = {
    "hyundai": {"ehyundai.com", "www.ehyundai.com"},
    "lotte": {"lotteshopping.com", "www.lotteshopping.com"},
    "shinsegae": {"deptmapp.shinsegae.com"},
}
IMAGE_HOSTS = {
    "hyundai": SOURCE_HOSTS["hyundai"],
    "lotte": SOURCE_HOSTS["lotte"] | {"minfo.lotteshopping.com"},
    "shinsegae": SOURCE_HOSTS["shinsegae"],
}


def clean_html(value: str) -> str:
    for _ in range(3):
        decoded = unescape(value)
        if decoded == value:
            break
        value = decoded
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def official_url(brand: str, raw_url: str, *, image: bool = False) -> str:
    raw_url = unescape(raw_url).strip()
    if not raw_url:
        return ""
    candidate = urljoin(SOURCES[brand], raw_url)
    parsed = urlparse(candidate)
    allowed_hosts = IMAGE_HOSTS[brand] if image else SOURCE_HOSTS[brand]
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in allowed_hosts:
        return ""
    return candidate


def category_for(title: str, badge: str = "") -> str:
    text = f"{badge} {title}".lower()
    if any(word in text for word in ("할인", "쿠폰", "sale", "세일", "무이자")):
        return "discount"
    if any(
        word in text
        for word in ("사은", "증정", "리워드", "포인트", "상품권", "gift")
    ):
        return "gift"
    return "shopping"


def _first(pattern: str, value: str) -> str:
    match = re.search(pattern, value, flags=re.IGNORECASE | re.DOTALL)
    return clean_html(match.group(1)) if match else ""


def _dedupe(items: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if not item["title"] or not item["sourceUrl"] or item["id"] in seen:
            continue
        seen.add(item["id"])
        result.append(item)
    return result


def parse_hyundai(page: str) -> list[dict]:
    section = _first_raw(
        r'<div\s+class="event_list"[^>]*>(.*?)<div\s+class="paging_wrap', page
    )
    items: list[dict] = []
    for block in re.findall(r"<li[^>]*>(.*?)</li>", section, re.I | re.S):
        href_match = re.search(r'<a\s+href="([^"]+)"', block, re.I)
        title = _first(r'<p\s+class="tit"[^>]*>(.*?)</p>', block)
        period = _first(r'<span\s+class="date"[^>]*>(.*?)</span>', block)
        image_match = re.search(r'<img\s+src="([^"]+)"', block, re.I)
        if not href_match or not title:
            continue
        source_url = official_url("hyundai", href_match.group(1))
        if not source_url:
            continue
        event_no = parse_qs(urlparse(source_url).query).get("eventNo", [title])[0]
        items.append(
            {
                "id": f"hyundai-{event_no}",
                "brand": "hyundai",
                "category": category_for(title),
                "title": title,
                "summary": "현대백화점 공식 이벤트",
                "location": "현대백화점 전점",
                "period": period,
                "sourceUrl": source_url,
                "imageUrl": official_url(
                    "hyundai", image_match.group(1) if image_match else "", image=True
                ),
            }
        )
    return _dedupe(items)[:20]


LOTTE_DETAIL_PATHS = {
    "C00901": "/thku/thkuDetail?thkuNo=",
    "C00902": "/cpn/cpnDetail?cpnInfoNo=",
    "C00903": "/shpgnews/shpgnewsDetail?shpgNewsNo=",
    "C00908": "/cuterent/cuterentDetail?entNo=",
    "C00914": "/cuterent/cuterentDetail?entNo=",
}


def parse_lotte(page: str) -> list[dict]:
    items: list[dict] = []
    blocks = re.findall(
        r'<li\s+class="[^"]*content-item[^"]*"[^>]*>(.*?)</li>',
        page,
        re.IGNORECASE | re.DOTALL,
    )
    for block in blocks:
        link = re.search(
            r"goCntsLink\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'",
            block,
            re.IGNORECASE,
        )
        if not link or link.group(3).upper() == "Y":
            continue
        content_type, content_no = link.group(1), link.group(2)
        path = LOTTE_DETAIL_PATHS.get(content_type)
        if not path:
            continue
        title = _first(r'class="__title[^"]*"[^>]*>(.*?)</div>', block)
        badge = _first(r'class="__badge"[^>]*>.*?<span[^>]*>(.*?)</span>', block)
        info = _first_raw(r'class="__info"[^>]*>(.*?)</div>', block)
        locations = [clean_html(value) for value in re.findall(r"<span[^>]*>(.*?)</span>", info, re.I | re.S)]
        period = _first(r'class="__date"[^>]*>(.*?)</div>', block)
        image_match = re.search(r'<img\s+src="([^"]+)"', block, re.I)
        source_url = official_url(
            "lotte",
            f"https://www.lotteshopping.com{path}{content_no}&ch=shopnow",
        )
        if not source_url:
            continue
        items.append(
            {
                "id": f"lotte-{content_no}",
                "brand": "lotte",
                "category": category_for(title, badge),
                "title": title,
                "summary": "롯데백화점 공식 행사",
                "location": " · ".join(locations) or "롯데백화점",
                "period": period,
                "sourceUrl": source_url,
                "imageUrl": official_url(
                    "lotte", image_match.group(1) if image_match else "", image=True
                ),
            }
        )
    return _dedupe(items)[:50]


def parse_shinsegae(page: str) -> list[dict]:
    section = _first_raw(
        r'<div\s+class="shin_list"[^>]*>(.*?)<div\s+class="btn_viewmore', page
    )
    items: list[dict] = []
    for block in re.findall(r"<li[^>]*>(.*?)</li>", section, re.I | re.S):
        href_match = re.search(r'<a\s+href="([^"]+)', block, re.I)
        title = _first(r'class="cnt_tit"[^>]*>(.*?)</div>', block)
        location = _first(r'class="cnt_type"[^>]*>(.*?)</div>', block)
        period = _first(r'class="cnt_date"[^>]*>(.*?)</div>', block)
        image_match = re.search(r"background:\s*url\('([^']+)'\)", block, re.I)
        if not href_match or not title:
            continue
        raw_href = unescape(href_match.group(1)).rstrip('&" ')
        source_url = official_url("shinsegae", raw_href)
        if not source_url:
            continue
        event_no = parse_qs(urlparse(source_url).query).get("eventSeq", [title])[0]
        items.append(
            {
                "id": f"shinsegae-{event_no}",
                "brand": "shinsegae",
                "category": category_for(title),
                "title": title,
                "summary": "신세계백화점 공식 뉴스 및 이벤트",
                "location": location or "신세계백화점",
                "period": period,
                "sourceUrl": source_url,
                "imageUrl": official_url(
                    "shinsegae", image_match.group(1) if image_match else "", image=True
                ),
            }
        )
    return _dedupe(items)[:20]


def _first_raw(pattern: str, value: str) -> str:
    match = re.search(pattern, value, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else ""


PARSERS: dict[str, Callable[[str], list[dict]]] = {
    "hyundai": parse_hyundai,
    "lotte": parse_lotte,
    "shinsegae": parse_shinsegae,
}


def fetch_page(brand: str, url: str) -> str:
    fixture_dir = os.environ.get("SHOPPING_INFO_FIXTURE_DIR")
    if fixture_dir:
        fixture_path = Path(fixture_dir) / f"{brand}.html"
        if not fixture_path.exists():
            fixture_path = Path(fixture_dir) / f"{brand}_events.html"
        return fixture_path.read_text(encoding="utf-8")
    result = subprocess.run(
        [
            "curl",
            "--location",
            "--compressed",
            "--fail",
            "--silent",
            "--show-error",
            "--max-time",
            "35",
            "--user-agent",
            USER_AGENT,
            "--header",
            "Accept-Language: ko-KR,ko;q=0.9",
            url,
        ],
        check=True,
        capture_output=True,
    )
    return result.stdout.decode("utf-8", errors="replace")


def load_previous() -> dict:
    if not OUTPUT_PATH.exists():
        return {"items": [], "sources": {}}
    try:
        return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"items": [], "sources": {}}


def main() -> int:
    previous = load_previous()
    previous_items = previous.get("items", [])
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    items: list[dict] = []
    source_status: dict[str, dict] = {}
    success_count = 0

    for brand, url in SOURCES.items():
        try:
            parsed = PARSERS[brand](fetch_page(brand, url))
            if not parsed:
                raise ValueError("공식 페이지에서 행사 카드를 찾지 못했습니다")
            items.extend(parsed)
            source_status[brand] = {
                "ok": True,
                "count": len(parsed),
                "checkedAt": now,
                "url": url,
            }
            success_count += 1
        except Exception as error:  # A stale feed is safer than an empty feed.
            stale = [item for item in previous_items if item.get("brand") == brand]
            items.extend(stale)
            source_status[brand] = {
                "ok": False,
                "count": len(stale),
                "checkedAt": now,
                "url": url,
                "message": str(error)[:240],
            }
            print(f"{brand}: {error}; kept {len(stale)} stale items", file=sys.stderr)

    if success_count == 0:
        print("All official sources failed; the existing feed was left unchanged", file=sys.stderr)
        return 1

    feed = {
        "schemaVersion": 1,
        "updatedAt": now,
        "sourceNotice": "각 행사 카드를 눌러 공식 상세 홈페이지에서 최종 조건을 확인하세요.",
        "sources": source_status,
        "items": _dedupe(items),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(feed['items'])} items to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
