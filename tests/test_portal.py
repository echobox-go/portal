from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
REPO = HERE.parent

from app import main  # noqa: E402

TOKEN = "s3cret-proxy-token"


@pytest.fixture
def client(tmp_path, monkeypatch):
    profiles = tmp_path / "users"
    shutil.copytree(HERE / "fixtures" / "users", profiles)
    monkeypatch.setenv("EBOX_PROFILES_DIR", str(profiles))
    monkeypatch.setenv("EBOX_PROXY_TOKEN", TOKEN)
    monkeypatch.setenv("EBOX_ADMINS", "niklas")
    monkeypatch.delenv("EBOX_DEV_USER", raising=False)
    c = TestClient(main.app)
    c.profiles = profiles
    return c


def as_(user):
    return {"Remote-User": user, "X-Ebox-Proxy-Token": TOKEN}


def test_health(client):
    assert client.get("/healthz").json() == {"ok": True}


def test_remote_user_ignored_without_proxy_token(client):
    r = client.get("/api/me", headers={"Remote-User": "niklas"})
    assert r.status_code == 401
    r = client.get("/api/me", headers={"Remote-User": "niklas", "X-Ebox-Proxy-Token": "wrong"})
    assert r.status_code == 401


def test_me_and_email_style_user(client):
    assert client.get("/api/me", headers=as_("niklas")).json() == {"user": "niklas", "admin": True}
    assert client.get("/api/me", headers=as_("Emil@example.org")).json()["user"] == "emil"


def test_unconfigured_portal_refuses(client, monkeypatch):
    monkeypatch.delenv("EBOX_PROXY_TOKEN")
    assert client.get("/api/me", headers={"Remote-User": "niklas"}).status_code == 503


def test_users_cannot_edit_each_other(client):
    assert client.get("/api/profiles/niklas", headers=as_("emil")).status_code == 403
    assert client.get("/api/profiles/emil", headers=as_("emil")).json()["keymap"] == "dvorak"
    assert client.get("/api/profiles/emil", headers=as_("niklas")).status_code == 200  # admin


def test_put_validates(client):
    good = {"user": "emil", "base": "arch", "desktop": "hyprland", "keymap": "dvorak"}
    assert client.put("/api/profiles/emil", json=good, headers=as_("emil")).status_code == 200
    saved = yaml.safe_load((client.profiles / "emil" / "profile.yaml").read_text())
    assert saved["desktop"] == "hyprland"
    bad = {**good, "base": "debian"}
    r = client.put("/api/profiles/emil", json=bad, headers=as_("emil"))
    assert r.status_code == 422 and "base" in r.json()["detail"]
    mismatch = {**good, "user": "niklas"}
    assert client.put("/api/profiles/emil", json=mismatch, headers=as_("emil")).status_code == 422


def test_path_traversal_rejected(client):
    assert client.get("/api/profiles/..%2F..%2Fetc", headers=as_("niklas")).status_code in (403, 404)


def test_form_roundtrip(client):
    page = client.get("/", headers=as_("emil"))
    assert page.status_code == 200 and "echobox<span>-go</span>" in page.text
    r = client.post("/profile", headers=as_("emil"), follow_redirects=False,
                    data={"base": "arch", "cpu_level": "generic", "desktop": "gnome",
                          "keymap": "dvorak", "packages": "firefox, vim\ngit"})
    assert r.status_code == 303 and r.headers["location"] == "/?saved=1"
    saved = yaml.safe_load((client.profiles / "emil" / "profile.yaml").read_text())
    assert saved["packages"] == ["firefox", "vim", "git"]
    assert saved["sync"]["home_paths"] == ["Documents", ".ssh"]  # untouched fields kept


def test_agent_endpoints_not_implemented(client):
    assert client.post("/api/agent/enrol").status_code == 501


def test_brand_assets(client):
    assert client.get("/favicon.svg").headers["content-type"].startswith("image/svg+xml")


def test_error_message_is_escaped(client):
    r = client.get("/?error=%3Cscript%3Ealert(1)%3C/script%3E", headers=as_("emil"))
    assert "<script>alert(1)" not in r.text and "&lt;script&gt;" in r.text


def test_schema_copy_matches_builder():
    """schema/ is a copy of the builder repo's schema; keep them identical."""
    builder = REPO.parent / "builder" / "profiles" / "schema" / "profile.schema.json"
    if not builder.is_file():
        pytest.skip("builder repo not checked out next to portal")
    assert (REPO / "schema" / "profile.schema.json").read_bytes() == builder.read_bytes()
