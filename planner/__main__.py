"""CLI.

  python -m planner solve   [dataset.json] [--engine greedy|ortools|baseline|all] [--time-limit 10] [-o out]
  python -m planner replan  out/plan_greedy.json --event EV3 [--event EV1] [--engine ...] [--stability minimal|full] [--at HH:MM]
  python -m planner explain out/plan_greedy.json R012
  python -m planner compare out/plan_baseline.json out/plan_greedy.json [...]
  python -m planner verify  out/plan_greedy.json [...]
  python -m planner narrate out/plan_ortools.json [--request R033] [--summary] [--diff] [--baseline out/plan_baseline.json] [--dry-run]
  python -m planner chat    out/plan_ortools.json [--ask "почему R033 не у Царькова?"]
  python -m planner risk    out/plan_ortools.json [--engine ortools|greedy] [--time-limit 3] [--eps 0,0.1,0.2,0.3] [--stress-only]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .engines import solve
from .model import Problem, hhmm
from .plan import build_plan, routes_from_plan
from .replan import replan

DEFAULT_DS = "data/synth/dataset.json"


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump(obj: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def print_plan(plan: dict) -> None:
    m = plan["metrics"]
    print(f"\n== {plan['engine']}  plan {plan['plan_id']}  ({plan['solve_time_s']} c)"
          + (f"  перепланирование в {plan['now']}" if plan.get("now") else ""))
    for rt in plan["routes"]:
        tag = f"  [недоступен с {rt['unavailable_from']}]" if rt.get("unavailable_from") else ""
        seq = " → ".join(f"{s['request_id']}{'*' if s['locked'] else ''} {s['start']}" for s in rt["stops"])
        print(f"  {rt['engineer_id']} {rt['name']:<12} {rt['transport']:<6} {rt['shift']}  {rt['total_km']:5.1f} км  "
              f"{len(rt['stops']):2d} з.  {seq}{tag}")
    if plan["unassigned"]:
        print("  Не назначены:")
        for rid in plan["unassigned"]:
            print(f"    {rid}: {plan['assignments'][rid]['text']}")
    print(f"  Итого: инженеров {m['engineers_used']}/{m['engineers_total']}, назначено {m['assigned']}, "
          f"не назначено {m['unassigned']}, пробег {m['total_km']} км, ожидание {m['total_wait_min']} мин")
    if plan.get("diff"):
        d = plan["diff"]
        print(f"  Diff: {d['summary']}")
        for rid, v in d["requests"].items():
            if v["status"] != "unchanged":
                print(f"    {rid}: {v}")


def cmd_solve(a) -> None:
    ds = load(a.dataset)
    if a.travel:
        ds["config"]["travel"]["mode"] = a.travel
    engines = ["baseline", "greedy", "ortools"] if a.engine == "all" else [a.engine]
    for eng in engines:
        p = Problem.from_dataset(ds)
        t0 = time.time()
        routes, unassigned = solve(p, eng, time_limit=a.time_limit)
        plan = build_plan(p, p, routes, unassigned, eng, dataset=a.dataset, solve_time=time.time() - t0)
        dump(plan, Path(a.out) / f"plan_{eng}.json")
        print_plan(plan)


def cmd_replan(a) -> None:
    old = load(a.plan)
    ds = load(old["dataset"])
    evs = {e["id"]: e for e in ds["events"]}
    events = [evs[i] for i in a.event]
    now = hhmm(a.at) if a.at else None
    new = replan(ds, old, events, a.engine or old["engine"], now=now, stability=a.stability,
                 time_limit=a.time_limit, dataset_path=old["dataset"])
    dump(new, Path(a.out) / f"replan_{'_'.join(a.event)}_{new['engine']}.json")
    print_plan(new)


def cmd_explain(a) -> None:
    plan = load(a.plan)
    x = plan["assignments"].get(a.request_id)
    if not x:
        print("нет такой заявки в плане")
        return
    print(x["text"])
    print(json.dumps(x["reason"], ensure_ascii=False, indent=2))


def cmd_narrate(a) -> None:
    from .llm import Narrator
    from .reasoning import bundle_diff, bundle_plan, bundle_request
    plan = load(a.plan)
    ds = load(plan["dataset"])
    p = Problem.from_dataset(ds)
    for ev in plan.get("events", []):
        if ev["type"] == "urgent_request":
            p.requests[ev["request"]["id"]] = p.new_request(dict(ev["request"], priority="urgent"))
    p.rebuild_matrix(ds.get("matrix"))
    baseline = load(a.baseline) if a.baseline else None
    n = Narrator(model=a.model)
    if not a.dry_run:
        print(f"[ЛЛМ: {'доступна, ' + n.model if n.available else 'недоступна — шаблонный текст'}]\n")
    for rid in a.request or []:
        if a.dry_run:
            print(json.dumps(bundle_request(plan, p, rid), ensure_ascii=False, indent=1))
        else:
            print(f"--- {rid}\n{n.explain_request(plan, p, rid)}\n")
    if a.summary:
        print(json.dumps(bundle_plan(plan, p, baseline), ensure_ascii=False, indent=1) if a.dry_run
              else f"--- саммари\n{n.summarize_plan(plan, p, baseline)}\n")
    if a.diff:
        if not plan.get("diff"):
            print("это не перепланирование, diff нет")
        else:
            print(json.dumps(bundle_diff(plan, p), ensure_ascii=False, indent=1) if a.dry_run
                  else f"--- перепланирование\n{n.explain_diff(plan, p)}\n")
    if n.last_error:
        print(f"[ошибка ЛЛМ, показан шаблон: {n.last_error}]")
    if n.last_usage:
        u = n.last_usage
        print(f"[tokens: prompt {getattr(u, 'prompt_tokens', '?')} completion {getattr(u, 'completion_tokens', '?')}]")


def cmd_chat(a) -> None:
    from .llm import Narrator
    plan = load(a.plan)
    p = Problem.from_dataset(load(plan["dataset"]))
    baseline = load(a.baseline) if a.baseline else None
    n = Narrator(model=a.model)
    history: list = []
    questions = [a.ask] if a.ask else None
    while True:
        q = questions.pop(0) if questions else (input("диспетчер> ") if questions is None else None)
        if not q:
            break
        answer, history = n.chat(plan, p, q, history, baseline)
        print(answer, "\n")
        if a.ask:
            break


def cmd_risk(a) -> None:
    from .risk import assess, frontier, recommendation_text
    plan = load(a.plan)
    ds = load(plan["dataset"])
    ds["config"]["travel"]["mode"] = plan.get("travel_mode", "matrix")
    p = Problem.from_dataset(ds)
    routes = {k: [rid for rid in v if rid in p.requests] for k, v in routes_from_plan(plan).items()}
    cfg = ds["config"].get("robustness", {}).get("risk", {})
    t0 = time.time()
    a0 = assess(p, routes, cfg)
    print(f"Текущий план: min tol {a0['min_tol']} мин, без запаса {len(a0['tight_stops'])}: {a0['tight_stops']}; "
          f"стресс-тест ({a0['stress']['runs']} прогонов): ожид. опозданий {a0['stress']['expected_late']}, "
          f"P(хотя бы одно) {a0['stress']['p_any_late']}, переработка {a0['stress']['expected_overtime_min']} мин  "
          f"[{time.time() - t0:.3f} с]")
    top = list(a0["stress"]["late_prob"].items())[:5]
    print("  чаще всего опаздывают:", ", ".join(f"{rid} ({int(pr*100)} %)" for rid, pr in top))
    if a.stress_only:
        return
    eps = [float(x) for x in a.eps.split(",")] if a.eps else None
    t0 = time.time()
    fr = frontier(ds, a.engine, a.time_limit, eps, base_routes=routes)
    total = time.time() - t0
    print(f"\n{'ε':>5} {'инж.':>5} {'назн.':>6} {'км':>7} {'min tol':>8} {'тесных':>7} {'E[опозд]':>9} {'P(any)':>7} {'перераб':>8} {'солвер':>7} {'оценка':>7}")
    for v in fr["variants"]:
        print(f"{v['eps']:>5} {v['engineers_used']:>5} {v['assigned']:>6} {v['total_km']:>7} {v['min_tol']:>8} {v['tight_stops']:>7} "
              f"{v['expected_late']:>9} {v['p_any_late']:>7} {v['expected_overtime_min']:>8} {v['t_solve_s']:>6}с {v['t_assess_s']:>6}с")
    print(f"\nрекомендуемая подушка: {fr['recommended_eps']}   (весь фронт: {total:.1f} с, {a.engine})")
    fr["text"] = recommendation_text(p, fr)
    fr["base_plan_id"] = plan["plan_id"]
    print(fr["text"])
    import copy
    for v in fr["variants"]:                       # каждый вариант — полноценный план, его можно открыть в Ганте
        d = copy.deepcopy(ds)
        d["config"]["robustness"] = v["robustness"]
        pv = Problem.from_dataset(d)
        vplan = build_plan(pv, pv, v.pop("routes"), set(v["unassigned_ids"]), f"{a.engine} ε={v['eps']}", dataset=plan["dataset"])
        vplan["risk_variant"] = {"eps": v["eps"], "of": plan["plan_id"]}
        path = Path(a.out) / "risk" / f"plan_eps{v['eps']}.json"
        dump(vplan, path)
        v["plan_file"], v["plan_id"] = str(path), vplan["plan_id"]
    dump(fr, Path(a.out) / "risk.json")


def cmd_verify(a) -> None:
    from .verify import verify
    bad = 0
    for path in a.plans:
        plan = load(path)
        errs = verify(load(plan["dataset"]), plan)
        print(f"{path}: {'OK' if not errs else f'{len(errs)} ошибок'}")
        for e in errs:
            print("   ", e)
        bad += bool(errs)
    raise SystemExit(bad)


def cmd_compare(a) -> None:
    plans = [load(x) for x in a.plans]
    print(f"{'engine':<10} {'инж.':>5} {'назн.':>6} {'не назн.':>9} {'км':>8} {'макс км':>8} {'время':>6}")
    for pl in plans:
        m = pl["metrics"]
        print(f"{pl['engine']:<10} {m['engineers_used']:>5} {m['assigned']:>6} {m['unassigned']:>9} "
              f"{m['total_km']:>8} {max(m['km_per_engineer'].values()):>8} {pl['solve_time_s']:>6}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="planner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("solve")
    s.add_argument("dataset", nargs="?", default=DEFAULT_DS)
    s.add_argument("--engine", default="greedy", choices=["baseline", "greedy", "ortools", "all"])
    s.add_argument("--time-limit", type=float, default=10.0)
    s.add_argument("--travel", choices=["matrix", "normative"], help="дорога: по координатам или нормативные 20 мин")
    s.add_argument("-o", "--out", default="out")
    s.set_defaults(fn=cmd_solve)
    r = sub.add_parser("replan")
    r.add_argument("plan")
    r.add_argument("--event", action="append", required=True)
    r.add_argument("--engine")
    r.add_argument("--stability", default="minimal", choices=["minimal", "full"])
    r.add_argument("--at", help="HH:MM, по умолчанию — время последнего события")
    r.add_argument("--time-limit", type=float, default=10.0)
    r.add_argument("-o", "--out", default="out")
    r.set_defaults(fn=cmd_replan)
    e = sub.add_parser("explain")
    e.add_argument("plan")
    e.add_argument("request_id")
    e.set_defaults(fn=cmd_explain)
    n = sub.add_parser("narrate")
    n.add_argument("plan")
    n.add_argument("--request", action="append")
    n.add_argument("--summary", action="store_true")
    n.add_argument("--diff", action="store_true")
    n.add_argument("--baseline")
    n.add_argument("--model", help="model_name из litellm_config.yaml (по умолчанию $LLM_MODEL или dispatcher)")
    n.add_argument("--dry-run", action="store_true", help="показать бандл фактов вместо вызова ЛЛМ")
    n.set_defaults(fn=cmd_narrate)
    ch = sub.add_parser("chat")
    ch.add_argument("plan")
    ch.add_argument("--ask")
    ch.add_argument("--baseline")
    ch.add_argument("--model")
    ch.set_defaults(fn=cmd_chat)
    rk = sub.add_parser("risk")
    rk.add_argument("plan")
    rk.add_argument("--engine", default="ortools", choices=["ortools", "greedy"])
    rk.add_argument("--time-limit", type=float, default=3.0)
    rk.add_argument("--eps")
    rk.add_argument("--stress-only", action="store_true")
    rk.add_argument("-o", "--out", default="out")
    rk.set_defaults(fn=cmd_risk)
    v = sub.add_parser("verify")
    v.add_argument("plans", nargs="+")
    v.set_defaults(fn=cmd_verify)
    c = sub.add_parser("compare")
    c.add_argument("plans", nargs="+")
    c.set_defaults(fn=cmd_compare)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
