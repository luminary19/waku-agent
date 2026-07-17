"""DETERMINISTIC EVAL — the dashboard rotates idle chat threads.

Live bug: a tester returned days later and their fresh 'what's up' landed in a
week-old 32-message thread. New rule: if the current session's newest message
is older than WAKU_SESSION_IDLE_MINUTES, the next chat starts a new thread
(old one stays in History)."""

from __future__ import annotations

from evals.helpers import ScriptedClient, make_waku
from waku.ops.dashboard import _maybe_rotate_session


def _seed(app, session_id, age_minutes):
    app.conn.execute(
        "INSERT INTO chat_log (role, content, session_id, created_at) "
        "VALUES ('user', 'old message', ?, datetime('now', ?))",
        (session_id, f"-{age_minutes} minutes"),
    )
    app.conn.commit()


def test_idle_session_rotates(tmp_path, monkeypatch):
    monkeypatch.setenv("WAKU_SESSION_IDLE_MINUTES", "60")
    app = make_waku(tmp_path / "home", client=ScriptedClient([]))
    before = app.session.session_id
    _seed(app, before, age_minutes=120)          # 2h idle > 60m threshold
    _maybe_rotate_session(app)
    assert app.session.session_id != before
    assert app.session.session_id.startswith("dashboard-")
    assert app.session.history == []             # fresh working memory too


def test_active_session_stays(tmp_path, monkeypatch):
    monkeypatch.setenv("WAKU_SESSION_IDLE_MINUTES", "60")
    app = make_waku(tmp_path / "home", client=ScriptedClient([]))
    before = app.session.session_id
    _seed(app, before, age_minutes=5)            # active conversation
    _maybe_rotate_session(app)
    assert app.session.session_id == before


def test_empty_session_stays(tmp_path, monkeypatch):
    monkeypatch.setenv("WAKU_SESSION_IDLE_MINUTES", "60")
    app = make_waku(tmp_path / "home", client=ScriptedClient([]))
    before = app.session.session_id
    _maybe_rotate_session(app)                   # no messages at all -> no-op
    assert app.session.session_id == before


def test_rotation_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("WAKU_SESSION_IDLE_MINUTES", "0")
    app = make_waku(tmp_path / "home", client=ScriptedClient([]))
    before = app.session.session_id
    _seed(app, before, age_minutes=10000)
    _maybe_rotate_session(app)
    assert app.session.session_id == before
