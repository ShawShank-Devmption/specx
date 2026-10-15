#!/usr/bin/env python3
"""SpecX project draft PDF — Anthropic-themed (cream / coral / slate)."""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY, TA_CENTER
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table,
    TableStyle, PageBreak, KeepTogether, HRFlowable, NextPageTemplate
)
from reportlab.lib.styles import ParagraphStyle

# ---------------------------------------------------------------- theme
CREAM      = HexColor("#FAF7F0")   # page background
CREAM_DEEP = HexColor("#F2EDE3")   # panel background
CORAL      = HexColor("#D97757")   # Anthropic accent
CORAL_DARK = HexColor("#BC5A38")
INK        = HexColor("#29261B")   # near-black warm ink
SLATE      = HexColor("#57534A")   # secondary text
LINE       = HexColor("#DDD5C6")   # hairlines
WHITE      = HexColor("#FFFFFF")

PAGE_W, PAGE_H = A4
M = 20 * mm

# ------- Anthropic-style typefaces (Tiempos ≈ Source Serif 4, Styrene ≈ Archivo)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

FD = "/home/claude/specx/fonts"
pdfmetrics.registerFont(TTFont("Serif", f"{FD}/SourceSerif-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Serif-Bold", f"{FD}/SourceSerif-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Serif-Italic", f"{FD}/SourceSerif-Italic.ttf"))
pdfmetrics.registerFont(TTFont("Serif-BoldItalic", f"{FD}/SourceSerif-BoldItalic.ttf"))
pdfmetrics.registerFont(TTFont("Sans", f"{FD}/Archivo-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Sans-Bold", f"{FD}/Archivo-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Sans-Medium", f"{FD}/Archivo-Medium.ttf"))
addMapping("Serif", 0, 0, "Serif")
addMapping("Serif", 1, 0, "Serif-Bold")
addMapping("Serif", 0, 1, "Serif-Italic")
addMapping("Serif", 1, 1, "Serif-BoldItalic")
addMapping("Sans", 0, 0, "Sans")
addMapping("Sans", 1, 0, "Sans-Bold")
addMapping("Sans", 0, 1, "Sans")
addMapping("Sans", 1, 1, "Sans-Bold")

SERIF = "Serif"
SERIF_B = "Serif-Bold"
SERIF_I = "Serif-Italic"
SANS = "Sans"
SANS_B = "Sans-Bold"
SANS_O = "Sans-Medium"

# ---------------------------------------------------------------- styles
def S(name, **kw):
    return ParagraphStyle(name, **kw)

st_kicker = S("kicker", fontName=SANS_B, fontSize=8.5, leading=12,
              textColor=CORAL_DARK, spaceAfter=4, alignment=TA_LEFT,
              tracking=1)
st_h1 = S("h1", fontName=SERIF_B, fontSize=21, leading=25, textColor=INK,
          spaceBefore=6, spaceAfter=10)
st_h2 = S("h2", fontName=SERIF_B, fontSize=14.5, leading=18, textColor=INK,
          spaceBefore=14, spaceAfter=6)
st_h3 = S("h3", fontName=SANS_B, fontSize=10.5, leading=14, textColor=CORAL_DARK,
          spaceBefore=10, spaceAfter=4)
st_body = S("body", fontName=SERIF, fontSize=10, leading=14.5, textColor=INK,
            alignment=TA_JUSTIFY, spaceAfter=7)
st_body_first = S("bodyf", parent=st_body, spaceBefore=2)
st_small = S("small", fontName=SANS, fontSize=8, leading=11, textColor=SLATE)
st_cell = S("cell", fontName=SANS, fontSize=8.2, leading=11, textColor=INK)
st_cellb = S("cellb", fontName=SANS_B, fontSize=8.2, leading=11, textColor=INK)
st_cellh = S("cellh", fontName=SANS_B, fontSize=8.2, leading=11, textColor=WHITE)
st_quote = S("quote", fontName=SERIF_I, fontSize=10, leading=14.5,
             textColor=SLATE, leftIndent=10, spaceAfter=8)
st_ref = S("ref", fontName=SERIF, fontSize=8.7, leading=12.2, textColor=INK,
           spaceAfter=4, leftIndent=14, firstLineIndent=-14)

# ---------------------------------------------------------------- page furniture
SECTION_TITLE = {"current": ""}

def bg(canv):
    canv.saveState()
    canv.setFillColor(CREAM)
    canv.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    canv.restoreState()

def on_cover(canv, doc):
    bg(canv)
    canv.saveState()
    # top coral band
    canv.setFillColor(CORAL)
    canv.rect(0, PAGE_H - 8 * mm, PAGE_W, 8 * mm, stroke=0, fill=1)
    # bottom hairline + footer
    canv.setStrokeColor(LINE); canv.setLineWidth(0.7)
    canv.line(M, 18 * mm, PAGE_W - M, 18 * mm)
    canv.setFont(SANS, 8); canv.setFillColor(SLATE)
    canv.drawString(M, 12.5 * mm, "SpecX  ·  Project Draft v1.0  ·  August 2026")
    canv.drawRightString(PAGE_W - M, 12.5 * mm, "Prepared for AI Course Review · VIT")
    canv.restoreState()

def on_page(canv, doc):
    bg(canv)
    canv.saveState()
    # header
    canv.setFillColor(CORAL)
    canv.rect(0, PAGE_H - 4 * mm, PAGE_W, 4 * mm, stroke=0, fill=1)
    canv.setFont(SANS_B, 7.5); canv.setFillColor(CORAL_DARK)
    canv.drawString(M, PAGE_H - 12 * mm, "S P E C X")
    canv.setFont(SANS, 7.5); canv.setFillColor(SLATE)
    canv.drawRightString(PAGE_W - M, PAGE_H - 12 * mm,
                         "Verified Website-to-WebMCP Conversion, Sandboxed Agent Testing & Optimisation")
    canv.setStrokeColor(LINE); canv.setLineWidth(0.6)
    canv.line(M, PAGE_H - 14.5 * mm, PAGE_W - M, PAGE_H - 14.5 * mm)
    # footer
    canv.line(M, 15 * mm, PAGE_W - M, 15 * mm)
    canv.setFont(SANS, 8); canv.setFillColor(SLATE)
    canv.drawString(M, 10 * mm, "Project Draft · Confidential — for course review")
    canv.setFillColor(CORAL_DARK); canv.setFont(SANS_B, 8.5)
    canv.drawRightString(PAGE_W - M, 10 * mm, f"{canv.getPageNumber():02d}")
    canv.restoreState()

