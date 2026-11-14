"""CLI: python -m health_graph {import,query,list} ...

  python -m health_graph import --db health.rl fixtures/fhir/*.json
  python -m health_graph query --db health.rl trend --param loinc=4548-4
  python -m health_graph list
  python -m health_graph receive --db health.rl      # pair Klarbefund by QR code
  python -m health_graph knowledge --db health.rl    # seed risks, scores, markers, reference ranges
  python -m health_graph scores --db health.rl       # compute risk scores, store them with their inputs
  python -m health_graph anamnesis --db health.rl --plan      # findings in the data, the questions they raise
  python -m health_graph anamnesis --db health.rl --answers answers.json   # store answers (- = stdin)
  python -m health_graph anamnesis --questions       # every question and its answer codes
  python -m health_graph protocols --db health.rl --plan      # LE8, FINDRISC, AUDIT-C, ... prefilled from the data
  python -m health_graph protocols --db health.rl --protocol findrisc --answers a.json   # store one protocol
"""
import argparse
import sys

from . import fhir, store
from .queries import QUERIES


def _table(rows: list[dict]) -> str:
    if not rows:
        return "(no rows)"
    cols = list(rows[0])
    cells = [[("" if r[c] is None else str(r[c])) for c in cols] for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in cells)) for i, c in enumerate(cols)]
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    fmt = lambda vals: "| " + " | ".join(v.ljust(w) for v, w in zip(vals, widths)) + " |"
    return "\n".join([line, fmt(cols), line, *map(fmt, cells), line])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="health_graph", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser("import", help="import FHIR Bundles into a local .rl store")
    imp.add_argument("--db", required=True)
    imp.add_argument("bundles", nargs="+")

    q = sub.add_parser("query", help="run a named read-only query")
    q.add_argument("--db", required=True)
    q.add_argument("name", choices=sorted(QUERIES))
    q.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")

    rc = sub.add_parser("receive", help="receive reports + Apple Health from Klarbefund (QR pairing)")
    rc.add_argument("--db", required=True)
    rc.add_argument("--port", type=int, default=8787)
    rc.add_argument("--host", help="address to put in the QR code (default: this Mac's Wi-Fi address)")
    rc.add_argument("--rotate", action="store_true", help="new token: phones paired before must scan again")
    rc.add_argument("--qr-png", help="also save the QR code as a PNG (contains the token)")
    rc.add_argument("--print-link", action="store_true", help="also print the pairing link (contains the token)")
    rc.add_argument("--require-mount", action="store_true",
                    help="refuse to start unless the store's folder is a mounted volume (encrypted vault)")

    kn = sub.add_parser("knowledge", help="seed the knowledge layer (idempotent)")
    kn.add_argument("--db", required=True)
    kn.add_argument("--force", action="store_true")

    sc = sub.add_parser("scores", help="compute risk scores and store them in the graph with their inputs")
    sc.add_argument("--db", required=True)
    sc.add_argument("--smoker", choices=["yes", "no"],
                    help="default: the latest anamnesis answer, else no")
    sc.add_argument("--region", choices=["low", "moderate", "high", "very high"], default="moderate")

    an = sub.add_parser("anamnesis", help="anamnesis from the data: findings, questions, store the answers")
    an.add_argument("--db")
    an.add_argument("--plan", action="store_true", help="the findings, what the data answers, the questions to ask")
    an.add_argument("--json", action="store_true", help="with --plan: print the plan as JSON")
    an.add_argument("--answers", help='JSON {key: code | [codes] | {"codes", "text", "basedOn", "findings"}}, '
                                      'key = question or question@date from the plan, - = stdin')
    an.add_argument("--questions", action="store_true", help="print the questions and answer codes")
    an.add_argument("--show", action="store_true", help="print the latest stored answers")

    pr = sub.add_parser("protocols", help="anamnesis protocols (LE8, FINDRISC, AUDIT-C, ...): prefilled, stored")
    pr.add_argument("--db")
    pr.add_argument("--plan", action="store_true", help="the protocols prefilled from the data, ranked for this person")
    pr.add_argument("--json", action="store_true", help="with --plan: print it as JSON")
    pr.add_argument("--protocol", help="with --answers: the protocol answered (le8, findrisc, audit-c, ...)")
    pr.add_argument("--answers", help='JSON {linkId: code | [codes] | {"codes", "text", "observation"}}, - = stdin')
    pr.add_argument("--seed", action="store_true", help="write the protocols, items and SNOMED codes into the graph")

    sub.add_parser("list", help="list the named queries")
    args = ap.parse_args(argv)

    if args.cmd == "list":
        for name, (desc, _) in sorted(QUERIES.items()):
            print(f"{name:11} {desc}")
        return 0

    if args.cmd == "receive":
        from .receiver import serve
        serve(args.db, port=args.port, rotate=args.rotate, host=args.host, qr_png=args.qr_png,
              print_link=args.print_link, require_mount=args.require_mount)
        return 0

    if args.cmd == "knowledge":
        from . import knowledge
        conn = store.connect(args.db)
        store.init_schema(conn)
        counts = knowledge.seed(conn, force=args.force)
        conn.close()
        print("knowledge:", ", ".join(f"{k}={v}" for k, v in counts.items()) or "already current")
        return 0

    if args.cmd == "protocols":
        import json
        from . import protocols
        if not args.db:
            for p in protocols.PROTOCOLS:
                print(f"{p['id']:14} {p['name']} ({p.get('year')}): {len(p['items'])} items, "
                      f"risks {', '.join(p['risks'])}")
            return 0
        conn = store.connect(args.db)
        store.init_schema(conn)
        try:
            if args.seed:
                print("protocols:", ", ".join(f"{k}={v}" for k, v in protocols.seed(conn).items()))
            if args.answers:
                if not args.protocol:
                    print("--answers needs --protocol")
                    return 2
                raw = sys.stdin.read() if args.answers == "-" else open(args.answers, encoding="utf-8").read()
                pid = conn.execute("MATCH (p:Patient) RETURN p.id AS id").single()["id"]
                counts = protocols.store_response(conn, pid, args.protocol, json.loads(raw), source="cli")
                print(f"{args.protocol}: {counts['answers']} answers stored"
                      + (f", score {counts['score']:g} ({counts['band']})" if counts["score"] is not None else
                         f" ({counts['band']})" if counts["band"] else ""))
            if args.plan:
                plan = protocols.plan(conn)
                if args.json:
                    print(json.dumps(plan, indent=2, ensure_ascii=False))
                else:
                    for p in plan["protocols"]:
                        sc = p["score"] or {}
                        state = (f"score {sc['value']:g}" + (f" ({sc['band']})" if sc.get("band") else
                                 f", {len(sc.get('missing', []))} to answer") if sc.get("value") is not None
                                 else sc.get("band") or "")
                        print(f"{p['name']}: {p['prefilled']} of {len(p['items'])} prefilled; {state}")
                        for why in p["forYou"]:
                            print(f"  for you: {why}")
                        for it in p["items"]:
                            if it["prefilled"]:
                                print(f"  {it['linkId']}: {it['prefilled']['code']} ({it['prefilled']['text']})")
        finally:
            conn.close()
        return 0

    if args.cmd == "anamnesis":
        import json
        from . import anamnesis
        if args.questions or not args.db:
            for it in anamnesis.ITEMS:
                opts = ", ".join(f"{c}{'*' if f else ''}" for c, _, f in it["options"])
                print(f"{it['linkId']:17} {it['text']}\n{'':17} [{opts}]{' (several)' if it['multiple'] else ''}"
                      f"  risks: {', '.join(it['risks'])}")
            print("* = a known risk factor")
            return 0
        if args.plan:
            conn = store.connect(args.db, read_only=True)
            plan = anamnesis.plan(conn)
            conn.close()
            if args.json:
                print(json.dumps(plan, ensure_ascii=False, indent=1))
                return 0
            for f in plan["findings"]:
                vals = "; ".join(f"{v['name']} {v['value']} {v['unit']} ({v['date']}, {v['trigger']})"
                                 for v in f["values"]) or json.dumps(f["detail"], ensure_ascii=False)
                print(f"finding  {f['id']:16} {vals}")
            for k in plan["known"]:
                print(f"known    {k['fact']:16} {k['detail']}")
            for r in plan["rechecks"]:
                print(f"recheck  {r['name']:16} {r['date']} ({r['flag']}, {r['ageDays']} days old)")
            for s in plan["skipped"]:
                print(f"skip     {s['key']:16} {s['reason'][:100]}")
            for q in plan["questions"]:
                print(f"ask      {q['key']:16} {q['text']}  [{', '.join(o['code'] for o in q['options'])}]")
            return 0
        conn = store.connect(args.db)
        store.init_schema(conn)
        found = list(conn.execute("MATCH (p:Patient) RETURN p.id AS id"))
        if len(found) != 1:
            print(f"expected one patient in the graph, found {len(found)}")
            return 1
        pid = found[0]["id"]
        if args.answers:
            raw = sys.stdin.read() if args.answers == "-" else open(args.answers, encoding="utf-8").read()
            counts = anamnesis.store_response(conn, pid, json.loads(raw))
            print(f"anamnesis: {counts['answers']} answers stored, {counts['riskFactors']} of them risk factors")
        else:
            n = anamnesis.seed(conn)
            print(f"anamnesis: questionnaire seeded ({n} question-risk links)")
        if args.show:
            for link_id, a in anamnesis.latest_answers(conn, pid).items():
                print(f"{link_id:22} {', '.join(a['labels'] or [])}{' / ' + a['text'] if a['text'] else ''}"
                      f"{'  (risk factor)' if a['riskFactor'] else ''}")
        conn.close()
        return 0

    if args.cmd == "scores":
        import datetime as dt
        from . import knowledge, risk
        conn = store.connect(args.db)
        store.init_schema(conn)
        knowledge.seed(conn)
        found = list(conn.execute("MATCH (p:Patient) RETURN p.id AS id, p.birthYear AS y, p.gender AS g"))
        p = found[0] if len(found) == 1 else None
        if not p:
            print("no patient in the graph")
            return 1
        age = dt.date.today().year - p["y"] if p["y"] else None
        said = None
        if args.smoker is None:
            from . import anamnesis
            said = anamnesis.latest_answers(conn, p["id"]).get("smoking")
            args.smoker = "yes" if said and "current" in (said["codes"] or []) else "no"
            print(f"smoking: {args.smoker} ({'from the anamnesis' if said else 'no anamnesis answer, assumed'})")
        stored = 0
        for s in risk.compute_scores(conn, age, p["g"], args.smoker == "yes", args.region):
            if s.id and s.value is not None:
                n = knowledge.store_score(conn, p["id"], s.id, s.value, s.band, s.light, s.observations,
                                          f"age {age}, {p['g']}, smoking {args.smoker}", s.note,
                                          dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
                if said and s.id == "score2":  # SCORE2 used the smoking answer: link it as an input
                    conn.execute(anamnesis.LINK_SCORE_ANSWER, {"scoreId": f"{p['id']}-score2", "answerId": said["id"]})
                print(f"{s.name}: stored, from {n} values")
                stored += 1
        conn.close()
        print(f"{stored} scores stored")
        return 0

    if args.cmd == "import":
        conn = store.connect(args.db)
        store.init_schema(conn)
        for path in args.bundles:
            parsed = fhir.parse_bundle(fhir.load_bundle(path))
            n = store.import_report(conn, parsed)
            ready = sum(o["hubEligible"] for o in parsed.observations)
            print(f"{path}: report {parsed.report_id}, {n} values ({ready} Hub-ready)")
        counts = store.omop_transform(conn)
        print("OMOP:", ", ".join(f"{k}={v}" for k, v in counts.items()))
        conn.close()
        return 0

    params = dict(p.split("=", 1) for p in args.param)
    conn = store.connect(args.db, read_only=True)
    rows = [dict(r) for r in conn.execute(QUERIES[args.name][1], params)]
    conn.close()
    print(_table(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
