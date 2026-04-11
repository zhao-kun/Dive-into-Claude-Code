# Dive into Claude Code: The Design Space of Today's AI Agent System

<p align="center">
  <img src="./assets/main_structure.png" width="85%" alt="High-level system structure of Claude Code">
</p>

<p align="center">
  <a href="https://arxiv.org/abs/XXXX.XXXXX"><img src="https://img.shields.io/badge/arXiv-XXXX.XXXXX-b31b1b.svg" alt="arXiv"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-CC--BY--NC--SA--4.0-lightgrey.svg" alt="License"></a>
  <a href="https://github.com/VILA-Lab/Dive-into-ClaudeCode/stargazers"><img src="https://img.shields.io/github/stars/VILA-Lab/Dive-into-ClaudeCode?style=social" alt="Stars"></a>
</p>

> **A source-level architectural analysis of Claude Code (v2.1.88, ~1,900 TypeScript files, ~512K lines of code), combined with a curated collection of community analyses, a design-space guide for agent builders, and a cross-system comparison matrix.**

<!-- TODO: Update author list -->
**Authors:** _To be updated._

> [!TIP]
> **TL;DR** -- Only 1.6% of Claude Code's codebase is AI decision logic. The other 98.4% is deterministic infrastructure -- permission gates, context management, tool routing, and recovery logic. The agent loop is a simple while-loop; the real engineering complexity lives in the systems around it. This repo dissects that architecture and distills it into actionable design guidance for anyone building AI agent systems.

---

## Key Highlights

- **98.4% Infrastructure, 1.6% AI** -- The world's most prominent AI coding agent is overwhelmingly deterministic harness, not AI scaffolding.
- **The Loop Is Simple; Everything Else Is Not** -- The core agent loop is a straightforward while-loop. The 7-mode permission system, 5-layer compaction pipeline, 4 extensibility mechanisms, subagent isolation, and append-only storage are where the complexity lives.
- **Five Values Drive Every Design Decision** -- Human authority, safety, reliability, capability amplification, and contextual adaptability trace through 13 principles to specific implementation choices.
- **Defense in Depth Has Shared Failure Modes** -- Seven independent safety layers, but they share token-cost constraints. 50+ subcommands bypass security analysis entirely.
- **The Pre-Trust Execution Window** -- Five patched CVEs share one root cause: extensions execute *before* the trust dialog appears.
- **Context Is the Binding Constraint** -- The ~200K-token window drives nearly every architectural decision in the system.
- **What Resists Reimplementation** -- Comparing with OpenClaw: the loop is easy to copy; the cross-cutting harness (hooks, classifier, compaction, isolation) is not.

---

<details>
<summary><b>Table of Contents</b></summary>

