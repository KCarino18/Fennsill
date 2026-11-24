"""Cloud store + security acceptance tests (temp SQLite)."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPO / "templates"))
sys.path.insert(0, str(REPO / "connector"))
sys.path.insert(0, str(REPO / "connector" / "runtime"))

import store  # noqa: E402
from security_artifact import (  # noqa: E402
    SecurityError,
    body_has_wifi_keys,
    validate_artifact_args,
    validate_chart_args,
)


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


class CloudStoreTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        store.DB_PATH = Path(self._td.name) / "test.db"
        store.init_db()

    def tearDown(self):
        self._td.cleanup()

    def test_signup_pending(self):
        out = store.signup("a@example.com", "password1")
        expect(out["subscribed"] is False, out)
        expect(out["status"] == "pending", out)
        expect(out["current_period_end"] is None, out)
        expect(bool(out["token"]), "token")

    def test_signup_conflict_no_extra_month(self):
        store.signup("a@example.com", "password1")
        try:
            store.signup("a@example.com", "password1")
            raise AssertionError("expected conflict")
        except store.StoreError as exc:
            expect(exc.http_status == 409, exc)

    def test_clock_after_heartbeat_and_mcp(self):
        a = store.signup("a@example.com", "password1")
        user = store.user_from_session(a["token"])
        uid = int(user["id"])
        store.link_device(uid, "FSA1B2C3D4E5F6", "desk")
        try:
            store.require_mcp_access(uid)
            raise AssertionError("should need heartbeat")
        except store.StoreError as exc:
            expect(exc.code == "device_not_activated", exc)
        key = store.issue_device_token(uid, "FSA1B2C3D4E5F6")
        auth = store.auth_device_token(key)
        store.heartbeat(auth)
        sub = store.require_mcp_access(uid)
        expect(sub["subscribed"] is True, sub)
        expect(sub["status"] == "active", sub)
        end1 = sub["current_period_end"]
        sub2 = store.require_mcp_access(uid)
        expect(sub2["current_period_end"] == end1, "end must not move")

    def test_push_claim_cross_tenant(self):
        a = store.signup("a@example.com", "password1")
        b = store.signup("b@example.com", "password2")
        ua = store.user_from_session(a["token"])
        ub = store.user_from_session(b["token"])
        store.link_device(int(ua["id"]), "FSA1B2C3D4E5F6")
        store.link_device(int(ub["id"]), "FSB1B2C3D4E5F6")
        ka = store.issue_device_token(int(ua["id"]), "FSA1B2C3D4E5F6")
        kb = store.issue_device_token(int(ub["id"]), "FSB1B2C3D4E5F6")
        store.heartbeat(store.auth_device_token(ka))
        store.heartbeat(store.auth_device_token(kb))
        job = store.enqueue_job(
            user_id=int(ua["id"]),
            device_id="FSA1B2C3D4E5F6",
            html="<html><body>hi</body></html>",
        )
        claimed = store.claim_next_job(store.auth_device_token(ka))
        expect(claimed and claimed["job_id"] == job["job_id"], claimed)
        other = store.claim_next_job(store.auth_device_token(kb))
        expect(other is None, other)
        try:
            store.enqueue_job(
                user_id=int(ub["id"]),
                device_id="FSA1B2C3D4E5F6",
                html="<html><body>x</body></html>",
            )
            raise AssertionError("B must not push to A device")
        except store.StoreError as exc:
            expect(exc.http_status == 403, exc)

    def test_expired_blocks_and_no_second_month(self):
        a = store.signup("a@example.com", "password1")
        user = store.user_from_session(a["token"])
        uid = int(user["id"])
        store.link_device(uid, "FSA1B2C3D4E5F6")
        key = store.issue_device_token(uid, "FSA1B2C3D4E5F6")
        store.heartbeat(store.auth_device_token(key))
        store.require_mcp_access(uid)
        past = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        store.set_access_subscription("a@example.com", "active", past)
        try:
            store.require_mcp_access(uid)
            raise AssertionError("expired should block")
        except store.StoreError as exc:
            expect(exc.code == "subscription_inactive", exc)
        try:
            store.begin_access_period(uid)
            raise AssertionError("must not open second free month")
        except store.StoreError as exc:
            expect(exc.code == "subscription_inactive", exc)

    def test_operator_inactive(self):
        a = store.signup("a@example.com", "password1")
        user = store.user_from_session(a["token"])
        uid = int(user["id"])
        store.link_device(uid, "FSA1B2C3D4E5F6")
        key = store.issue_device_token(uid, "FSA1B2C3D4E5F6")
        store.heartbeat(store.auth_device_token(key))
        store.require_mcp_access(uid)
        store.set_access_subscription("a@example.com", "inactive", None)
        try:
            store.require_mcp_access(uid)
            raise AssertionError("inactive should block")
        except store.StoreError as exc:
            expect(exc.code == "subscription_inactive", exc)

    def test_manifest_operator_only_read(self):
        store.publish_update_manifest(
            "stable", "1.0.0", "https://example.com/app.bin", "a" * 64
        )
        m = store.get_update_manifest("stable")
        expect(m and m["version"] == "1.0.0", m)

    def test_wifi_rejected(self):
        expect(body_has_wifi_keys({"ssid": "x"}) is True, "ssid")
        try:
            validate_artifact_args(
                device_id="FSA1B2C3D4E5F6",
                html='<html><img src="https://evil"></html>',
            )
            raise AssertionError("external url")
        except SecurityError:
            pass

    def test_bad_device_id(self):
        a = store.signup("a@example.com", "password1")
        user = store.user_from_session(a["token"])
        try:
            store.link_device(int(user["id"]), "BAD")
            raise AssertionError("bad id")
        except store.StoreError as exc:
            expect(exc.http_status == 400, exc)

    def test_complete_cross_device(self):
        a = store.signup("a@example.com", "password1")
        b = store.signup("b@example.com", "password2")
        ua = store.user_from_session(a["token"])
        ub = store.user_from_session(b["token"])
        store.link_device(int(ua["id"]), "FSA1B2C3D4E5F6")
        store.link_device(int(ub["id"]), "FSB1B2C3D4E5F6")
        ka = store.issue_device_token(int(ua["id"]), "FSA1B2C3D4E5F6")
        kb = store.issue_device_token(int(ub["id"]), "FSB1B2C3D4E5F6")
        store.heartbeat(store.auth_device_token(ka))
        store.heartbeat(store.auth_device_token(kb))
        job = store.enqueue_job(
            user_id=int(ua["id"]),
            device_id="FSA1B2C3D4E5F6",
            html="<html><body>hi</body></html>",
        )
        store.claim_next_job(store.auth_device_token(ka))
        try:
            store.complete_job(store.auth_device_token(kb), job["job_id"], ok=True)
            raise AssertionError("B must not complete A job")
        except store.StoreError as exc:
            expect(exc.http_status == 403, exc)


class ToolRegistrationTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        store.DB_PATH = Path(self._td.name) / "test.db"
        store.init_db()

    def tearDown(self):
        self._td.cleanup()

    def test_no_set_wifi_tool(self):
        import main as cloud_main

        names = {t.name for t in cloud_main.server._tool_manager.list_tools()}
        expect("list_panels" in names, names)
        expect("push_chart" in names, names)
        expect("push_artifact" in names, names)
        expect("get_push_status" in names, names)
        expect("set_wifi" not in names, names)

    def test_cloud_instructions_prefer_push_chart(self):
        import main as cloud_main

        text = cloud_main.server.instructions or ""
        expect("push_chart" in text, text)
        expect("delivered" in text, text)

    def test_dns_rebinding_enabled(self):
        import main as cloud_main

        settings = cloud_main._transport_security()
        expect(settings.enable_dns_rebinding_protection is True, settings)
        expect("mcp.fennsill.com" in settings.allowed_hosts, settings.allowed_hosts)

    def test_chart_args_and_enqueue(self):
        a = store.signup("chart@example.com", "password1")
        user = store.user_from_session(a["token"])
        uid = int(user["id"])
        store.link_device(uid, "FSA1B2C3D4E5F6")
        key = store.issue_device_token(uid, "FSA1B2C3D4E5F6")
        store.heartbeat(store.auth_device_token(key))
        clean = validate_chart_args(
            device_id="FSA1B2C3D4E5F6",
            title="Demo",
            labels=["A", "B"],
            values=[1, 2],
            require_device_id=True,
        )
        from chart_page import render_chart_html

        html = render_chart_html(
            title=clean["title"],
            labels=clean["labels"],
            values=clean["values"],
            chart_type="bar",
        )
        job = store.enqueue_job(
            user_id=uid,
            device_id=clean["device_id"],
            html=html,
            title=clean["title"],
        )
        expect(bool(job.get("job_id")), job)
        try:
            validate_chart_args(
                device_id="BAD",
                title="x",
                labels=["A"],
                values=[1],
                require_device_id=True,
            )
            raise AssertionError("bad device id")
        except SecurityError as exc:
            expect("list_panels" in str(exc).lower() or "fs" in str(exc).lower(), exc)


if __name__ == "__main__":
    unittest.main()

