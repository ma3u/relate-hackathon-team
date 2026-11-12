# Claude Desktop demo: questions to ask the health graph

For the demo video: Claude Desktop with the `klarbefund-health` MCP server
(read-only, a snapshot of the graph in the encrypted vault; see
[KLARBEFUND.md](../KLARBEFUND.md#claude-desktop-step-by-step)). Each question
makes Claude write Cypher against Relate, so the answers walk the graph:
values, their sources, the reference ranges and the risk knowledge.

## Before recording

1. Quit Claude Desktop (⌘Q) and open it again, so the server starts with a
   fresh snapshot (it includes the knowledge layer and the stored scores).
2. New chat. Check the tools menu lists **klarbefund-health**.
3. Start the screen recording: ⌘⇧5 → *Record Selected Portion* → the Claude
   window → *Record*. Stop with the ⏹ in the menu bar.
4. Allow each tool call when Claude asks ("Allow for this chat").

## The questions (paste one at a time, wait for the answer)

1. **What is in it?**
   > Using klarbefund-health: what is in my health graph? Count the kinds of data, the sources and the time span.

2. **Scores with their evidence**
   > What risk scores are stored for me? For each one, show the lab values it was calculated from, with their dates.

3. **Official vs optimal**
   > Which of my latest lab values are outside the official guideline range, and which are inside it but not optimal? Use the ReferenceRange nodes, and name the health risk each one is a marker of.

4. **Wearables meet the lab** (optional, if there is time)
   > How did my resting heart rate and HRV develop over the last year, and how do they line up with my lab report dates?

Claude's answers are estimates and explanations, not medical advice; the
closing line of the video says so.
