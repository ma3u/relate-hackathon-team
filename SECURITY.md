# Security policy

This repository is Klarbefund's local health graph: **Klarbefund for Mac** with its
MCP server, the receiver the iPhone sends to, the Python and Swift code that builds the
[Neo4j Relate](https://neo4j.com/) graph, the vault script and the 3D view. All of it
runs on the person's own Mac and holds their own health data; none of it is a server on
the internet. It is a research project with one maintainer, not a certified product.

Klarbefund for iPhone and the EHDS Integration Hub live in
[ma3u/MinimumViableHealthDataspacev2](https://github.com/ma3u/MinimumViableHealthDataspacev2),
with their own [security policy](https://github.com/ma3u/MinimumViableHealthDataspacev2/blob/main/SECURITY.md).

## Reporting a vulnerability

Report it privately through GitHub:
**[Report a vulnerability](https://github.com/ma3u/relate-hackathon-team/security/advisories/new)**.
Please do not open a public issue, pull request or discussion for it.

Include what you can of:

- the component (see [Scope](#scope)) and the commit or Klarbefund for Mac build;
- the steps to reproduce it, or a proof of concept;
- the impact you see.

**Never put real health data in a report**, yours or anyone's. Reproduce with the
fictional data in [`fixtures/`](fixtures/) and [`examples/`](examples/), or describe the
shape of the data instead of its values.

English or German, as you prefer.

## What happens next

| Step                                | Within                                                                                         |
| ----------------------------------- | ---------------------------------------------------------------------------------------------- |
| Acknowledgement                     | 5 working days                                                                                 |
| Assessment and severity             | 10 working days, rated with [CVSS 4.0](https://www.first.org/cvss/v4-0/specification-document) |
| Fix or mitigation, critical or high | 30 days                                                                                        |
| Fix, medium or low                  | the next build                                                                                 |
| Public advisory                     | after the fix, at most 90 days after the report, at a date agreed with you                     |

The fix lands on `main` and in the next Klarbefund for Mac build. The advisory is
published as a GitHub Security Advisory of this repository, with a CVE requested through
GitHub where one applies, and credits you unless you prefer otherwise. If a deadline
slips, you hear why and by when.

## Supported versions

| Version                                           | Supported |
| ------------------------------------------------- | --------- |
| `main`                                            | ✅        |
| Klarbefund for Mac, the newest build (TestFlight) | ✅        |
| Older builds                                      | ❌        |

## Scope

What each part promises; a way to break one of these promises is a vulnerability.

| Component                                        | Where                                                                              | Its promise                                                                                                                                                                                                                                                                        |
| ------------------------------------------------ | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Klarbefund for Mac                               | [`apps/mac/Klarbefund/`](apps/mac/Klarbefund/)                                     | Sandboxed. While the app is closed the graph exists only sealed with AES-256-GCM; the key stays in this Mac's keychain                                                                                                                                                             |
| The MCP server, `klarbefund-mcp`                 | [`apps/mac/klarbefund-mcp/`](apps/mac/klarbefund-mcp/)                             | No network: sandboxed with only the app-sandbox and app-group entitlements. Reads a read-only snapshot, refuses write clauses, returns at most 500 rows. Writes nothing but anamnesis answers, and those only as a request the app checks and stores                               |
| The receiver, in the app and on the command line | [`swift/mac/`](swift/mac/), [`health_graph/receiver.py`](health_graph/receiver.py) | TLS 1.2 or later, pinned by the certificate's SHA-256 from the QR code; a 256-bit bearer token; private-network and loopback clients only; a FHIR Bundle of at most 10 MB                                                                                                          |
| The vault                                        | [`scripts/health_vault.sh`](scripts/health_vault.sh)                               | The command-line store lives in an AES-256 encrypted disk image, opened only while used; its password is in the login keychain and never printed; the receiver refuses to write while the image is not mounted (`--require-mount`). Claude reads a read-only copy inside the image |
| The 3D view server                               | [`scripts/graph3d_serve.py`](scripts/graph3d_serve.py)                             | Listens on 127.0.0.1 only; a write needs this run's token, this origin and this host; bodies of at most 64 KB; no answer is logged                                                                                                                                                 |
| The graph's content                              | [`health_graph/`](health_graph/), [`swift/Sources/`](swift/Sources/)               | Text read from a report or stored as an answer must not be able to make Claude act against the person (prompt injection through the graph)                                                                                                                                         |
| This repository                                  |                                                                                    | No real health data and no credentials, not even git-ignored                                                                                                                                                                                                                       |

Not in scope, or to report upstream:

- Neo4j Relate itself, to [Neo4j](https://neo4j.com/security/); Apple's platforms, to
  [Apple](https://security.apple.com/); Claude Desktop and Anthropic's services, to
  [Anthropic](https://www.anthropic.com/responsible-disclosure-policy);
- that the rows Claude reads go into the person's Claude conversation: that is the
  documented design ([`docs/MCP.md`](docs/MCP.md#security)), not a leak;
- attacks that need code already running as the person's macOS user, or as root,
  unless they cross the app sandbox or the sealing;
- Klarbefund for iPhone and the EHDS Integration Hub: their
  [own policy](https://github.com/ma3u/MinimumViableHealthDataspacev2/blob/main/SECURITY.md).

## Testing rules

- **Fictional data only.** Test with [`fixtures/`](fixtures/), [`examples/`](examples/)
  or a graph you made up, never with someone else's graph.
- **Your own devices and networks.** The receiver serves only the local network; test it
  on a network you run.
- **No social engineering, phishing or physical attacks.**

Research in good faith that follows these rules is welcome: the maintainer will not take
legal action against it.

## How the project checks its own security

Self-tested; not an independent penetration test and not a certification.

- The MCP server's security model, why it takes no OAuth over stdio, and what a remote
  version would need: [`docs/MCP.md`](docs/MCP.md#security). Inspect its tools yourself
  with the MCP Inspector ([`scripts/mcp_capabilities.sh`](scripts/mcp_capabilities.sh)).
- The receiver's threats and mitigations:
  [`docs/KLARBEFUND.md`](docs/KLARBEFUND.md#security--privacy-model); the app's sandbox
  and sealing: [`docs/MAC.md`](docs/MAC.md).
- Tests in CI on every push ([`test.yml`](.github/workflows/test.yml)): the Python suite
  (the receiver refuses requests without the token, its certificate is a v3 server
  certificate), the Swift graph and receiver tests, and the Relate CLI installed with a
  checked signature.
- Klarbefund for iPhone and the hub: STRIDE threat models, a security test report and a
  BSI C5 gap analysis, at
  [ma3u.github.io/MinimumViableHealthDataspacev2/docs/security](https://ma3u.github.io/MinimumViableHealthDataspacev2/docs/security).
