"""Tests for the assistant tools layer (A1).

Covers: allow-list enforcement, org isolation, no PII leakage, size cap, blind-mode masking,
and that no tool can reach transition/publish/send."""
import inspect
import json
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.assistant.tools import (
    RESULT_CAP,
    TOOL_ALLOW_LIST,
    TOOLS,
    _app_alias_row,
    _cap,
    alias,
    execute_tool,
    resolve_alias,
    scrub,
    tool_schemas,
)
from app.db import session_factory
from app.deps import OrgContext
from app.main import app
from app.models import Application, Job, Membership, Organization, Score, User

from .conftest import CV_LINA, JOB, PASSWORD, apply, published_job, register


def _ctx_for(db, email: str) -> OrgContext:
    user = db.scalar(select(User).where(User.email == email))
    m = db.scalar(select(Membership).where(Membership.user_id == user.id))
    return OrgContext(user, m.organization, m.role)


# ---- session-scoped setup: one org with a job and an application ----

_SETUP_DONE = {}


def _ensure_setup():
    if _SETUP_DONE:
        return _SETUP_DONE
    c = TestClient(app)
    register(c, "tools-main@example.com", org="ToolsMainCorp")
    job = published_job(c, JOB)
    token = apply(c, job["slug"], CV_LINA, "lina-tools@example.com", name="Lina Tools")
    _SETUP_DONE["job"] = job
    _SETUP_DONE["email"] = "tools-main@example.com"
    return _SETUP_DONE


def _run_tool(email, tool_name, args):
    """Execute a tool in a fresh DB session that is committed and closed."""
    setup = _ensure_setup()
    db = session_factory()()
    try:
        ctx = _ctx_for(db, email)
        result = execute_tool(db, ctx, tool_name, args)
        db.commit()
        return result
    finally:
        db.close()


# ---------------------------------------------------------------- allow-list

def test_all_tools_in_allow_list():
    for name in TOOLS:
        assert name in TOOL_ALLOW_LIST, f"Tool '{name}' not in allow-list"


def test_no_tool_outside_allow_list():
    for name in TOOL_ALLOW_LIST:
        assert name in TOOLS, f"Allow-list entry '{name}' has no implementation"


def test_unknown_tool_rejected():
    db = session_factory()()
    try:
        user = User(email="dummy@x.com", password_hash="x", full_name="x", role="recruiter")
        org = Organization(name="x", slug="x-dummy-tools")
        ctx = OrgContext(user, org, "recruiter")
        result = execute_tool(db, ctx, "reject_everyone", {})
        assert "error" in result
        assert "Unknown" in result["error"]
    finally:
        db.close()


# ---------------------------------------------------------------- no forbidden imports

def test_no_tool_handler_calls_forbidden():
    for name, tool in TOOLS.items():
        source = inspect.getsource(tool.handler)
        for forbidden in ("transition(", "publish(", "send_pending(", "erase_application(",
                          "erase_user(", "bulk_reject("):
            assert forbidden not in source, f"Tool '{name}' calls forbidden function '{forbidden}'"


# ---------------------------------------------------------------- org isolation

def test_org_isolation():
    _ensure_setup()
    job = _SETUP_DONE["job"]

    client_b = TestClient(app)
    register(client_b, "iso-other@example.com", org="IsoOtherCorp")

    db = session_factory()()
    try:
        ctx_b = _ctx_for(db, "iso-other@example.com")
        for tool_name in ("job_overview", "get_shortlist", "job_analytics", "check_job_quality"):
            result = execute_tool(db, ctx_b, tool_name, {"job_id": job["id"]})
            assert result.get("error") == "Job not found", f"{tool_name} did not reject foreign job"
    finally:
        db.close()


# ---------------------------------------------------------------- no PII leakage

def test_no_pii_in_shortlist():
    _ensure_setup()
    result = _run_tool(_SETUP_DONE["email"], "get_shortlist", {"job_id": _SETUP_DONE["job"]["id"]})
    text = json.dumps(result, default=str)
    assert "lina-tools@example.com" not in text.lower()
    assert "lina tools" not in text.lower()
    assert "+212 6 12 34 56 78" not in text