# ---------------------------------------------------------------- helpers
def rule(width_pct=100, color=CORAL, thick=2):
    return HRFlowable(width=f"{width_pct}%", thickness=thick, color=color,
                      spaceBefore=2, spaceAfter=8, hAlign="LEFT")

def section(kicker, title):
    return [
        Spacer(1, 4),
        Paragraph(kicker.upper(), st_kicker),
        Paragraph(title, st_h1),
        rule(18, CORAL, 2.4),
    ]

def bullets(items, gap=3):
    out = []
    for it in items:
        out.append(Paragraph(
            f'<font color="#BC5A38">■</font>&nbsp;&nbsp;{it}',
            S("b", parent=st_body, alignment=TA_LEFT, spaceAfter=gap,
              leftIndent=12, firstLineIndent=-12)))
    return out

def panel(flows, bg_color=CREAM_DEEP, border=CORAL):
    t = Table([[flows]], colWidths=[PAGE_W - 2 * M])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg_color),
        ("LINEBEFORE", (0, 0), (0, -1), 2.6, border),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return t

def feature_card(tag, title, body_paras, tag_bg=CORAL):
    head = Table(
        [[Paragraph(f'<font color="white"><b>{tag}</b></font>',
                    S("tag", fontName=SANS_B, fontSize=9, leading=11,
                      textColor=WHITE, alignment=TA_CENTER)),
          Paragraph(f"<b>{title}</b>",
                    S("ct", fontName=SERIF_B, fontSize=11.5, leading=14,
                      textColor=INK))]],
        colWidths=[26 * mm, PAGE_W - 2 * M - 26 * mm - 24])
    head.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), tag_bg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (1, 0), (1, 0), 10),
    ]))
    inner = [head, Spacer(1, 5)] + body_paras
    card = Table([[inner]], colWidths=[PAGE_W - 2 * M])
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.8, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return [card, Spacer(1, 8)]

def data_table(header, rows, col_widths, align_map=None):
    data = [[Paragraph(h, st_cellh) for h in header]]
    for r in rows:
        data.append([Paragraph(c, st_cell) for c in r])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), CORAL),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 1, CORAL_DARK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, CREAM_DEEP]),
        ("GRID", (0, 1), (-1, -1), 0.4, LINE),
    ]
    t.setStyle(TableStyle(style))
    return t

# ================================================================ CONTENT
story = []

# ------------------------------------------------ COVER
story.append(Spacer(1, 60))
story.append(Paragraph("PROJECT DRAFT · ARTIFICIAL INTELLIGENCE COURSE · AUGUST 2026", st_kicker))
story.append(Spacer(1, 6))
story.append(Paragraph("SpecX",
    S("cov1", fontName=SERIF_B, fontSize=46, leading=50, textColor=INK)))
story.append(Spacer(1, 8))
story.append(rule(30, CORAL, 3))
story.append(Paragraph(
    "Verified Website-to-WebMCP Conversion, Sandboxed Agent Testing "
    "and Safety-Preserving Optimisation",
    S("cov2", fontName=SERIF, fontSize=17, leading=23, textColor=SLATE)))
story.append(Spacer(1, 26))
story.append(Paragraph(
    "SpecX converts developer-authorised websites into verified, machine-readable WebMCP "
    "tool interfaces for AI agents. It grounds every generated tool in executable contracts, "
    "stress-tests it inside a disposable browser sandbox, and improves it through a "
    "statistically gated closed loop &mdash; augmented with four learning-based subsystems: "
    "adversarial deep-reinforcement-learning fuzzing, graph-neural-network risk prediction "
    "over typed workflow graphs, a multimodal patch-generation model, and a streaming "
    "anomaly-detection safety layer.", st_body))
story.append(Spacer(1, 20))

cov_rows = [
    ["Document type", "Full project draft — features, literature review, concepts, implementation, publication plan"],
    ["Existing functionalities", "F1 Contract-Grounded Verification · F2 Closed-Loop Optimisation · F3 Evidence-Based Generation · F4 Agent-Readiness Evaluation"],
    ["New functionalities", "S1 Adversarial DRL Fuzzing · S2 GNN Workflow-Risk Prediction · S4 Multimodal Structured Patching · S6 Streaming Anomaly Detection"],
    ["Deliverables", "CLI · CI integration · web dashboard · verified WebMCP definitions · workflow manifests · agent-readiness reports · research paper"],
    ["Target venues", "IEEE Access (primary) · Empirical Software Engineering · Journal of Systems and Software"],
]
cov_data = [[Paragraph(f"<b>{a}</b>", st_cellb), Paragraph(b, st_cell)] for a, b in cov_rows]
covt = Table(cov_data, colWidths=[42*mm, PAGE_W - 2*M - 42*mm])
covt.setStyle(TableStyle([
    ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("LINEBELOW", (0,0), (-1,-2), 0.5, LINE),
    ("TOPPADDING", (0,0), (-1,-1), 6),
    ("BOTTOMPADDING", (0,0), (-1,-1), 6),
]))
story.append(covt)
story.append(NextPageTemplate("content"))
story.append(PageBreak())

# ------------------------------------------------ 1. ABSTRACT & MOTIVATION
story += section("Section 01", "Abstract &amp; Motivation")
story.append(Paragraph(
    "WebMCP lets web applications expose structured, machine-readable tools to AI agents: a page "
    "carrying WebMCP tool definitions effectively behaves as a client-side MCP server that agents "
    "can call directly, instead of scraping and clicking through the raw DOM. The proposal, which "
    "grew out of the MCP-B project and is now advanced through the W3C Web Machine Learning "
    "Community Group by Google and Microsoft, shipped as an early preview behind a flag in Chrome "
    "146 in February 2026, with broader native support expected later in the year. The opportunity "
    "is therefore immediate &mdash; and so is the risk: auto-generated tools may invoke the wrong "
    "action, cause unapproved side effects, silently leak data through background requests, or be "
    "so poorly named and described that agents cannot reliably select them.", st_body_first))
story.append(Paragraph(
    "SpecX addresses this end to end. It (i) analyses a developer-authorised website&rsquo;s "
    "repository, DOM, accessibility tree, API traces and existing end-to-end tests to generate "
    "atomic WebMCP tool wrappers; (ii) derives executable preconditions and postconditions for "
    "every tool and verifies them in a controlled browser sandbox, quarantining anything unsafe, "
    "unverifiable or incorrect; (iii) optimises tool names, descriptions and schemas through "
    "measured agent testing behind a statistical regression gate that never trades safety for "
    "performance; and (iv) evaluates agent readiness across four conditions &mdash; raw DOM, "
    "generated, verified, and optimised WebMCP &mdash; over typed workflow graphs.", st_body))
