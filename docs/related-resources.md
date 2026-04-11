[Back to Main README](../README.md)

# Related Resources: Claude Code Community Analysis

> A curated collection of the best public analyses, reverse-engineering efforts, and technical deep-dives about Claude Code's architecture.

---

## Source Code Analysis

| Resource | Description |
|:---------|:------------|
| [Marco Kotrotsos -- "Claude Code Internals" (15-part series)](https://kotrotsos.medium.com/claude-code-internals-part-1-high-level-architecture-9881c68c799f) | The most systematic pre-leak analysis. Covers architecture, agent loop, message structure, tools, session state, permissions, sub-agents, MCP, terminal UI, and telemetry. Based on v2.0.76. |
| [George Sung -- "Tracing Claude Code's LLM Traffic"](https://medium.com/@georgesung/tracing-claude-codes-llm-traffic-agentic-loop-sub-agents-tool-use-prompts-7796941806f5) | Traced actual LLM traffic to document the agentic loop. Includes complete system prompts and full API logs. Discovered dual model usage (Opus for main loop, Haiku for metadata). |
| [Alex Kim -- "The Claude Code Source Leak"](https://alex000kim.com/posts/2026-03-31-claude-code-source-leak/) | Definitive first-responder post-leak analysis. Covers anti-distillation mechanisms, frustration detection, Undercover Mode, and auto-compaction failure stats (~250K wasted API calls/day). |
| [Haseeb Qureshi -- "Inside the Claude Code source"](https://gist.github.com/Haseeb-Qureshi/d0dc36844c19d26303ce09b42e7188c1) | Key module analysis with highlighted surprises: React/Ink UI, four compaction strategies, dynamic prompt boundary system. |
| [Agiflow -- "Reverse Engineering Prompt Augmentation Mechanisms"](https://agiflow.io/blog/claude-code-internals-reverse-engineering-prompt-augmentation/) | Identified 5 distinct prompt augmentation mechanisms backed by actual API network traces. Showed how Skills work via two-step semantic matching. |
| [Engineer's Codex -- "Diving into Claude Code's Source Code Leak"](https://read.engineerscodex.com/p/diving-into-claude-codes-source-code) | Accessible overview: modular system prompt, ~40 tools, 46K-line query engine, anti-distillation. |
| [Reid Barber -- "Reverse Engineering Claude Code"](https://www.reidbarber.com/blog/reverse-engineering-claude-code) | One of the earliest analyses (mid-2025). Documents the REPL architecture and tool suite. |
| [Kir Shatrov -- "Reverse Engineering Claude Code"](https://kirshatrov.com/posts/claude-code-internals) | Used mitmproxy to intercept API calls. Demonstrated a single experiment: 40 seconds LLM time, $0.11 cost. |

## Architecture Comparisons

| Resource | Description |
|:---------|:------------|
| [Haseeb Qureshi -- "AI Coding Agent Architecture Analysis"](https://gist.github.com/Haseeb-Qureshi/2213cc0487ea71d62572a645d7582518) | Cross-agent comparison: Claude Code vs Codex vs Cline vs OpenCode architectures. |
| [Han HELOIR YAN -- "Nobody Analyzed Its Architecture"](https://medium.com/data-science-collective/everyone-analyzed-claude-codes-features-nobody-analyzed-its-architecture-1173470ab622) | Argues the moat is the harness, not the model. Aligns with our report's thesis. |
| [DEV Community -- "Claude Code Architecture via Rust Rewrite"](https://dev.to/brooks_wilson_36fbefbbae4/claude-code-architecture-explained-agent-loop-tool-system-and-permission-model-rust-rewrite-41b2) | Architecture analysis through the lens of the claw-code Rust rewrite. 18 built-in tools in a three-layer structure. |

## GitHub Repositories

| Resource | Description |
|:---------|:------------|
| [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) | "Bash is all you need." Build a nano Claude Code agent from scratch, step by step (sessions s00-s19). Best educational resource for implementers. |
| [ultraworkers/claw-code](https://github.com/ultraworkers/claw-code) | Clean-room Rust reimplementation. 179K stars in 9 days. Reduced 512K LoC TypeScript to ~20K lines Rust. |
| [Yuyz0112/claude-code-reverse](https://github.com/Yuyz0112/claude-code-reverse) | Visualize Claude Code's LLM interactions. Interactive tool showing API requests per task scenario. |
| [nblintao/awesome-claude-code-postleak-insights](https://github.com/nblintao/awesome-claude-code-postleak-insights) | Best curated post-leak resource. Covers BUDDY, KAIROS, ULTRAPLAN, Undercover Mode, AutoDream memory consolidation. |
| [alejandrobalderas/claude-code-from-source](https://github.com/alejandrobalderas/claude-code-from-source) | 18-chapter technical book analyzing Claude Code's architecture from source maps. |
| [ComeOnOliver/claude-code-analysis](https://github.com/ComeOnOliver/claude-code-analysis) | Comprehensive reverse-engineering of internal modules and design patterns. |
| [AgiFlow/claude-code-prompt-analysis](https://github.com/AgiFlow/claude-code-prompt-analysis) | API request/response logs across 5 conversation sessions. Unique empirical methodology. |

## Specialized Deep Dives

| Topic | Resource |
|:------|:---------|
| **Memory Architecture** | [MindStudio -- "The Three-Layer Memory Architecture"](https://www.mindstudio.ai/blog/claude-code-source-leak-memory-architecture) -- In-context memory, MEMORY.md pointer index, CLAUDE.md static config. |
| **Permission System** | [Marco Kotrotsos -- "Part 8: The Permission System"](https://kotrotsos.medium.com/claude-code-internals-part-8-the-permission-system-624bd7bb66b7) |
| **Prompt Caching** | [ClaudeCodeCamp -- "How Prompt Caching Actually Works"](https://www.claudecodecamp.com/p/how-prompt-caching-actually-works-in-claude-code) |
| **MCP Integration** | [Gigi Sayfan -- "MCP Unleashed"](https://medium.com/@the.gigi/claude-code-deep-dive-mcp-unleashed-0c7692f9c2c2) |
| **Compression & Telemetry** | [WaveSpeedAI -- "Architecture Deep Dive"](https://wavespeed.ai/blog/posts/claude-code-architecture-leaked-source-deep-dive/) -- Three-layer compression, frustration metrics. |

## Open-Source Agent Systems

| System | Key Design Choice | Link |
|:-------|:-----------------|:-----|
| **OpenHands** | Container isolation, open platform | [Paper (ICLR 2025)](https://arxiv.org/abs/2407.16741) / [GitHub](https://github.com/All-Hands-AI/OpenHands) |
| **SWE-Agent** | Docker-based, custom agent-computer interface | [Paper (NeurIPS 2024)](https://arxiv.org/abs/2405.15793) / [GitHub](https://github.com/SWE-agent/SWE-agent) |
| **Aider** | Git-as-safety-net, edit format innovation | [GitHub](https://github.com/Aider-AI/aider) |
| **OpenClaw** | Claude Code structural mirror (Anthropic official) | [GitHub](https://github.com/anthropics/anthropic-cookbook/tree/main/misc/open_claw) |

## Academic References

| Paper | Relevance |
|:------|:----------|
| [A Survey on Code Generation with LLM-based Agents](https://arxiv.org/abs/2508.00083) | Comprehensive survey of AI coding agent field |
| [AI Agent Systems: Architectures, Applications, and Evaluation](https://arxiv.org/html/2601.01743v1) | Broad agent system taxonomy |
| [SWE-bench Verified Leaderboard](https://www.swebench.com/) | Primary benchmark for coding agent evaluation |

---

*Know a resource that should be listed here? Open an issue or PR.*
