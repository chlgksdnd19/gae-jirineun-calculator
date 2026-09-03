#!/usr/bin/env python3
"""Build the public department-store information feed without paid services."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse


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
    "hyundai": SOURCE_HOSTS["hyundai"] | {"imgprism.ehyundai.com"},
    "lotte": SOURCE_HOSTS["lotte"] | {"minfo.lotteshopping.com"},
    "shinsegae": SOURCE_HOSTS["shinsegae"],
}

HYUNDAI_BRANCHES = {
    "B00140000": "더현대 서울",
    "B00146000": "더현대 대구",
    "B00121000": "압구정본점",
    "B00122000": "무역센터점",
    "B00126000": "천호점",
    "B00127000": "신촌점",
    "B00141000": "미아점",
    "B00142000": "목동점",
    "B00143000": "중동점",
    "B00145000": "킨텍스점",
    "B00148000": "판교점",
    "B00129000": "울산점",
    "B00147000": "충청점",
    "B00124000": "커넥트현대 부산",
    "B00179000": "커넥트현대 청주",
    "B00172000": "현대아울렛 김포점",
    "B00174000": "현대아울렛 송도점",
    "B00177000": "현대아울렛 대전점",
    "B00178000": "현대아울렛 SPACE1",
    "B00173000": "현대아울렛 동대문점",
    "B00171000": "현대아울렛 가산점",
    "B00175000": "현대아울렛 가든파이브점",
    "B00176000": "현대아울렛 대구점",
}

SHINSEGAE_STORES = {
    "SC00002": "강남점",
    "SC00007": "신세계 사우스시티",
    "SC00006": "광주신세계",
    "SC00011": "김해점",
    "SC00013": "대구신세계",
    "SC00060": "대전신세계 Art & Science",
    "SC00005": "마산점",
    "SC00001": "본점",
    "SC00008": "센텀시티",
    "SC00012": "스타필드 하남점",
    "SC00010": "의정부점",
    "SC00009": "천안아산점",
    "SC00003": "타임스퀘어점",
}

FASHION_KEYWORDS = (
    "패션",
    "의류",
    "신발",
    "슈즈",
    "스니커즈",
    "운동화",
    "아우터",
    "모피",
    "스포츠",
    "아웃도어",
    "골프",
    "언더웨어",
    "란제리",
    "캐주얼",
    "남성복",
    "여성복",
    "아동복",
    "데님",
    "재킷",
    "자켓",
    "패딩",
    "코트",
    "니트",
    "티셔츠",
    "팬츠",
    "가방",
    "잡화",
    "해외패션",
    "여성패션",
    "남성패션",
    "영패션",
    "new collection",
    "뉴 컬렉션",
    "f/w",
    "fw ",
)

FASHION_BRANDS = {
    "진도모피",
    "유닛",
    "케네스레이디",
    "리스트",
    "제이제이지고트",
    "k2그룹",
    "와코루",
    "로로피아나",
    "플리츠미",
    "더잠",
    "내셔널지오그래픽",
    "뉴발란스",
    "컨버스",
    "클럽모나코",
    "dkny",
    "바버",
    "쌤소나이트",
    "폴스미스",
    "톰브라운",
    "아르마니",
    "제냐",
    "라르디니",
    "스톤아일랜드",
    "질스튜어트",
    "띠어리",
    "분더샵",
    "룰루레몬",
    "뷰오리",
    "포터리",
    "블런드스톤",
}

DISCOUNT_KEYWORDS = (
    "할인",
    "쿠폰",
    "sale",
    "세일",
    "특가",
    "시즌오프",
    "clearance",
    "프로모션",
    "리워드",
    "혜택",
    "균일가",
    "적립",
)


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
    if any(word in text for word in (*DISCOUNT_KEYWORDS, "무이자", "%")):
        return "discount"
    if any(
        word in text
        for word in ("사은", "증정", "리워드", "포인트", "상품권", "gift")
    ):
        return "gift"
    return "shopping"


def topics_for(
    title: str,
    badge: str = "",
    brand_name: str = "",
    genre: str = "",
    detail: str = "",
) -> list[str]:
    """Classify fashion content without treating location text as content."""

    text = clean_html(" ".join((title, badge, brand_name, genre, detail))).lower()
    topics: list[str] = []
    if re.search(r"(?:나이키|\bnike\b|\bsnkrs\b|\b조던\b|\bjordan\b)", text):
        topics.append("nike")
    if re.search(
        r"(?:아디다스|\badidas\b|이지\s*부스트|\byeezy\b|\bterrex\b|\b테렉스\b)",
        text,
    ):
        topics.append("adidas")

    bracket_tokens = {
        clean_html(value).lower()
        for value in re.findall(r"\[([^\]]+)\]", title)
    }
    branded = any(
        any(brand in token for brand in FASHION_BRANDS) for token in bracket_tokens
    )
    is_fashion = bool(topics) or branded or any(word in text for word in FASHION_KEYWORDS)
    if is_fashion:
        topics.insert(0, "fashion")
    return topics


def add_topics(
    item: dict,
    *,
    badge: str = "",
    brand_name: str = "",
    genre: str = "",
    detail: str = "",
) -> dict:
    topics = topics_for(
        item.get("title", ""), badge, brand_name, genre, detail
    )
    if topics:
        item["topics"] = topics
    return item


def is_fashion_item(item: dict) -> bool:
    return "fashion" in item.get("topics", [])


def _date_from_compact(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 8:
        return ""
    return f"{digits[:4]}.{digits[4:6]}.{digits[6:8]}"


def _fashion_sort_key(item: dict) -> tuple:
    topics = item.get("topics", [])
    priority = 5
    if "nike" in topics or "adidas" in topics:
        priority = 0 if item.get("category") == "discount" else 1
    elif "fashion" in topics:
        priority = 2 if item.get("category") == "discount" else 3
    brand_order = {"hyundai": 0, "lotte": 1, "shinsegae": 2}
    return (priority, brand_order.get(item.get("brand"), 9), item.get("title", ""))


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
            add_topics({
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
            })
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
            add_topics({
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
            }, badge=badge)
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
            add_topics({
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
            })
        )
    return _dedupe(items)[:20]


def parse_hyundai_news_api(
    page: str, branch_code: str, branch_name: str
) -> list[dict]:
    payload = json.loads(page)
    result = payload.get("result", {})
    if str(result.get("result")) != "200":
        return []
    items: list[dict] = []
    for raw in result.get("items", []):
        title = clean_html(str(raw.get("evntCrdNm", "")))
        topics = topics_for(title)
        if "fashion" not in topics:
            continue
        event_id = str(raw.get("evntCrdCd", "")).strip()
        if not event_id:
            continue
        type_code = str((raw.get("evntCrdTypeCd") or {}).get("value", "01"))
        category_name = {
            "01": "event",
            "02": "gift",
            "03": "culture",
            "04": "special",
        }.get(type_code, "event")
        source_url = official_url(
            "hyundai",
            "/newPortal/SN/SN_0201000.do?"
            + urlencode(
                {
                    "evntCrdCd": event_id,
                    "category": category_name,
                    "page": "1",
                    "branchCd": branch_code,
                }
            ),
        )
        image_path = str(raw.get("imgPath2", "")).strip()
        image_url = official_url(
            "hyundai",
            f"https://imgprism.ehyundai.com/{image_path}" if image_path else "",
            image=True,
        )
        start = _date_from_compact(str(raw.get("expsEvntStartDt", "")))
        end = _date_from_compact(str(raw.get("expsEvntEndDt", "")))
        period = " ~ ".join(value for value in (start, end) if value)
        place = clean_html(str(raw.get("evntPlceNm", "")))
        item = {
            "id": f"hyundai-{event_id}",
            "brand": "hyundai",
            "category": category_for(title),
            "title": title,
            "summary": f"현대백화점 {branch_name} 공식 쇼핑뉴스",
            "location": " · ".join(value for value in (branch_name, place) if value),
            "period": period,
            "sourceUrl": source_url,
            "imageUrl": image_url,
            "topics": topics,
        }
        if source_url:
            items.append(item)
    return _dedupe(items)


def parse_shinsegae_shopping_json(page: str, store_name: str) -> list[dict]:
    payload = json.loads(page)
    raw_items = (payload.get("shoppingInfoList") or {}).get("page", [])
    items: list[dict] = []
    for raw in raw_items:
        title = clean_html(str(raw.get("title1", "")))
        badge = clean_html(str(raw.get("badge1", "")))
        brand_name = clean_html(str(raw.get("brandNm", "")))
        genre = clean_html(str(raw.get("genreNm", "")))
        topics = topics_for(title, badge, brand_name, genre)
        if "fashion" not in topics:
            continue
        content_id = str(raw.get("id", "")).strip()
        store_code = str(raw.get("storeCd", "")).strip()
        main_code = str(raw.get("mainCd", "")).strip()
        page_link = str(raw.get("link", "")).strip()
        if not content_id or not store_code or not main_code or not page_link:
            continue
        source_url = official_url(
            "shinsegae",
            "/shopping/view.do?"
            + urlencode(
                {
                    "mainCd": main_code,
                    "pageLink": page_link,
                    "contentDtlCd": str(raw.get("contentDtlCd", "")),
                    "contentId": content_id,
                    "storeCd": store_code,
                    "brandCd": str(raw.get("brandCd", "")),
                }
            ),
        )
        image_url = official_url(
            "shinsegae", str(raw.get("imgUrl2", "")), image=True
        )
        location = " · ".join(
            value
            for value in (
                clean_html(str(raw.get("storeNm", ""))) or store_name,
                clean_html(str(raw.get("viewNm", ""))),
                clean_html(str(raw.get("floorNm", ""))),
            )
            if value
        )
        item = {
            "id": f"shinsegae-shopping-{store_code}-{content_id}",
            "brand": "shinsegae",
            "category": category_for(title, badge),
            "title": title,
            "summary": " · ".join(
                value for value in (brand_name, badge, "신세계 공식 쇼핑정보") if value
            ),
            "location": location,
            "period": clean_html(str(raw.get("expDt", ""))),
            "sourceUrl": source_url,
            "imageUrl": image_url,
            "topics": topics,
        }
        if source_url:
            items.append(item)
    return _dedupe(items)


def parse_lotte_branches(page: str) -> dict[str, str]:
    branches: dict[str, str] = {}
    for raw in re.findall(r"changeCstrInfo\((\{.*?\})\)", page, re.I | re.S):
        try:
            data = json.loads(unescape(raw))
        except (TypeError, ValueError):
            continue
        if data.get("cstrLrclsCd") not in {"C00110", "C00130"}:
            continue
        code = str(data.get("cstrCd", "")).strip()
        name = clean_html(str(data.get("cstrDspNm", "")))
        if code and name:
            branches[code] = name
    return branches


def _curl_url(url: str) -> str:
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


def collect_hyundai_fashion() -> list[dict]:
    def collect_branch(branch_code: str, branch_name: str) -> list[dict]:
        list_url = (
            "https://www.ehyundai.com/newPortal/SN/SN_0101000.do?"
            + urlencode({"branchCd": branch_code})
        )
        list_page = _curl_url(list_url)
        dm_match = re.search(r"var\s+curtMblDmCd\s*=\s*'([^']+)'", list_page)
        if not dm_match:
            raise ValueError(f"{branch_name}: 모바일 전단 ID를 찾지 못했습니다")
        dm_code = dm_match.group(1)
        results: list[dict] = []
        for type_code in ("01", "04"):
            param = (
                f"mblDmCd={dm_code}&evntCrdTypeCd={type_code}"
                "&pageSize=100&page=1"
            )
            api_url = (
                "https://www.ehyundai.com/newPortal/SN/GetCmsContentsAJX.do?"
                f"apiID=ifAppHdcms012&param={quote(param, safe='')}"
            )
            results.extend(
                parse_hyundai_news_api(
                    _curl_url(api_url), branch_code, branch_name
                )
            )
        return results

    return _collect_parallel(HYUNDAI_BRANCHES.items(), collect_branch, "hyundai fashion")


def collect_lotte_fashion(seed_page: str) -> list[dict]:
    branches = parse_lotte_branches(seed_page)
    if not branches:
        branches = {
            "0002": "잠실점",
            "0001": "본점",
            "0005": "부산본점",
            "0406": "의왕점",
            "0352": "동부산점",
            "0362": "기흥점",
            "0331": "김해점",
            "0346": "이천점",
            "0339": "파주점",
        }

    def collect_branch(code: str, _name: str) -> list[dict]:
        url = "https://www.lotteshopping.com/shopnow/cntsList?" + urlencode(
            {"cstrCd": code}
        )
        return [item for item in parse_lotte(_curl_url(url)) if is_fashion_item(item)]

    return _collect_parallel(branches.items(), collect_branch, "lotte fashion")


def collect_shinsegae_fashion() -> list[dict]:
    def collect_store(store_code: str, store_name: str) -> list[dict]:
        results: list[dict] = []
        for main_code in ("11", "02", "04"):
            url = "https://deptmapp.shinsegae.com/shopping/ajaxList.do?" + urlencode(
                {"mainCd": main_code, "storeCd": store_code}
            )
            results.extend(
                parse_shinsegae_shopping_json(_curl_url(url), store_name)
            )
        return results

    return _collect_parallel(
        SHINSEGAE_STORES.items(), collect_store, "shinsegae fashion"
    )


def _collect_parallel(
    entries, collector: Callable[[str, str], list[dict]], label: str
) -> list[dict]:
    items: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(collector, code, name): (code, name)
            for code, name in entries
        }
        for future in as_completed(futures):
            code, name = futures[future]
            try:
                items.extend(future.result())
            except Exception as error:
                print(f"{label} {code} {name}: {error}", file=sys.stderr)
    return _dedupe(items)


def extract_benefit_summary(page: str) -> str:
    candidates: list[tuple[int, str]] = []
    for raw in re.findall(r"<(?:td|p|em)[^>]*>(.*?)</(?:td|p|em)>", page, re.I | re.S):
        value = clean_html(raw)
        if not value or len(value) > 220:
            continue
        lower = value.lower()
        if "지금 롯데백화점에서 다양한 혜택과 소식을" in value:
            continue
        score = 0
        if any(word in lower for word in ("할인", "특가", "%", "지원금", "적립", "h.point")):
            score += 4
        if "구매 시" in lower or "이상 구매" in lower:
            score += 2
        if any(word in lower for word in ("증정", "혜택", "프로모션")):
            score += 1
        if score:
            candidates.append((score, value))
    ordered: list[str] = []
    for _score, value in sorted(candidates, key=lambda entry: -entry[0]):
        if value not in ordered:
            ordered.append(value)
        if len(ordered) == 2:
            break
    return " · ".join(ordered)


def enrich_priority_items(items: list[dict]) -> list[dict]:
    targets = [
        item
        for item in items
        if any(topic in item.get("topics", []) for topic in ("nike", "adidas"))
    ]

    def enrich(item: dict) -> tuple[str, str]:
        return item["id"], extract_benefit_summary(_curl_url(item["sourceUrl"]))

    summaries: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(enrich, item): item for item in targets[:40]}
        for future in as_completed(futures):
            try:
                item_id, summary = future.result()
                if summary:
                    summaries[item_id] = summary
            except Exception as error:
                print(f"priority detail: {error}", file=sys.stderr)

    for item in items:
        summary = summaries.get(item["id"])
        if not summary:
            continue
        item["summary"] = summary
        lower = summary.lower()
        if any(
            word in lower
            for word in (
                "할인",
                "특가",
                "%",
                "지원금",
                "적립",
                "h.point",
                "리워드",
                "쿠폰",
                "sale",
            )
        ):
            item["category"] = "discount"
    return items


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
    return _curl_url(url)


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
    source_pages: dict[str, str] = {}
    success_count = 0

    for brand, url in SOURCES.items():
        try:
            source_page = fetch_page(brand, url)
            source_pages[brand] = source_page
            parsed = PARSERS[brand](source_page)
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

    if not os.environ.get("SHOPPING_INFO_FIXTURE_DIR") and os.environ.get(
        "SHOPPING_INFO_SKIP_SUPPLEMENTAL", "0"
    ) != "1":
        collectors = {
            "hyundai": collect_hyundai_fashion,
            "lotte": lambda: collect_lotte_fashion(source_pages.get("lotte", "")),
            "shinsegae": collect_shinsegae_fashion,
        }
        for brand, collector in collectors.items():
            try:
                fashion_items = collector()
                if not fashion_items:
                    raise ValueError("지점별 패션 쇼핑뉴스를 찾지 못했습니다")
                items.extend(fashion_items)
                source_status.setdefault(brand, {})["fashionCount"] = len(fashion_items)
            except Exception as error:
                stale = [
                    item
                    for item in previous_items
                    if item.get("brand") == brand and is_fashion_item(item)
                ]
                items.extend(stale)
                source_status.setdefault(brand, {})["fashionCount"] = len(stale)
                source_status[brand]["fashionMessage"] = str(error)[:240]
                print(
                    f"{brand} supplemental: {error}; kept {len(stale)} stale fashion items",
                    file=sys.stderr,
                )

        items = enrich_priority_items(_dedupe(items))

    items = sorted(_dedupe(items), key=_fashion_sort_key)

    feed = {
        "schemaVersion": 1,
        "updatedAt": now,
        "sourceNotice": "롯데·현대·신세계 공식 쇼핑뉴스를 매일 확인합니다. 각 카드를 눌러 지점·기간·제외 품목 등 최종 조건을 확인하세요.",
        "sources": source_status,
        "items": items,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(feed['items'])} items to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