story.append(Paragraph(
    "Following the review committee&rsquo;s provisional acceptance, this draft incorporates four "
    "additional AI functionalities selected from the eight suggested enhancements: <b>S1</b> an "
    "adversarial deep-reinforcement-learning fuzzer that hunts for contract violations, race "
    "conditions and hidden side effects; <b>S2</b> graph neural networks that turn typed workflow "
    "graphs into embedding spaces for predicting unmapped data dependencies and high-risk execution "
    "paths; <b>S4</b> a fine-tuned multimodal transformer that converts DOM diffs, network traces "
    "and screenshots into structured code patches and schema corrections; and <b>S6</b> a streaming "
    "anomaly-detection layer (Isolation Forest + LSTM autoencoder) that catches slow-leaking "
    "unapproved effects during sandboxed testing. The selection was made after a prior-art study "
    "(Section 3) to maximise defensible novelty, architectural coherence, one-semester feasibility, "
    "and clean ablation design for the accompanying journal paper.", st_body))

story.append(panel([Paragraph(
    "<b>Thesis of the paper.</b> Contract-verified, adversarially tested and learning-optimised "
    "WebMCP interfaces measurably improve agent success, efficiency and safety compared with raw "
    "DOM interaction and unverified generated tools &mdash; and each added subsystem contributes an "
    "independently measurable share of that improvement.", S("pp", parent=st_body, spaceAfter=0))]))

story.append(PageBreak())

# ------------------------------------------------ 2. EXISTING FEATURES
story += section("Section 02", "Existing Functionalities (F1&ndash;F4)")
story.append(Paragraph(
    "The four functionalities below form the accepted core of SpecX. F1 and F2 were proposed as "
    "completely new; F3 and F4 as upgrades of existing generator and benchmark work. Together they "
    "define the pipeline into which the new S-features plug.", st_body_first))

story += feature_card("F1 · NEW", "Contract-Grounded Tool Verification", [
    Paragraph("Derives <i>executable</i> preconditions and postconditions for every candidate tool "
    "from five evidence surfaces: repository code, rendered DOM, accessibility (ARIA) tree, "
    "network traces, and optional backend audit events. Each tool is executed in a controlled "
    "browser &mdash; a disposable sandbox or an MCP-B Chrome integration &mdash; and its observable "
    "effects are checked against the contract. Tools with incorrect, unapproved or unverifiable "
    "effects are quarantined rather than shipped.", S("fc", parent=st_body, spaceAfter=3)),
    Paragraph("<b>Output:</b> pass/fail verdicts per contract clause, effect diffs, quarantine list "
    "with machine-readable reasons.", st_small)])

story += feature_card("F2 · NEW", "Safety-Preserving Closed-Loop Optimisation", [
    Paragraph("An external evaluation agent exercises the verified tools on realistic held-out "
    "tasks. Failure traces guide LLM-driven revisions of tool <i>names, descriptions and approved "
    "JSON schemas</i> &mdash; the agent-facing metadata that governs tool selection &mdash; never "
    "the underlying action. A statistical regression gate accepts a revision only when repeated "
    "trials show improvement <i>and</i> all safety invariants still hold.", S("fc", parent=st_body, spaceAfter=3)),
    Paragraph("<b>Output:</b> optimised tool metadata, per-revision trial statistics, accepted/rejected "
    "revision log.", st_small)])

story += feature_card("F3 · UPGRADE", "Evidence-Based Website-to-WebMCP Generation", [
    Paragraph("Extends form/action generators with repository parsing, semantic DOM/ARIA signals, "
    "API traces and existing end-to-end tests to identify candidate actions and emit "
    "implementation-ready, <i>atomic</i> WebMCP tool definitions (one verifiable action per tool). "
    "Atomicity is what makes F1&rsquo;s contracts checkable.", S("fc", parent=st_body, spaceAfter=3)),
    Paragraph("<b>Output:</b> WebMCP tool definitions with parameter schemas, provenance links back "
    "to the evidence that justified each tool.", st_small)])

story += feature_card("F4 · UPGRADE", "Comparative Agent-Readiness Evaluation &amp; Workflow Graphs", [
    Paragraph("Extends web-agent benchmarks with four conditions &mdash; raw DOM, generated, "
    "verified, and optimised WebMCP &mdash; so every pipeline stage is measurable. Builds "
    "<i>typed workflow graphs</i> whose nodes are tools (with type signatures and risk levels) and "
    "whose edges encode valid ordering, state transitions and data dependencies.", S("fc", parent=st_body, spaceAfter=3)),
    Paragraph("<b>Output:</b> agent-readiness report per application version, workflow manifests, "
    "benchmark scores per condition.", st_small)])

story.append(Paragraph(
    "<b>Project outcome.</b> A standalone CLI, CI integration and web dashboard that convert "
    "authorised websites into verified, performance-optimised WebMCP interfaces with tests, "
    "diagnostics, workflow manifests and reports &mdash; plus a controlled research study of whether "
    "contract-verified WebMCP interfaces improve agent success, efficiency and safety.", st_body))

story.append(PageBreak())

# ------------------------------------------------ 3. LITERATURE REVIEW
story += section("Section 03", "Literature Review &amp; Prior-Art Positioning")
story.append(Paragraph(
    "A deep prior-art search was conducted across the eight suggested enhancements and the SpecX "
    "core (arXiv, ICSE/FSE/ISSTA, NeurIPS/ICML/ICLR, WWW, plus the 2025&ndash;2026 MCP/WebMCP "
    "ecosystem). Three conclusions drive this draft: the WebMCP problem is real and current; the "
    "SpecX core has close 2026 neighbours that must be cited and explicitly distinguished; and the "
    "four selected S-features each occupy a defensible gap.", st_body_first))

story.append(Paragraph("3.1 &nbsp;WebMCP and the MCP ecosystem", st_h2))
story.append(Paragraph(
    "WebMCP originated in the MCP-B project (Alex Nahas, early 2025) and was unified into a joint "
    "Google/Microsoft proposal in August 2025; the W3C Web Machine Learning Community Group adopted "
    "it in September 2025 and published a Draft Community Group Report in February 2026. Chrome 146 "
    "ships an early preview behind a testing flag. On the security side, static scanners such as "
    "MCP-Scan and Cisco&rsquo;s mcp-scanner audit MCP server definitions for prompt-injection and "
    "tool-poisoning patterns &mdash; but they analyse <i>declared</i> tools statically. SpecX "
    "differs categorically: it <i>generates</i> tools from live websites and verifies their "
    "<i>runtime effects</i> in a sandbox.", st_body))

