# -*- coding: utf-8 -*-
"""cli / __main__ 的输入展开、参数组合与入口分发。"""

import io
import os
import shutil
import unittest
import uuid
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pypdf import PdfWriter

from ulpp import __main__ as entry
from ulpp import cli

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SAMPLE = os.path.join(ROOT, "examples", "sample.pdf")


class CliEdgeBase(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(ROOT, f"ulpp_cli_edge_{uuid.uuid4().hex[:8]}")
        os.makedirs(self.dir, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.out = os.path.join(self.dir, "out")
        os.makedirs(self.out, exist_ok=True)

    def path(self, name):
        return os.path.join(self.dir, name)

    def make_pdf(self, name="blank.pdf"):
        path = self.path(name)
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        with open(path, "wb") as fh:
            writer.write(fh)
        return path


class TestPrescanAndExpand(CliEdgeBase):
    def test_prescan_lang_forms(self):
        self.assertEqual(cli._prescan_lang(["--lang", "en", "x"]), "en")
        self.assertEqual(cli._prescan_lang(["--lang=zh"]), "zh")
        self.assertIsNone(cli._prescan_lang(["x"]))
        self.assertIsNone(cli._prescan_lang(["--lang"]))

    def test_safe_extract_zip(self):
        src = self.make_pdf("in.pdf")
        zip_path = self.path("in.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(src, arcname="folder/in.pdf")
            zf.writestr("readme.txt", "ignore me")
            zf.writestr("empty/", "")
        dest = self.path("unzipped")
        files = cli._safe_extract_zip(zip_path, dest)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith("_in.pdf"))
        self.assertTrue(os.path.exists(files[0]))

    def test_expand_directory_zip_pdf_glob_and_dedupe(self):
        src = self.make_pdf("a.pdf")
        folder = self.path("folder")
        os.makedirs(folder)
        shutil.copy2(src, os.path.join(folder, "b.pdf"))
        Path(folder, "note.txt").write_text("x", encoding="utf-8")
        zip_path = self.path("bundle.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(src, arcname="c.pdf")
        result = cli.expand_inputs([folder, zip_path, src, src, os.path.join(folder, "*.pdf")])
        names = sorted(os.path.basename(p) for p in result)
        self.assertIn("b.pdf", names)
        self.assertIn("a.pdf", names)
        self.assertEqual(len(result), len(set(os.path.abspath(p) for p in result)))

    def test_expand_zip_uses_tempdir(self):
        src = self.make_pdf("z.pdf")
        zip_path = self.path("z.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(src, arcname="z.pdf")
        tmp = self.path("ziptmp")
        os.makedirs(tmp)
        with patch.object(cli.tempfile, "mkdtemp", return_value=tmp):
            result = cli.expand_inputs([zip_path])
        self.assertTrue(result[0].startswith(tmp))


class TestGridAndText(CliEdgeBase):
    def parse(self, argv):
        return cli.build_arg_parser().parse_args(argv)

    def test_grid_default_and_overrides(self):
        grid = cli.grid_from_args(self.parse([]))
        self.assertEqual(grid.per_sheet, 45)

        grid = cli.grid_from_args(self.parse([
            "--preset", "24", "--cols", "2", "--rows", "3",
            "--cell", "50x40", "--pitch", "51x41",
            "--margin-top", "3", "--inset", "1",
        ]))
        self.assertEqual((grid.cols, grid.rows), (2, 3))
        self.assertEqual((grid.cell_w, grid.cell_h), (50, 40))
        self.assertEqual((grid.pitch_x, grid.pitch_y), (51, 41))
        self.assertEqual(grid.margin_top, 3)
        self.assertEqual(grid.inset, 1)

    def test_grid_from_config(self):
        path = self.path("grid.json")
        from ulpp.config import GridSpec
        GridSpec(cols=2, rows=2).save(path)
        grid = cli.grid_from_args(self.parse(["--config", path]))
        self.assertEqual(grid.per_sheet, 4)

    def test_bad_preset_exits(self):
        with self.assertRaises(SystemExit):
            cli.grid_from_args(self.parse(["--preset", "does-not-exist"]))

    def test_collect_text_from_args_and_file(self):
        text_file = self.path("t.txt")
        Path(text_file).write_text("文件行 |2\n", encoding="utf-8")
        items = cli.collect_text_items(self.parse(["--text", "A", "--text-file", text_file]))
        self.assertEqual(len(items), 2)
        items = cli.collect_text_items(self.parse(["--text-file", text_file]))
        self.assertEqual(len(items), 1)


class TestMain(CliEdgeBase):
    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_list_presets(self):
        rc, out, _ = self.run_cli(["--list-presets"])
        self.assertEqual(rc, 0)
        self.assertIn("45", out)

    def test_no_input(self):
        rc, _, err = self.run_cli([])
        self.assertEqual(rc, 2)
        self.assertTrue(err)

    def test_text_only_and_save_config(self):
        cfg = self.path("saved.json")
        rc, out, err = self.run_cli([
            "--text", "文字 |2", "-o", self.out, "--save-config", cfg,
            "--no-proof", "--no-csv",
        ])
        self.assertEqual(rc, 0, err)
        self.assertTrue(os.path.exists(cfg))
        self.assertTrue(any(p.endswith(".pdf") for p in os.listdir(self.out)))

    def test_pdf_input_quiet(self):
        rc, out, err = self.run_cli([SAMPLE, "-o", self.out, "-q", "--first-page-only"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, "")
        self.assertTrue(any(p.endswith(".pdf") for p in os.listdir(self.out)))

    def test_no_content_returns_three(self):
        blank = self.make_pdf()
        rc, _, err = self.run_cli([blank, "-o", self.out])
        self.assertEqual(rc, 3)
        self.assertTrue(err)

    def test_default_out_dir_next_to_input(self):
        src = self.path("side.pdf")
        shutil.copy2(SAMPLE, src)
        rc, _, err = self.run_cli([src, "--no-proof", "--no-csv", "-q"])
        self.assertEqual(rc, 0, err)
        from ulpp.i18n import tr
        produced_dir = os.path.join(self.dir, tr("out.default_dir"))
        self.assertTrue(os.path.isdir(produced_dir))
        self.assertTrue(any(n.endswith(".pdf") for n in os.listdir(produced_dir)))

    def test_prescan_language_is_applied(self):
        rc, _, err = self.run_cli(["--lang", "zh", "--text", "中文", "-o", self.out, "-q"])
        self.assertEqual(rc, 0, err)


class TestEntryMain(unittest.TestCase):
    def run_entry(self, argv):
        fake_sys = SimpleNamespace(argv=["ulpp"] + list(argv))
        with patch.object(entry, "sys", fake_sys), \
                patch("ulpp.i18n.set_language") as set_language:
            return entry.main(), set_language

    def test_parse_gui_args(self):
        self.assertEqual(entry._parse_gui_args([]), (True, None))
        self.assertEqual(entry._parse_gui_args(["--lang", "en"]), (True, "en"))
        self.assertEqual(entry._parse_gui_args(["--lang=zh"]), (True, "zh"))
        self.assertEqual(entry._parse_gui_args(["--lang"]), (False, None))
        self.assertEqual(entry._parse_gui_args(["--lang", "-x"]), (False, None))
        self.assertEqual(entry._parse_gui_args(["file.pdf"]), (False, None))

    def test_v2_dispatch(self):
        with patch("ulpp.ui.shell.main", return_value=7) as shell:
            rc, set_language = self.run_entry(["--v2", "--lang", "en"])
        self.assertEqual(rc, 7)
        shell.assert_called_once_with("en")
        set_language.assert_called_with("en")

    def test_no_args_opens_gui(self):
        with patch("ulpp.gui.main") as gui:
            rc, set_language = self.run_entry([])
        self.assertEqual(rc, 0)
        gui.assert_called_once_with()
        set_language.assert_called_with(None)

    def test_language_only_opens_gui(self):
        with patch("ulpp.gui.main") as gui:
            rc, set_language = self.run_entry(["--lang=zh"])
        self.assertEqual(rc, 0)
        gui.assert_called_once_with()
        set_language.assert_called_with("zh")

    def test_other_args_go_to_cli(self):
        with patch("ulpp.cli.main", return_value=3) as cli_main:
            rc, _ = self.run_entry(["file.pdf"])
        self.assertEqual(rc, 3)
        cli_main.assert_called_once_with(["file.pdf"])


if __name__ == "__main__":
    unittest.main()
