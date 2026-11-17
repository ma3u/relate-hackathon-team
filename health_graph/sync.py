"""Keep the anamnesis answers in step between Klarbefund for Mac and the vault.

Answers reach two graphs: Klarbefund for Mac's own (Claude stores them there through the app's
MCP helper) and the vault (~/RelateHealth/health.rl, where Claude Code and the scripts store them).
Each side only adds; nothing is ever changed or deleted on the other side.

- app -> vault: a response the vault does not have is stored with the vault's own functions, under
  its original time and source, so it gets the same id as in the app.
- vault -> app: the app owns its graph, so a response goes the way Claude's answers go: through the
  helper's save_anamnesis_answers / save_protocol_answers, which leave a request in the app's Inbox.
  The app stamps it with the time it stores it.

That last point is why two responses are matched by what they say, not by id: the questionnaire,
and per question the answer codes and the text. Answers a protocol derives itself (family-cvd from
the family history) are left out of the match; storing the response derives them again.

The helper is signed into the app's group, so it can read the app's graph where a shell may not.
It is started per sync and spoken to over stdio (MCP, JSON-RPC), read-only except for those two tools.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field

from . import anamnesis, protocols

HELPER = os.environ.get("KLARBEFUND_MCP", "/Applications/Klarbefund.app/Contents/Helpers/klarbefund-mcp")

# Every response with its answers, the codes they rest on and the value a protocol answer was
# prefilled from. The same statement runs on both graphs.
RESPONSES = """
MATCH (r:QuestionnaireResponse)-[:HAS_ANSWER]->(a:Answer)
OPTIONAL MATCH (a)-[:BASED_ON]->(c:LoincCode)
OPTIONAL MATCH (a)-[:PREFILLED_FROM]->(o:Observation)
WITH r, a, collect(DISTINCT c.code) AS basedOn, collect(DISTINCT o.resourceId) AS observations
ORDER BY a.id
RETURN r.id AS id, r.authored AS authored, r.source AS source, r.protocol AS protocol,
       collect({linkId: a.linkId, context: a.context, codes: a.codes, text: a.text, findings: a.findings,
                question: a.question, prefilled: a.prefilled, derivedFrom: a.derivedFrom,
                basedOn: basedOn, observations: observations}) AS answers
ORDER BY authored, id
"""


@dataclass
class Response:
    id: str
    authored: str
    source: str | None
    questionnaire: str            # klarbefund-anamnesis, or a protocol id (findrisc, le8, ...)
    answers: list[dict] = field(default_factory=list)

    @classmethod
    def of(cls, row: dict) -> "Response":
        questionnaire = row.get("protocol") or row["id"].split("|")[-2]
        return cls(row["id"], row["authored"], row.get("source"), questionnaire, list(row.get("answers") or []))

    @property
    def is_anamnesis(self) -> bool:
        return self.questionnaire == anamnesis.QUESTIONNAIRE["id"]

    def own_answers(self) -> list[dict]:
        return [a for a in self.answers if not a.get("derivedFrom")]

    def fingerprint(self) -> tuple:
        return (self.questionnaire, tuple(sorted(
            (_key(a), tuple(sorted(a.get("codes") or [])), (a.get("text") or "").strip())
            for a in self.own_answers())))

    def as_answers(self) -> dict:
        """The answers in the form store_response and the helper's save tools take."""
        out: dict = {}
        for a in self.own_answers():
            value: dict = {"codes": list(a.get("codes") or [])}
            if a.get("text"):
                value["text"] = a["text"]
            if self.is_anamnesis:
                value.update(basedOn=list(a.get("basedOn") or []), findings=list(a.get("findings") or []))
                if a.get("question"):
                    value["question"] = a["question"]
            else:
                if a.get("prefilled"):
                    value["prefilled"] = a["prefilled"]
                if a.get("observations"):
                    value["observation"] = a["observations"][0]
            out[_key(a)] = value
        return out


def _key(a: dict) -> str:
    return f"{a['linkId']}@{a['context']}" if a.get("context") else a["linkId"]


def responses(rows: list[dict]) -> list[Response]:
    return [Response.of(r) for r in rows]