story.append(Paragraph("3.2 &nbsp;Closest neighbours to the SpecX core (must-cite)", st_h2))
story.append(data_table(
    ["Work", "What it does", "How SpecX differs"],
    [["<b>ContractSkill</b> (arXiv 2603.20340, 2026)",
      "Compiles web-agent skills into contracted artifacts with preconditions, step specs, postconditions and recovery rules; enables deterministic verification and patch-based repair. Lifts VisualWebArena skill success from ~9&ndash;11% to ~28&ndash;38%.",
      "Verifies hand-drafted <i>skills</i> against page state only. SpecX targets <i>generated WebMCP tools</i>, grounds contracts in five surfaces (code, DOM, ARIA, network, audit events), and adds a generation stage ContractSkill lacks."],
     ["<b>CoEvoSkills</b> (arXiv 2604.01687, 2026)",
      "Skill generator and information-isolated surrogate verifier co-evolve through generate&ndash;verify&ndash;refine cycles; oracle returns opaque pass/fail.",
      "Optimises skill <i>code</i> via an LLM surrogate. SpecX optimises agent-facing <i>metadata</i> (names, descriptions, schemas) behind a statistical regression gate with hard safety invariants."],
     ["<b>Formal Verification of Agent Skills</b> (arXiv 2605.23951, 2026)",
      "Three verification surfaces; checks every world-state change has a matching audit-log envelope; contrasts itself with plain JSON-Schema validation.",
      "Verifies existing skills formally. SpecX unifies generation + multi-surface runtime verification + adversarial fuzzing + closed-loop optimisation in one system, and evaluates agent readiness comparatively."]],
    [34*mm, 68*mm, PAGE_W - 2*M - 34*mm - 68*mm]))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "Because these works are so close, the paper&rsquo;s related-work section must lead with them "
    "and argue the distinction explicitly; the core&rsquo;s novelty rests on the WebMCP generation "
    "target and multi-surface grounding, with the S-features carrying independent contributions.", st_body))

story.append(Paragraph("3.3 &nbsp;Prior art per suggested enhancement", st_h2))
story.append(data_table(
    ["#", "Enhancement", "Closest prior art", "Nov.", "Verdict"],
    [["S1", "Adversarial DRL fuzzing of tool contracts",
      "WebRLED (curiosity-driven DRL web GUI testing, arXiv 2504.19237); GENESIS-RL edge-case generation; ARLAS adversarial RL for agent safety (arXiv 2510.05442). All target coverage/crashes or prompt injection &mdash; none reward <i>contract violations of agent tools</i>.",
      "4 / 5", "<b>Adopt</b>"],
     ["S2", "GNNs on typed workflow graphs",
      "FLORA / FLORA-Bench (arXiv 2503.11301): GNNs predict agentic-workflow <i>performance</i> (~0.78 acc., up to 125&times; speed-up vs LLM judging). Provenance-graph GNNs in security. None predict <i>data dependencies or safety-invariant violations</i>.",
      "4 / 5", "<b>Adopt</b>"],
     ["S4", "Multimodal transformer &rarr; structured patches",
      "SVRepair (2602.06090), GALA (2604.08089), VisualRepair (2607.14075): multimodal automated program repair from screenshots. None repair <i>tool schemas/descriptions</i> or consume network traces as a modality.",
      "4 / 5", "<b>Adopt</b>"],
     ["S6", "Streaming anomaly detection on traces + DOM mutations",
      "Hybrid LSTM-AE + Isolation Forest is standard in network intrusion detection; trajectory-level agent-safety monitors (TRACE/JANUS). Not applied to <i>DOM-mutation + network streams during tool sandbox verification</i>.",
      "3.5 / 5", "<b>Adopt</b>"],
     ["S3", "CLIP-style code&harr;DOM&harr;trace contrastive embedding",
      "GNN-Coder (2502.15202) already does CLIP-style code&ndash;text alignment; Pix2Struct, Screen2Vec cover UI understanding. Requires a large aligned tri-modal corpus + pre-training compute.",
      "2.5 / 5", "Defer"],
     ["S5", "MAML meta-learning for tool descriptions",
      "System Prompt Optimization with Meta-Learning (2505.09666); DSPy/MIPROv2, OPRO are simpler, stronger baselines reviewers will demand. MAML bilevel optimisation is unstable at student scale.",
      "2.5 / 5", "Defer"],
     ["S7", "RAG over Cypress/Playwright scripts",
      "Autonomous QA Agent (2601.06034): RAG-grounded Selenium generation, 90% execution success vs 30% baseline; Playwright codegen/MCP. Near-solved engineering pattern.",
      "2 / 5", "Engineering aid only"],
     ["S8", "SHAP/IG readiness scorecards",
      "AgentSHAP (2512.12597) is explicitly the first framework for explaining tool importance in LLM agents via Monte-Carlo Shapley values &mdash; pre-empts the core claim.",
      "2 / 5", "Reporting feature only"]],
    [8*mm, 30*mm, 90*mm, 12*mm, PAGE_W - 2*M - 8*mm - 30*mm - 90*mm - 12*mm]))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "Benchmark anchoring: ST-WebAgentBench (222 policy-paired tasks; Completion-under-Policy metric, "
    "under which evaluated agents complete safely far less often than nominally) supplies the safety "
    "dimension; OSWorld-MCP (158 auto-generated MCP tools across 7 applications, tool-vs-GUI "
    "ablation) is the nearest tool-condition comparator; WebArena and Mind2Web supply task pools. "
    "No prior benchmark spans SpecX&rsquo;s four conditions (raw DOM / generated / verified / "
    "optimised), which itself is a contribution.", st_body))

story.append(PageBreak())

# ------------------------------------------------ 4. NEW FEATURES
story += section("Section 04", "New Functionalities (S1, S2, S4, S6)")
story.append(Paragraph(
    "Four of the eight reviewer suggestions are adopted. Selection criteria: publishable novelty "
    "surviving the prior art above, coherence with F1&ndash;F4, one-semester feasibility for a small "
    "team, and a clean per-feature ablation. Each card states what the feature does, where it plugs "
    "in, and its defensible novelty claim.", st_body_first))