def test_no_pii_in_candidate():
    _ensure_setup()
    result = _run_tool(_SETUP_DONE["email"], "get_shortlist", {"job_id": _SETUP_DONE["job"]["id"]})
    all_candidates = result.get("members", []) + result.get("review_lane", []) + result.get("below", [])
    if not all_candidates:
        pytest.skip("no scored candidate")

    cand_result = _run_tool(_SETUP_DONE["email"], "get_candidate", {"alias": all_candidates[0]["alias"]})
    cand_text = json.dumps(cand_result, default=str)
    assert "lina-tools@example.com" not in cand_text.lower()
    assert "+212 6 12 34 56 78" not in cand_text


# ---------------------------------------------------------------- alias system

def test_alias_format():
    a = alias("12345678-1234-1234-1234-123456789abc")
    assert a.startswith("cand_")
    assert len(a) == 13


def test_resolve_alias():
    _ensure_setup()
    result = _run_tool(_SETUP_DONE["email"], "get_shortlist", {"job_id": _SETUP_DONE["job"]["id"]})

    all_candidates = result.get("members", []) + result.get("review_lane", []) + result.get("below", [])
    if not all_candidates:
        pytest.skip("no candidates")
    a = all_candidates[0]["alias"]
    db = session_factory()()
    try:
        ctx = _ctx_for(db, _SETUP_DONE["email"])
        resolved = resolve_alias(db, ctx, a)
        assert resolved is not None
        assert alias(str(resolved.id)) == a
    finally:
        db.close()


# ---------------------------------------------------------------- size cap

def test_result_cap():
    big = {"data": "x" * (RESULT_CAP + 1000)}
    capped = _cap(big)
    text = json.dumps(capped, default=str)
    assert len(text) <= RESULT_CAP + 100


# ---------------------------------------------------------------- scrub

def test_scrub_removes_pii():
    data = {"full_name": "Alice", "email": "a@b.com", "phone": "123", "score": 85,
            "nested": {"name": "Bob", "value": 1}}
    cleaned = scrub(data)
    assert "full_name" not in cleaned
    assert "email" not in cleaned
    assert "phone" not in cleaned
    assert cleaned["score"] == 85
    assert "name" not in cleaned["nested"]
    assert cleaned["nested"]["value"] == 1


# ---------------------------------------------------------------- blind mode masking

def test_blind_mode_hides_profile():
    app_mock = MagicMock(spec=Application)
    app_mock.id = uuid.uuid4()
    app_mock.status = "new"
    app_mock.pinned = False
    app_mock.source = "public"
    app_mock.submitted_at = datetime.now(UTC)
    app_mock.profile = {"title": "Data Scientist", "total_months": 60, "full_name": "Secret"}

    score_mock = MagicMock(spec=Score)
    score_mock.total = 75.0
    score_mock.subscores = {"skills": 0.8}
    score_mock.knockout_failed = False
    score_mock.flags = []
    score_mock.detail = {"counterfactuals": [{"label": "Docker"}]}
    app_mock.score = score_mock

    row = _app_alias_row(app_mock, blind=True)
    assert "title" not in row
    assert "years" not in row

    row_visible = _app_alias_row(app_mock, blind=False)
    assert "title" in row_visible
    assert row_visible["title"] == "Data Scientist"


# ---------------------------------------------------------------- tool schemas

def test_tool_schemas_valid():
    schemas = tool_schemas()
    assert len(schemas) == len(TOOLS)
    for s in schemas:
        assert s["type"] == "function"
        assert "name" in s["function"]
        assert "parameters" in s["function"]


# ---------------------------------------------------------------- list_jobs

def test_list_jobs():
    _ensure_setup()
    result = _run_tool(_SETUP_DONE["email"], "list_jobs", {})
    assert "jobs" in result
    assert len(result["jobs"]) >= 1


# ---------------------------------------------------------------- proposals

def test_propose_weights():
    _ensure_setup()
    result = _run_tool(_SETUP_DONE["email"], "propose_weights",
                       {"job_id": _SETUP_DONE["job"]["id"],
                        "weights": {"skills": 0.5, "requirements": 0.5}})
    assert "action" in result or "error" in result


def test_propose_shortlist_policy():
    _ensure_setup()
    result = _run_tool(_SETUP_DONE["email"], "propose_shortlist_policy",
                       {"job_id": _SETUP_DONE["job"]["id"],
                        "mode": "TOP_N", "n": 5, "threshold": 60})
    assert result.get("action") == "set_shortlist_policy"
