"""CLI: python -m health_graph {import,query,list} ...

  python -m health_graph import --db health.rl fixtures/fhir/*.json
  python -m health_graph query --db health.rl trend --param loinc=4548-4
  python -m health_graph list
  python -m health_graph receive --db health.rl      # pair Klarbefund by QR code
  python -m health_graph knowledge --db health.rl    # seed risks, scores, markers, reference ranges
  python -m health_graph scores --db health.rl       # compute risk scores, store them with their inputs
  python -m health_graph anamnesis --questions       # the anamnesis questions and their answer codes
  python -m health_graph anamnesis --db health.rl --answers answers.json   # store answers (- = stdin)
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

    an = sub.add_parser("anamnesis", help="the anamnesis questions; store a person's answers in the graph")
    an.add_argument("--db")
    an.add_argument("--answers", help='JSON {linkId: code | [codes] | {"codes": [...], "text": "..."}}, - = stdin')
    an.add_argument("--questions", action="store_true", help="print the questions and answer codes")
    an.add_argument("--show", action="store_true", help="print the latest stored answers")

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
