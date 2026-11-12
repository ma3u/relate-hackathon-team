## Inspiration

Our health data lives in a dozen places: lab reports on paper, heart rate and sleep on an Apple Watch, PDFs from labs that spell their own name four ways. Every app that offers to connect them wants it in its cloud. We wanted one connected picture of our health **on hardware we own**, every number traceable to its source and compared with the guidelines. Relate, Neo4j's embedded graph database, made it possible: small enough for an iPhone app, the same Cypher on the Mac.

## What it does

1. **Scan:** our iPhone app Klarbefund reads a paper lab report, codes every value with LOINC and keeps where it came from.
2. **Graph on the phone:** Relate builds the graph inside the app. Encrypted, never backed up, never sent anywhere.
3. **Copy on your Mac:** paired by QR code (pinned certificate, secret token), over Wi-Fi or a **USB cable**, into an AES-256 encrypted vault.
4. **Knowledge in the graph:** 173 reference ranges (official and optimal), 6 health risks, 4 risk scores (SCORE2, eGFR, FIB-4, TyG), each score linked to the values it used.
5. **Dashboard:** rings per health domain, traffic lights, trends and graph views of how measures connect.
6. **Ask:** Claude Desktop queries the graph through Relate's MCP server, read-only; only the rows an answer needs leave the Mac.

## How we built it

One Swift library on Relate runs on iPhone and Mac. The model and queries were written in Python first; the Swift Cypher is generated from it and checked by a parity test. FHIR R4, LOINC, UCUM and OMOP throughout; SwiftNIO for the TLS receiver; Apple's usbmux protocol for the cable. Built with Claude Code; the video narrated in a cloned voice with ElevenLabs.

## Challenges we ran into

- An open Relate reader blocked the writer: Claude now reads a snapshot.
- iOS rejected our TLS certificates (explicit EC curve parameters) before any pinning ran.
- No shared Wi-Fi on a hotspot, so we built the USB path.
- Demo data leaked into a real graph once; demo launches now have their own pairing.
- Real data is messy: a report scanned twice, units in g/L vs mg/dL. Each measurement now counts once, and units convert only where exact.

## Accomplishments that we're proud of

- The same graph on iPhone and Mac, kept honest by 87 tests.
- Real data end to end: 28 lab reports and two years of Apple Watch weeks.
- Every score points at its evidence; SCORE2 matches the paper's published examples.
- No cloud on the way, and Claude found gaps in our graph that we then fixed.

## What we learned

A graph makes provenance natural: "which values was my score calculated from?" is one Cypher walk. An LLM is a good auditor of your own data. And privacy is a design, not a setting.

## What's next for MyHealthCoach: My Local Health Graph, Not the Cloud's

Whoop data, merged lab names, ranges for every unit labs print, and sharing a report with the European Health Data Space only when you decide.

*Not a medical device: the scores are published estimates, not a diagnosis.*
