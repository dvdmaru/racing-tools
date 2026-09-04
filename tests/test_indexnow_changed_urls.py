#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IndexNow 變動判斷的回歸測試：文章頁必須推得出去。

## 由來（2026-09-04）

`_indexnow_changed_urls()` 原本只有一個來源：**工作樹髒檔**。它的 docstring 寫著
「public-racing/ 產物有 commit、CI checkout 乾淨 → build 後髒檔＝本次變動」。

那個假設對**每週 cron** 成立（抓到新賽果 → 重建與 committed 不同 → 有髒檔 → 推），
對**內容型 PR 剛好反過來**：文章的產物是在 PR 裡就 commit 進去的（本 repo 慣例，
public-racing/ 有近 600 個追蹤檔），CI 重建出位元組相同的東西 → 零髒檔；
文章頁已被追蹤所以也不是 untracked → 判定「無變動」→ **永不推送**。

實測證據：2026-08-31 諾里斯續約篇與 2026-09-04 的 2027 里程篇，兩次部署 IndexNow
推的都只有 `/results/` 這種靠 live 資料驅動的頁，**文章本身一次都沒被推過**。
這個洞無聲存在了很久，因為 Charlie 每次上新文章都會手動去 GSC 要求索引，
手動動作一直在遮蓋它——**「有跑」不等於「有推到」**。

## 這裡釘三件事，而且必須一起釘

1. **內容型 PR 的形狀**（產物已 commit、工作樹乾淨）必須推得出文章 URL。
   這是把缺陷做成可執行的重現：關掉新來源，這條就會紅。
2. **cron 的形狀**（工作樹髒）行為不變——修法不准把原本會推的情況弄丟。
3. **workflow 的兩半必須同時在**：`fetch-depth: 2` 與 `--indexnow-from-commit`。
   ☠️ 只有其中一半等於沒修：沒有深度就拿不到父 commit（程式會降級成只看髒檔），
   沒有旗標則根本不啟用。**分開釘會讓人以為改一半就好**，所以合成一條測試。
"""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_module():
    """update-racing.py 名字有連字號，import 不了，用 spec 載入。"""
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("updateracing",
                                                  ROOT / "scripts" / "update-racing.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["updateracing"] = m
    spec.loader.exec_module(m)
    return m


ur = _load_module()


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


class _FakeRepo:
    """一個最小的 repo，模擬 CI 乾淨 checkout 後的狀態。"""

    def __init__(self, tmp):
        self.path = pathlib.Path(tmp)
        _git(self.path, "init", "-q", "-b", "main")
        _git(self.path, "config", "user.email", "t@example.com")
        _git(self.path, "config", "user.name", "t")
        self.write("public-racing/index.html", "home v1")
        self.commit("初始")

    def write(self, rel, body):
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def commit(self, msg):
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-q", "-m", msg)


class ContentPrShapeTests(unittest.TestCase):
    """內容型 PR：產物已 commit、工作樹乾淨。舊實作在這裡回空清單。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = _FakeRepo(self.tmp.name)
        # 模擬合併一個內容 PR：新增文章頁 + 改首頁，全部 commit 進去
        self.repo.write("public-racing/articles/new-piece/index.html", "文章")
        self.repo.write("public-racing/index.html", "home v2")
        self.repo.commit("feat(article): 新文章（產物一併 commit）")
        self._orig_root = ur.ROOT
        ur.ROOT = self.repo.path

    def tearDown(self):
        ur.ROOT = self._orig_root
        self.tmp.cleanup()

    def test_working_tree_is_clean(self):
        """前提檢查：這個形狀下工作樹確實是乾淨的（洞的成因）。"""
        out = _git(self.repo.path, "status", "--porcelain").stdout.strip()
        self.assertEqual(out, "", "工作樹應為乾淨，否則本測試沒有重現到那個形狀")

    def test_old_behaviour_finds_nothing(self):
        """只看工作樹髒檔 → 什麼都推不出來。這就是 2026-09-04 之前的實際行為。"""
        urls, new = ur._indexnow_changed_urls(from_commit=False)
        self.assertEqual(urls, [], "舊來源在內容型 PR 應該一條都找不到（這正是那個洞）")
        self.assertEqual(new, [])

    def test_from_commit_finds_the_article(self):
        """啟用 commit-diff 來源 → 文章與首頁都推得出來，且文章被標成新頁。"""
        urls, new = ur._indexnow_changed_urls(from_commit=True)
        self.assertIn(f"{ur.BASE_URL}/articles/new-piece/", urls)
        self.assertIn(f"{ur.BASE_URL}/", urls)
        self.assertIn(f"{ur.BASE_URL}/articles/new-piece/", new,
                      "新增的頁要進 new（部署前 404，是 live 探測的訊號）")
        self.assertNotIn(f"{ur.BASE_URL}/", new, "既有頁被修改不算新頁")


