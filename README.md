# Dive into Claude Code: The Design Space of Today's AI Agent System

<p align="center">
  <img src="./assets/main_structure.png" width="85%" alt="High-level system structure of Claude Code">
</p>

<p align="center">
  <a href="https://arxiv.org/abs/XXXX.XXXXX"><img src="https://img.shields.io/badge/arXiv-XXXX.XXXXX-b31b1b.svg" alt="arXiv"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-CC--BY--NC--SA--4.0-lightgrey.svg" alt="License"></a>
  <a href="https://github.com/XXX/Dive-into-ClaudeCode/stargazers"><img src="https://img.shields.io/github/stars/XXX/Dive-into-ClaudeCode?style=social" alt="Stars"></a>
</p>

> **A source-level architectural analysis of Claude Code (v2.1.88, ~1,900 TypeScript files, ~512K lines of code), revealing the design patterns, engineering trade-offs, and system-level decisions that power one of the most capable AI coding agents in production.**

<!-- TODO: Update author list -->
**Authors:** _To be updated._

---

## Key Highlights

- **98.4% Infrastructure, 1.6% AI** -- Only ~1.6% of Claude Code's codebase is AI decision logic. The vast majority is deterministic operational harness -- permission gates, tool routing, context management, and recovery logic.
- **The Loop Is Simple; Everything Around It Is Not** -- The core agent loop is a straightforward while-loop (ReAct pattern). The real engineering complexity lives in the surrounding subsystems: a 7-mode permission system, a 5-layer context compaction pipeline, 4 extensibility mechanisms, subagent isolation, and append-only session storage.
- **Five Human Values Drive Every Design Decision** -- The architecture traces from five values (human authority, safety, reliability, capability amplification, contextual adaptability) through 13 design principles to specific implementation choices.
- **Defense in Depth -- But With Shared Failure Modes** -- Seven independent safety layers protect the system, but they share economic constraints (token costs). Commands exceeding 50 subcommands bypass security analysis entirely.
- **The Pre-Trust Execution Window** -- Five patched CVEs share a root cause: hooks and MCP servers execute during initialization *before* the trust dialog appears, creating a structurally privileged attack window.
- **Context Window as the Binding Constraint** -- The ~200K-token context window drives nearly every architectural decision. Five compaction layers, lazy-loaded instructions, deferred tool schemas, and summary-only subagent returns all exist because context is scarce.
- **What Resists Reimplementation** -- A comparison with OpenClaw shows the agent loop is easy to replicate, but cross-cutting harness systems (hooks pipeline, auto-mode classifier, graduated compaction, worktree isolation) are largely absent.

---

## Table of Contents

