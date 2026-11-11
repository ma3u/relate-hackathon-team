# Relate by Neo4j Hackathon — Team Up 🤝

I'm taking part in the **[Relate by Neo4j Hackathon](https://relate.devpost.com/)** and I'm **looking for teammates** (teams can have up to 4 people).
This repo summarizes the hackathon so we can get going quickly. It will become our project repo once the team is set.

👉 **Want to join?** [Open a "Join the team" issue](../../issues/new?template=join-the-team.md) and tell me a bit about yourself.

---

## Looking for teammates

**Me:** _TODO: role / main skills / time zone (CET) / availability per week_

**Who would be a great fit** (any of these, no need to tick every box):

- 🦀 / 🐍 **Rust or Python** developers (Relate is a Rust/Python library)
- 🤖 **AI agent / LLM** builders (MCP, tool use, RAG, coding agents)
- 🕸️ **Graph / Cypher** people (Neo4j, knowledge graphs, graph data modeling)
- 🌐 **Frontend / WebAssembly** (Relate runs in the browser for interactive graph views)
- 🎬 **Storytelling / demo / design** — clarity is 1/5 of the score, and a ≤3 min demo video is required

**How we'd work:** async, GitHub issues + PRs, a short weekly call. Ideas welcome — see [Project ideas](#project-ideas).

---

## The hackathon at a glance

| | |
|---|---|
| **Name** | Relate by Neo4j Hackathon |
| **Theme** | **"Context, Connected"** — show how connected data helps agents, apps, or people find and use the relationships that matter |
| **Sponsor** | Neo4j, Inc. — celebrating the launch of Relate at NODES 2026 |
| **Format** | Online, ~1 month, hosted on Devpost |
| **Team size** | 1–4 people; each person can only be on one team; one submission per team |
| **Eligibility** | 18+ (or age of majority), where legal. See [eligibility notes](#heads-up-the-rules-page-is-still-a-draft) for Neo4j employees |
| **Prize pool** | ~$6,197 in Apple hardware (3 winning teams) |

### Key dates

Times from the Devpost schedule (shown in CET / GMT+1):

| Phase | Start | End |
|---|---|---|
| **Submissions** | Thu, Nov 12, 2026 03:00 CET (= Wed, Nov 11, 6 PM PST) | **Sat, Dec 12, 2026 03:00 CET** (= Fri, Dec 11, 6 PM PST) |
| Public voting | Nov 12, 03:00 CET | Dec 17, 03:00 CET |
| Judging | Dec 12, 03:15 CET | Dec 17, 08:45 CET |
| Winners announced | Dec 19, 02:00 CET (Devpost schedule) — the rules text says Thu, Dec 17 | |

> ⏰ **Practical deadline:** have everything submitted by **Friday, Dec 11 evening (CET)**.

### Prizes (marked "not yet final" in the rules)

| Place | Prize | Approx. value |
|---|---|---|
| 🥇 1st | Mac Studio M5 Max, 64 GB / 1 TB | $3,799 |
| 🥈 2nd | Mac mini M6, 32 GB / 512 GB | $1,499 |
| 🥉 3rd | Mac mini M6, 16 GB / 256 GB | $899 |

Prizes go **per winning team, not per member** — one physical item, the team names one recipient. Winners pay their own taxes/import duties.

### Judging criteria (all weighted equally)

1. **Creativity** — how original the idea and approach are
2. **Usefulness** — how well it solves a real problem
3. **Completeness** — works end to end and runs from the setup instructions
4. **Clarity** — quality of the write-up, demo, and visual presentation
5. **Effective use of connected context** — how well it uses Relate's graph, retrieval, and agent features

---

## What we must submit

- [ ] Project title + description (what it does, why it's useful)
- [ ] **Public GitHub repo** (stays public through judging), tagged with the topic Neo4j announces (TBD, e.g. `neo4j`)
- [ ] **Setup instructions** a judge can follow to install and run it
- [ ] **Demo**: video of up to ~3 min (viewable without login) _or_ a link to a working demo; screenshots welcome
- [ ] Statement of which **Relate capabilities, third-party tools, and AI tools** we used (AI coding tools are allowed but must be disclosed)
- [ ] Disclose any reused earlier code / OSS libraries — only work done during the contest period is judged
- [ ] Project must make **meaningful use of Relate** (CLI, embedded, WebAssembly, MCP, Bolt/HTTP, hybrid retrieval, or a Neo4j/Aura connection)

---

## About Relate

Relate is an **open-source, embedded graph database for AI agents** and the engineers who build them. It runs as a library inside your app — no signup, no server.

- **Install and go** — one command adds a Relate skill to your coding agent
- **Query in process** — traverse relationships and run vector search without network calls
- **Agent-ready results** — JSON output with row limits and errors that explain how to fix them
- **Safe shared state** — transactions so multiple agents can update the same graph
- **Lightweight** — one file per graph, memory limits, delete when done
- **Connect when needed** — pull a subgraph from Neo4j, query with Cypher over MCP, Bolt, or HTTP
- **Runs in the browser** — WebAssembly build for interactive graph views
- Use it from the **CLI**, as a **Rust** or **Python** library, or via **WASM**

### Resources

- 🌐 Website: <https://relatedb.ai>
- ⚡ Quickstart / install: <https://relatedb.ai/docs/get-started/install>
- 💻 Source: <https://github.com/relatedb/relate>
- 💡 Idea list: <https://github.com/jexp/relate-ideas>
- 🏆 Devpost: <https://relate.devpost.com/> · [Rules](https://relate.devpost.com/rules) · [Schedule](https://relate.devpost.com/details/dates)

---

## Project ideas

Brainstorm space — add yours via an issue or PR.

- _TODO_
- Browse <https://github.com/jexp/relate-ideas> for inspiration

---

## Heads-up: the rules page is still a draft

As of Nov 11, 2026 the published [rules](https://relate.devpost.com/rules) still contain `[Legal to confirm]` placeholders and contradict the landing page in places. Worth watching for updates:

- **New vs. existing projects** — the landing page says a project "can be new or extend something you already have"; the rules say it must be **started on or after Nov 11, 2026**.
- **Teams** — the landing page says "Hack as an individual… you can work with teammates"; the rules allow teams of **1–4**.
- **Neo4j employees** — the landing page says they may take part but can't win prizes; the rules say they can't enter.
- **Winner announcement** — Dec 17 (rules) vs. Dec 19 (Devpost schedule).
- Still TBD: exact deadline time, repo topic tag, video length, Discord/community channel, contact email, judging (panel only vs. panel + community vote).

_This summary is unofficial. The Devpost page and official rules win in case of doubt._