@dataclass
class Plan:
    to_vault: list[Response]
    to_app: list[Response]
    differ: list[str]             # ids on both sides whose answers differ: reported, never moved


def plan(app: list[Response], vault: list[Response]) -> Plan:
    """What each side says that the other does not.

    One id on both sides is one response, even if an answer was edited on one side since: it is
    reported, not copied, because a copy would be a second, newer response with the same answers.
    """
    app_ids, vault_ids = {r.id: r for r in app}, {r.id: r for r in vault}
    differ = sorted(i for i in app_ids.keys() & vault_ids.keys()
                    if app_ids[i].fingerprint() != vault_ids[i].fingerprint())
    in_app, in_vault = {r.fingerprint() for r in app}, {r.fingerprint() for r in vault}
    to_vault = [r for r in app if r.id not in vault_ids and r.fingerprint() not in in_vault]
    to_app = [_newer_only(r, app) for r in vault if r.id not in app_ids and r.fingerprint() not in in_app]
    return Plan(to_vault, [r for r in to_app if r.own_answers()], differ)


def _newer_only(r: Response, app: list[Response]) -> Response:
    """The app stamps what it stores with the time it stores it, so an answer it holds from later than
    r would be outranked by r's older one. Such answers stay out of what is sent."""
    later = {_key(a) for x in app if x.questionnaire == r.questionnaire and x.authored > r.authored
             for a in x.own_answers()}
    return Response(r.id, r.authored, r.source, r.questionnaire, [a for a in r.answers if _key(a) not in later])


def store_in_vault(conn, patient_id: str, items: list[Response]) -> list[str]:
    """Store each response under its own time and source. One line per response; a refused one says why."""
    lines = []
    for r in items:
        try:
            if r.is_anamnesis:
                n = anamnesis.store_response(conn, patient_id, r.as_answers(), source=r.source or "app",
                                             authored=r.authored)["answers"]
            else:
                n = protocols.store_response(conn, patient_id, r.questionnaire, r.as_answers(),
                                             source=r.source or "app", authored=r.authored)["answers"]
            lines.append(f"to vault  {r.questionnaire:22} {r.authored}  {n} answers")
        except ValueError as e:  # a question or code the vault's definitions no longer know
            lines.append(f"refused   {r.questionnaire:22} {r.authored}  {e}")
    return lines


class AppHelper:
    """Klarbefund for Mac's MCP helper, started for one sync and spoken to over stdio."""

    def __init__(self, path: str = HELPER):
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} not found: install Klarbefund for Mac, or set KLARBEFUND_MCP")
        self.proc = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True)
        self.next_id = 0
        self._call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "clientInfo": {"name": "health_graph-sync", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _send(self, message: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def _call(self, method: str, params: dict) -> dict:
        self.next_id += 1
        self._send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params})
        assert self.proc.stdout is not None
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("Klarbefund's helper closed the connection")
            reply = json.loads(line)
            if reply.get("id") == self.next_id:
                if "error" in reply:
                    raise RuntimeError(reply["error"].get("message", "helper error"))
                return reply["result"]

    def tool(self, name: str, arguments: dict) -> str:
        result = self._call("tools/call", {"name": name, "arguments": arguments})
        text = "".join(c.get("text", "") for c in result.get("content", []))
        if result.get("isError"):
            raise RuntimeError(f"{name}: {text}")
        return text

    def rows(self, statement: str) -> list[dict]:
        return json.loads(self.tool("read_cypher", {"statement": statement}))["rows"]

    def responses(self) -> list[Response]:
        return responses(self.rows(RESPONSES))

    def submit(self, r: Response) -> str:
        if r.is_anamnesis:
            return self.tool("save_anamnesis_answers", {"answers": r.as_answers()})
        return self.tool("save_protocol_answers", {"protocol": r.questionnaire, "answers": r.as_answers()})

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.terminate()
        self.proc.wait(timeout=5)


def send_to_app(helper, items: list[Response]) -> list[str]:
    lines = []
    for r in items:
        try:
            helper.submit(r)
            lines.append(f"to app    {r.questionnaire:22} {r.authored}  {len(r.own_answers())} answers (in its Inbox)")
        except RuntimeError as e:
            lines.append(f"refused   {r.questionnaire:22} {r.authored}  {e}")
    return lines