story += feature_card("S1 · NEW", "Adversarial DRL Contract Fuzzer &nbsp;&rarr;&nbsp; plugs into F1", [
    Paragraph("A deep-reinforcement-learning agent (PPO/DQN) treats the F1 sandbox as a Gym-style "
    "environment. Its <i>actions</i> mutate tool parameters, reorder calls, and fire concurrent "
    "invocations; its <i>state</i> is the observed DOM + network + audit delta; its <i>reward</i> is "
    "+1 for each newly triggered contract violation, unapproved side effect or race condition, "
    "shaped by a curiosity bonus for novel states. Standard LLM-driven test trails explore the "
    "happy path; the adversarial agent is paid to break it.", S("fc", parent=st_body, spaceAfter=3)),
    Paragraph("<b>Novelty claim:</b> to our knowledge, the first adversarial-RL fuzzer whose reward "
    "is defined over executable pre/postcondition violations of WebMCP/MCP agent tools (vs. "
    "coverage/crash rewards in WebRLED &amp; GUI-testing RL).", st_small)])

story += feature_card("S2 · NEW", "GNN Workflow-Risk &amp; Dependency Prediction &nbsp;&rarr;&nbsp; plugs into F4 (feeds F1)", [
    Paragraph("F4&rsquo;s typed workflow graphs are embedded with graph neural networks (GCN/GAT via "
    "PyTorch Geometric). Two heads: (i) <i>edge prediction</i> recovers unmapped data dependencies "
    "between tools; (ii) <i>node/subgraph classification</i> forecasts high-risk execution paths and "
    "non-obvious safety-invariant violations across long tool sequences &mdash; before any sandbox "
    "run. Training labels come from F1/S1 sandbox verdicts, so the fuzzer literally generates the "
    "GNN&rsquo;s training data.", S("fc", parent=st_body, spaceAfter=3)),
    Paragraph("<b>Novelty claim:</b> first GNN predicting <i>safety-invariant violations and data "
    "dependencies</i> on typed WebMCP workflow graphs &mdash; FLORA-style graph learning repurposed "
    "from performance prediction to safety.", st_small)])

story += feature_card("S4 · NEW", "Multimodal Structured Patch Generator &nbsp;&rarr;&nbsp; plugs into F2", [
    Paragraph("Replaces unstructured textual failure traces in the F2 revision loop with a "
    "fine-tuned vision-language model (Qwen-VL/LLaVA-class, LoRA-adapted) that ingests serialised "
    "DOM diffs, network trace logs and screenshots <i>simultaneously</i> and emits "
    "schema-constrained JSON: concrete code patches and tool-schema corrections. Structured output "
    "makes revisions machine-applicable and auditable by the regression gate.", S("fc", parent=st_body, spaceAfter=3)),
    Paragraph("<b>Novelty claim:</b> first multimodal (DOM-diff + trace + screenshot) model producing "
    "structured WebMCP schema/tool patches &mdash; adjacent multimodal APR (SVRepair, GALA, "
    "VisualRepair) repairs general program bugs, not agent-tool metadata.", st_small)])

story += feature_card("S6 · NEW", "Streaming Anomaly-Detection Safety Layer &nbsp;&rarr;&nbsp; plugs into F1", [
    Paragraph("During every sandboxed run, windowed features from browser network traces and DOM "
    "MutationObserver streams feed two detectors: an Isolation Forest (scikit-learn) for point "
    "anomalies and a small LSTM autoencoder trained on approved traces, whose reconstruction error "
    "flags sequence anomalies. This catches what deterministic contracts miss: slow-leaking side "
    "effects, delayed background POSTs, silent storage writes, unauthorised third-party calls.", S("fc", parent=st_body, spaceAfter=3)),
    Paragraph("<b>Novelty claim:</b> a real-time learned safety layer over DOM-mutation + network "
    "streams during agent-tool sandbox verification &mdash; a novel application of a well-proven "
    "hybrid detector, positioned as complementary to (not replacing) contract checks.", st_small)])

story.append(Paragraph(
    "<b>Why not S3, S5, S7, S8.</b> S3 needs a large aligned code&ndash;DOM&ndash;trace corpus and "
    "contrastive pre-training compute a student team cannot marshal, and GNN-Coder weakens its "
    "claim. S5 is pre-empted by meta-learned prompt optimisation and is unstable to train; "
    "DSPy/OPRO-style baselines would likely win. S7 is an excellent engineering aid (and will be "
    "used internally in F3) but is too incremental to claim. S8 is pre-empted by AgentSHAP; it "
    "survives as a dashboard reporting feature, not a contribution.", st_body))

story.append(PageBreak())

# ------------------------------------------------ 5. CONCEPTS
story += section("Section 05", "Concepts Explained")
story.append(Paragraph(
    "Every technical concept the system relies on, in the order it appears in the pipeline. This "
    "section doubles as the paper&rsquo;s background section and as onboarding material for new "
    "team members.", st_body_first))

