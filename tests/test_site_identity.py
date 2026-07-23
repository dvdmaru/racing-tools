# T-03 站名層紅線固化（Charlie 2026-07-23 裁決選 A）＋ S-A2 tabs 鍵盤焦點。
# 規則：站名層欄位（website_name / feed_channel_title / org_name / WebSite.name）
# 零「F1」字樣；F1 指涉一律放描述層（website_desc / feed_channel_desc / 頁面 title）。
import importlib.util
import json
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
