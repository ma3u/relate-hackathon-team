# The Klarbefund MCP server

Klarbefund for Mac brings its own [Model Context Protocol](https://modelcontextprotocol.io) server, `klarbefund-mcp`, a small sandboxed helper inside the app (`Klarbefund.app/Contents/Helpers/klarbefund-mcp`). Claude Desktop starts it when you connect Claude in step 3 of the app; through it Claude reads your health graph, read-only, while Klarbefund for Mac is open. It is the server behind the "Klarbefund Health Graph" extension. For the app itself see [MAC.md](MAC.md).

What it offers:

- **4 tools**: `get_schema` (labels and relationship types with counts), `read_cypher` (one `MATCH ... RETURN` query, at most 500 rows), `anamnesis_plan` (what stands out in your own values, what your data already answers, and only the questions left), all three read-only; and `save_anamnesis_answers`, which hands the answers you confirmed to Klarbefund for Mac to store. See [The anamnesis skill](#the-anamnesis-skill).
- **25 prompts**, the use cases you pick from Claude's **+** menu: risks and what to improve, values and trends, the doctor's visit, habits and Apple Watch, the graph and the evidence, setup and privacy. Each prompt carries Klarbefund's rules: dates and the age of every value, newer evidence before older, ask about habits the graph cannot know, not medical advice.
- **8 guides** as MCP resources (`klarbefund://guide/...`, Markdown) that Claude can read: start, install, pairing, usage, the graph and the 3D view, how evidence is weighed, security, and the list of prompts.
- **Instructions** that describe the graph's schema and the same rules, sent when a client connects.

Prompts, guides and rules live in one file, [`apps/mac/Shared/MCPCatalog.swift`](../apps/mac/Shared/MCPCatalog.swift). The helper serves it, the app's "What Claude can do here" sheet shows it, and the Claude Desktop extension's manifest lists it. No health data is in it: these are texts, the same for everyone.

## Transport and protocol revisions

The server speaks MCP over **stdio**: JSON-RPC 2.0, one message per line on standard input and output. It is a child process of Claude Desktop and opens no port.

| Revision | How a client starts | Notes |
| --- | --- | --- |
| `2026-07-28` | `server/discover`, then every request names the revision in `params._meta["io.modelcontextprotocol/protocolVersion"]` | Stateless. Results carry `resultType: "complete"` and the server in `_meta["io.modelcontextprotocol/serverInfo"]`; lists and guides carry `ttlMs: 3600000` and `cacheScope: "public"` (they change only with an app update). Tool results are never marked cacheable. An unknown revision is answered with `-32022 Unsupported protocol version` and `data: {supported, requested}`. |
| `2025-11-25`, `2025-06-18`, `2025-03-26`, `2024-11-05` | `initialize` | The server answers with the client's revision if it knows it, else `2025-11-25`. A request without the `_meta` revision is treated as one of these. |

Over stdio a 2026-07-28 client probes with `server/discover` first and falls back to `initialize` when that fails, so old and new clients both connect. The capabilities are `tools`, `prompts` and `resources`, each with `listChanged: false`.

## Security

What protects the data, from the inside out:

- **The graph at rest.** One Neo4j Relate file (`health.rl`) inside Klarbefund for Mac's sandbox. While the app is closed it exists only as `health.rl.sealed`, AES-256-GCM, with a key that stays in this Mac's keychain (this device only).
- **A snapshot only while the app is open.** The app writes a copy to `Snapshot/health.rl` in its app-group container after each transfer and deletes it when it quits. Without the snapshot the server answers every query with "Klarbefund for Mac is not open, so the health graph is sealed".
- **No network.** The helper is sandboxed with exactly two entitlements, `com.apple.security.app-sandbox` and `com.apple.security.application-groups` (the app group it shares with the app). Without `com.apple.security.network.client` or `network.server` it can neither open a port nor reach the network; macOS enforces that, not the code. (The app itself has the network entitlements, for receiving from the iPhone over the local Wi-Fi.)
- **Read-only, twice; answers only through the app.** The helper opens the snapshot read-only (`HealthStore(path:readOnly: true)`), and before that it refuses any query containing a write clause (`CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `DROP`, `LOAD CSV`, `FOREACH`). The snapshot is a copy: even a write that got through would not reach the sealed graph. The one way anything is written is `save_anamnesis_answers`: the helper checks the answers against the questions and leaves one request file in the app-group container's `Inbox`; Klarbefund for Mac, which owns the graph, stores it and deletes the file (or renames it `.rejected`, with the reason). Nothing but anamnesis answers can be written that way.
- **You approve.** The reading tools are annotated `readOnlyHint: true`, `destructiveHint: false`, `openWorldHint: false`; `save_anamnesis_answers` `readOnlyHint: false`, `destructiveHint: false`. Claude Desktop asks before a tool runs unless you allowed it, and the prompt asks you to confirm your answers before they are saved.
- **What reaches the conversation.** The rows Claude asks for go into your Claude conversation, like anything you type, under your Claude account's privacy settings. Ask for counts and summaries when you do not need the values. Prompts, guides and the lists contain no health data.

### Why there is no OAuth

MCP's authorization is OAuth 2.1, and it is defined for HTTP transports. For stdio the [specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) is explicit:

> Implementations using an STDIO transport SHOULD NOT follow this specification, and instead retrieve credentials from the environment.

This server takes no credentials at all: there is no remote party to authenticate. The operating system decides who can start it (the logged-in user, through Claude Desktop) and which files it can read (its sandbox and the app group).

### What a remote version would need

If Klarbefund ever offered the graph to claude.ai or another device, the server would have to run over **Streamable HTTP** and follow MCP's authorization:

- **OAuth 2.1** with an authorization server of its own; the MCP server is an OAuth resource server that accepts only access tokens issued for it.
- **PKCE** (S256) on every authorization code flow.
- **Protected Resource Metadata, [RFC 9728](https://www.rfc-editor.org/rfc/rfc9728)**: the server publishes which authorization server it trusts and points to it in its `WWW-Authenticate` challenge.
- **Resource Indicators, [RFC 8707](https://www.rfc-editor.org/rfc/rfc8707)**: clients name the server in the `resource` parameter, so tokens are bound to it; the server checks the audience and never passes a token on.
- **Issuer validation, [RFC 9207](https://www.rfc-editor.org/rfc/rfc9207)**: clients check the `iss` parameter of the authorization response against the authorization server they started with, against mix-up attacks.
- HTTPS, `Origin` checks, and a data store that is no longer only on the Mac, which is a different privacy promise from the one Klarbefund makes today.

## Inspect it yourself

With the official [MCP Inspector](https://github.com/modelcontextprotocol/inspector). Build the app first (`cd apps/mac && xcodegen generate && xcodebuild -scheme Klarbefund build`), then point the Inspector at the helper:

```bash
HELPER=$(ls -t ~/Library/Developer/Xcode/DerivedData/Klarbefund-*/Build/Products/Debug/Klarbefund.app/Contents/Helpers/klarbefund-mcp | head -1)

# CLI: one method per run, JSON out
npx -y @modelcontextprotocol/inspector@2.13.0 --cli --format json $HELPER --method tools/list
npx -y @modelcontextprotocol/inspector@2.13.0 --cli --format json $HELPER --method prompts/list
npx -y @modelcontextprotocol/inspector@2.13.0 --cli --format json $HELPER --method resources/list
npx -y @modelcontextprotocol/inspector@2.13.0 --cli --format json $HELPER --method resources/read --uri klarbefund://guide/security
npx -y @modelcontextprotocol/inspector@2.13.0 --cli --format json $HELPER --method prompts/get --prompt-name marker_trend --prompt-args marker=LDL
# the same over 2026-07-28 instead of initialize
npx -y @modelcontextprotocol/inspector@2.13.0 --cli --format json --protocol-era modern $HELPER --method prompts/list

# Web UI: starts on localhost and opens the browser; add a stdio server whose command is $HELPER
npx -y @modelcontextprotocol/inspector@2.13.0
```

Or by hand, one JSON line in, one out:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28"}}}' | $HELPER
```

`tools/call` with `get_schema` or `read_cypher` reads your real graph while Klarbefund for Mac is open: the rows go to your terminal or the Inspector, not to Claude.

`scripts/mcp_capabilities.sh` runs the Inspector CLI (pinned to 2.13.0) against the newest build and rewrites the section below; `--check` only checks it is current. It calls list and discovery methods only.

## What the server offers

<!-- generated:start -->
Generated by `scripts/mcp_capabilities.sh` with the MCP Inspector 2.13.0 (`--cli`) against the built `klarbefund-mcp`: the lists below are what a client receives. Do not edit by hand.

- **Server:** klarbefund-health
- **Revisions** (`server/discover`): `2026-07-28`, `2025-11-25`, `2025-06-18`, `2025-03-26`, `2024-11-05`
- **Capabilities:** prompts, resources, tools
- **Counts:** 4 tools, 25 prompts, 8 resources (the same prompt list through `initialize` and through 2026-07-28)

### Tools

| Tool | Title | Annotations | Description |
| --- | --- | --- | --- |
| `get_schema` | Health graph schema | readOnlyHint: true, destructiveHint: false, openWorldHint: false | Labels and relationship types in the user's health graph, with counts. Call this first. |
| `read_cypher` | Read-only Cypher query | readOnlyHint: true, destructiveHint: false, openWorldHint: false | Run one read-only Cypher query (MATCH ... RETURN) against the user's health graph. Returns JSON rows (at most 500). |
| `anamnesis_plan` | Anamnesis from my data | readOnlyHint: true, destructiveHint: false, openWorldHint: false | Findings in the user's own data, what the graph already answers, values too old to judge, and only the questions left. |
| `save_anamnesis_answers` | Store my anamnesis answers | readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false | Hands the confirmed answers to Klarbefund for Mac, which checks and stores them. |

### Prompts

| Prompt | Title | Arguments | Description |
| --- | --- | --- | --- |
| `my_risks` | Where are my risks? | – | The six health risks the graph tracks, ranked by your recent values, with the main driver and the gaps. |
| `what_to_improve` | What should I improve first? | `focus` (optional) | The three changes with the largest expected benefit, with targets and when to measure again. |
| `tired_what_to_measure` | I always feel tired: what should I measure? | `since` (optional) | The lab values that can explain tiredness, which you have, and which are missing or old. |
| `heart_risk_score` | My 10-year heart risk (SCORE2) | – | SCORE2 from your graph and your smoking status, with the inputs, the category and what moves it. |
| `lipids_newer_markers` | My cholesterol, with the newer markers | – | LDL next to ApoB, non-HDL, the TG/HDL ratio, AIP, remnant cholesterol and Lp(a), over time. |
| `insulin_resistance` | Early signs of insulin resistance | – | HbA1c, fasting glucose, TyG, TG/HDL, liver values, waist and activity, before diabetes shows. |
| `kidney_check` | My kidneys over time | – | eGFR (CKD-EPI 2021) and its trend, the KDIGO category, and whether urine albumin is missing. |
| `liver_check` | My liver | – | ALT, AST, GGT, platelets and FIB-4 with the EASL cut-offs, and what alcohol and weight do. |
| `bone_check` | My bones and vitamin D | – | What the graph knows about bone health, and why one old vitamin D value says little. |
| `out_of_range` | Which values need attention? | – | Your newest values outside the guideline range, or inside it but not optimal, with sources. |
| `marker_trend` | How has a value changed? | `marker` | Every value of one marker over time, the range on each date, and the change per year. |
| `explain_value` | Explain one value | `marker` | What a marker measures, your values, its range and source, the risks it marks and what moves it. |
| `report_summary` | Summarise a lab report | `date` (optional) | One report in plain language: what was measured, what stands out, what changed since the last one. |
| `next_lab_panel` | What should my next lab test include? | – | The markers your graph lacks or has only old values of, ordered by what they would change. |
| `anamnesis` | Anamnesis from my data, for my family doctor | `language` (optional) | Questions only about what stands out in your own values, your answers stored in the graph, and a brief that helps your family doctor weigh your risks. |
| `doctor_brief` | Write a doctor's brief | `reason` (optional), `language` (optional) | One page to hand over: reason, values outside the range, trends, scores, gaps, questions. |
| `doctor_visit` | Prepare my doctor's visit | – | The four most important topics for a short appointment, with trends, questions and sources. |
| `habits_interview` | Ask me about my habits | – | A short interview about what the graph cannot know, and how the answers change the picture. |
| `apple_watch` | My Apple Watch weeks | – | Resting heart rate, HRV, VO2 max, steps and sleep over time, and the risks they mark. |
| `whats_in_my_graph` | What is in my health graph? | – | The kinds of data, their sources and time span, and three good next questions. |
| `graph_guide` | Help me read my health graph | `question` (optional) | The layers of the graph, how they connect, three paths that matter for you, with the queries. |
| `old_evidence` | Which of my ranges rest on older evidence? | – | Ranges and claims from superseded or older sources, the newer view, and what changes for you. |
| `research_copy` | What would a study see? | – | Your OMOP research copy: what a study under the EHDS would receive instead of your reports. |
| `setup_guide` | Install and connect Klarbefund | – | iPhone, Mac and Claude, step by step, with checks and troubleshooting. |
| `privacy_check` | What leaves my Mac? | – | Where your data is, what Claude can read, what reaches the conversation, and how it is protected. |

### Resources (guides)

| URI | Title | Type | Description |
| --- | --- | --- | --- |
| `klarbefund://guide/start` | Start here | text/markdown | What this server is, what it can read, and how to ask. |
| `klarbefund://guide/install` | Install Klarbefund and connect Claude | text/markdown | The apps, the order, the Connect button, and the manual setup. |
| `klarbefund://guide/pairing` | Pair your iPhone with your Mac | text/markdown | Export to my Mac (Relate): the QR code, the Wi-Fi, the pinned connection. |
| `klarbefund://guide/usage` | Ask good questions | text/markdown | The prompts, how to phrase your own questions, and useful queries. |
| `klarbefund://guide/graph` | The health graph and the 3D view | text/markdown | The layers of the graph, how they connect, and how to read the 3D view. |
| `klarbefund://guide/evidence` | How Klarbefund weighs evidence | text/markdown | Recency, guideline editions, older statements, and the newer markers. |
| `klarbefund://guide/security` | Security and privacy | text/markdown | Where the data is, what this server can do, the MCP transport, and why there is no OAuth. |
| `klarbefund://guide/use-cases` | What you can ask: the prompts | text/markdown | Every prompt this server offers, grouped, with what it does. |
<!-- generated:end -->

## The anamnesis skill

A questionnaire that asks everyone everything also asks what the graph already knows. The `anamnesis` prompt starts from your data instead:

1. **`anamnesis_plan` finds what stands out.** The newest value of each analyte (across its LOINC codes and units) against the guideline range that applied on its date, in the same unit and for your sex, else against the range the lab printed. A value outside it, or within 5 % of a limit, is a finding, and so is a value only the lab flags (Lp(a) inside the ESC/EAS range but above the lab's limit). Also: FIB-4 from 1.30 (AST, ALT and the platelet count of one visit, within 14 days), a peak systolic pressure in an exercise test from 210 mmHg (men) or 190 mmHg (women), Apple Watch weeks with blood oxygen below 95 %, and smoking when SCORE2 needs it. Values older than 18 months are not judged; they go on the recheck list.
2. **It skips what the data answers.** A 24-hour blood pressure measurement, Apple Watch exercise minutes, a weight series and a bone density scan answer their questions; a question answered in the last 12 months is not asked again. Each skip comes with its reason.
3. **It asks why a value may be what it is.** Each finding has its own questions: for NT-proBNP or creatinine, hard exercise in the 48 hours before that sample (asked per sample date); for Lp(a), whether relatives were tested; for LDL and ApoB, statin history and diet; for an exaggerated exercise blood pressure, family history and home readings.
4. **Your answers go into your graph**, after you confirm them, linked to the finding, the sample date and the codes they are about, and to the health risks when an answer is a known risk factor. SCORE2 then takes your smoking answer as its input.
5. **A brief for your family doctor**: each finding with its values and sources, the answers that change how to read it, the tests the plan suggests, the risk scores and three questions.

The rules, questions and queries live in [`health_graph/anamnesis.py`](../health_graph/anamnesis.py) and are generated into the Swift library, so the command line (`python -m health_graph anamnesis --db … --plan`) and the MCP server ask the same questions; the Swift and Python tests check that they agree.
