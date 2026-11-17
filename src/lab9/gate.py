"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    rows, base_rows = pr.get("rows") or [], base.get("rows") or []
    man, base_man = pr.get("manifest") or {}, base.get("manifest") or {}

    # 1. Metric values must be real numbers: NaN/inf compare False against every threshold.
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v} (NaN/inf slips past every threshold)")

    # 2. Graders must have run on every row. A crashed grader is not a pass.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s) in the report")
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    for m in graded:
        holes = [f"{r.get('item_id')}@{r.get('seed')}" for r in rows if r.get(m) is None]
        if holes:
            problems.append(f"{len(holes)} row(s) have no value for graded metric {m} (first: {holes[0]})")
        odd = [r.get(m) for r in rows if r.get(m) is not None and not isinstance(r.get(m), bool)]
        if odd:
            problems.append(f"metric {m} has non-boolean row values (e.g. {odd[0]!r})")

    # 3. Coverage: exactly one row per (item, seed), the same grid as the baseline's.
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dupes = len(keys) - len(set(keys))
    if dupes:
        problems.append(f"{dupes} duplicated (item, seed) row(s): a copied passing row can replace a failing one")
    want = (man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        problems.append(f"{len(rows)} rows but manifest says {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want}")
    for f in ("items", "seeds"):
        if f in base_man and man.get(f) != base_man.get(f):
            problems.append(f"manifest {f} {man.get(f)!r} differs from the baseline's {base_man.get(f)!r}")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if base_rows and set(keys) != base_keys:
        miss, extra = len(base_keys - set(keys)), len(set(keys) - base_keys)
        problems.append(f"(item, seed) set differs from the baseline: {miss} missing, {extra} extra (dropped or cherry-picked)")

    # 4. Slice tags come from the label; an item may not change slice between baseline and PR.
    def tags(rs: list[dict]) -> dict[str, set[tuple[str, ...]]]:
        out: dict[str, set[tuple[str, ...]]] = {}
        for r in rs:
            out.setdefault(r.get("item_id"), set()).add(tuple(sorted(r.get("slices") or [])))
        return out
    pt, bt = tags(rows), tags(base_rows)
    moved = sorted(i for i in pt if i in bt and pt[i] != bt[i])
    if moved:
        problems.append(f"slice tags changed for {len(moved)} item(s) (first: {moved[0]}): relabelling hides a slice regression")
    split = sorted(i for i, t in pt.items() if len(t) > 1)
    if split:
        problems.append(f"item {split[0]} carries different slice tags on different seeds")

    # 5. Reported metrics must be what the rows say (a hand-edited number is not a measurement).
    problems += _recompute_mismatch(pr, spec)

    # 6. Ratchet: on the same eval-set version, thresholds may only get stricter.
    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += _ratchet(base_spec, spec)
    return problems


def _recompute_mismatch(pr: dict, spec: dict) -> list[str]:
    from lab9.eval import aggregate

    rows = pr.get("rows") or []
    if not rows:
        return ["report has no rows"]
    ids = [m["id"] for m in spec.get("metrics", []) if all(m["id"] in r for r in rows)]
    has_cost = all("cost" in r for r in rows)
    try:
        again = aggregate([r if has_cost else {**r, "cost": 0.0} for r in rows], ids,
                          k_values=spec.get("pass_k", []))
    except (TypeError, ValueError, KeyError) as e:
        return [f"metrics cannot be recomputed from rows ({type(e).__name__}: {e})"]
    out = []
    for k, v in (pr.get("metrics") or {}).items():
        if k not in again or (k == "cost_per_success" and not has_cost):
            continue
        w = again[k]
        if isinstance(v, (int, float)) and isinstance(w, (int, float)):
            if math.isfinite(v) and abs(v - w) > 1e-6:
                out.append(f"metric {k} reported {v} but the rows give {w}")
        elif v != w and not (isinstance(v, float) and not math.isfinite(v)):
            out.append(f"metric {k} reported {v!r} but the rows give {w!r}")
    return out


def _looser(old: dict, new: dict) -> list[str]:
    """What got laxer from old to new threshold set (+ blocking / no_significant_drop flags)."""
    out = []
    ot, nt = old.get("threshold", old), new.get("threshold", new)
    for k in ("min", "max", "max_increase"):
        if k in ot:
            if k not in nt:
                out.append(f"{k} removed")
            elif (k == "min" and nt[k] < ot[k]) or (k != "min" and nt[k] > ot[k]):
                out.append(f"{k} {ot[k]} -> {nt[k]}")
    if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
        out.append("no_significant_drop dropped")
    if old.get("blocking") and not new.get("blocking"):
        out.append("no longer blocking")
    return out


def _ratchet(base_spec: dict, spec: dict) -> list[str]:
    problems = []
    new_m = {m["id"]: m for m in spec.get("metrics", [])}
    for m in base_spec.get("metrics", []):
        if m["id"] not in new_m:
            problems.append(f"ratchet: metric {m['id']} removed from the spec")
        else:
            problems += [f"ratchet: metric {m['id']} {w}" for w in _looser(m, new_m[m["id"]])]
    new_s = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        key = (s["name"], s["metric"])
        if key not in new_s:
            problems.append(f"ratchet: slice {s['name']}/{s['metric']} removed from the spec")
        else:
            problems += [f"ratchet: slice {s['name']}/{s['metric']} {w}" for w in _looser(s, new_s[key])]
    for f in ("seeds", "eval_set", "labels", "bootstrap"):
        if f in base_spec and spec.get(f) != base_spec.get(f):
            problems.append(f"ratchet: spec {f} changed on the same eval-set version")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            # A slice that vanished from the PR (items relabelled out of it) cannot be judged: block.
            verdict, note = "missing", "no PR rows carry this slice"
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in s and val < s["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if s.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
