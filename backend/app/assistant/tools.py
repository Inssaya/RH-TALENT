"""Recruiter assistant tool registry.

Each tool is a read-only or proposal function that runs as the caller (OrgContext).
Results use aliases instead of personal data and are capped at 6000 characters.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..ai import jobs_ai
from ..ai.scoring import DEFAULT_WEIGHTS, validate_weights
from ..deps import OrgContext
from ..models import Application, ApplicationEvent, Job, Score, ShortlistSnapshot
from ..services import current_version, job_counts, shortlist_rows

RESULT_CAP = 6000

TOOL_ALLOW_LIST = frozenset([
    "list_jobs", "job_overview", "get_shortlist", "get_candidate",
    "compare_candidates", "job_analytics", "check_job_quality", "suggest_talents",
    "propose_job_draft", "propose_shortlist_policy", "propose_weights",
])

_FORBIDDEN_IMPORTS = {"transition", "publish", "send", "erase", "delete", "bulk_reject"}


@dataclass
class Tool:
    name: str
    kind: Literal["read", "proposal"]
    description: str
    parameters: dict
    handler: Callable[..., dict]


TOOLS: dict[str, Tool] = {}


def _register(name: str, kind: Literal["read", "proposal"], description: str, parameters: dict):
    def decorator(fn: Callable) -> Callable:
        TOOLS[name] = Tool(name=name, kind=kind, description=description, parameters=parameters, handler=fn)
        return fn
    return decorator


# ---------------------------------------------------------------- aliases

def alias(app_id: str) -> str:
    return f"cand_{app_id.replace('-', '')[:8]}"


def resolve_alias(db: Session, ctx: OrgContext, alias_str: str) -> Application | None:
    prefix = alias_str.replace("cand_", "") if alias_str.startswith("cand_") else alias_str
    for app in db.scalars(select(Application).join(Job).where(Job.organization_id == ctx.org.id)):
        if app.id.hex[:8] == prefix:
            return app
    return None


# ---------------------------------------------------------------- PII scrubbing

_PII_KEYS = {"full_name", "name", "email", "phone", "e-mail"}


def scrub(data: dict, blind: bool = False) -> dict:
    out = {}
    for k, v in data.items():
        if k in _PII_KEYS:
            continue
        if isinstance(v, dict):
            out[k] = scrub(v, blind)
        elif isinstance(v, list):
            out[k] = [scrub(i, blind) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


def _cap(result: dict) -> dict:
    text = json.dumps(result, default=str)
    if len(text) <= RESULT_CAP:
        return result
    result["_truncated"] = True
    trimmed = json.dumps(result, default=str)
    if len(trimmed) <= RESULT_CAP:
        return result
    return {"_truncated": True, "error": "Result too large"}


# ---------------------------------------------------------------- helpers

def _get_job(db: Session, ctx: OrgContext, job_id: str) -> Job:
    import uuid
    try:
        uid = uuid.UUID(job_id)
    except ValueError:
        return None
    job = db.get(Job, uid)
    if not job or job.organization_id != ctx.org.id:
        return None
    return job


def _app_alias_row(app: Application, blind: bool) -> dict:
    s = app.score
    row = {
        "alias": alias(str(app.id)),
        "status": app.status,
        "score": s.total if s else None,
        "subscores": s.subscores if s else None,
        "knockout_failed": s.knockout_failed if s else False,
        "flags": s.flags if s else [],
        "pinned": app.pinned,
        "source": app.source,
        "submitted_at": app.submitted_at.isoformat(),
    }
    if not blind or app.status not in ("new", "shortlisted", "rejected"):
        row["title"] = app.profile.get("title", "")
        row["years"] = round((app.profile.get("total_months") or 0) / 12, 1)
    if s and s.detail:
        top_missing = [c["label"] for c in (s.detail.get("counterfactuals") or [])[:2]]
        if top_missing:
            row["top_missing"] = top_missing
    return row


# ---------------------------------------------------------------- tool implementations

@_register("list_jobs", "read", "List all jobs in the organization", {
    "type": "object", "properties": {}, "required": []})
def _list_jobs(db: Session, ctx: OrgContext) -> dict:
    jobs = db.scalars(select(Job).where(Job.organization_id == ctx.org.id).order_by(Job.created_at.desc())).all()
    counts = job_counts(db, [j.id for j in jobs])
    return {"jobs": [{"id": str(j.id), "title": j.title, "status": j.status, "city": j.city,
                       "applications": counts.get(j.id, 0)} for j in jobs]}


@_register("job_overview", "read", "Get overview of a job: status, counts, policy, quality warnings", {
    "type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]})
def _job_overview(db: Session, ctx: OrgContext, job_id: str) -> dict:
    job = _get_job(db, ctx, job_id)
    if not job:
        return {"error": "Job not found"}
    v = current_version(db, job)
    count = job_counts(db, [job.id]).get(job.id, 0)
    out = {"id": str(job.id), "title": job.title, "status": job.status, "city": job.city,
           "country": job.country, "remote": job.remote, "contract_type": job.contract_type,
           "applications": count, "version": job.current_version, "blind_mode": job.blind_mode,
           "policy": {"mode": job.sl_mode, "n": job.sl_n, "threshold": job.sl_threshold, "cap": job.sl_cap},
           "weights": job.weights or DEFAULT_WEIGHTS}
    if v:
        out["quality"] = jobs_ai.quality_report(v.draft)
    return out


@_register("get_shortlist", "read", "Get the shortlist for a job with aliases", {
    "type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]})
def _get_shortlist(db: Session, ctx: OrgContext, job_id: str) -> dict:
    job = _get_job(db, ctx, job_id)
    if not job:
        return {"error": "Job not found"}
    from ..services import refresh_shortlist
    snap = refresh_shortlist(db, job, reason="assistant")
    apps = db.scalars(select(Application).where(Application.job_id == job.id)).all()
    app_map = {str(a.id): a for a in apps}
    blind = job.blind_mode

    def lane(ids):
        return [_app_alias_row(app_map[i], blind) for i in ids if i in app_map]

    members = lane(snap.members if snap else [])
    member_ids = {r["alias"] for r in members}
    review = lane(snap.review_lane if snap else [])
    review_ids = {r["alias"] for r in review}
    all_rows = {alias(str(a.id)): _app_alias_row(a, blind) for a in apps}
    below = [r for a_alias, r in all_rows.items()
             if a_alias not in member_ids and a_alias not in review_ids
             and r["status"] not in ("rejected", "withdrawn") and not r["knockout_failed"]
             and r.get("score") is not None]
    below.sort(key=lambda r: -(r["score"] or -1))
    return {"members": members, "review_lane": review, "below": below[:20],
            "cutoff_score": snap.cutoff_score if snap else None,
            "total_applications": len(apps)}


@_register("get_candidate", "read", "Get details for a candidate by alias", {
    "type": "object", "properties": {"alias": {"type": "string"}}, "required": ["alias"]})
def _get_candidate(db: Session, ctx: OrgContext, alias: str) -> dict:
    app = resolve_alias(db, ctx, alias)
    if not app:
        return {"error": "Candidate not found"}
    blind = app.job.blind_mode
    s = app.score
    out = _app_alias_row(app, blind)
    out["job_id"] = str(app.job_id)
    out["job_title"] = app.job.title
    if s and s.detail:
        detail = scrub(dict(s.detail), blind)
        for key in ("skills", "requirements"):
            if key in detail:
                items = detail[key]
                for item in items:
                    if "evidence" in item and len(item["evidence"]) > 300:
                        item["evidence"] = item["evidence"][:300]
        out["detail"] = detail
    events = db.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id == app.id)
                        .order_by(ApplicationEvent.created_at)).all()
    out["events"] = [{"from": e.from_status, "to": e.to_status, "actor": e.actor_kind,
                      "at": e.created_at.isoformat()} for e in events]
    profile = scrub(dict(app.profile), blind)
    if blind and app.status in ("new", "shortlisted", "rejected"):
        for k in ("full_name", "email", "phone"):
            profile.pop(k, None)
    out["profile"] = profile
    return out


@_register("compare_candidates", "read", "Compare up to 3 candidates by alias", {
    "type": "object", "properties": {"aliases": {"type": "array", "items": {"type": "string"}, "maxItems": 3}},
    "required": ["aliases"]})
def _compare_candidates(db: Session, ctx: OrgContext, aliases: list[str]) -> dict:
    if len(aliases) > 3:
        return {"error": "Maximum 3 candidates"}
    rows = []
    for a in aliases:
        app = resolve_alias(db, ctx, a)
        if not app:
            rows.append({"alias": a, "error": "not found"})
            continue
        blind = app.job.blind_mode
        row = _app_alias_row(app, blind)
        if app.score and app.score.detail:
            detail = scrub(dict(app.score.detail), blind)
            row["skills"] = detail.get("skills", [])
            row["requirements"] = detail.get("requirements", [])
        rows.append(row)
    return {"candidates": rows}


@_register("job_analytics", "read", "Get analytics for a job", {
    "type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]})
def _job_analytics(db: Session, ctx: OrgContext, job_id: str) -> dict:
    from collections import Counter
    job = _get_job(db, ctx, job_id)
    if not job:
        return {"error": "Job not found"}
    apps = db.scalars(select(Application).where(Application.job_id == job.id)).all()
    scores = [a.score for a in apps if a.score]
    hist = [0] * 10
    for s in scores:
        hist[min(9, int(s.total // 10))] += 1
    missing: Counter = Counter()
    for s in scores:
        for r in s.detail.get("skills", []):
            if r["match"] < 1 and r["kind"] == "required":
                missing[r["label"]] += 1
    return {
        "total": len(apps),
        "by_status": dict(Counter(a.status for a in apps)),
        "score_histogram": hist,
        "average_score": round(sum(s.total for s in scores) / len(scores), 1) if scores else None,
        "missing_required_skills": [{"label": k, "count": v} for k, v in missing.most_common(8)],
        "human_review_requests": sum(1 for a in apps if a.human_review_requested),
    }


@_register("check_job_quality", "read", "Check quality of a job post", {
    "type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]})
def _check_job_quality(db: Session, ctx: OrgContext, job_id: str) -> dict:
    job = _get_job(db, ctx, job_id)
    if not job:
        return {"error": "Job not found"}
    v = current_version(db, job)
    if not v:
        return {"error": "No version"}
    return jobs_ai.quality_report(v.draft)


@_register("suggest_talents", "read", "Suggest matching talent pool profiles for a job", {
    "type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]})
def _suggest_talents(db: Session, ctx: OrgContext, job_id: str) -> dict:
    from ..matching import suggest_talents as _suggest
    job = _get_job(db, ctx, job_id)
    if not job:
        return {"error": "Job not found"}
    v = current_version(db, job)
    if not v:
        return {"error": "No version"}
    results = _suggest(db, job, v)
    return {"talents": [scrub(r) for r in results]}


@_register("propose_job_draft", "proposal", "Propose changes to a job draft", {
    "type": "object", "properties": {"job_id": {"type": "string"}, "draft": {"type": "object"}},
    "required": ["job_id", "draft"]})
def _propose_job_draft(db: Session, ctx: OrgContext, job_id: str, draft: dict) -> dict:
    job = _get_job(db, ctx, job_id)
    if not job:
        return {"error": "Job not found"}
    return {"action": "update_job_draft", "params": {"job_id": job_id, "draft": draft},
            "summary": f"Update the draft of '{job.title}'"}


@_register("propose_shortlist_policy", "proposal", "Propose a change to shortlist policy", {
    "type": "object",
    "properties": {
        "job_id": {"type": "string"},
        "mode": {"type": "string", "enum": ["TOP_N", "THRESHOLD", "TOP_N_FLOOR"]},
        "n": {"type": "integer"}, "threshold": {"type": "number"},
    },
    "required": ["job_id", "mode", "n", "threshold"]})
def _propose_shortlist_policy(db: Session, ctx: OrgContext, job_id: str, mode: str, n: int, threshold: float) -> dict:
    job = _get_job(db, ctx, job_id)
    if not job:
        return {"error": "Job not found"}
    return {"action": "set_shortlist_policy", "params": {"job_id": job_id, "mode": mode, "n": n, "threshold": threshold},
            "summary": f"Change shortlist to {mode} (n={n}, threshold={threshold})"}


@_register("propose_weights", "proposal", "Propose new scoring weights", {
    "type": "object",
    "properties": {
        "job_id": {"type": "string"},
        "weights": {"type": "object"},
    },
    "required": ["job_id", "weights"]})
def _propose_weights(db: Session, ctx: OrgContext, job_id: str, weights: dict) -> dict:
    job = _get_job(db, ctx, job_id)
    if not job:
        return {"error": "Job not found"}
    try:
        validated = validate_weights(weights)
    except ValueError as e:
        return {"error": str(e)}
    return {"action": "set_weights", "params": {"job_id": job_id, "weights": validated},
            "summary": f"Change scoring weights for '{job.title}'"}


# ---------------------------------------------------------------- execution

def execute_tool(db: Session, ctx: OrgContext, name: str, arguments: dict) -> dict:
    if name not in TOOLS:
        return {"error": f"Unknown tool: {name}"}
    if name not in TOOL_ALLOW_LIST:
        return {"error": f"Tool not allowed: {name}"}
    tool = TOOLS[name]
    try:
        result = tool.handler(db, ctx, **arguments)
    except Exception as e:
        return {"error": f"Tool error: {str(e)[:200]}"}
    audit.log(db, "assistant.tool", actor=ctx.user, resource=name,
              organization_id=ctx.org.id,
              payload={"tool": name, "args_keys": list(arguments.keys())})
    return _cap(result)


def tool_schemas() -> list[dict]:
    return [{"type": "function", "function": {"name": t.name, "description": t.description,
             "parameters": t.parameters}} for t in TOOLS.values()]
