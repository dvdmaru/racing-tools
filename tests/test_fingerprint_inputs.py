"""Fingerprint inputs that previously left selective encyclopedia regeneration stale."""
import hashlib
import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


regen = _load("regen_fingerprint_inputs", "regen-encyclopedia.py")


class FingerprintInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.intros = self.tmp / "intros"
        self.intros.mkdir()
        self.intro = self.intros / "2002.md"
        self.intro.write_text("approved intro v1", encoding="utf-8")
        self.approved = {"season-intro-2002": {"article_sha256": self._sha(self.intro)}}
        self.orig_intro_dir = regen.gs.INTRO_DIR
        self.orig_approved = regen.gs._load_approved
        regen.gs.INTRO_DIR = self.intros
        regen.gs._load_approved = lambda: self.approved
        self.addCleanup(self._restore_intro)
        self.con = regen.fs.connect_db()
        self.addCleanup(self.con.close)

    @staticmethod
    def _sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _restore_intro(self):
        regen.gs.INTRO_DIR = self.orig_intro_dir
        regen.gs._load_approved = self.orig_approved

    def test_intro_edit_changes_only_its_season_and_regenerates_only_that_year(self):
        before = regen.compute_fingerprints(self.con)
        fp = self.tmp / "fingerprints.json"
        fp.write_text(json.dumps(before), encoding="utf-8")
        self.intro.write_text("approved intro v2", encoding="utf-8")

        rendered = []
        originals = (regen.gs._render_one_season, regen.gs.render_index,
                     regen.dr.render_index, regen.dr.gen_driver,
                     regen.cg.render_index, regen.cg.gen_constructor,
                     regen.gs.render_round, regen.save_fingerprints)
        regen.gs._render_one_season = lambda year, urls, rounds: rendered.append(year)
        regen.gs.render_index = lambda built: "index"
        regen.dr.render_index = lambda con: "drivers"
        regen.dr.gen_driver = lambda did, con: {"slug": did}
        regen.cg.render_index = lambda con: "constructors"
        regen.cg.gen_constructor = lambda cid, con: {"slug": cid}
        regen.gs.render_round = lambda *args: "round"
        regen.save_fingerprints = lambda *args, **kwargs: None
        try:
            result = regen.selective_regen(self.con, fp_path=fp)
        finally:
            (regen.gs._render_one_season, regen.gs.render_index,
             regen.dr.render_index, regen.dr.gen_driver,
             regen.cg.render_index, regen.cg.gen_constructor,
             regen.gs.render_round, regen.save_fingerprints) = originals
        self.assertEqual(result["changed_years"], [2002])
        self.assertEqual(rendered, [2002])

    def test_constructor_roster_file_changes_driver_fingerprints(self):
        roster = self.tmp / "constructor-roster.json"
        roster.write_text("{}", encoding="utf-8")
        original = regen.CONSTRUCTOR_ROSTER
        regen.CONSTRUCTOR_ROSTER = roster
        try:
            before = regen.compute_fingerprints(self.con)
            roster.write_text('{"changed":true}', encoding="utf-8")
            after = regen.compute_fingerprints(self.con)
        finally:
            regen.CONSTRUCTOR_ROSTER = original
        self.assertNotEqual(before["drivers"], after["drivers"])
        self.assertEqual(before["seasons"], after["seasons"])

    # ---------- 譯名表 sha（2026-08-24 補；原本只有賽道頁有）----------
    #
    # ☠️ 病灶：譯名住在 scripts/*-zh.json，不在 db.sqlite。改一個譯名 → db 切片 sha 不變
    # → 選擇性重生說「這頁沒變」→ 頁上印的還是舊譯名，全綠。賽道頁 2026-08-23 就切了
    # 這份 sha，車手頁與車隊頁沒有。
    #
    # 兩個方向都要測，缺一不可：
    # ① 陽性——會渲染那張表的頁群，改了必須失效；
    # ② 陰性——不渲染那張表的頁群，改了必須**不**失效（否則等於每次改譯名白刷全站，
    #    而且「全部都變」這種實作照樣能讓 ① 全綠）。

    def _sandbox_scripts(self):
        """把 scripts/*-zh.json 複製到暫存目錄並讓 regen 指過去，才能就地改而不動 repo。"""
        sand = self.tmp / "scripts"
        sand.mkdir(exist_ok=True)
        for name in ("circuit-zh.json", "driver-zh.json", "team-zh.json", "race-zh.json"):
            src = ROOT / "scripts" / name
            if src.exists():
                shutil.copy2(src, sand / name)
        original = regen.SCRIPTS
        regen.SCRIPTS = sand
        self.addCleanup(setattr, regen, "SCRIPTS", original)
        return sand

    def _touch(self, path):
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    def test_team_zh_edit_invalidates_every_page_group_that_prints_team_names(self):
        """陽性：車隊頁（自己的譯名）、車手頁（車隊 chips）、賽道頁（優勝車隊）、
        賽季線（車隊積分榜／車手所屬車隊）與分站頁都要變。"""
        sand = self._sandbox_scripts()
        before = regen.compute_fingerprints(self.con)
        self._touch(sand / "team-zh.json")
        after = regen.compute_fingerprints(self.con)
        for group in ("constructors", "drivers", "circuits", "seasons", "rounds"):
            self.assertNotEqual(before[group], after[group],
                                f"改 team-zh.json 後 {group} 指紋沒變＝該頁群會靜默 stale")

    def test_driver_zh_edit_does_not_invalidate_constructor_pages(self):
        """陰性：車隊頁上沒有任何車手名，改 driver-zh.json 不准白刷它。

        沒有這一條的話，「把三張表全切進每個頁群」也會讓上面那個陽性測試全綠，
        代價是每次改一個車手譯名就重生全部車隊頁。
        """
        sand = self._sandbox_scripts()
        before = regen.compute_fingerprints(self.con)
        self._touch(sand / "driver-zh.json")
        after = regen.compute_fingerprints(self.con)
        self.assertNotEqual(before["drivers"], after["drivers"])
        self.assertNotEqual(before["circuits"], after["circuits"])
        self.assertNotEqual(before["seasons"], after["seasons"],
                            "賽季總覽印車手名（積分榜、各站冠軍），driver-zh 一改必須失效")
        self.assertEqual(before["constructors"], after["constructors"],
                         "車隊頁不印車手名，卻因 driver-zh.json 失效＝白刷")

    def test_driver_zh_edit_invalidates_the_season_line(self):
        """陽性：賽季總覽的車手積分榜／各站冠軍、車手分頁、分站頁都印車手譯名，
        改一個字元就必須讓 seasons 與 rounds 兩群失效（否則 415 頁靜默 stale）。"""
        sand = self._sandbox_scripts()
        before = regen.compute_fingerprints(self.con)
        self._touch(sand / "driver-zh.json")
        after = regen.compute_fingerprints(self.con)
        for group in ("seasons", "rounds"):
            self.assertNotEqual(before[group], after[group],
                                f"改 driver-zh.json 後 {group} 指紋沒變＝該頁群會靜默 stale")
        # 逐年檢查：不是只有某一季變，而是每一季的切片都吃到這張表。
        self.assertEqual(sorted(before["seasons"]), sorted(after["seasons"]))
        for year, sha in before["seasons"].items():
            self.assertNotEqual(sha, after["seasons"][year], f"{year} 季指紋沒吃到 driver-zh")

    def test_race_zh_edit_invalidates_only_the_season_line(self):
        """陽性＋陰性：分站名譯名只印在賽季線（總覽的各站冠軍表、車手／車隊分頁的逐站列）
        與分站頁上；車手生涯頁／車隊頁／賽道頁一個分站名都不印。

        ⚠️ PR #59 原本這條叫 test_unrendered_zh_table_never_invalidates_anything，斷言
        race-zh.json「不被任何百科頁群渲染」。那個前提對賽季線是錯的——2024 賽季總覽的
        HTML 裡就有「澳洲站」。錯的陰性測試比沒有測試更糟：它會把真的洞鎖成「預期行為」。
        """
        sand = self._sandbox_scripts()
        race_zh = sand / "race-zh.json"
        if not race_zh.exists():
            self.skipTest("race-zh.json 不存在，此測試前提不成立")
        before = regen.compute_fingerprints(self.con)
        self._touch(race_zh)
        after = regen.compute_fingerprints(self.con)
        for group in ("seasons", "rounds"):
            self.assertNotEqual(before[group], after[group],
                                f"{group} 印分站名，race-zh.json 一改卻沒失效＝靜默 stale")
        for group in ("constructors", "drivers", "circuits"):
            self.assertEqual(before[group], after[group],
                             f"race-zh.json 沒被 {group} 渲染，卻讓它失效＝白刷")

    def test_circuit_zh_edit_invalidates_round_pages_but_not_the_season_line(self):
        """賽道譯名只有 render_round 印（rc.circuit_pair）；賽季總覽與車手／車隊分頁不印。

        所以 circuit-zh.json 掛在分站頁指紋、不進 _year_slice：進去就等於改一個賽道譯名
        白刷 415 頁的整條賽季線。陰性那半才是這條測試的重點。
        """
        sand = self._sandbox_scripts()
        circuit_zh = sand / "circuit-zh.json"
        if not circuit_zh.exists():
            self.skipTest("circuit-zh.json 不存在，此測試前提不成立")
        before = regen.compute_fingerprints(self.con)
        self._touch(circuit_zh)
        after = regen.compute_fingerprints(self.con)
        for group in ("rounds", "circuits"):
            self.assertNotEqual(before[group], after[group],
                                f"{group} 印賽道名，circuit-zh.json 一改卻沒失效＝靜默 stale")
        for group in ("seasons", "drivers", "constructors"):
            self.assertEqual(before[group], after[group],
                             f"circuit-zh.json 沒被 {group} 渲染，卻讓它失效＝白刷")

    def test_fingerprints_are_stable_when_nothing_changes(self):
        """陰性基準：什麼都不改，兩次計算必須完全相同（否則上面的陽性斷言毫無意義）。"""
        self._sandbox_scripts()
        self.assertEqual(regen.compute_fingerprints(self.con),
                         regen.compute_fingerprints(self.con))

    def test_adjudicated_override_is_fingerprinted_only_for_affected_season(self):
        override_slice = regen._season_override_slice(1976)
        self.assertEqual(override_slice["renderer"], "preserve-raw-json-type-v1")
        rows = override_slice["rows"]
        self.assertEqual(len(rows), 6)
        self.assertIn({"table": "driver_standings", "season": 1976,
                       "entity_id": "hunt", "field": "points",
                       "raw_value": 66.0, "value": 69.0, "by": "charlie"}, rows)
        self.assertEqual(regen._season_override_slice(2026), [],
                         "無裁決的當季不得因歷史 override 白刷")


if __name__ == "__main__":
    unittest.main()
