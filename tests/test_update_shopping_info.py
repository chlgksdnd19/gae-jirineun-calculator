import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from update_shopping_info import (
    clean_html,
    official_url,
    parse_hyundai,
    parse_lotte,
    parse_shinsegae,
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


if __name__ == "__main__":
    unittest.main()
