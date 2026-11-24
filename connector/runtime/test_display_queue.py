"""Tests for the local display queue (order, hold metadata, reorder, remove)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parents[1]
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(ROOT / "templates"))


class DisplayQueueTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        (self.root / "connector").mkdir(parents=True)
        os.environ["FENNSILL_ROOT"] = str(self.root)
        os.environ["FENNSILL_DISPLAY_QUEUE"] = str(
            self.root / "connector" / "display_queue.json"
        )
        os.environ["FENNSILL_QUEUE_PREVIEWS"] = str(
            self.root / "connector" / "queue_previews"
        )
        # Fresh module state for path helpers.
        import importlib

        import display_queue as dq

        importlib.reload(dq)
        self.dq = dq
        self.frame = bytes([0xFF] * dq.FRAME_BYTES)

    def tearDown(self):
        self._tmpdir.cleanup()
        for key in (
            "FENNSILL_ROOT",
            "FENNSILL_DISPLAY_QUEUE",
            "FENNSILL_QUEUE_PREVIEWS",
        ):
            os.environ.pop(key, None)

    def test_append_order_and_preview(self):
        a = self.dq.append_item(job_id="j1", title="First", hold_sec=300, frame=self.frame)
        b = self.dq.append_item(job_id="j2", title="Second", hold_sec=180, frame=self.frame)
        items = self.dq.list_items()
        self.assertEqual([i["id"] for i in items], [a["id"], b["id"]])
        self.assertEqual(items[0]["hold_sec"], 300)
        self.assertEqual(items[1]["hold_sec"], 180)
        self.assertTrue(Path(a["preview_path"]).is_file())
        self.assertTrue(Path(a["frame_path"]).is_file())
        self.assertEqual(self.dq.load_frame_bytes(a), self.frame)

    def test_move_waiting_not_showing(self):
        a = self.dq.append_item(job_id="j1", title="A", hold_sec=0, frame=self.frame)
        b = self.dq.append_item(job_id="j2", title="B", hold_sec=0, frame=self.frame)
        self.assertTrue(self.dq.move_item(b["id"], -1))
        ids = [i["id"] for i in self.dq.list_items()]
        self.assertEqual(ids, [b["id"], a["id"]])
        self.dq.mark_showing(b["id"], held_until=9999999999)
        self.assertFalse(self.dq.move_item(b["id"], 1))
        self.assertFalse(self.dq.move_item(a["id"], -1))  # cannot swap with showing

    def test_remove_deletes_files(self):
        a = self.dq.append_item(job_id="j1", title="A", hold_sec=0, frame=self.frame)
        preview = Path(a["preview_path"])
        frame = Path(a["frame_path"])
        removed = self.dq.remove_item(a["id"])
        self.assertIsNotNone(removed)
        self.assertEqual(self.dq.list_items(), [])
        self.assertFalse(preview.is_file())
        self.assertFalse(frame.is_file())

    def test_hold_clamp_and_mark_showing(self):
        self.assertEqual(self.dq.clamp_hold_sec(-5), 0)
        self.assertEqual(self.dq.clamp_hold_sec(999999), self.dq.MAX_HOLD_SEC)
        a = self.dq.append_item(job_id="j1", title="A", hold_sec=60, frame=self.frame)
        marked = self.dq.mark_showing(a["id"], held_until=12345.0)
        self.assertEqual(marked["status"], self.dq.STATUS_SHOWING)
        self.assertEqual(marked["held_until"], 12345.0)
        head = self.dq.head_item()
        self.assertEqual(head["status"], self.dq.STATUS_SHOWING)
        self.dq.finish_head(a["id"])
        self.assertEqual(self.dq.list_items(), [])

    def test_has_job(self):
        self.dq.append_item(job_id="abc", title="A", hold_sec=0, frame=self.frame)
        self.assertTrue(self.dq.has_job("abc"))
        self.assertFalse(self.dq.has_job("nope"))


class HoldSecStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        db = Path(self._tmpdir.name) / "cloud.db"
        os.environ["FENNSILL_CLOUD_DB"] = str(db)
        cloud_dir = ROOT / "cloud"
        sys.path.insert(0, str(cloud_dir))
        import importlib

        import store

        importlib.reload(store)
        self.store = store
        store.init_db()

    def tearDown(self):
        self._tmpdir.cleanup()
        os.environ.pop("FENNSILL_CLOUD_DB", None)

    def test_enqueue_and_claim_hold_sec(self):
        a = self.store.signup("hold@example.com", "password1")
        user = self.store.user_from_session(a["token"])
        uid = int(user["id"])
        self.store.link_device(uid, "FSA1B2C3D4E5F6")
        key = self.store.issue_device_token(uid, "FSA1B2C3D4E5F6")
        auth = self.store.auth_device_token(key)
        self.store.heartbeat(auth)
        job = self.store.enqueue_job(
            user_id=uid,
            device_id="FSA1B2C3D4E5F6",
            html="<html><body>hi</body></html>",
            title="Hold me",
            hold_sec=300,
        )
        self.assertEqual(job["hold_sec"], 300)
        claimed = self.store.claim_next_job(auth)
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["hold_sec"], 300)
        self.assertEqual(claimed["job_id"], job["job_id"])
        info = self.store.get_job_for_user(uid, job["job_id"])
        self.assertEqual(info["hold_sec"], 300)
        self.assertEqual(info["status"], "claimed")


if __name__ == "__main__":
    unittest.main()