concepts = [
 ("MCP &amp; WebMCP",
  "The Model Context Protocol (MCP) is a JSON-RPC-based standard through which AI applications "
  "discover and invoke external tools with typed parameter schemas. <b>WebMCP</b> moves the tool "
  "surface into the web page itself: a site declares JavaScript-backed tools (name, description, "
  "input schema, handler), and a browsing agent calls them directly instead of parsing the DOM. "
  "MCP-B is the Chrome-extension lineage of the same idea and serves as one of SpecX&rsquo;s two "
  "execution targets."),
 ("Atomic tool wrappers",
  "A tool is <i>atomic</i> when it performs exactly one verifiable action (e.g., &ldquo;add item "
  "to cart&rdquo;, never &ldquo;add item and checkout&rdquo;). Atomicity is what makes contracts "
  "decidable: each tool has a small, checkable effect footprint, and workflows are recovered as "
  "graphs over atomic tools rather than baked into monoliths."),
 ("Preconditions &amp; postconditions (design by contract)",
  "A <i>precondition</i> states what must hold before a tool may run (user logged in, form field "
  "present, cart non-empty); a <i>postcondition</i> states what must hold after (order row created, "
  "exactly one POST to /api/orders, confirmation dialog visible). SpecX derives both as "
  "<i>executable</i> checks from code, DOM, ARIA, network traces and audit events &mdash; the "
  "&ldquo;contract-grounded&rdquo; part of F1. A tool that cannot be given a checkable contract is "
  "quarantined as unverifiable."),
 ("Sandboxed execution &amp; quarantine",
  "Every candidate tool runs inside a disposable browser environment (seeded database, network "
  "interception, no external effects) so that misbehaviour is observable but harmless. Quarantine "
  "means the tool is excluded from the shipped WebMCP manifest and reported with the exact contract "
  "clause it violated."),
 ("Closed-loop optimisation &amp; regression gates",
  "An evaluation agent attempts held-out tasks with the current tool set; failures produce traces; "
  "an LLM (later, S4&rsquo;s model) proposes metadata revisions; the revised set is re-trialled. A "
  "<i>statistical regression gate</i> (paired trials, significance test, effect size) accepts a "
  "revision only if performance improves and no safety invariant regresses &mdash; preventing the "
  "optimiser from &ldquo;improving&rdquo; success by weakening safeguards."),
 ("Deep reinforcement learning &amp; adversarial rewards (S1)",
  "RL trains an agent to maximise cumulative reward through trial and error; <i>deep</i> RL uses "
  "neural networks (here PPO/DQN) over rich state. An <i>adversarial reward</i> pays the agent for "
  "making the system under test fail &mdash; each new contract violation, race condition or "
  "unapproved effect is a point. A curiosity bonus (reward for novel states) prevents the fuzzer "
  "from replaying the same crash."),
 ("Race conditions &amp; hidden side effects",
  "A race condition is behaviour that depends on the timing/interleaving of concurrent operations "
  "(double-submit creating two orders). A hidden side effect is any state change outside the "
  "declared contract (an analytics beacon, a background write). S1 searches for both actively; S6 "
  "watches for them passively."),
 ("Graph neural networks &amp; typed embeddings (S2)",
  "GNNs learn vector representations of nodes and edges by iteratively aggregating information from "
  "neighbours (GCN: spectral convolutions; GAT: learned attention weights). Embedding SpecX&rsquo;s "
  "typed workflow graphs lets the system <i>predict</i> missing data-dependency edges (link "
  "prediction) and classify paths by violation risk (node/subgraph classification) before spending "
  "sandbox time &mdash; a learned prioritiser in front of the verifier."),
 ("Multimodal transformers &amp; structured decoding (S4)",
  "A vision-language transformer jointly attends over text tokens (serialised DOM diffs, network "
  "logs) and image patches (screenshots). LoRA fine-tuning adapts a pre-trained model cheaply by "
  "training small low-rank adapter matrices. <i>Schema-constrained decoding</i> forces the output "
  "to be valid JSON matching a patch schema, so every revision is machine-applicable."),
 ("Isolation Forests &amp; LSTM autoencoders (S6)",
  "An Isolation Forest isolates anomalies with random splits &mdash; anomalous points need fewer "
  "splits, giving an anomaly score without labelled attacks. An LSTM autoencoder learns to "
  "compress-and-reconstruct <i>normal</i> sequences; abnormal sequences reconstruct poorly, and the "
  "reconstruction error is the alarm. Together they cover point anomalies and temporal anomalies "
  "over network/DOM streams."),
 ("Typed workflow graphs &amp; agent readiness (F4)",
  "Nodes are tools annotated with type signatures and risk levels; edges encode valid ordering, "
  "state transitions and data flow. <i>Agent readiness</i> is the measured ability of a standard "
  "agent to complete tasks against an interface, reported across the four benchmark conditions "
  "with success, efficiency (steps/tokens) and safety (policy-violation) metrics."),
]
for title, body in concepts:
    story.append(KeepTogether([
        Paragraph(title, st_h3),
        Paragraph(body, st_body)]))

story.append(PageBreak())

# ------------------------------------------------ 6. IMPLEMENTATION
story += section("Section 06", "Implementation Plan")
story.append(Paragraph(
    "The plan follows a strict dependency order &mdash; <b>S6 &rarr; S1 &rarr; S2 &rarr; S4</b> "
    "&mdash; chosen so that each stage produces the data the next one trains on: S6 needs only "
    "approved traces; S1 reuses the sandbox and generates violation examples; S2 trains on "
    "S1/F1&rsquo;s verdict labels; S4 trains on failure&ndash;patch pairs harvested from F2 runs.", st_body_first))

story.append(Paragraph("6.1 &nbsp;Architecture &amp; stack", st_h2))
story.append(data_table(
    ["Layer", "Components", "Technology"],
    [["Generation (F3)", "Repo parser, DOM/ARIA analyser, API-trace miner, atomic tool emitter; internal RAG over Cypress/Playwright scripts (S7 as engineering aid)",
      "Node.js/TypeScript, Playwright, tree-sitter, LLM API"],
     ["Verification (F1)", "Contract deriver, disposable sandbox, effect differ, quarantine manager",
      "Playwright + CDP, Docker sandboxes, network interception (mitmproxy), seeded Postgres"],
     ["S6 safety layer", "Feature windower over network + MutationObserver streams; Isolation Forest; LSTM-AE",
      "scikit-learn, PyTorch (small LSTM), streaming via CDP events"],
     ["S1 fuzzer", "Gym wrapper around sandbox; parameter/ordering/concurrency action space; violation+curiosity reward",
      "Gymnasium, Stable-Baselines3 (PPO/DQN)"],
     ["S2 graph model", "Typed graph builder; GCN/GAT with edge-prediction + risk-classification heads",
      "PyTorch Geometric, NetworkX"],
     ["Optimisation (F2 + S4)", "Evaluation agent harness, regression gate, VLM patch generator with JSON-constrained decoding",
      "LLM/VLM APIs, LoRA (PEFT), outlines/jsonschema decoding, SciPy stats"],
     ["Evaluation (F4)", "Four-condition benchmark runner, workflow-manifest exporter, readiness reports",
      "WebArena/Mind2Web task pools, ST-WebAgentBench-style safety scoring, OSWorld-MCP comparator"],
     ["Delivery", "CLI, CI integration, dashboard",
      "Node CLI, GitHub Actions, React dashboard"]],
    [26*mm, 82*mm, PAGE_W - 2*M - 26*mm - 82*mm]))

story.append(Paragraph("6.2 &nbsp;Semester timeline (14 weeks)", st_h2))
story.append(data_table(
    ["Weeks", "Milestone", "Exit criterion"],
    [["1&ndash;2", "F3 generator + F1 sandbox skeleton on 2 seed apps (one e-commerce, one CRUD/admin)", "Atomic tools generated with provenance; sandbox replays a tool run deterministically"],
     ["3&ndash;4", "F1 contracts on all five surfaces; quarantine flow; <b>S6</b> detectors trained on approved traces", "Injected slow side effects detected; false-positive rate on benign tools measured"],
     ["5&ndash;7", "<b>S1</b> Gym environment + PPO fuzzer; baseline random &amp; coverage-guided fuzzers", "DRL beats baselines on violations found per sandbox-hour (else invoke fallback, &sect;6.4)"],
     ["8&ndash;9", "<b>S2</b> graph builder + GNN heads trained on F1/S1 verdicts", "GNN beats rule-based dependency checker on held-out precision/recall"],
     ["10&ndash;11", "F2 loop + regression gate; harvest failure&ndash;patch pairs; <b>S4</b> LoRA fine-tune + constrained decoding", "Structured patches apply cleanly; loop converges in fewer iterations than text-trace baseline"],
     ["12&ndash;13", "F4 four-condition benchmark across &ge;3 applications; full ablation matrix; statistics", "Every S-feature has an isolated effect size with significance test"],
     ["14", "Paper draft, artifact packaging (code, seeds, manifests), dashboard polish", "Reproducibility package runs end-to-end from a clean clone"]],
    [16*mm, 88*mm, PAGE_W - 2*M - 16*mm - 88*mm]))

