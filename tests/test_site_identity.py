# T-03 站名層紅線固化（Charlie 2026-07-23 裁決選 A）＋ S-A2 tabs 鍵盤焦點。
# 規則：站名層欄位（website_name / feed_channel_title / org_name / WebSite.name）
# 零「F1」字樣；F1 指涉一律放描述層（website_desc / feed_channel_desc / 頁面 title）。
import importlib.util
import json
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("racinglib", ROOT / "scripts" / "racinglib.py")
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

SITE = json.loads((ROOT / "config" / "site.json").read_text())


class TestSiteNameLayerNoF1(unittest.TestCase):
    """站名層欄位不得含 F1 字樣（IP 紅線：域名/站名/品牌零 F1，內文指涉 OK）。"""

    def test_name_layer_fields_have_no_f1(self):
        for key in ("org_name", "website_name", "feed_channel_title",
                    "brand_mark", "brand_tag", "title_suffix"):
            self.assertNotIn("F1", SITE[key], f"站名層欄位 {key} 含 F1 字樣")

    def test_website_node_name_clean_desc_carries_f1(self):
        node = rc.website_node(SITE)
        self.assertNotIn("F1", node["name"])
        # 資訊沒有丟：F1 指涉移到 description（描述層）
        self.assertIn("F1", node.get("description", ""))

    def test_home_title_exists_for_homepage(self):
        # build-articles.py 首頁 <title> 前半改讀 home_title（不再 split website_name）
        self.assertTrue(SITE.get("home_title"))


class TestTabsFocusVisible(unittest.TestCase):
    """S-A2：CSS-only tabs 的 radio 聚焦時，對應 label 必須有可見焦點框。"""

    def test_tabgroup_emits_focus_visible_rule(self):
        html = rc.tabgroup("tg", [("a", "甲", "<p>A</p>", ""), ("b", "乙", "<p>B</p>", "")])
        self.assertIn('#tg-a:focus-visible~.tablabels label[for="tg-a"]', html)
        self.assertIn('#tg-b:focus-visible~.tablabels label[for="tg-b"]', html)
        self.assertIn("outline:2px solid var(--accent)", html)


class TestSisterSiteInterlink(unittest.TestCase):
    """姊妹站互連清單＝本站目前唯一可靠的被發現路徑，只增不減。

    2026-07-31 GSC 實查：本站 index_inspect 回 `URL is unknown to Google`、
    三個月只被檢索 1 次。真因是全網域零連入，而備援的 sitemap 卡在 twtools.cc
    全家族的 GSC pending。所以這道測試釘的不是排版，是**發現路徑不能被靜默拿掉**。
    """

    # twtools 生態系八站（不含本站自己）。改名可以改文案，網域不准消失。
    REQUIRED_HOSTS = {
        "aire.twtools.cc", "tree.twtools.cc", "foootball.twtools.cc",
        "baseball.twtools.cc", "basketball.twtools.cc", "shhhh.cc", "dvdmaru.com",
    }

    @staticmethod
    def _hosts(entries):
        return {urlsplit(u).netloc for _, u in entries}

    def test_sister_list_covers_every_family_site(self):
        missing = self.REQUIRED_HOSTS - self._hosts(rc.SISTER_SITES)
        self.assertEqual(missing, set(), f"姊妹站清單漏了：{sorted(missing)}")

    def test_missing_host_is_actually_caught(self):
        """反向：拿掉一站，上面那條斷言必須真的不成立。

        全綠有兩種可能——清單真的完整，或斷言寫壞了什麼都比不到。
        沒有這條，這個檔就是本站踩過四次的「gate 太寬但全綠」。
        """
        truncated = [e for e in rc.SISTER_SITES if "basketball" not in e[1]]
        self.assertTrue(self.REQUIRED_HOSTS - self._hosts(truncated))

    def test_rendered_footer_links_are_followed_and_exclude_self(self):
        html = rc.sister_sites_html(SITE)
        for host in self.REQUIRED_HOSTS:
            self.assertIn(host, html, f"footer 沒渲染出 {host}")
        # 自家內鏈不加 nofollow：內鏈權重就是目的
        self.assertNotIn("nofollow", html)

    def test_self_exclusion_actually_removes_a_link(self):
        """排除本站的機制要真的會動。

        直接對 racing 斷言「沒有自連」是假測試——racing 本來就不在清單裡，
        那條斷言永遠成立、抓不到任何事。所以改成餵一個 base 命中清單的站，
        看那個連結是否真的消失。
        """
        as_baseball = dict(SITE, base="https://baseball.twtools.cc")
        html = rc.sister_sites_html(as_baseball)
        self.assertNotIn("baseball.twtools.cc", html)
        self.assertIn("basketball.twtools.cc", html)  # 其他站不受影響

    def test_footer_carries_sister_links_on_every_page(self):
        """掛在 site_footer_html＝每一頁都有，不是只有首頁。"""
        self.assertIn("basketball.twtools.cc", rc.site_footer_html(SITE))


if __name__ == "__main__":
    unittest.main()
