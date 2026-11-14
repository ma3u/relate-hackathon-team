import Foundation

/// What the Klarbefund MCP server offers Claude, in one place: the prompts (the
/// use cases a person picks from Claude's prompt menu), the guides (MCP
/// resources Claude can read), and the rules every answer follows. The server
/// (klarbefund-mcp) serves this list; Klarbefund for Mac shows the same list.
///
/// No health data here: these are instructions and texts, the same for everyone.
enum MCPCatalog {
  static let serverName = "klarbefund-health"
  static let serverTitle = "Klarbefund Health Graph"

  /// The MCP revisions the server speaks. 2026-07-28 is stateless (server/discover,
  /// the version in each request's _meta); the older ones start with initialize.
  static let modernVersions = ["2026-07-28"]
  static let legacyVersions = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]

  // ── prompts ──────────────────────────────────────────────────────────────

  struct Argument {
    let name: String
    let description: String
    let required: Bool
    /// How a given value enters the text: "%@" is replaced by the value.
    let phrase: String
    /// The text used when the argument is left out.
    let fallback: String
  }

  enum Group: String, CaseIterable {
    case risks = "Risks and what to improve"
    case values = "Values and trends"
    case doctor = "Doctor's visit"
    case habits = "Habits and Apple Watch"
    case evidence = "The graph and the evidence"
    case setup = "Setup and privacy"
  }

  struct Prompt {
    let name: String
    let title: String
    let description: String
    let group: Group
    let arguments: [Argument]
    /// The request, with {{argument}} where an argument's phrase goes.
    let template: String
    /// What a person would type to ask for it.
    var ask: String { title }
  }

  /// The rules appended to every prompt. The server's instructions say the same.
  static let rules = """
    How to answer (Klarbefund's rules):
    - Use the klarbefund-health tools: get_schema first, then read_cypher. Count a value seen in two \
    reports once (o.duplicateOf IS NULL).
    - Time matters. Give the date and the age of every value you quote. Weigh newer values more: a value \
    from the last 12 months describes now; an older one describes the past and needs a recheck before it \
    carries weight. Where a marker has values under two LOINC codes (two units), use the newest.
    - Compare a value with the guideline range in the same unit that applied on its date, and name the \
    source and its year. Be critical of older statements: when a range or claim rests on a source more \
    than ten years old, or on one a newer edition replaced, say so and give the newer view.
    - Use the newer, more informative markers where the evidence supports them, next to the classic \
    ones: ApoB and non-HDL cholesterol beside LDL cholesterol; the triglyceride/HDL ratio, the atherogenic \
    index of plasma and remnant cholesterol as signs of insulin resistance and triglyceride-rich particles; \
    Lp(a) once in life. LDL cholesterol stays a cause of atherosclerosis; the newer markers add to it, \
    they do not replace it.
    - Before you judge a risk, ask what the graph cannot know, and only that: anamnesis_plan lists the \
    findings in my data, what the graph already answers, and the questions left. Never ask what my data \
    shows (a 24-hour blood pressure, Apple Watch activity, a weight series) or what I answered in the last \
    year. Store answers only with save_anamnesis_answers, after I confirmed them.
    - Say what is missing or too old to judge, and which test would close the gap.
    - Not medical advice and not a diagnosis: help me understand my data and prepare questions for my \
    doctor. Anything urgent (chest pain, shortness of breath, fainting, signs of a stroke) belongs with a \
    doctor or emergency service now.
    - Answer in the language I write in.
    """

  static let prompts: [Prompt] = [
    // Risks and what to improve
    Prompt(
      name: "my_risks", title: "Where are my risks?",
      description: "The six health risks the graph tracks, ranked by your recent values, with the main driver and the gaps.",
      group: .risks, arguments: [],
      template: """
        Where are my health risks? Go through the six health risks in my graph (HealthRisk nodes: \
        conditions the knowledge layer tracks for everyone, not diagnoses). For each: my newest value on \
        each of its markers with date and age, whether it is inside the guideline range valid on that \
        date, and the scores that apply (SCORE2, eGFR, FIB-4, TyG). Rank the risks by how much recent \
        evidence lies outside the range, a value counting half after one year. Name my main risk, what \
        drives it and which newer markers support or weaken that, what is missing or too old to judge, \
        and which habits would change the picture. Ask me about those habits first.
        """),
    Prompt(
      name: "what_to_improve", title: "What should I improve first?",
      description: "The three changes with the largest expected benefit, with targets and when to measure again.",
      group: .risks,
      arguments: [Argument(name: "focus", description: "Optional: one area, e.g. cholesterol, blood sugar, fitness",
                           required: false, phrase: " Focus on %@.", fallback: "")],
      template: """
        What should I improve first?{{focus}} From my health graph, pick the three changes with the \
        largest expected benefit for me, from my newest values and the evidence in the graph (Study and \
        guideline nodes, with year and effect size). For each: the values behind it with dates, a realistic \
        target and the guideline that sets it, what usually moves it (diet, activity, sleep, alcohol, \
        smoking, weight, or a medication to discuss with my doctor), and when to measure again. Ask me \
        about my habits before you rank, and say plainly what the evidence does not show.
        """),
    Prompt(
      name: "tired_what_to_measure", title: "I always feel tired: what should I measure?",
      description: "The lab values that can explain tiredness, which you have, and which are missing or old.",
      group: .risks,
      arguments: [Argument(name: "since", description: "Optional: how long, e.g. 3 months",
                           required: false, phrase: " It has been like this for %@.", fallback: "")],
      template: """
        I always feel tired.{{since}} Which lab values could explain tiredness, and which of them are \
        missing in my graph or older than 12 months? Check at least haemoglobin and MCV, ferritin and \
        transferrin saturation, TSH, vitamin B12 and folate, HbA1c and fasting glucose, creatinine and \
        eGFR, sodium, potassium and calcium, ALT and GGT, CRP, and vitamin D (with the caveat on its \
        evidence), and my Apple Watch weeks (sleep, resting heart rate, HRV, steps) if I have them. Make a \
        table: marker, my newest value and date, range and source, verdict (fine, outside, missing, too \
        old). Turn the gaps into a short lab request I can take to my doctor. Ask me about sleep and \
        snoring, mood, stress, alcohol, diet, medication and, if it applies, menstruation. Name the \
        warning signs that need a doctor soon: weight loss, fever, night sweats, breathlessness, chest \
        pain, blood loss.
        """),
    Prompt(
      name: "heart_risk_score", title: "My 10-year heart risk (SCORE2)",
      description: "SCORE2 from your graph and your smoking status, with the inputs, the category and what moves it.",
      group: .risks, arguments: [],
      template: """
        Estimate my 10-year risk of heart attack and stroke with SCORE2 (ESC 2021): age from my year of \
        birth, sex, my newest systolic blood pressure, total and HDL cholesterol (from one report if \
        possible) and smoking (ask me). Germany is a moderate-risk region. Show the inputs with dates, the \
        result and the ESC 2021 category for my age, then how it changes if each input reached its target. \
        Say what SCORE2 leaves out: LDL and ApoB, Lp(a), family history, kidney function, and diabetes \
        (SCORE2-Diabetes). SCORE2 is for ages 40 to 69 without known heart disease or diabetes; say so if \
        it does not apply to me. A stored result may already be in the graph: \
        (:Patient)-[:HAS_SCORE]->(:ScoreResult)-[:OF]->(:RiskScore).
        """),
    Prompt(
      name: "lipids_newer_markers", title: "My cholesterol, with the newer markers",
      description: "LDL next to ApoB, non-HDL, the TG/HDL ratio, AIP, remnant cholesterol and Lp(a), over time.",
      group: .risks, arguments: [],
      template: """
        Analyse my blood lipids over time. Newest LDL, HDL and total cholesterol, triglycerides, non-HDL \
        cholesterol, ApoB and Lp(a), with dates. From values of one and the same day compute: non-HDL \
        (total minus HDL), the triglyceride/HDL ratio (3.0 in mg/dL units, 1.3 in mmol/L units, marked \
        insulin resistance in overweight adults in McLaughlin 2003; the paper's SI figure of 1.8 does not \
        convert to 3.0, so use the stricter one), the atherogenic index of plasma, log10 of TG/HDL in \
        mmol/L (0.11 and 0.21 are common cut-offs, not guideline ones), and remnant cholesterol, total \
        minus LDL minus HDL (EAS/EFLM 2016 flags 0.9 mmol/L non-fasting). Say whether ApoB and LDL agree \
        or diverge, what the 2025 ESC/EAS focused update says about Lp(a), and that LDL stays causal \
        (EAS consensus 2017) while ApoB counts the particles. Ask me whether the samples were fasting.
        """),
    Prompt(
      name: "insulin_resistance", title: "Early signs of insulin resistance",
      description: "HbA1c, fasting glucose, TyG, TG/HDL, liver values, waist and activity, before diabetes shows.",
      group: .risks, arguments: [],
      template: """
        Look for early signs of insulin resistance, before diabetes would show: HbA1c and fasting glucose \
        over time (ADA ranges), the TyG index (ln of triglycerides in mg/dL times glucose in mg/dL over 2, \
        only from a fasting sample of one day), the triglyceride/HDL ratio, ALT and GGT, waist, BMI, \
        blood pressure and Apple Watch activity. Explain what each adds, which are missing (fasting \
        insulin is rarely on a panel), and how sure one can be. Ask me whether the samples were fasting, \
        and about diet, alcohol, sleep and activity.
        """),
    Prompt(
      name: "kidney_check", title: "My kidneys over time",
      description: "eGFR (CKD-EPI 2021) and its trend, the KDIGO category, and whether urine albumin is missing.",
      group: .risks, arguments: [],
      template: """
        How are my kidneys doing over time? eGFR from creatinine with CKD-EPI 2021 (race-free) and the \
        lab's own eGFR, the change per year, the KDIGO G category (KDIGO 2024 kept the 2012 categories), and \
        the urine albumin-to-creatinine \
        ratio (KDIGO needs both; say if it is missing). Add blood pressure and HbA1c, which drive kidney \
        risk. Remember: one eGFR between 60 and 89 without albumin in the urine is not chronic kidney \
        disease; CKD needs a finding that lasts three months. Mention cystatin C if creatinine may mislead \
        (much muscle, little muscle, creatine supplements).
        """),
    Prompt(
      name: "liver_check", title: "My liver",
      description: "ALT, AST, GGT, platelets and FIB-4 with the EASL cut-offs, and what alcohol and weight do.",
      group: .risks, arguments: [],
      template: """
        Check my liver values over time: ALT, AST, GGT, platelets, and FIB-4 from age, AST, ALT and \
        platelets of one day (EASL cut-offs 1.30 and 2.67; 2.0 from age 65). Relate them to \
        triglycerides, waist and BMI (fatty liver, MASLD, EASL-EASD-EASO 2024), and to the risks fatty \
        liver raises in the graph. Ask me about alcohol, medication and supplements before you judge.
        """),
    Prompt(
      name: "bone_check", title: "My bones and vitamin D",
      description: "What the graph knows about bone health, and why one old vitamin D value says little.",
      group: .risks, arguments: [],
      template: """
        What does my graph say about bone health? Vitamin D, calcium, phosphate, PTH and alkaline \
        phosphatase if present, with dates; the risks that raise osteoporosis in the graph and whether \
        any applies to me. Be critical about vitamin D: the 30 ng/mL range comes from the Endocrine Society \
        2011 guideline; its 2024 guideline sets no target level and advises against routine testing in \
        healthy adults under 75. Ask me about age at menopause if it applies, fractures, family history, \
        smoking, alcohol, activity and corticosteroids, which matter more than one value.
        """),

    // Values and trends
    Prompt(
      name: "out_of_range", title: "Which values need attention?",
      description: "Your newest values outside the guideline range, or inside it but not optimal, with sources.",
      group: .values, arguments: [],
      template: """
        Which of my newest lab values are outside the guideline range valid on their date, and which are \
        inside it but not optimal? Use the ReferenceRange nodes, name the health risk each value is a \
        marker of and the source with its year. Put values older than 12 months in a separate list: they \
        need a recheck before they count.
        """),
    Prompt(
      name: "marker_trend", title: "How has a value changed?",
      description: "Every value of one marker over time, the range on each date, and the change per year.",
      group: .values,
      arguments: [Argument(name: "marker", description: "The marker, e.g. LDL, HbA1c, ferritin, or a LOINC code",
                           required: true, phrase: "%@", fallback: "the marker I name")],
      template: """
        Show how my {{marker}} changed over time: every value with date, lab and unit (convert units \
        only where the conversion is exact), the range valid on each date, the change per year, and \
        whether the newest change is larger than this test's usual variation. Mark values older than \
        12 months as history.
        """),
    Prompt(
      name: "explain_value", title: "Explain one value",
      description: "What a marker measures, your values, its range and source, the risks it marks and what moves it.",
      group: .values,
      arguments: [Argument(name: "marker", description: "The marker, e.g. ApoB, GGT, TSH",
                           required: true, phrase: "%@", fallback: "the marker I name")],
      template: """
        Explain {{marker}} in plain language: what it measures and why labs test it, my values newest \
        first with dates, the guideline range with its source and edition, the health risks it is a \
        marker of in my graph, the studies that examine it, and what moves it. Keep it to one screen.
        """),
    Prompt(
      name: "report_summary", title: "Summarise a lab report",
      description: "One report in plain language: what was measured, what stands out, what changed since the last one.",
      group: .values,
      arguments: [Argument(name: "date", description: "Optional: the report's date (YYYY-MM-DD); default the newest",
                           required: false, phrase: "the report of %@", fallback: "my newest lab report")],
      template: """
        Summarise {{date}} in plain language: who issued it and when, what was measured, which values \
        are outside the range, and what changed against the report before it. Cite the page and line \
        (Observation.sourceLine) for every value, so I can check it on the paper.
        """),
    Prompt(
      name: "next_lab_panel", title: "What should my next lab test include?",
      description: "The markers your graph lacks or has only old values of, ordered by what they would change.",
      group: .values, arguments: [],
      template: """
        Plan my next blood test from what my graph has and lacks. For each of the six health risks: the \
        markers guidelines name, my newest date for each, and which are missing or older than 12 \
        months (Lp(a) once in a lifetime is enough; ApoB and the urine albumin-to-creatinine ratio are \
        often missing). Give a short list ordered by what it would change, with the guideline for each, \
        and say which need a fasting sample.
        """),

    // Doctor's visit
    Prompt(
      name: "anamnesis", title: "Anamnesis from my data, for my family doctor",
      description: "Questions only about what stands out in your own values, your answers stored in the graph, "
        + "and a brief that helps your family doctor weigh your risks.",
      group: .doctor,
      arguments: [
        Argument(name: "language", description: "Optional: the brief's language, e.g. German",
                 required: false, phrase: " Write the brief in %@.", fallback: "")
      ],
      template: """
        Take my anamnesis from my own data, so my family doctor can weigh my risks better. \
        1. Call anamnesis_plan. \
        2. Show me briefly what stands out: each finding with its values, dates, units, the range and its \
        source, and in one sentence why it matters (the finding's why). Then what my data already answers \
        (known), what I answered before (skipped, with the date), and the values too old to judge (rechecks), \
        so I can see you will not ask about them. \
        3. Ask only the plan's questions, two to four at a time, grouped by the finding that raises them, with \
        the options as given; take my own words where no option fits. Ask nothing my data already answers; \
        if a question can be answered from the graph after all, check with read_cypher instead of asking. \
        4. Read my answers back in a short list. When I confirm, store them with save_anamnesis_answers: the \
        plan's key, the option codes, my own words as text, and the plan's basedOn and findings. \
        5. Write a one-page brief for my family doctor.{{language}} Per finding: the values with date, lab, \
        unit, range and source; my answers that change how to read it (for example hard exercise before \
        the sample for NT-proBNP or creatinine, smoking in SCORE2); the tests the plan suggests. Then the \
        risk scores in the graph with their inputs, the rechecks, and three questions for the appointment. \
        Factual and short, no diagnosis, every number as in the graph so it can be checked on the paper.
        """),
    Prompt(
      name: "doctor_brief", title: "Write a doctor's brief",
      description: "One page to hand over: reason, values outside the range, trends, scores, gaps, questions.",
      group: .doctor,
      arguments: [
        Argument(name: "reason", description: "Optional: why you go, e.g. check-up, always tired",
                 required: false, phrase: " The reason for the visit: %@.", fallback: ""),
        Argument(name: "language", description: "Optional: the brief's language, e.g. German",
                 required: false, phrase: " Write the brief in %@.", fallback: ""),
      ],
      template: """
        Write a one-page brief for my doctor from my health graph, to hand over at the start of the \
        appointment.{{reason}}{{language}} Sections: reason for the visit; values outside the guideline \
        range, newest first, with date, lab, unit, range and source; trends with their dates; risk \
        scores with their inputs; what is missing or old; my habits and medication (ask me, do not \
        guess); three questions for the doctor. Factual and short, no diagnosis, every number exactly as \
        in the graph so it can be checked on the paper reports.
        """),
    Prompt(
      name: "doctor_visit", title: "Prepare my doctor's visit",
      description: "The four most important topics for a short appointment, with trends, questions and sources.",
      group: .doctor, arguments: [],
      template: """
        Prepare my next doctor's visit from my health graph: the four most important topics for a \
        six-minute appointment, the trends behind each (with dates), one question per topic, and the \
        guideline sources.
        """),

    // Habits and Apple Watch
    Prompt(
      name: "habits_interview", title: "Ask me about my habits",
      description: "A short interview about what the graph cannot know, and how the answers change the picture.",
      group: .habits, arguments: [],
      template: """
        Interview me, one short question at a time, about what my graph cannot know: smoking (never, \
        former since when, current and how much), alcohol (drinks per week), diet (pattern, sugary drinks, \
        processed food), fasting (intermittent fasting, and whether my blood samples were taken fasting), \
        physical activity (minutes per week, strength training), sleep (hours, snoring), stress, family \
        history (early heart attack or stroke, diabetes), medication and supplements. Then summarise how \
        my answers change the reading of my values and risk scores, with the evidence.
        """),
    Prompt(
      name: "apple_watch", title: "My Apple Watch weeks",
      description: "Resting heart rate, HRV, VO2 max, steps and sleep over time, and the risks they mark.",
      group: .habits, arguments: [],
      template: """
        Summarise my Apple Watch weekly means (Observation.sourceKind = 'device-weekly-mean'): resting \
        heart rate, heart rate variability, VO2 max, steps and sleep, as available. Compare the last 12 \
        months with before, link each to the health risks it marks, and cite the studies in the graph \
        (for example Kodama 2009 on fitness, Paluch 2022 on steps). Watch estimates are not lab \
        measurements; say how far to trust each.
        """),

    // The graph and the evidence
    Prompt(
      name: "whats_in_my_graph", title: "What is in my health graph?",
      description: "The kinds of data, their sources and time span, and three good next questions.",
      group: .evidence, arguments: [],
      template: """
        What is in my health graph? Count the kinds of data, their sources and the time span (oldest and \
        newest date per kind), say which markers were measured often and which only once or long ago, \
        and suggest three questions I could ask next.
        """),
    Prompt(
      name: "graph_guide", title: "Help me read my health graph",
      description: "The layers of the graph, how they connect, three paths that matter for you, with the queries.",
      group: .evidence,
      arguments: [Argument(name: "question", description: "Optional: a question to answer with a query",
                           required: false, phrase: " Then answer this with a query: %@", fallback: "")],
      template: """
        Explain my health graph as a map, like Klarbefund's 3D view: the layers (me, reports, values, \
        LOINC codes, reference ranges, the knowledge layer of health risks, scores, studies and \
        guidelines, the OMOP research copy), how they connect, and three paths that matter for me, for \
        example a value to its code to the risk it marks to the study behind it. Use get_schema and small \
        read_cypher queries, show the queries so I can learn them, and say what the colours and the depth \
        mean in the 3D view (older values sit further back and smaller).{{question}}
        """),
    Prompt(
      name: "old_evidence", title: "Which of my ranges rest on older evidence?",
      description: "Ranges and claims from superseded or older sources, the newer view, and what changes for you.",
      group: .evidence, arguments: [],
      template: """
        Find where my graph's judgements rest on older or superseded evidence: ReferenceRange nodes with \
        validUntil or supersededBy, sources older than ten years, and markers whose guideline has a newer \
        edition (for example vitamin D: the Endocrine Society 2011 range of 30 ng/mL against its 2024 \
        guideline). For each: my value, the old view, the newer view with its source, and what changes \
        for me. Also say where an older statement still holds.
        """),
    Prompt(
      name: "research_copy", title: "What would a study see?",
      description: "Your OMOP research copy: what a study under the EHDS would receive instead of your reports.",
      group: .evidence, arguments: [],
      template: """
        Show me my OMOP research copy (OMOPPerson, OMOPMeasurement): what a research study under the \
        European Health Data Space would receive instead of my reports, what is left out (name, \
        documents, page and line), and three example rows. Explain in two sentences what a data permit \
        and pseudonymisation mean for me.
        """),

    // Setup and privacy
    Prompt(
      name: "setup_guide", title: "Install and connect Klarbefund",
      description: "iPhone, Mac and Claude, step by step, with checks and troubleshooting.",
      group: .setup, arguments: [],
      template: """
        Walk me through setting up Klarbefund, one step at a time, and check each step with me: \
        Klarbefund on the iPhone and Klarbefund for Mac (TestFlight), reports scanned or imported on the \
        iPhone, the iPhone paired with the Mac, Claude Desktop connected, and a first test with \
        get_schema. Read the guides klarbefund://guide/install and klarbefund://guide/pairing. If a step \
        fails, ask what I see and use their troubleshooting sections.
        """),
    Prompt(
      name: "privacy_check", title: "What leaves my Mac?",
      description: "Where your data is, what Claude can read, what reaches the conversation, and how it is protected.",
      group: .setup, arguments: [],
      template: """
        Explain where my health data is and what leaves my Mac when I use you with Klarbefund: read the \
        guide klarbefund://guide/security. Cover where the graph lives and how it is sealed, what this \
        server can and cannot do, which MCP transport and protocol it uses and why it needs no OAuth, and \
        which rows reach this conversation. End with three settings or habits that keep it private.
        """),
  ]

  /// The request a prompt sends, with its arguments filled in and the rules appended.
  static func render(_ prompt: Prompt, arguments: [String: String]) -> String {
    var text = prompt.template
    for a in prompt.arguments {
      let value = arguments[a.name]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      let piece = value.isEmpty ? a.fallback : a.phrase.replacingOccurrences(of: "%@", with: value)
      text = text.replacingOccurrences(of: "{{\(a.name)}}", with: piece)
    }
    return text + "\n\n" + rules
  }

  // ── guides (MCP resources) ───────────────────────────────────────────────

  struct Guide {
    let uri: String
    let name: String
    let title: String
    let description: String
    let text: String
  }

  static var guides: [Guide] {
    [
      Guide(
        uri: "klarbefund://guide/start", name: "start", title: "Start here",
        description: "What this server is, what it can read, and how to ask.",
        text: """
          # Klarbefund Health Graph: start here

          This MCP server lets Claude read your health graph, the one Klarbefund for Mac keeps on your Mac: \
          lab values scanned from paper reports on your iPhone, Apple Watch weekly means, and a knowledge \
          layer of health risks, scores, reference ranges, studies and guidelines. Read-only, on your Mac, \
          only while Klarbefund for Mac is open.

          ## How to ask
          - Pick a prompt from Claude's prompt menu (the + button, then Klarbefund Health Graph), or just ask.
          - Start with "What is in my health graph?", then "Where are my risks?".
          - The guides: klarbefund://guide/install, klarbefund://guide/pairing, klarbefund://guide/usage, \
          klarbefund://guide/graph, klarbefund://guide/evidence, klarbefund://guide/security, \
          klarbefund://guide/use-cases.

          Not medical advice: Klarbefund helps you understand your data and prepare questions for your doctor.
          """),
      Guide(
        uri: "klarbefund://guide/install", name: "install", title: "Install Klarbefund and connect Claude",
        description: "The apps, the order, the Connect button, and the manual setup.",
        text: """
          # Install Klarbefund and connect Claude

          1. iPhone: install Klarbefund from the TestFlight invitation. Scan a paper lab report or import a \
          PDF; allow Apple Health if you want your Apple Watch weeks in the graph.
          2. Mac: install Klarbefund for Mac from the same TestFlight invitation (one app record for iPhone \
          and Mac). Open it: it shows a pairing QR code.
          3. Pair: see klarbefund://guide/pairing.
          4. Claude: install Claude Desktop (claude.ai/download). In Klarbefund for Mac, step 3, click \
          "Connect Claude Desktop". Klarbefund builds a Claude Desktop extension (.mcpb) around its MCP \
          helper and hands it to Claude, which asks you to install it.
          5. Test: ask Claude "What is in my health graph?". Claude calls get_schema and shows the counts.

          ## Manual setup
          Claude Desktop, Settings, Developer, Edit Config, then add under "mcpServers" an entry \
          "klarbefund-health" whose "command" is the helper inside the app: \
          /Applications/Klarbefund.app/Contents/Helpers/klarbefund-mcp (Klarbefund for Mac shows the exact path).

          ## Troubleshooting
          - "the health graph is sealed": open Klarbefund for Mac. Claude can read the graph only while it is open.
          - The graph is empty: pair the iPhone and tap "Send everything now".
          - Claude does not list Klarbefund: restart Claude Desktop, then check Settings, Extensions.
          """),
      Guide(
        uri: "klarbefund://guide/pairing", name: "pairing", title: "Pair your iPhone with your Mac",
        description: "Export to my Mac (Relate): the QR code, the Wi-Fi, the pinned connection.",
        text: """
          # Pair your iPhone with your Mac

          1. Open Klarbefund for Mac. Step 1 shows a QR code and this Mac's address.
          2. On the iPhone: Klarbefund, More (the … button), Export to my Mac (Relate).
          3. Scan the QR code, then tap "Send everything now". The Mac shows "Data received".

          iPhone and Mac need the same Wi-Fi. The QR code carries the Mac's address, a pairing token and \
          the fingerprint of the Mac's certificate: the iPhone talks only to this Mac, over TLS pinned to \
          that fingerprint. Nothing passes through a cloud.

          ## Troubleshooting
          - Nothing arrives: both devices on the same Wi-Fi (not a guest network), and allow "Local \
          Network" for Klarbefund on the iPhone (Settings, Privacy and Security, Local Network).
          - A new Mac or a reinstalled app: scan the new QR code; the old pairing no longer matches.
          - A firewall: allow incoming connections for Klarbefund in macOS Settings, Network, Firewall.
          """),
      Guide(
        uri: "klarbefund://guide/usage", name: "usage", title: "Ask good questions",
        description: "The prompts, how to phrase your own questions, and useful queries.",
        text: """
          # Ask good questions

          The prompts in Claude's menu cover the common questions; each carries Klarbefund's rules (dates, \
          newer evidence, your habits, not medical advice). The full list: klarbefund://guide/use-cases.

          Your own questions work best when they name a marker, a time span or a goal: "How has my LDL \
          changed since 2024?", "Which values should I recheck before my check-up?", "What could explain \
          my tiredness?".

          ## Useful queries
          - Newest value per marker: MATCH (o:Observation)-[:CODED_BY]->(c:LoincCode) WHERE o.duplicateOf \
          IS NULL RETURN c.code, o.display, o.valueQuantity, o.unit, o.effectiveDate ORDER BY o.effectiveDate DESC
          - Markers of a risk: MATCH (c:LoincCode)-[:MARKER_OF]->(r:HealthRisk {id: 'cardiovascular'}) RETURN c.code
          - Evidence for a marker: MATCH (c:LoincCode {code: '1884-6'})<-[:EXAMINES]-(s:Study) RETURN s.citation, s.year
          """),
      Guide(
        uri: "klarbefund://guide/graph", name: "graph", title: "The health graph and the 3D view",
        description: "The layers of the graph, how they connect, and how to read the 3D view.",
        text: """
          # The health graph and the 3D view

          Layers:
          - You: (:Patient), with year of birth and sex if you shared them.
          - Reports and values: (:Patient)-[:HAS_DIAGNOSTIC_REPORT]->(:DiagnosticReport)-[:HAS_RESULT]->(:Observation); \
          Apple Watch weekly means hang on you directly (sourceKind 'device-weekly-mean').
          - Codes and ranges: (:Observation)-[:CODED_BY]->(:LoincCode)<-[:APPLIES_TO]-(:ReferenceRange), \
          each range with its source, edition (validFrom, validUntil, supersededBy) and unit.
          - Knowledge: (:LoincCode)-[:MARKER_OF]->(:HealthRisk); (:RiskScore)-[:ESTIMATES]->(:HealthRisk); \
          (:HealthRisk)-[:RAISES_RISK_OF]->(:HealthRisk) from studies; (:Study)-[:EXAMINES|ABOUT|INFORMS|CITES]->(...).
          - Research copy: (:OMOPPerson), (:OMOPMeasurement).

          A HealthRisk is a condition the knowledge layer tracks for everyone, not a diagnosis: nothing \
          links you to one. Your values on its markers say where you stand.

          ## The 3D view
          Step 1 shows the health risks with your standing: the risks your recent values point to are \
          large and bright, the others small and dim, and the panel on the right ranks them. Older values \
          sit further back and are smaller: a value counts half after one year. Red: outside the range. \
          Orange arrows: in studies, people who have one condition develop another more often.
          """),
      Guide(
        uri: "klarbefund://guide/evidence", name: "evidence", title: "How Klarbefund weighs evidence",
        description: "Recency, guideline editions, older statements, and the newer markers.",
        text: """
          # How Klarbefund weighs evidence

          - Recency: a value counts half after one year, a quarter after two. A display rule, not a \
          clinical one: an old value describes the past and needs a recheck.
          - Editions: a reference range applies from its validFrom to its validUntil; a range a newer \
          edition replaced is labelled so, with supersededBy.
          - Older statements: a source more than ten years old is named as such, with the newer view. \
          Example: the Endocrine Society 2011 vitamin D range of 30 ng/mL; its 2024 guideline (Demay et al.) \
          sets no target level and advises against routine testing in healthy adults under 75.
          - Lipids: LDL cholesterol causes atherosclerosis (EAS consensus 2017, Ference et al.). ApoB \
          counts the atherogenic particles and is the better single measure when triglycerides are high \
          (Sniderman et al. 2019; ESC/EAS 2019 and the 2025 focused update). The triglyceride/HDL ratio \
          and the atherogenic index of plasma point to insulin resistance (McLaughlin et al. 2003; \
          meta-analysis Assempoor et al. 2025); remnant cholesterol (total minus LDL minus HDL) to \
          triglyceride-rich particles (Balling et al. 2025). They add to LDL; none replaces it. HDL \
          cholesterol is not protective by itself (Voight et al. 2012).
          - Lipids need no fasting sample (EAS/EFLM 2016), but the TyG index needs a fasting glucose.
          - Observational studies show associations, not causes. Risk links between conditions describe \
          people who have the condition, not you.
          """),
      Guide(
        uri: "klarbefund://guide/security", name: "security", title: "Security and privacy",
        description: "Where the data is, what this server can do, the MCP transport, and why there is no OAuth.",
        text: """
          # Security and privacy

          ## Where your data is
          - The graph is one Neo4j Relate file inside Klarbefund for Mac's sandbox, sealed with AES-256 \
          while the app is closed; the key stays in the Mac's keychain.
          - While the app is open it keeps a read-only snapshot in its app-group container for this \
          server. Closing the app deletes the snapshot.

          ## What this server can do
          - It runs on your Mac as a child process of Claude Desktop and talks to it over stdio (standard \
          input and output). It opens no network port and, sandboxed without the network entitlement, \
          cannot reach the network.
          - It opens the snapshot read-only and rejects queries that would write. It can only answer \
          what Claude asks.
          - One exception, for the anamnesis: save_anamnesis_answers checks the answers you confirmed and \
          leaves them in a folder only Klarbefund for Mac reads (the app-group container's Inbox). The app, \
          which owns your graph, stores them and deletes the request; it refuses an answer that is not one of \
          the question's options. Nothing else can be written this way.
          - Claude Desktop asks before a tool runs, unless you allowed it.

          ## Protocol and authorization
          - MCP over stdio, JSON-RPC 2.0, one message per line. Revisions: 2026-07-28 (stateless: \
          server/discover, the version in each request's _meta), and 2025-11-25, 2025-06-18, 2025-03-26 \
          and 2024-11-05 through initialize.
          - OAuth 2.1 is MCP's authorization for HTTP transports. For stdio the specification says \
          implementations should not use it and should take credentials from the environment. This server \
          needs none: the operating system decides who can start it and which files it can read.
          - If Klarbefund ever offers a remote server (for claude.ai or the iPhone), it would use \
          Streamable HTTP with OAuth 2.1: PKCE, protected resource metadata (RFC 9728), resource \
          indicators (RFC 8707) and issuer validation (RFC 9207).

          ## What reaches the conversation
          The rows Claude asks for go into your Claude conversation, as anything you type does, and are \
          handled under your Claude account's privacy settings. Ask for counts and summaries when you \
          do not need the values.
          """),
      Guide(
        uri: "klarbefund://guide/use-cases", name: "use-cases", title: "What you can ask: the prompts",
        description: "Every prompt this server offers, grouped, with what it does.",
        text: useCasesMarkdown),
    ]
  }

  static var useCasesMarkdown: String {
    var lines = ["# What you can ask", "",
                 "Each prompt is in Claude's prompt menu (+, Klarbefund Health Graph). \(prompts.count) prompts:"]
    for g in Group.allCases {
      let ps = prompts.filter { $0.group == g }
      if ps.isEmpty { continue }
      lines += ["", "## \(g.rawValue)"]
      for p in ps {
        let args = p.arguments.map { $0.required ? $0.name : "\($0.name) (optional)" }
        lines.append("- **\(p.title)** (`\(p.name)`\(args.isEmpty ? "" : ", " + args.joined(separator: ", "))): \(p.description)")
      }
    }
    return lines.joined(separator: "\n")
  }
}
