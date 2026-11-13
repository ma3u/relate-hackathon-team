## Inspiration

Our lab reports sit on paper, our heart data on an Apple Watch, and every app that connects them wants our data in its cloud. We wanted one health graph on hardware we own.

## What it does

Klarbefund scans a paper lab report on the iPhone and codes every value with LOINC. Relate builds a graph on the phone and, over Wi-Fi, the same graph in Klarbefund for Mac, sealed with AES-256 whenever the app is closed (developers can use a USB cable and an encrypted vault from the command line). There it adds official and optimal ranges, risk scores with their evidence, a dashboard, and answers from Claude through Relate's MCP server.

## How we built it

One Swift library on Relate for iPhone and Mac, generated from a tested Python reference. FHIR, LOINC and OMOP throughout; pinned TLS, a Mac app that seals the graph with AES-256, and a USB path for developers.

## Challenges we ran into

A reader that blocked the writer, iOS rejecting our certificates, no shared Wi-Fi, and messy real data: reports scanned twice, units in g/L vs mg/dL.

## Accomplishments that we're proud of

The same graph on phone and Mac, 87 tests, real data end to end, and every score pointing at the values it came from.

## What we learned

A graph makes provenance natural, and an LLM is a good auditor of your own data.

## What's next for MyHealthCoach: My Local Health Graph, Not the Cloud's

Whoop data, cleaner lab names, and sharing a report with the EU health data space only when you decide.

*Not a medical device: the scores are estimates, not a diagnosis.*