story.append(Paragraph("6.3 &nbsp;Experiment &amp; ablation design", st_h2))
story += bullets([
 "<b>Conditions:</b> raw DOM &rarr; generated (F3) &rarr; verified (F1+S1+S6) &rarr; optimised (F2+S4), each evaluated by the same frozen agent on the same held-out task pool.",
 "<b>Per-feature ablations:</b> S1 vs random/coverage fuzzing (violations per sandbox-hour, severity mix); S2 vs rule-based checker and MLP-on-features (dependency P/R, pre-sandbox risk ranking quality); S4 vs unstructured text traces and text-only structured patches (success gain per revision, iterations-to-convergence); S6 on/off with injected slow leaks (detection rate, FPR).",
 "<b>Metrics:</b> task success, steps and tokens to completion, policy-violation rate (Completion-under-Policy style), quarantine precision, time-to-first-violation.",
 "<b>Statistics:</b> &ge;10 paired trials per condition; paired tests with Holm&ndash;Bonferroni correction; report effect sizes and confidence intervals &mdash; the F2 regression gate already provides this machinery.",
])
story.append(Paragraph("6.4 &nbsp;Risk register &amp; fallbacks", st_h2))
story += bullets([
 "<b>S1 underperforms</b> after ~2 weeks of tuning &rarr; fall back to coverage-guided fuzzing with curiosity heuristics, reclassify S1 as engineering, and promote S7 (RAG generation) to the fourth ablatable contribution.",
 "<b>S2 cannot beat the rule-based checker</b> &rarr; demote to interpretability/visualisation aid; consider promoting an S8-style scorecard with explicit AgentSHAP differentiation.",
 "<b>Sparse S4 training pairs</b> &rarr; bootstrap with synthetic failure injection (mutate schemas, break selectors) before harvesting real loop data.",
 "<b>WebMCP spec drift</b> (Chrome preview evolving) &rarr; pin to the February 2026 draft; keep the MCP-B extension path as the stable fallback target.",
])
story.append(PageBreak())

# ------------------------------------------------ 7. PUBLICATION
story += section("Section 07", "Path to a Successful Journal Publication")
story.append(Paragraph(
    "Acceptance will not hinge on the ML methods themselves &mdash; all four are established "
    "primitives &mdash; but on <i>honest novelty framing, airtight empirical design, and "
    "reproducibility</i>. The checklist below is what reviewers at the target venues will actually "
    "look for.", st_body_first))

story.append(Paragraph("7.1 &nbsp;Contribution list (&ge; 4 novel approaches)", st_h2))
story += bullets([
 "<b>C1 — System.</b> First end-to-end pipeline generating WebMCP tools from developer-authorised live websites with <i>multi-surface</i> contract grounding (code + DOM + ARIA + network + audit events) and sandbox quarantine — explicitly differentiated from ContractSkill, CoEvoSkills and formal skill verification.",
 "<b>C2 — S1.</b> First adversarial-RL fuzzer rewarded on executable contract violations of agent tools.",
 "<b>C3 — S2.</b> First GNN predicting data dependencies and safety-invariant violations on typed WebMCP workflow graphs (vs. FLORA's performance prediction).",
 "<b>C4 — S4.</b> First multimodal (DOM-diff + trace + screenshot) model emitting structured WebMCP schema/tool patches inside a safety-gated revision loop.",
 "<b>C5 — S6.</b> A streaming learned safety layer over DOM-mutation + network streams during tool verification — a novel application, framed as complementary to contracts.",
 "<b>C6 — Benchmark.</b> The first four-condition agent-readiness benchmark (raw DOM / generated / verified / optimised WebMCP) with typed workflow manifests, released as an artifact.",
])
story.append(Paragraph(
    "Every &ldquo;first&rdquo; must be hedged as <i>&ldquo;to our knowledge&rdquo;</i> with a stated "
    "literature-cutoff date, and the prior-art search re-run immediately before submission &mdash; "
    "the field moved fast enough in 2026 that a six-week-old novelty claim can expire.", st_body))

story.append(Paragraph("7.2 &nbsp;What determines acceptance", st_h2))
story.append(data_table(
    ["Determinant", "What reviewers expect", "SpecX answer"],
    [["Novelty defense", "Related work engages the <i>closest</i> neighbours head-on, not a survey of distant ones",
      "Dedicated subsection on ContractSkill / CoEvoSkills / arXiv 2605.23951 with a differentiation table; per-feature closest-work citations (WebRLED, FLORA, SVRepair-family, AgentSHAP)"],
     ["Empirical rigour", "Controlled conditions, paired trials, significance tests, effect sizes, multiple applications",
      "Four-condition design over &ge;3 apps, &ge;10 paired trials, Holm&ndash;Bonferroni, CIs; the regression gate doubles as the stats engine"],
     ["Ablatability", "Each claimed contribution isolated and measured",
      "One ablation arm per S-feature (Section 6.3); no bundled claims"],
     ["Threats to validity", "Explicit internal/external/construct threats",
      "Seed-app selection bias, agent-model dependence, WebMCP spec drift, synthetic-injection realism for S6, fuzzer reward hacking for S1"],
     ["Reproducibility", "Public code, data, seeds, exact model versions, one-command replication",
      "Artifact: CLI + seed apps + manifests + trained checkpoints + benchmark harness; pinned Chrome/spec versions"],
     ["Writing &amp; scope", "One coherent story, not eight features",
      "Narrative: <i>generate &rarr; verify (S6, S1) &rarr; predict (S2) &rarr; repair (S4) &rarr; measure (benchmark)</i> — every feature advances the same safety thesis"]],
    [26*mm, 62*mm, PAGE_W - 2*M - 26*mm - 62*mm]))

