## Inspiration

Our health data lives in a dozen places. Lab reports on paper, in a drawer. Heart rate, HRV and sleep on an Apple Watch. A cardiology work-up as five PDFs from three labs that spell their own name four different ways. Every app that offers to "connect" them wants the data in its cloud.

We wanted the opposite: **one connected picture of a person's health, on hardware they own**, where every number can be traced back to the line on the paper it came from, compared with what the guidelines say, and asked about in plain words, without giving the data away.

Relate, Neo4j's new embedded graph database, made that possible: a real graph database small enough to run inside an iPhone app and inside a Mac command-line tool, with the same Cypher on both.

## What it does

1. **Scan.** Klarbefund, our iPhone app, reads a paper lab report with the camera, codes every value with LOINC and UCUM, and keeps where it came from: the page, the line, whether it was read from a photo or from the lab's own file.
2. **A graph on the phone.** Inside the app, Relate turns the reports into a graph: values over time per test, values without a code, risk-relevant measures. Encrypted by iOS, never backed up, never sent anywhere.
3. **A copy on your own Mac.** Pairing is a QR code carrying a pinned certificate and a 256-bit token. The phone sends to that Mac only: over Wi-Fi with TLS, or **over a USB cable** when there is no shared network. On the Mac the same Relate library builds the same graph, inside an AES-256 encrypted disk image that is open only while in use.
4. **Knowledge in the graph.** Next to the values, the graph holds sourced medical knowledge: 173 reference ranges with the **official guideline range and the optimal band**, 6 health risks (cardiovascular, type 2 diabetes, kidney, liver, osteoporosis, fitness), 4 published risk scores (SCORE2, eGFR CKD-EPI 2021, FIB-4, TyG) and 55 links from measures to the risks guidelines name them as markers of. Score results are stored with links to the exact values they were calculated from.
5. **A dashboard.** Rings for each health domain and for the week's Apple Watch signals, traffic lights from published categories (green optimal, amber within the guideline but not optimal, red outside), lab trends, graph views of how the measures connect for each risk, and the metadata model drawn live from the graph.
6. **Ask.** Claude Desktop talks to the graph through Relate's MCP server, read-only, on a snapshot. It writes the Cypher, follows a score back to its inputs, and only the rows an answer needs leave the Mac.

## How we built it

- **One library, two platforms.** `HealthGraph` is a Swift package on Relate's `RelateFFI.xcframework`. The iPhone app and the Mac receiver use the same code, so a report becomes the same nodes everywhere.
- **A Python reference, a generated Swift port.** The graph model, the import and every named query were written in Python first. The Swift Cypher is *generated* from it, and a parity test fails if the two drift apart.
- **Standards all the way.** FHIR R4 bundles from the app, LOINC and UCUM codes, NCBI Taxonomy for gut bacteria, and an OMOP CDM v5.4 projection inside the graph.
- **The Mac side** is Swift with SwiftNIO and NIOSSL for the TLS receiver, swift-certificates for the X.509 identity, CryptoKit for the certificate pin, and a small client for Apple's usbmux protocol for the cable path.
- **The knowledge layer** comes from Klarbefund's own sourced reference table, exported with its LOINC codes and seeded idempotently into the graph; the risk scores are implemented from their papers and tested against the papers' own example results.
- **The demo video** is generated from a storyboard: HTML cards rendered by headless Chrome, narration in a cloned voice from ElevenLabs, and the Claude segment rendered from the real conversation transcript.
- Built with Claude Code as a pair programmer, from the first spike to this page.

## Challenges we ran into

- **A reader blocks the writer.** An open read-only Relate handle in another process made the receiver's writes fail with "storage locked" or a bare "internal error". Claude now reads a snapshot copy inside the vault, and the receiver retries.
- **Apple's TLS refused our certificates.** OpenSSL wrote the EC key with explicit curve parameters, and iOS rejected it before any pinning code ran. The receiver now makes named-curve, X.509 v3 certificates and checks them on start.
- **macOS keys Local Network permission to the code signature,** and `swift build` signs ad hoc, a new identity each build. The fix was signing the receiver with a stable developer identity.
- **No shared Wi-Fi.** On a hotspot, phone and Mac could not see each other, so we added a USB transfer: the Mac opens a TCP stream to the phone's loopback through usbmuxd, proves it is the paired Mac with the token, and only then does the phone send.
- **Demo data leaked into a real graph.** The Simulator, paired with the real receiver, exported fictional reports on the next demo launch. We deleted them and gave demo launches their own pairing keys, so it cannot happen again.
- **Real data is messy.** One report scanned twice, the same result printed on two documents, a microbiome report listing species twice, ApoB in g/L where the range was in mg/dL (our first dashboard showed it 100 times too small). The graph now counts each measurement once, links the copies with `SAME_AS` and converts units only where the conversion is exact.

## Accomplishments that we're proud of

- **The same Relate graph on an iPhone and a Mac**, from one Swift library, kept honest by a test suite: 43 Python tests, 28 for the Swift library and 16 for the Mac receiver.
- **It runs on real data.** 28 real lab reports and two years of Apple Watch weeks went through the whole chain: scan, phone graph, USB transfer, encrypted vault, dashboard and Claude.
- **Every number has its evidence.** A risk score points at the exact values it used, each value at its report and the line it was read from, each range at its guideline.
- **SCORE2 reproduces the paper.** Our implementation matches the four example risks the ESC publishes.
- **Nothing passes through a cloud on the way.** Pinned TLS or a cable, an encrypted vault, a read-only snapshot for the AI.
- **The AI found our mistakes.** Asked about the graph, Claude pointed out missing links and units; we fixed them and asked again.

## What we learned

- **A graph makes provenance natural.** "Which values was my SCORE2 calculated from, and where did each come from?" is one Cypher walk, not a join puzzle.
- **An LLM is a good auditor of your own data.** When Claude answered from the graph, it found gaps we had missed: risks without a marker link, a unit with no range, one lab under four spellings.
- **Privacy is a design, not a setting.** Every step had to answer "who can see this?": the phone, the cable, the vault, the snapshot, the rows Claude reads.
- **Embedded changes the architecture.** With the database inside the app, there is no server to secure, and the same query runs on the phone and the Mac.

## What's next for MyHealthCoach: My Local Health Graph, Not the Cloud's

- **Whoop** next to the Apple Watch: recovery, strain and sleep in the same graph.
- **Cleaner sources:** merging lab names spelled several ways, and ranges for every unit labs actually print (µkat/L for liver enzymes).
- **More of the year in one place:** blood pressure and VO₂ max norms with sources, so every ring has a published reference.
- **Sharing on your terms:** handing one report's subgraph to the European Health Data Space hub with `relate push`, only when you decide to.

*Klarbefund explains; it is not a medical device. The risk scores are published estimates for groups of people, shown with their sources, and are not a diagnosis.*
