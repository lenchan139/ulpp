# -*- coding: utf-8 -*-
"""SheetStore 的损坏数据、迁移与默认值分支。"""

import json
import os
import shutil
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ulpp.config import GridSpec
from ulpp import sheets
from ulpp.sheets import (
    PrinterProfile,
    SheetRecord,
    SheetStore,
    SheetStoreError,
    default_sheets_path,
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
JSON_UTF8 = {"encoding": "utf-8"}


class SheetsEdgeBase(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(ROOT, f"ulpp_sheets_edge_{uuid.uuid4().hex[:8]}")
        os.makedirs(self.dir, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = Path(self.dir) / "sheets.json"

    def write(self, name, payload):
        target = Path(self.dir) / name
        target.write_text(json.dumps(payload, ensure_ascii=False), **JSON_UTF8)
        return target


class TestDefaultPath(SheetsEdgeBase):
    def test_windows_appdata_branch(self):
        fake_os = SimpleNamespace(name="nt", environ={"APPDATA": self.dir})
        with patch.object(sheets, "os", fake_os), \
                patch.object(sheets, "_migrate_legacy", side_effect=lambda p: p):
            path = default_sheets_path()
        self.assertEqual(path, Path(self.dir) / "ulpp" / "sheets.json")

    def test_migrate_legacy_existing_new(self):
        self.path.write_text("{}", **JSON_UTF8)
        self.assertEqual(sheets._migrate_legacy(self.path), self.path)

    def test_migrate_legacy_copies_old(self):
        new = Path(self.dir) / "ulpp" / "sheets.json"
        old = Path(self.dir) / "label-sheet" / "sheets.json"
        old.parent.mkdir(parents=True)
        old.write_text('{"old": true}', **JSON_UTF8)
        result = sheets._migrate_legacy(new)
        self.assertEqual(result, new)
        self.assertTrue(new.exists())

    def test_migrate_legacy_copy_failure_uses_old(self):
        new = Path(self.dir) / "ulpp" / "sheets.json"
        old = Path(self.dir) / "label-sheet" / "sheets.json"
        old.parent.mkdir(parents=True)
        old.write_text("{}", **JSON_UTF8)
        with patch.object(sheets.shutil, "copy2", side_effect=OSError("denied")):
            result = sheets._migrate_legacy(new)
        self.assertEqual(result, old)


class TestPrinterAndRecord(unittest.TestCase):
    def test_invalid_feed_falls_back(self):
        p = PrinterProfile.from_dict({"id": "x", "feed": "sideways"})
        self.assertEqual(p.feed, "face_up_short")

    def test_sheet_grid_not_object(self):
        with self.assertRaises(SheetStoreError):
            SheetRecord.from_dict({"grid": [1, 2]})

    def test_sheet_bad_dimensions(self):
        with self.assertRaises(SheetStoreError):
            SheetRecord.from_dict({"grid": GridSpec(cols=0).to_dict()})

    def test_sheet_defaults_id_and_name(self):
        record = SheetRecord.from_dict({"grid": GridSpec(cols=2, rows=2).to_dict()})
        self.assertTrue(record.id)
        self.assertTrue(record.name.startswith("sheet-"))


class TestStoreBranches(SheetsEdgeBase):
    def test_path_string_is_coerced(self):
        store = SheetStore(path=str(self.path))
        self.assertIsInstance(store.path, Path)

    def test_path_none_uses_default(self):
        with patch.object(sheets, "default_sheets_path", return_value=self.path):
            store = SheetStore(path=None)
        self.assertEqual(store.path, self.path)

    def test_bad_default_printer_resets(self):
        store = SheetStore(path=self.path, printers=[PrinterProfile(id="p1")],
                           default_printer="missing")
        self.assertEqual(store.default_printer, "p1")

    def test_get_printer_unknown_returns_first(self):
        store = SheetStore(path=self.path, printers=[PrinterProfile(id="p1")])
        self.assertEqual(store.get_printer("nope").id, "p1")

    def test_save_printer_replaces_and_sets_default(self):
        store = SheetStore(path=self.path)
        store.save_printer(PrinterProfile(id="p1", name="one"))
        store.save_printer(PrinterProfile(id="p1", name="two"))
        self.assertEqual([p.name for p in store.printers if p.id == "p1"], ["two"])
        store.default_printer = ""
        store.save_printer(PrinterProfile(id="p2"))
        self.assertEqual(store.default_printer, "p2")

    def test_unique_name_skips_taken_suffixes(self):
        store = SheetStore(path=self.path)
        store.add_sheet("paper", GridSpec(cols=2, rows=2))
        store.add_sheet("paper", GridSpec(cols=2, rows=2))
        third = store.add_sheet("paper", GridSpec(cols=2, rows=2))
        self.assertEqual(third.name, "paper #3")
        blank = store.add_sheet("   ", GridSpec(cols=2, rows=2))
        self.assertEqual(blank.name, "sheet")

    def test_get_mark_unknown_ids(self):
        store = SheetStore(path=self.path)
        self.assertIsNone(store.get_sheet("nope"))
        self.assertEqual(store.mark_used("nope", [1]), [])
        self.assertEqual(store.mark_free("nope", [1]), [])

    def test_load_top_level_not_object(self):
        self.path.write_text("[]", **JSON_UTF8)
        with self.assertRaises(SheetStoreError):
            SheetStore.load(self.path)

    def test_load_bad_version(self):
        self.path.write_text(json.dumps({"version": "abc"}), **JSON_UTF8)
        with self.assertRaises(SheetStoreError):
            SheetStore.load(self.path)

    def test_load_future_version(self):
        self.path.write_text(json.dumps({"version": 999}), **JSON_UTF8)
        with self.assertRaises(SheetStoreError):
            SheetStore.load(self.path)

    def test_load_skips_non_dict_sheets_and_dedups_ids(self):
        payload = {
            "version": 1,
            "sheets": [
                "not-a-dict",
                {"id": "same", "name": "A", "grid": GridSpec(cols=2, rows=2).to_dict()},
                {"id": "same", "name": "B", "grid": GridSpec(cols=2, rows=2).to_dict()},
            ],
        }
        self.path.write_text(json.dumps(payload), **JSON_UTF8)
        store = SheetStore.load(self.path)
        self.assertEqual([s.name for s in store.sheets], ["A", "B"])
        self.assertNotEqual(store.sheets[0].id, store.sheets[1].id)

    def test_load_corrupt_sheet_record(self):
        payload = {"version": 1, "sheets": [{"grid": "bad"}]}
        self.path.write_text(json.dumps(payload), **JSON_UTF8)
        with self.assertRaises(SheetStoreError):
            SheetStore.load(self.path)

    def test_load_corrupt_printer_record(self):
        payload = {"version": 1, "printers": [{"offset_x_mm": "not-a-number"}]}
        self.path.write_text(json.dumps(payload), **JSON_UTF8)
        with self.assertRaises(SheetStoreError):
            SheetStore.load(self.path)

    def test_load_ignores_non_dict_printers_and_saves_explicit_path(self):
        payload = {"version": 1, "printers": ["junk"]}
        self.path.write_text(json.dumps(payload), **JSON_UTF8)
        store = SheetStore.load(self.path)
        other = Path(self.dir) / "other.json"
        saved = store.save(other)
        self.assertEqual(saved, other)
        self.assertTrue(other.exists())
        self.assertEqual(store.path, other)


if __name__ == "__main__":
    unittest.main()
