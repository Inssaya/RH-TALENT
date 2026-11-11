"""Shortlist computation. The size N and the threshold T always come from the job's policy:
there is no constant shortlist size anywhere in the business code."""
from dataclasses import dataclass

TIE_TOLERANCE = 1.0  # points on 100: the reproducibility tolerance of the score


@dataclass
class Policy:
    mode: str = "TOP_N"  # TOP_N | THRESHOLD | TOP_N_FLOOR
    n: int = 10
    threshold: float = 65.0
    cap: int | None = None


def compute_shortlist(rows: list[dict], policy: Policy) -> dict:
    """rows: {id, total, skills, requirements, knockout_failed, provisional, quality, pinned, status}.

    Returns members (ordered), below, review_lane, excluded, cutoff_score and human-readable notes."""
    notes: list[dict] = []
    review = [r for r in rows if r["quality"] < 0.6 and not r["knockout_failed"]]
    provisional = [r for r in rows if r["provisional"] and r not in review]
    excluded = [r for r in rows if r["knockout_failed"]]
    skip = {r["id"] for r in review + provisional + excluded}
    eligible = sorted((r for r in rows if r["id"] not in skip),
                      key=lambda r: (-r["total"], -r["skills"], -r["requirements"], str(r["id"])))
    if provisional:
        notes.append({"code": "provisional_excluded", "count": len(provisional)})

    if policy.mode == "THRESHOLD":
        members = [r for r in eligible if r["total"] >= policy.threshold]
        if policy.cap and len(members) > policy.cap:
            members = _with_ties(members, policy.cap, notes)
    elif policy.mode == "TOP_N_FLOOR":
        qualified = [r for r in eligible if r["total"] >= policy.threshold]
        members = _with_ties(qualified, policy.n, notes)
        if len(qualified) < policy.n:
            notes.append({"code": "fewer_qualified", "qualified": len(qualified), "requested": policy.n})
    else:
        members = _with_ties(eligible, policy.n, notes)
        if len(eligible) < policy.n:
            notes.append({"code": "fewer_eligible", "eligible": len(eligible), "requested": policy.n})

    ids = {r["id"] for r in members}
    below = [r for r in eligible if r["id"] not in ids]
    if not members and policy.mode != "TOP_N" and below:
        best = below[:3]
        suggestion = int(best[min(len(best), 3) - 1]["total"])
        would = sum(1 for r in below if r["total"] >= suggestion)
        notes.append({"code": "empty_shortlist", "suggested_threshold": suggestion, "would_include": would,
                      "best_below": [r["id"] for r in best]})
    # candidates already advanced by a human stay visible even when they leave the top
    pinned_out = [r["id"] for r in below
                  if r["pinned"] or r["status"] in ("to_contact", "interview", "offer", "hired")]
    return {
        "members": [r["id"] for r in members], "below": [r["id"] for r in below],
        "review_lane": [r["id"] for r in review], "provisional": [r["id"] for r in provisional],
        "excluded": [r["id"] for r in excluded], "pinned_outside": pinned_out,
        "cutoff_score": members[-1]["total"] if members else None, "notes": notes,
    }


def _with_ties(ordered: list[dict], n: int, notes: list[dict]) -> list[dict]:
    """Take the n best; candidates tied with the last one (within the tolerance) are all included."""
    if len(ordered) <= n:
        return list(ordered)
    cut = ordered[n - 1]["total"]
    members = list(ordered[:n])
    extra = [r for r in ordered[n:] if cut - r["total"] < TIE_TOLERANCE]
    if extra:
        notes.append({"code": "ties_included", "n": n, "extra": len(extra)})
    return members + extra


def diff(prev_members: list[str], new_members: list[str]) -> dict:
    p, n = set(prev_members), set(new_members)
    return {"entered": [i for i in new_members if i not in p], "left": [i for i in prev_members if i not in n]}