story.append(Paragraph("7.3 &nbsp;Venue strategy", st_h2))
story.append(data_table(
    ["Venue", "Profile", "Fit &amp; strategy"],
    [["<b>IEEE Access</b> (primary)", "2025 JIF &asymp; 4.2, Q2; broad scope; ~30-day first decision; APC applies; acceptance figures vary by source (~20&ndash;45%)",
      "Best first target: values applied novelty + solid experiments; fast enough for a student timeline. Verify current APC and acceptance data before submission."],
     ["<b>Empirical Software Engineering</b> (Springer)", "Q1, CiteScore &asymp; 8.6; review often &gt; 12 weeks; demands genuine empirical depth",
      "Choose if the four-condition benchmark study becomes the headline; requires the full statistical apparatus and threats-to-validity treatment"],
     ["<b>Journal of Systems and Software</b> / <b>Automated Software Engineering</b>", "JSS 2025 JIF &asymp; 3.8 (Q2); AuSE strongly scope-matched to automated generation + verification",
      "Prestige upgrades if early results are strong; AuSE&rsquo;s scope (automation of SE tasks) matches SpecX almost verbatim"],
     ["TOSEM / TSE (aspirational)", "Leading SE journals (JIF &asymp; 6+); very long cycles; expect major revisions",
      "Only with exceptionally strong results and a mature artifact; not for the course deadline"]],
    [34*mm, 62*mm, PAGE_W - 2*M - 34*mm - 62*mm]))

story.append(Paragraph("7.4 &nbsp;Pre-submission checklist", st_h2))
story += bullets([
 "Re-run the prior-art search (arXiv, Semantic Scholar alerts on &ldquo;WebMCP&rdquo;, &ldquo;agent tool verification&rdquo;, &ldquo;skill contracts&rdquo;) and update every novelty hedge.",
 "Verify the exact WebMCP draft date against the W3C repository (github.com/webmachinelearning/webmcp) — sources conflict, and a wrong spec date in paragraph one destroys credibility.",
 "Confirm venue metrics (JIF, APC, acceptance rate) against Clarivate JCR and official journal pages — aggregator numbers disagree.",
 "Freeze the evaluation agent model and Chrome version; record all seeds; package a one-command replication script.",
 "Internal red-team review: have a teammate attack each novelty claim with the cited prior work before a reviewer does.",
 "Secure faculty guidance sign-off (Dr. Yoganand S / CFAIR) on authorship order, ethics of testing only developer-authorised sites, and data release.",
])

story.append(Spacer(1, 6))
story.append(panel([Paragraph(
    "<b>Bottom line.</b> SpecX ships six defensible contributions wrapped in one safety thesis. The "
    "core pipeline alone would be judged incremental against 2026 skill-verification work — the four "
    "selected S-features and the four-condition benchmark are what make this publishable. Execute in "
    "the stated order, keep every claim ablated and hedged, and target IEEE Access first with EMSE "
    "as the empirical-track alternative.", S("pp2", parent=st_body, spaceAfter=0))]))

# ------------------------------------------------ REFERENCES
story.append(PageBreak())
story += section("Appendix", "Key References")
refs = [
 "Lu et al., &ldquo;ContractSkill: Repairable Contract-Based Skills for Multimodal Web Agents,&rdquo; arXiv:2603.20340, 2026.",
 "&ldquo;CoEvoSkills: Co-Evolving Skill Generation and Surrogate Verification for Web Agents,&rdquo; arXiv:2604.01687, 2026.",
 "&ldquo;Methods for Formal Verification of Agent Skills: Three Layers Toward a Mechanically Checkable Capability-Containment Proof,&rdquo; arXiv:2605.23951, 2026.",
 "&ldquo;WebRLED: Curiosity-Driven Deep Reinforcement Learning for Web GUI Testing,&rdquo; arXiv:2504.19237, 2025.",
 "&ldquo;Adversarial Reinforcement Learning for Large Language Model Agent Safety (ARLAS),&rdquo; arXiv:2510.05442, 2025.",
 "&ldquo;FLORA: GNN-Based Performance Prediction for Agentic Workflows / FLORA-Bench,&rdquo; arXiv:2503.11301, 2025.",
 "&ldquo;SVRepair,&rdquo; arXiv:2602.06090; &ldquo;GALA,&rdquo; arXiv:2604.08089; &ldquo;VisualRepair,&rdquo; arXiv:2607.14075 — multimodal automated program repair, 2026.",
 "&ldquo;AgentSHAP: Interpreting LLM Agent Tool Importance with Monte Carlo Shapley Value Estimation,&rdquo; arXiv:2512.12597, 2025.",
 "&ldquo;GNN-Coder: Boosting Semantic Code Retrieval with Combined GNNs and Transformer,&rdquo; arXiv:2502.15202, 2025.",
 "&ldquo;System Prompt Optimization with Meta-Learning,&rdquo; arXiv:2505.09666, 2025.",
 "&ldquo;Autonomous QA Agent: RAG-Grounded Test Script Generation,&rdquo; arXiv:2601.06034, 2026.",
 "&ldquo;ST-WebAgentBench: Evaluating Safety and Trustworthiness of Web Agents (Completion-under-Policy),&rdquo; arXiv, 2024/2025.",
 "&ldquo;OSWorld-MCP: Tool-vs-GUI Evaluation with Auto-Generated MCP Tools,&rdquo; 2025/2026.",
 "W3C Web Machine Learning CG, &ldquo;WebMCP,&rdquo; Draft Community Group Report, Feb 2026 (verify date). github.com/webmachinelearning/webmcp.",
 "Combination of Isolation Forest and LSTM Autoencoder for Anomaly Detection — hybrid detector literature (network intrusion detection).",
]
for r in refs:
    story.append(Paragraph(r, st_ref))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "Note: several 2026 arXiv preprints above may still be under review; confirm final versions, "
    "authors and claims before citing them as settled prior art in the submitted manuscript.",
    st_small))

# ================================================================ BUILD
frame = Frame(M, 20 * mm, PAGE_W - 2 * M, PAGE_H - 40 * mm, id="f")
frame_cover = Frame(M, 22 * mm, PAGE_W - 2 * M, PAGE_H - 45 * mm, id="fc")
doc = BaseDocTemplate("/home/claude/specx/SpecX_Project_Draft.pdf", pagesize=A4,
                      leftMargin=M, rightMargin=M, topMargin=20*mm, bottomMargin=20*mm,
                      title="SpecX — Project Draft",
                      author="Shashank — VIT, B.Tech CSE (Data Science)")
doc.addPageTemplates([
    PageTemplate(id="cover", frames=[frame_cover], onPage=on_cover),
    PageTemplate(id="content", frames=[frame], onPage=on_page),
])
doc.build(story)
print("PDF built OK")