class CronShapeTests(unittest.TestCase):
    """cron：重建產生髒檔。修法不准把原本會推的情況弄丟。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = _FakeRepo(self.tmp.name)
        self.repo.write("public-racing/results/index.html", "賽果 v1")
        self.repo.commit("既有賽果頁")
        # 模擬 CI 內重建：賽果頁內容變了、又多一個新頁（未追蹤）
        self.repo.write("public-racing/results/index.html", "賽果 v2")
        self.repo.write("public-racing/standings/index.html", "積分榜（新）")
        self._orig_root = ur.ROOT
        ur.ROOT = self.repo.path

    def tearDown(self):
        ur.ROOT = self._orig_root
        self.tmp.cleanup()

    def test_dirty_files_still_detected(self):
        urls, new = ur._indexnow_changed_urls(from_commit=False)
        self.assertIn(f"{ur.BASE_URL}/results/", urls)
        self.assertIn(f"{ur.BASE_URL}/standings/", urls)
        self.assertIn(f"{ur.BASE_URL}/standings/", new, "untracked 新頁要進 new")
        self.assertNotIn(f"{ur.BASE_URL}/results/", new)


class ShallowCloneTests(unittest.TestCase):
    """拿不到父 commit 時要**明講並降級**，不准靜默當成「沒有變動」。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name)
        _git(self.path, "init", "-q", "-b", "main")
        _git(self.path, "config", "user.email", "t@example.com")
        _git(self.path, "config", "user.name", "t")
        (self.path / "public-racing").mkdir(parents=True)
        (self.path / "public-racing" / "index.html").write_text("home", encoding="utf-8")
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-q", "-m", "唯一一個 commit（無父）")
        self._orig_root = ur.ROOT
        ur.ROOT = self.path

    def tearDown(self):
        ur.ROOT = self._orig_root
        self.tmp.cleanup()

    def test_no_parent_degrades_loudly(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            urls, _ = ur._indexnow_changed_urls(from_commit=True)
        self.assertEqual(urls, [], "沒有父 commit 時不應憑空生出 URL")
        self.assertIn("fetch-depth", buf.getvalue(),
                      "降級必須印出可行動的訊息（要人去把 fetch-depth 補上），不可靜默")


class PathToUrlTests(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(ur._path_to_url("public-racing/articles/x/index.html"),
                         f"{ur.BASE_URL}/articles/x/")
        self.assertEqual(ur._path_to_url("public-racing/llms.txt"),
                         f"{ur.BASE_URL}/llms.txt")
        self.assertIsNone(ur._path_to_url("public-racing/sitemap.xml"),
                          )
        self.assertIsNone(ur._path_to_url("public-racing/articles/x/cover.png"))


class WorkflowWiringTests(unittest.TestCase):
    """☠️ 兩半必須同時在——只有其中一半等於沒修。

    ⚠️ **一律解析 YAML 結構，不要對整份檔案做字串比對。**
    本檔第一版就是字串比對，反向對照當場抓到它是假的：workflow 的**註解**裡
    也寫著 `fetch-depth: 2` 與 `--indexnow-from-commit`，所以把真正的設定整個拿掉，
    測試照樣全綠。本 repo 記憶裡的原話：**散文宣稱≠實際接線**。
    """

    WF = ROOT / ".github" / "workflows" / "racing-weekly.yml"

    def _steps(self):
        import yaml
        doc = yaml.safe_load(self.WF.read_text(encoding="utf-8"))
        return doc["jobs"]["update"]["steps"]

    def test_checkout_fetch_depth_is_at_least_two(self):
        """沒有深度就拿不到 HEAD^，程式會降級成只看髒檔＝等於沒修。"""
        checkout = [s for s in self._steps()
                    if isinstance(s.get("uses"), str) and "actions/checkout" in s["uses"]]
        self.assertTrue(checkout, "找不到 checkout step")
        depth = (checkout[0].get("with") or {}).get("fetch-depth")
        self.assertIsNotNone(depth, "checkout 必須設 fetch-depth（預設淺層 clone 拿不到父 commit）")
        self.assertGreaterEqual(int(depth), 2, "fetch-depth 至少要 2 才拿得到 HEAD^")

    def test_dispatch_passes_the_flag_and_cron_does_not(self):
        """旗標要在 run 指令裡、且掛在 workflow_dispatch 條件上。

        掛條件的理由：cron 每週都跑，無條件帶會把上一個 commit 的 URL 一推再推。
        """
        runs = [s["run"] for s in self._steps()
                if isinstance(s.get("run"), str) and "update-racing.py" in s["run"]]
        self.assertTrue(runs, "找不到跑 update-racing.py 的 step")
        cmd = runs[0]
        self.assertIn("--indexnow-from-commit", cmd,
                      "workflow_dispatch 必須帶 --indexnow-from-commit，否則新來源不啟用")
        self.assertIn("workflow_dispatch", cmd,
                      "旗標要掛在 workflow_dispatch 條件裡，不可無條件帶給 cron")


if __name__ == "__main__":
    unittest.main()
