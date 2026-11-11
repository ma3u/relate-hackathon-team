"""CLI: python -m health_graph {import,query,list} ...

  python -m health_graph import --db health.rl fixtures/fhir/*.json
  python -m health_graph query --db health.rl trend --param loinc=4548-4
  python -m health_graph list
  python -m health_graph receive --db health.rl      # pair Klarbefund by QR code
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

    sub.add_parser("list", help="list the named queries")
    args = ap.parse_args(argv)

    if args.cmd == "list":
        for name, (desc, _) in sorted(QUERIES.items()):
            print(f"{name:11} {desc}")
        return 0

    if args.cmd == "receive":
        from .receiver import serve
        serve(args.db, port=args.port, rotate=args.rotate, host=args.host, qr_png=args.qr_png,
              print_link=args.print_link)
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