- [Overview](#overview)
- [Values, Design Principles, and the Design Space](#values-design-principles-and-the-design-space)
- [Architecture Overview](#architecture-overview)
- [Turn Execution: The Agentic Query Loop](#turn-execution-the-agentic-query-loop)
- [Tool Authorization and Permission System](#tool-authorization-and-permission-system)
- [Extensibility: MCP, Plugins, Skills, and Hooks](#extensibility-mcp-plugins-skills-and-hooks)
- [Context Construction and Memory](#context-construction-and-memory)
- [Subagent Delegation and Orchestration](#subagent-delegation-and-orchestration)
- [Session Persistence and Recovery](#session-persistence-and-recovery)
- [Comparative Analysis: Claude Code vs. OpenClaw](#comparative-analysis-claude-code-vs-openclaw)
- [Discussion: Implications for Agent Builders](#discussion-implications-for-agent-builders)
- [Citation](#citation)
- [License](#license)

---

## Overview

Claude Code is an agentic coding tool released by Anthropic that can run shell commands, edit files, and call external services on behalf of the user. Despite growing adoption, Anthropic publishes user-facing documentation but not detailed architectural descriptions.

This paper fills that gap through **source-level analysis** of the extracted TypeScript codebase (v2.1.88), supplemented by official Anthropic documentation and a comparison with [OpenClaw](https://github.com/anthropics/anthropic-cookbook/tree/main/misc/open_claw), an open-source project that mirrors Claude Code's structure.

The analysis identifies **five human values** that motivate the architecture and traces them through **thirteen design principles** to specific implementation choices. It reveals that:

- The core of the system is a simple while-loop that calls the model, runs tools, and repeats.
- Most of the code, however, lives in the systems _around_ this loop.
- The architecture strongly amplifies short-term capability but provides few mechanisms that explicitly preserve long-term human understanding and codebase coherence.

The paper is organized in two parts: (1) a **design-space analysis** identifying recurring design questions that all coding agents must navigate, and (2) a **comparative calibration** with OpenClaw revealing which design commitments resist reimplementation.

---

## Values, Design Principles, and the Design Space

The paper argues that production coding agents embed human values in their architectural choices. Claude Code's architecture is driven by **five human values**:

| Value | Core Idea | Architectural Consequence |
|:------|:----------|:--------------------------|
| **Human Decision Authority** | Humans retain ultimate control via a principal hierarchy (Anthropic > operators > users) | Deny-first evaluation, graduated trust spectrum, append-only audit state |
| **Safety, Security, and Privacy** | The system protects even when human vigilance lapses | 7 independent safety layers, shell sandboxing, non-restoration of permissions on resume |
| **Reliable Execution** | Does what the human meant, stays coherent over time | Gather-act-verify loop, 5-layer compaction pipeline, graceful recovery |
| **Capability Amplification** | Materially increases what humans can accomplish | Deterministic infrastructure over decision scaffolding (98.4% harness, 1.6% AI logic) |
| **Contextual Adaptability** | Fits the user's context; the relationship improves over time | 4-level CLAUDE.md hierarchy, graduated extensibility, evolving trust trajectories |

A key empirical finding: when users approve 93% of permission prompts, the architectural response is not more warnings but **restructured boundaries** -- sandboxing and classifiers within which the agent works freely, rather than per-action approval that users stop reviewing.

These values are operationalized through **13 design principles** (Table 1 in the paper), including deny-first with human escalation, graduated trust spectrum, defense in depth, externalized programmable policy, context as scarce resource, append-only durable state, and minimal scaffolding with maximal operational harness.

<details>
<summary><b>The 13 Design Principles</b> (click to expand)</summary>

| Principle | Values Served | Design Question |
|:----------|:-------------|:----------------|
| Deny-first with human escalation | Authority, Safety | Should unrecognized actions be allowed, blocked, or escalated? |
| Graduated trust spectrum | Authority, Adaptability | Fixed permission level, or a spectrum users traverse over time? |
| Defense in depth with layered mechanisms | Safety, Authority, Reliability | Single safety boundary, or multiple overlapping ones? |
| Externalized programmable policy | Safety, Authority, Adaptability | Hardcoded policy, or externalized configs with lifecycle hooks? |
| Context as scarce resource with progressive management | Reliability, Capability | Single-pass truncation or graduated pipeline? |
| Append-only durable state | Reliability, Authority | Mutable state, checkpoint snapshots, or append-only logs? |
| Minimal scaffolding, maximal operational harness | Capability, Reliability | Invest in scaffolding-side reasoning, or operational infrastructure? |
| Values over rules | Capability, Authority | Rigid decision procedures, or contextual judgment with deterministic guardrails? |
| Composable multi-mechanism extensibility | Capability, Adaptability | One unified extension API, or layered mechanisms at different context costs? |
| Reversibility-weighted risk assessment | Capability, Safety | Same oversight for all actions, or lighter for reversible ones? |
| Transparent file-based configuration and memory | Adaptability, Authority | Opaque database, embedding-based retrieval, or user-visible files? |
| Isolated subagent boundaries | Reliability, Safety, Capability | Subagents share parent context and permissions, or operate in isolation? |
| Graceful recovery and resilience | Reliability, Capability | Fail hard on errors, or recover silently and reserve human attention for unrecoverable situations? |

</details>

The paper also applies a sixth concern -- **long-term capability preservation** -- as an evaluative lens. Citing evidence that developers who fully delegate to AI score 17% lower on comprehension tests, the paper asks whether short-term amplification comes at the cost of long-term human understanding.

---

## Architecture Overview

Claude Code's architecture answers **four recurring design questions** that every production coding agent must face:

| Design Question | Claude Code's Answer | Alternative Approaches |
|:----------------|:---------------------|:----------------------|
| **Where does reasoning live?** | Model reasons; harness enforces. Only ~1.6% is AI decision logic. | LangGraph: explicit state graphs. Devin: multi-step planners. |
| **How many execution engines?** | One single `queryLoop` function regardless of interface (CLI, SDK, IDE). | Mode-specific engines for different surfaces. |
| **What is the default safety posture?** | Deny-first: deny rules evaluated before ask rules before allow rules. | Container isolation (SWE-Agent), git rollback (Aider). |
| **What is the binding resource constraint?** | The ~200K-token context window. 5 compaction strategies run before every model call. | Compute budget, explicit scratchpad/working memory. |

### High-Level System Structure

The system decomposes into **7 functional components** (Figure 1 above):

1. **User** -- Submits prompts, approves permissions, reviews output
2. **Interfaces** -- Interactive CLI, headless CLI (`claude -p`), Agent SDK, IDE/Desktop/Browser
3. **Agent Loop** -- The iterative cycle of model call, tool dispatch, and result collection (`queryLoop` async generator)
4. **Permission System** -- Deny-first rule evaluation, auto-mode ML classifier, hook-based interception
5. **Tools** -- Up to 54 built-in tools + MCP-provided tools, assembled via `assembleToolPool`
6. **State & Persistence** -- Append-only JSONL session transcripts, global prompt history, subagent sidechains
7. **Execution Environment** -- Shell with optional sandboxing, filesystem, web fetching, MCP connections

All entry surfaces converge on the same agent loop -- the interactive CLI, headless CLI, Agent SDK, and IDE integration all flow through the same `queryLoop` function.

### 5-Layer Subsystem Decomposition

The 7-component model expands into **21 subsystems** across five layers:

- **Surface Layer** -- Entry points and rendering (CLI, headless, SDK, IDE)
- **Core Layer** -- Context assembly, agent loop, compaction pipeline, subagent spawning
- **Safety/Action Layer** -- Permissions (7 modes), auto-mode classifier, hook pipeline (27 events), tool pool, shell sandbox
- **State Layer** -- Runtime state, session persistence, CLAUDE.md + memory hierarchy, sidechain transcripts
- **Backend Layer** -- Shell execution, MCP server connections, 42 tool subdirectories

---

## Turn Execution: The Agentic Query Loop

<p align="center">
  <img src="./assets/iteration.png" width="60%" alt="Runtime turn flow">
</p>

The core loop follows the **ReAct pattern** (reason + act + observe) implemented as a **9-step pipeline** per turn:

1. **Settings resolution** -- Load configuration
2. **State initialization** -- Set up session state
3. **Context assembly** -- Build the context window from 9 ordered sources
4. **5 pre-model context shapers** -- Sequential compression pipeline
5. **Model call** -- Send assembled context to Claude
6. **Tool dispatch** -- Parse `tool_use` blocks from model response
7. **Permission gate** -- Evaluate deny-first rules, classifier, hooks
8. **Tool execution** -- Run approved actions
9. **Stop condition evaluation** -- Check termination criteria

### The 5 Pre-Model Context Shapers

Before *every* model call, five sequential shapers manage context pressure, applying the least disruptive compression first:

| Stage | Strategy | What It Handles |
|:------|:---------|:----------------|
| 1. **Budget Reduction** | Per-message size limits | Individual tool outputs that overflow size limits |
| 2. **Snip** | Lightweight older-history trimming | Temporal depth (old conversation turns) |
| 3. **Microcompact** | Fine-grained cache-aware compression | Cache overhead and prompt caching optimization |
| 4. **Context Collapse** | Read-time virtual projection (does NOT mutate stored history) | Very long conversation histories |
| 5. **Auto-Compact** | Full model-generated summary (last resort) | When all cheaper strategies are insufficient |

### Execution Model and Recovery

- **Concurrent-read, serial-write**: The `StreamingToolExecutor` begins executing tools as they stream in, with a fallback `runTools` path
- **Recovery mechanisms**: Max output tokens escalation (up to 3 retries), reactive compaction, prompt-too-long handling, streaming fallback, and a fallback model
- **5 stop conditions**: No tool use, max turns, context overflow, hook intervention, explicit abort

---

## Tool Authorization and Permission System

<p align="center">
  <img src="./assets/permission.png" width="75%" alt="Permission gate overview">
</p>

### 7 Permission Modes

The permission system implements a **graduated trust spectrum**:

| Mode | Behavior | Trust Level |
|:-----|:---------|:------------|
| `plan` | User approves all plans | Lowest |
| `default` | Standard interactive approval | Low |
| `acceptEdits` | File edits auto-approved, shell needs approval | Medium |
| `auto` | ML classifier evaluates tool safety | High |
| `dontAsk` | Minimal prompting | Higher |
| `bypassPermissions` | Skips most prompts (safety-critical checks remain) | Highest |
| `bubble` | Internal: subagent escalation to parent | (Special) |

**Key design choice: deny-first evaluation.** A broad deny rule (e.g., "deny all shell commands") *cannot* be overridden by a narrow allow rule (e.g., "allow npm test"). The strictest rule always wins.

### 7 Independent Safety Layers

A request must pass through all applicable layers -- any single layer can block it:

1. **Tool pre-filtering** -- Blanket-denied tools removed from model's view entirely
2. **Deny-first rule evaluation** -- Deny rules always take precedence
3. **Permission mode constraints** -- Active mode determines baseline handling
4. **Auto-mode ML classifier** -- Separate LLM call evaluating tool safety
5. **Shell sandboxing** -- Filesystem and network isolation for shell commands
6. **Non-restoration on resume** -- Session-scoped permissions never persist across session boundaries
7. **Hook-based interception** -- PreToolUse hooks can modify or block actions

### The Auto-Mode Classifier

The `yoloClassifier.ts` implements a two-stage ML-based safety evaluation using a base system prompt and separate permission templates for internal vs. external tools. This is a separate model call, providing an independent safety judgment beyond rule-based evaluation.

---

## Extensibility: MCP, Plugins, Skills, and Hooks

Claude Code provides **four extension mechanisms**, deliberately ordered by context cost:

| Mechanism | Context Cost | What It Provides |
|:----------|:-------------|:----------------|
| **Hooks** | Zero | 27 hook events across 5 categories. Shell commands, LLM-evaluated checks, HTTP webhooks, subagent verifiers. Can block, rewrite, or annotate tool requests. |
| **Skills** | Low | SKILL.md files with YAML frontmatter. Domain-specific instructions injected via SkillTool meta-tool. |
| **Plugins** | Medium | Packaging + distribution format. Accept 10 component types: commands, agents, skills, hooks, MCP servers, LSP servers, output styles, channels, settings, user config. |
| **MCP Servers** | High | External tool integration via Model Context Protocol. Multiple transports (stdio, SSE, HTTP, WebSocket, SDK, IDE). |

**Why four mechanisms?** Each trades deployment complexity for different extensibility at different context costs. Zero-context hooks can scale widely without touching the context window; high-context MCP is reserved for genuinely new tool surfaces.

### Tool Pool Assembly

`assembleToolPool` runs a 5-step pipeline: base tool enumeration (up to 54 tools) -> mode filtering -> deny rule pre-filtering -> MCP integration -> deduplication.

### Three Injection Points in the Agent Loop

Extensions can intervene at three stages:
- **assemble()** -- What the model sees (tool schemas, context)
- **model()** -- What the model can reach (available tools)
- **execute()** -- Whether and how an action runs (permission, modification, blocking)

---

## Context Construction and Memory

<p align="center">
  <img src="./assets/context.png" width="75%" alt="Context construction and memory hierarchy">
</p>

### 9 Ordered Context Sources

The context window is assembled from 9 sources, in order:

1. System prompt
2. Environment information
3. CLAUDE.md hierarchy (4 levels)
4. Path-scoped rules
5. Auto-memory entries
6. Tool metadata
7. Conversation history
8. Tool results
9. Compact summaries

### The CLAUDE.md Hierarchy

Instructions are delivered through a **4-level hierarchy**:

| Level | Path | Scope |
|:------|:-----|:------|
| Managed | `/etc/claude-code/CLAUDE.md` | System-wide (enterprise) |
| User | `~/.claude/CLAUDE.md` | Per-user preferences |
| Project | `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/rules/*.md` | Per-project conventions |
| Local | `CLAUDE.local.md` | Personal overrides (gitignored) |

**Key design choice:** CLAUDE.md is delivered as *user context*, not system prompt -- compliance is probabilistic, not deterministic. Permission rules provide the deterministic enforcement layer.

### File-Based Memory Over Vector DB

Claude Code uses **file-based memory** rather than embeddings or vector databases:
- Trades expressiveness for auditability, inspectability, and version-controllability
- No vector similarity index; uses LLM-based scan of memory-file headers to select up to 5 relevant files
- Users can directly inspect, edit, and version-control everything the agent sees

---

## Subagent Delegation and Orchestration

<p align="center">
  <img src="./assets/subagent.png" width="75%" alt="Subagent isolation and delegation">
</p>

### 6 Built-in Subagent Types

| Type | Purpose |
|:-----|:--------|
| **Explore** | Fast codebase exploration |
| **Plan** | Implementation strategy design |
| **General-purpose** | Multi-step autonomous tasks |
| **Claude Code Guide** | Documentation and help |
| **Verification** | Work validation |
| **Statusline-setup** | Configuration |

Custom subagents can be defined via `.claude/agents/*.md` files with YAML frontmatter.

### Key Difference: AgentTool vs. SkillTool

- **SkillTool** injects instructions into the *current* context window
- **AgentTool** spawns a *new isolated* context window -- the key distinction

### 3 Isolation Modes

| Mode | Mechanism | Use Case |
|:-----|:----------|:---------|
| **Worktree** | Git worktree for filesystem isolation | Parallel modifications without conflicts |
| **Remote** | Internal-only remote execution | Cloud-based execution |
| **In-process** | Shared filesystem, isolated conversation | Default mode |

### Sidechain Transcripts

Each subagent writes its own `.jsonl` transcript file. Only the **summary** returns to the parent context -- the full conversation history never enters the parent window. This prevents context explosion (subagent sessions cost ~7x tokens of standard sessions).

Multi-instance coordination uses **POSIX file locking** (`flock()`) -- zero external dependencies.

---

## Session Persistence and Recovery

<p align="center">
  <img src="./assets/session_compact.png" width="75%" alt="Session persistence and context compaction">
</p>

### Three Independent Persistence Channels

| Channel | Format | Purpose |
|:--------|:-------|:--------|
| **Session transcripts** | Append-only JSONL | Full conversation history with chain patching |
| **Global prompt history** | `history.jsonl` | Cross-session prompt recall |
| **Subagent sidechains** | Separate JSONL per subagent | Isolated subagent histories |

### Deliberate Safety Choice: Non-Restoration of Permissions

**Resume and fork do NOT restore session-scoped permissions.** Trust is always re-established in the current session. This is a deliberate safety choice -- security state never persists implicitly across session boundaries.

### Design Philosophy: Auditability Over Query Power

The append-only design means richer structured queries ("show me all tool calls that modified file X across sessions") require post-hoc reconstruction rather than direct lookup. The paper argues this trade-off is worthwhile: it preserves the ability to resume, fork, and audit sessions without modifying previously written state.

---

## Comparative Analysis: Claude Code vs. OpenClaw

The paper compares Claude Code with [OpenClaw](https://github.com/anthropics/anthropic-cookbook/tree/main/misc/open_claw) using a **three-zone framework**:

| Zone | Meaning | Examples |
|:-----|:--------|:--------|
| **Parity** | Functioning mirror | Basic agent loop, tool dispatch, message handling |
| **Partial** | Stubs or incomplete | Permission system (basic), context management (simple) |
| **Absent** | No implementation | Hook pipeline (27 events), auto-mode classifier, plugin/skill system, worktree isolation, 5-layer compaction |

### The Core Finding

> **The agent loop is straightforward to replicate. What resists reimplementation are the cross-cutting harness systems.**

The absent subsystems share common characteristics:
- Configuration-driven behavior change
- Integrated safety mechanisms
- Graduated resource management
- Cross-cutting interaction effects

This reveals that the **hardest design commitments to replicate are cross-cutting rather than modular** -- they span multiple subsystems and create emergent behaviors difficult to predict from any single component.

---

## Discussion: Implications for Agent Builders

### Design Philosophy: "Minimal Scaffolding, Maximal Operational Harness"

When frontier models converge in capability (top 3 within 1% on SWE-bench), the **quality of the operational harness becomes the principal differentiator**. This validates an architecture that invests in infrastructure over decision scaffolding.

### Value Tensions in Production

| Tension | Evidence |
|:--------|:---------|
| **Authority x Safety** | 93% approval rate = approval fatigue undermines vigilance |
| **Safety x Capability** | Token economics -- 50-subcommand bypass skips security analysis |
| **Adaptability x Safety** | CVEs from pre-trust initialization of hooks/MCP |
| **Capability x Adaptability** | Proactivity = +12-18% tasks but -50% user preference |
| **Capability x Reliability** | Bounded context prevents full codebase awareness |

### Practical Takeaways

1. **Invest in infrastructure, not scaffolding** -- As models converge in capability, the harness is the differentiator
2. **Treat context as the binding constraint** -- Build graduated compression pipelines, not single-pass truncation
3. **Layer safety mechanisms independently** -- But be aware of shared failure modes (especially economic constraints)
4. **Use graduated context-cost extensibility** -- Not all extensions need to consume context tokens
5. **Deny-first is better than approval-based** -- Users approve 93% of prompts without reviewing them
6. **Append-only persistence enables resume/fork/audit** -- The slight loss in query power is worth the flexibility
7. **Isolate subagent contexts** -- Summary-only returns prevent context explosion
8. **Mind the pre-trust execution window** -- Extension loading order relative to trust establishment is a real security concern
9. **File-based memory trades expressiveness for auditability** -- Users can inspect and version-control everything
10. **The sustainability gap is real** -- AI tools that amplify short-term productivity may erode long-term understanding

### Three Recurring Design Commitments

Across all subsystems, three cross-cutting patterns recur:
1. **Graduated layering over monolithic mechanisms** -- Safety, context, and extensibility all use stacked independent stages
2. **Append-only designs favoring auditability over query power** -- Everything can be reconstructed; nothing is destructively edited
3. **Model judgment within a deterministic harness** -- The model decides freely; the harness enforces boundaries

### The Open Question

> The most consequential open question is not how to add more autonomy, but **how to preserve human capability over time**. The architecture strongly amplifies short-term capability but provides few mechanisms that explicitly preserve long-term human understanding and codebase coherence.

---

## Citation

If you find this work useful, please consider citing:

```bibtex
@article{diveclaudecode2026,
  title={Dive into Claude Code: The Design Space of Today's AI Agent System},
  author={XXX},
  year={2026},
  url={https://arxiv.org/abs/XXXX.XXXXX}
}
```

---

## License

This work is licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
# Dive-into-ClaudeCode