**Core Analysis (from our report)**
- [Architecture at a Glance](#architecture-at-a-glance)
- [Values and Design Principles](#values-and-design-principles)
- [The Agentic Query Loop](#the-agentic-query-loop)
- [Safety and Permissions](#safety-and-permissions)
- [Extensibility](#extensibility)
- [Context and Memory](#context-and-memory)
- [Subagent Delegation](#subagent-delegation)
- [Session Persistence](#session-persistence)

**Expanded Content**
- [Agent Architecture Comparison Matrix](#agent-architecture-comparison-matrix)
- [Build Your Own AI Agent: A Design Guide](#build-your-own-ai-agent-a-design-guide)
- [Key Numbers at a Glance](#key-numbers-at-a-glance)
- [Reading Guide by Role](#reading-guide-by-role)
- [Related Resources: Community Analysis](#related-resources-community-analysis)
- [Citation](#citation)
- [License](#license)

</details>

---

## Architecture at a Glance

Claude Code answers **four design questions** that every production coding agent must face:

| Question | Claude Code's Answer |
|:---------|:---------------------|
| Where does reasoning live? | Model reasons; harness enforces. ~1.6% AI, 98.4% infrastructure. |
| How many execution engines? | One `queryLoop` for all interfaces (CLI, SDK, IDE). |
| Default safety posture? | Deny-first: deny > ask > allow. Strictest rule wins. |
| Binding resource constraint? | ~200K-token context window. 5 compaction layers before every model call. |

The system decomposes into **7 components** (User → Interfaces → Agent Loop → Permission System → Tools → State & Persistence → Execution Environment) across **5 layers** expanding into 21 subsystems.

> [!NOTE]
> For the full architectural deep dive -- 7 safety layers, 9-step turn pipeline, 5-layer compaction, and more -- see **[docs/architecture.md](./docs/architecture.md)**.

<p align="right"><a href="#dive-into-claude-code-the-design-space-of-todays-ai-agent-system">Back to top</a></p>

---

## Values and Design Principles

The architecture traces from **5 human values** through **13 design principles** to implementation:

| Value | Core Idea |
|:------|:----------|
| **Human Decision Authority** | Humans retain control via principal hierarchy. When 93% approval rate showed fatigue, response was restructured boundaries, not more warnings. |
| **Safety, Security, Privacy** | System protects even when human vigilance lapses. 7 independent safety layers. |
| **Reliable Execution** | Does what was meant. Gather-act-verify loop. Graceful recovery. |
| **Capability Amplification** | "A Unix utility, not a product." 98.4% is deterministic infrastructure enabling the model. |
| **Contextual Adaptability** | CLAUDE.md hierarchy, graduated extensibility, trust trajectories that evolve over time. |

<details>
<summary><b>The 13 Design Principles</b></summary>

| Principle | Design Question |
|:----------|:----------------|
| Deny-first with human escalation | Should unrecognized actions be allowed, blocked, or escalated? |
| Graduated trust spectrum | Fixed permission level, or spectrum users traverse over time? |
| Defense in depth | Single safety boundary, or multiple overlapping ones? |
| Externalized programmable policy | Hardcoded policy, or externalized configs with lifecycle hooks? |
| Context as scarce resource | Single-pass truncation or graduated pipeline? |
| Append-only durable state | Mutable state, snapshots, or append-only logs? |
| Minimal scaffolding, maximal harness | Invest in scaffolding or operational infrastructure? |
| Values over rules | Rigid procedures or contextual judgment with deterministic guardrails? |
| Composable multi-mechanism extensibility | One API or layered mechanisms at different costs? |
| Reversibility-weighted risk assessment | Same oversight for all, or lighter for reversible actions? |
| Transparent file-based config and memory | Opaque DB, embeddings, or user-visible files? |
| Isolated subagent boundaries | Shared context/permissions, or isolation? |
| Graceful recovery and resilience | Fail hard, or recover silently? |

</details>

The paper also applies a **sixth evaluative lens** -- long-term capability preservation -- citing evidence that developers who fully delegate to AI score 17% lower on comprehension tests.

<p align="right"><a href="#dive-into-claude-code-the-design-space-of-todays-ai-agent-system">Back to top</a></p>

---

## The Agentic Query Loop

<p align="center">
  <img src="./assets/iteration.png" width="60%" alt="Runtime turn flow">
</p>

The core is a **ReAct-pattern while-loop**: assemble context → call model → dispatch tools → check permissions → execute → repeat. Implemented as an `AsyncGenerator` yielding streaming events.

**Before every model call**, five compaction shapers run sequentially (cheapest first): Budget Reduction → Snip → Microcompact → Context Collapse → Auto-Compact.

<details>
<summary><b>More details: 9-step pipeline, recovery mechanisms, stop conditions</b></summary>

**9-step pipeline per turn:** Settings resolution → State init → Context assembly → 5 pre-model shapers → Model call → Tool dispatch → Permission gate → Tool execution → Stop condition

**Two execution paths:**
- `StreamingToolExecutor` -- begins executing tools as they stream in (latency optimization)
- Fallback `runTools` -- classifies tools as concurrent-safe or exclusive

**Recovery:** Max output token escalation (3 retries), reactive compaction (once per turn), prompt-too-long handling, streaming fallback, fallback model

**5 stop conditions:** No tool use, max turns, context overflow, hook intervention, explicit abort

</details>

<p align="right"><a href="#dive-into-claude-code-the-design-space-of-todays-ai-agent-system">Back to top</a></p>

---

## Safety and Permissions

<p align="center">
  <img src="./assets/permission.png" width="75%" alt="Permission gate">
</p>

**7 permission modes** form a graduated trust spectrum: `plan` → `default` → `acceptEdits` → `auto` (ML classifier) → `dontAsk` → `bypassPermissions` (+ internal `bubble`).

**Deny-first**: A broad deny *always* overrides a narrow allow. **7 independent safety layers** from tool pre-filtering through shell sandboxing to hook interception. Permissions are **never restored on resume** -- trust is re-established per session.

> [!WARNING]
> **Shared failure modes:** Defense-in-depth degrades when layers share constraints. All safety layers share token economics -- commands exceeding 50 subcommands bypass security analysis entirely due to token cost.

<details>
<summary><b>More details: authorization pipeline, auto-mode classifier, CVEs</b></summary>

**Authorization pipeline:** Pre-filtering (strip denied tools) → PreToolUse hooks → Deny-first rule evaluation → Permission handler (4 branches: coordinator, swarm worker, speculative classifier, interactive)

**Auto-mode classifier** (`yoloClassifier.ts`): Separate LLM call with internal/external permission templates. Two-stage: fast-filter + chain-of-thought.

**Pre-trust execution window:** 5 patched CVEs share root cause -- hooks and MCP servers execute during initialization *before* the trust dialog appears, creating a structurally privileged attack window outside the deny-first pipeline.

</details>

<p align="right"><a href="#dive-into-claude-code-the-design-space-of-todays-ai-agent-system">Back to top</a></p>

---

## Extensibility

<p align="center">
  <img src="./assets/extensibility.png" width="85%" alt="Three injection points: assemble, model, execute">
</p>

**Four mechanisms at graduated context costs:** Hooks (zero) → Skills (low) → Plugins (medium) → MCP (high). Three injection points in the agent loop: **assemble()** (what the model sees), **model()** (what it can reach), **execute()** (whether/how actions run).

<details>
<summary><b>More details: tool pool assembly, hook events, plugin components</b></summary>

**Tool pool assembly** (5-step): Base enumeration (up to 54 tools) → Mode filtering → Deny pre-filtering → MCP integration → Deduplication

**27 hook events** across 5 categories with 4 execution types (shell, LLM-evaluated, webhook, subagent verifier)

**Plugin manifest** accepts 10 component types: commands, agents, skills, hooks, MCP servers, LSP servers, output styles, channels, settings, user config

**Skills:** SKILL.md with 15+ YAML frontmatter fields. Key difference -- SkillTool injects into current context; AgentTool spawns isolated context.

</details>

<p align="right"><a href="#dive-into-claude-code-the-design-space-of-todays-ai-agent-system">Back to top</a></p>

---

## Context and Memory

<p align="center">
  <img src="./assets/context.png" width="75%" alt="Context construction">
</p>

**9 ordered sources** build the context window. CLAUDE.md instructions are delivered as **user context** (probabilistic compliance), not system prompt (deterministic). Memory is **file-based** (no vector DB) -- fully inspectable, editable, version-controllable.

<details>
<summary><b>More details: CLAUDE.md hierarchy, compaction pipeline, memory retrieval</b></summary>

**4-level CLAUDE.md hierarchy:** Managed (`/etc/`) → User (`~/.claude/`) → Project (`CLAUDE.md`, `.claude/rules/`) → Local (`CLAUDE.local.md`, gitignored)

**5-layer compaction** (graduated lazy-degradation): Budget reduction → Snip → Microcompact → Context Collapse (read-time projection, non-destructive) → Auto-Compact (full model summary, last resort)

**Memory retrieval:** LLM-based scan of memory-file headers, selects up to 5 relevant files. No embeddings, no vector similarity.

</details>

<p align="right"><a href="#dive-into-claude-code-the-design-space-of-todays-ai-agent-system">Back to top</a></p>

---

## Subagent Delegation

<p align="center">
  <img src="./assets/subagent.png" width="75%" alt="Subagent architecture">
</p>

**6 built-in types** (Explore, Plan, General-purpose, Guide, Verification, Statusline) + custom agents via `.claude/agents/*.md`. **Sidechain transcripts**: only summaries return to parent (~7x token cost). Three isolation modes: worktree, remote, in-process. Coordination via POSIX `flock()`.

<details>
<summary><b>More details: SkillTool vs AgentTool, permission scoping, custom agents</b></summary>

**SkillTool vs AgentTool:** SkillTool injects into current context (cheap). AgentTool spawns isolated context (expensive, but prevents context explosion).

**Permission override:** Subagent `permissionMode` applies UNLESS parent is in `bypassPermissions`/`acceptEdits`/`auto` (explicit user decisions always take precedence).

**Custom agents:** YAML frontmatter supports tools, disallowedTools, model, effort, permissionMode, mcpServers, hooks, maxTurns, skills, memory scope, background flag, isolation mode.

</details>

<p align="right"><a href="#dive-into-claude-code-the-design-space-of-todays-ai-agent-system">Back to top</a></p>

---

## Session Persistence

Three channels: append-only JSONL transcripts, global prompt history, subagent sidechains. **Permissions never restored on resume** -- trust is re-established per session. Design favors **auditability over query power**.

<details>
<summary><b>More details: compact boundary chain patching, checkpoints</b></summary>

**Chain patching:** Compact boundaries record `headUuid`/`anchorUuid`/`tailUuid`. The session loader patches the message chain at read time. Nothing is destructively edited on disk.

**Checkpoints:** File-history checkpoints for `--rewind-files`, stored at `~/.claude/file-history/<sessionId>/`.

</details>

<p align="right"><a href="#dive-into-claude-code-the-design-space-of-todays-ai-agent-system">Back to top</a></p>

---

## Agent Architecture Comparison Matrix

How do different production agent systems answer the same design questions? Using the design-space framework from our report:

| Design Dimension | Claude Code | SWE-Agent | OpenHands | Aider | Cursor |
|:-----------------|:------------|:----------|:----------|:------|:-------|
| **Reasoning placement** | Model reasons, harness enforces (1.6% AI) | Model reasons within ACI (Agent-Computer Interface) | Model + microagents with specialized roles | Model with edit-format innovation | Model integrated in IDE context |
| **Execution engine** | Single `queryLoop` for all surfaces | Single agent loop per task | Event-driven runtime with action execution | CLI-based conversation loop | IDE-embedded, editor-aware |
| **Safety posture** | Deny-first, 7 layers, ML classifier | Docker container isolation | Docker sandbox + confirmation prompts | Git rollback as safety net | IDE permission scoping |
| **Context strategy** | 5-layer graduated compaction | Sliding window + ACI commands | Condensation with observation management | Repository map + chat history | IDE-aware, file-scoped context |
| **Extensibility** | 4 mechanisms (hooks/skills/plugins/MCP) | Custom ACI commands | Microagents + custom tools | Repository conventions | IDE extensions + rules |
| **Subagent model** | Isolated sidechain transcripts, 3 isolation modes | N/A (single agent) | Microagent delegation | N/A (single agent) | N/A (single agent) |
| **Persistence** | Append-only JSONL, no permission restoration | Trajectory logging | Event stream persistence | Git history as persistence | IDE session state |
| **Primary insight** | Harness is the moat | Interface design matters | Openness enables research | Simplicity scales | IDE integration is UX |

> [!NOTE]
> This comparison is based on publicly available documentation, papers, and source analysis. Different versions and configurations may exhibit different characteristics. We welcome corrections via issues or PRs.

<p align="right"><a href="#dive-into-claude-code-the-design-space-of-todays-ai-agent-system">Back to top</a></p>

---

## Build Your Own AI Agent: A Design Guide

> Not a coding tutorial. A guide to the **design decisions** you must make, derived from architectural analysis.

Every production agent must navigate these six decisions:

| Decision | The Question | Key Insight |
|:---------|:-------------|:------------|
| [**Reasoning placement**](./docs/build-your-own-agent.md#decision-1-where-does-reasoning-live) | How much logic in the model vs. harness? | As models converge in capability, the harness becomes the differentiator. |
| [**Safety posture**](./docs/build-your-own-agent.md#decision-2-what-is-your-safety-posture) | How do you prevent harmful actions? | Defense-in-depth fails when layers share failure modes. |
| [**Context management**](./docs/build-your-own-agent.md#decision-3-how-do-you-manage-context) | What does the model see? | Design for context scarcity from day one. Graduated > single-pass. |
| [**Extensibility**](./docs/build-your-own-agent.md#decision-4-how-do-you-handle-extensibility) | How do extensions plug in? | Not all extensions need to consume context tokens. |
| [**Subagent architecture**](./docs/build-your-own-agent.md#decision-5-how-do-subagents-work) | Shared or isolated context? | Subagent sessions cost ~7x tokens. Summary-only returns are essential. |
| [**Session persistence**](./docs/build-your-own-agent.md#decision-6-how-do-sessions-persist) | What carries over? | Never restore permissions on resume. Auditability > query power. |

**Read the full guide: [docs/build-your-own-agent.md](./docs/build-your-own-agent.md)**

<p align="right"><a href="#dive-into-claude-code-the-design-space-of-todays-ai-agent-system">Back to top</a></p>

---

## Key Numbers at a Glance

| Metric | Value | Significance |
|:-------|:------|:-------------|
| AI decision logic | **1.6%** of codebase | 98.4% is deterministic infrastructure |
| TypeScript files analyzed | **~1,900** | ~512K lines of code (v2.1.88) |
| Permission approval rate | **93%** | Users stop reviewing -- motivates restructured boundaries |
| Safety layers | **7** independent | But share token-cost failure mode |
| Compaction stages | **5** sequential | Cheapest first, last resort = full model summary |
| Built-in tools | up to **54** | 19 unconditional, 35 feature-gated |
| Hook events | **27** | Across 5 categories, 4 execution types |
| Extension mechanisms | **4** | At graduated context costs (zero → high) |
| Permission modes | **7** | From `plan` (lowest trust) to `bypassPermissions` (highest) |
| Subagent token cost | **~7x** | vs. standard sessions; summary-only returns |
| CVEs from pre-trust window | **5** | All share same architectural root cause |
| Auto-approve at 750 sessions | **>40%** | Up from ~20% at <50 sessions (trust trajectory) |
| Complexity increase (Cursor study) | **+40.7%** | Initial velocity spike dissipates by month 3 |
| Comprehension test delta | **-17%** | Developers who fully delegate to AI |

<p align="right"><a href="#dive-into-claude-code-the-design-space-of-todays-ai-agent-system">Back to top</a></p>

---

## Reading Guide by Role

| If you are a... | Start here | Then read |
|:----------------|:-----------|:----------|
| **Agent Builder** | [Build Your Own Agent Guide](./docs/build-your-own-agent.md) | [Architecture](./docs/architecture.md), [Comparison Matrix](#agent-architecture-comparison-matrix) |
| **Security Researcher** | [Safety and Permissions](#safety-and-permissions) | [Architecture: Safety Layers](./docs/architecture.md#seven-independent-safety-layers) |
| **Product Manager** | [Key Highlights](#key-highlights), [Key Numbers](#key-numbers-at-a-glance) | [Values and Principles](#values-and-design-principles) |
| **Researcher** | [Full Paper (arXiv)](https://arxiv.org/abs/XXXX.XXXXX) | [Comparison Matrix](#agent-architecture-comparison-matrix), [Related Resources](./docs/related-resources.md) |

<p align="right"><a href="#dive-into-claude-code-the-design-space-of-todays-ai-agent-system">Back to top</a></p>

---

## Related Resources: Community Analysis

The Claude Code ecosystem has produced remarkable community analyses. Here are the highlights:

| Resource | What Makes It Valuable |
|:---------|:----------------------|
| [Marco Kotrotsos' 15-part series](https://kotrotsos.medium.com/claude-code-internals-part-1-high-level-architecture-9881c68c799f) | Most systematic pre-leak analysis of Claude Code internals |
| [Alex Kim's post-leak analysis](https://alex000kim.com/posts/2026-03-31-claude-code-source-leak/) | Anti-distillation, frustration detection, ~250K wasted API calls/day |
| [Haseeb Qureshi's cross-agent comparison](https://gist.github.com/Haseeb-Qureshi/2213cc0487ea71d62572a645d7582518) | Claude Code vs Codex vs Cline vs OpenCode architectures |
| [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) | Build a nano Claude Code from scratch, step by step |
| [ultraworkers/claw-code](https://github.com/ultraworkers/claw-code) | Rust reimplementation: 512K LoC TypeScript → ~20K lines Rust. 179K stars in 9 days. |
| [George Sung's LLM traffic tracing](https://medium.com/@georgesung/tracing-claude-codes-llm-traffic-agentic-loop-sub-agents-tool-use-prompts-7796941806f5) | Complete system prompts and full API logs |
| [Agiflow's prompt augmentation reverse engineering](https://agiflow.io/blog/claude-code-internals-reverse-engineering-prompt-augmentation/) | 5 augmentation mechanisms backed by actual network traces |

**See the full curated list: [docs/related-resources.md](./docs/related-resources.md)**

<p align="right"><a href="#dive-into-claude-code-the-design-space-of-todays-ai-agent-system">Back to top</a></p>

---

## Citation

<details>
<summary>BibTeX</summary>

```bibtex
@article{diveclaudecode2026,
  title={Dive into Claude Code: The Design Space of Today's AI Agent System},
  author={XXX},
  year={2026},
  url={https://arxiv.org/abs/XXXX.XXXXX}
}
```

</details>

## License

This work is licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
