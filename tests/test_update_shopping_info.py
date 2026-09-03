import sys
import unittest
import json
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from update_shopping_info import (
    clean_html,
    official_url,
    parse_hyundai,
    parse_hyundai_news_api,
    parse_lotte,
    parse_lotte_branches,
    parse_shinsegae,
    parse_shinsegae_shopping_json,
    topics_for,
)


class ParserTest(unittest.TestCase):
    def test_encoded_markup_is_removed(self):
        self.assertEqual(clean_html("혜택 &lt;b&gt;안내&lt;/b&gt;"), "혜택 안내")

    def test_non_official_links_are_rejected(self):
        self.assertEqual(official_url("hyundai", "https://example.com/event"), "")
        self.assertEqual(official_url("lotte", "http://www.lotteshopping.com/event"), "")

    def test_missing_image_stays_empty(self):
        page = '''
        <div class="event_list"><ul><li>
          <a href="EV000003_14_V.do?eventNo=36877">
            <p class="tit">9월 무이자 할인</p>
          </a>
        </li></ul></div><div class="paging_wrap"></div>
        '''
        self.assertEqual(parse_hyundai(page)[0]["imageUrl"], "")

    def test_hyundai_detail_link(self):
        page = '''
        <div class="event_list"><ul><li>
          <a href="EV000003_14_V.do?eventNo=36877&amp;eventCd=B0349900">
            <img src="/banner.png"><p class="tit">9월 무이자 할인</p>
            <span class="date">2026.09.01 ~ 2026.09.30</span>
          </a>
        </li></ul></div><div class="paging_wrap"></div>
        '''
        items = parse_hyundai(page)
        self.assertEqual(items[0]["category"], "discount")
        self.assertIn("eventNo=36877", items[0]["sourceUrl"])

    def test_lotte_detail_link_and_ended_filter(self):
        page = '''
        <li class="content-item"><a onclick="goCntsLink('C00901', 'THK100', 'N');">
          <div class="__badge"><span>사은</span></div>
          <div class="__title s-title7-m">L.POINT 증정</div>
          <div class="__info"><span>백화점 전점</span></div>
          <div class="__date">9.1 ~ 9.30</div></a></li>
        <li class="content-item"><a onclick="goCntsLink('C00902', 'CPM200', 'Y');">
          <div class="__title s-title7-m">종료 쿠폰</div></a></li>
        '''
        items = parse_lotte(page)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["category"], "gift")
        self.assertEqual(
            items[0]["sourceUrl"],
            "https://www.lotteshopping.com/thku/thkuDetail?thkuNo=THK100&ch=shopnow",
        )

    def test_shinsegae_detail_link(self):
        page = '''
        <div class="shin_list"><ul><li><a href="./view.do?eventSeq=2770&amp;">
          <div style="background: url('/banner.png')"></div>
          <div class="cnt_type">전점</div><div class="cnt_tit">가을 쇼핑</div>
          <div class="cnt_date">2026.09.01 ~ 2026.09.13</div>
        </a></li></ul><div class="btn_viewmore"></div></div>
        '''
        items = parse_shinsegae(page)
        self.assertEqual(items[0]["location"], "전점")
        self.assertIn("eventSeq=2770", items[0]["sourceUrl"])

    def test_fashion_topics_avoid_yeezy_false_positive(self):
        self.assertEqual(topics_for("키네틱 스테이지 팝업"), [])
        self.assertEqual(topics_for("아디다스 YEEZY 할인"), ["fashion", "adidas"])
        self.assertEqual(topics_for("나이키 에어포스 특가"), ["fashion", "nike"])

    def test_hyundai_news_api_keeps_only_fashion(self):
        page = json.dumps(
            {
                "result": {
                    "result": "200",
                    "items": [
                        {
                            "evntCrdCd": "E1",
                            "evntCrdNm": "나이키 20% 할인",
                            "evntCrdTypeCd": {"value": "01"},
                            "evntPlceNm": "2층 본매장",
                            "expsEvntStartDt": "20260903000000",
                            "expsEvntEndDt": "20260906000000",
                            "imgPath2": "event/nike.jpg",
                        },
                        {
                            "evntCrdCd": "E2",
                            "evntCrdNm": "식품 선물세트",
                            "evntCrdTypeCd": {"value": "01"},
                        },
                    ],
                }
            }
        )
        items = parse_hyundai_news_api(page, "B00126000", "천호점")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["topics"], ["fashion", "nike"])
        self.assertEqual(items[0]["category"], "discount")
        self.assertIn("branchCd=B00126000", items[0]["sourceUrl"])

    def test_shinsegae_json_uses_genre_for_fashion(self):
        page = json.dumps(
            {
                "shoppingInfoList": {
                    "page": [
                        {
                            "id": "100",
                            "storeCd": "SC00002",
                            "mainCd": "02",
                            "title1": "가을 신상품 제안",
                            "badge1": "쇼핑뉴스",
                            "brandNm": "컨버스",
                            "genreNm": "해외패션",
                            "link": "/cms12/test.txt",
                            "contentDtlCd": "01",
                            "imgUrl2": "/cms12/test.jpg",
                            "storeNm": "강남점",
                            "viewNm": "백화점",
                            "floorNm": "4층",
                            "expDt": "2026.09.03 - 2026.09.13",
                        }
                    ]
                }
            }
        )
        items = parse_shinsegae_shopping_json(page, "강남점")
        self.assertEqual(len(items), 1)
        self.assertIn("fashion", items[0]["topics"])
        self.assertIn("pageLink=%2Fcms12%2Ftest.txt", items[0]["sourceUrl"])

    def test_lotte_branch_parser_excludes_shopping_malls(self):
        page = """
        <a onclick='changeCstrInfo({"cstrCd":"0339","cstrDspNm":"파주점","cstrLrclsCd":"C00130"})'>파주</a>
        <a onclick='changeCstrInfo({"cstrCd":"0405","cstrDspNm":"수지점","cstrLrclsCd":"C00120"})'>수지</a>
        """
        self.assertEqual(parse_lotte_branches(page), {"0339": "파주점"})


if __name__ == "__main__":
    unittest.main()
