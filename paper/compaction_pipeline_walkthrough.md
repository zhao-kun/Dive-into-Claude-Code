# Context Compaction Pipeline — A Concrete Walkthrough

*Companion to §4.3 and §7.3 of "Dive into Claude Code". Written for uncle kun.*

## 1. Why five layers, not one?

Most agent frameworks use a single compression strategy: either drop the oldest messages (single-pass truncation) or call the model to summarize everything (single-step LLM summary). Claude Code instead uses **five layers** ordered by cost and aggressiveness — the paper calls this a *lazy-degradation* principle. The cheapest layer runs every turn; escalation to the next layer only happens when the previous one left too little headroom.

| # | Layer | Function | Gate | Cost | What it mutates |
| --- | --- | --- | --- | --- | --- |
| 1 | Budget reduction | `applyToolResultBudget()` | always on | O(1) per msg | tool-result content |
| 2 | Snip | `snipCompactIfNeeded()` | `HISTORY_SNIP` | O(n) | trims early segments |
| 3 | Microcompact | cache-editing path | `CACHED_MICROCOMPACT` | O(k) cache ops | removes old tool-results by id |
| 4 | Context collapse | `applyCollapsesIfNeeded()` | `CONTEXT_COLLAPSE` | O(n) projection | read-time view only |
| 5 | Auto-compact | `compactConversation()` | on (user can disable) | **one model call** | append boundary + summary |

The five shapers run in `query.ts` before every model call, on the `messagesForQuery` array. Budget reduction composes cleanly with the rest because microcompact operates purely by `tool_use_id` and never inspects content. Auto-compact fires only when the context still exceeds the pressure threshold after layers 1–4.

---

## 2. A running scenario

Imagine uncle kun is on turn 45 of a session fixing `auth.test.ts`. The session has accumulated:

- **Turn 3** — `cat src/auth/config.json` → 12 KB tool-result
- **Turn 7** — `npm test auth.test.ts` → 80 KB of stderr (stack traces)
- **Turns 12–18** — six `grep` searches across `src/auth/` → ~8 KB each, 48 KB total
- **Turn 22** — `curl https://docs.internal/api/auth` → 200 KB HTML
- **Turn 30** — `Read src/auth/session.ts` → 15 KB
- **Turns 31–44** — planning, small edits, test re-runs — ~60 KB of assistant text + small tool results

At the start of turn 45, the context window is at ~400 K tokens out of 500 K — roughly 80 % full. Every shaper is about to see this state. Let's walk through what each one does.

---

## 3. Layer 1 — Budget reduction (always on)

**What it does.** Enforces a per-tool-result size cap at the moment the result is recorded. Oversized outputs are replaced with a **content reference**; the truncated bytes are persisted to agent/session storage so they can be reconstructed on resume (`services/sessionStorage.ts`). Exempt tools (those where `maxResultSizeChars` is not finite) keep their full output.

**When it triggers.** Every turn, for every new tool-result that exceeds its cap. Runs *before* microcompact because microcompact doesn't inspect content.

**Concrete effect on our scenario.**

Turn 7's stderr is 80 KB; Bash's cap is (say) 30 KB. The stored message becomes:

```text
tool_result · tool_use_id=bash_7
└── first 30 KB of stderr, verbatim
└── [content persisted · ref:run-9f2c · 50 KB truncated · resume via ReadToolResult]
```

Turn 22's 200 KB curl output is likewise capped to (say) 40 KB + reference. Savings on turn 45's context: **~230 KB → ~70 KB** across these two messages, with zero model involvement and zero information loss at the persistence layer.

**Why this exists.** Tool outputs are the single biggest source of context bloat. A cheap size cap per result is the lowest-cost first line of defense and is the only layer that is *content-aware* — the ones above operate at message granularity.

---

## 4. Layer 2 — Snip (`HISTORY_SNIP`)

**What it does.** A lightweight trim that **removes older history segments** and returns `{ messages, tokensFreed, boundaryMessage }`. Not content-aware — it lops whole turns off the early end of the conversation and writes a small marker in their place.

**When it triggers.** When the cheaper Budget layer didn't bring the window below a looser pressure threshold. Gated by the `HISTORY_SNIP` feature flag.

**Important gotcha (from the paper).** The main token counter reads `usage.input_tokens` from the most recent assistant message, and that message *survives* snip with its pre-snip `input_tokens` still attached. So snip's savings are invisible to the counter unless explicitly plumbed through. That's why `snipTokensFreed` is passed to auto-compact — otherwise auto-compact would over-fire.

**Concrete effect.**

Turns 1–8 (initial exploration, superseded by later findings) are snipped:

```text
Before snip:                  After snip:
  [turn 1]                      [boundary · snipped turns 1..8 · freed 42 KB]
  [turn 2]                      [turn 9]
   ...                           ...
  [turn 8]                      [turn 45]
  [turn 9]
   ...
  [turn 45]
```

The boundary is a small marker message, not a summary — no model call was made.

---

## 5. Layer 3 — Microcompact (`CACHED_MICROCOMPACT`)

**What it does.** Fine-grained compression that **always runs a time-based path** and **optionally a cache-aware path** (gated by `CACHED_MICROCOMPACT`). The cache-aware path is the interesting one: it uses Anthropic's cache-editing API to **delete tool-results without invalidating the existing prompt cache**. This matters because prompt-cache hits are ~10× cheaper and ~5× faster than a cache miss on a large prompt — keeping the cache warm while shrinking content is a big win.

Microcompact operates *by `tool_use_id`* — it never reads tool-result content. That's how it composes with budget reduction (which already rewrote content references).

**When it triggers.** Every turn (time-based path). The cached path defers boundary messages until after the API response, so it can report actual `cache_deleted_input_tokens` rather than estimates.

**Concrete effect.**

Six grep results from turns 12–18, each ~8 KB, are older than the microcompact time threshold. The model's request now sees:

```text
[turn 12] assistant: grep "JWT_SECRET" src/auth/     (tool_use preserved)
[turn 12] tool_result: ⟨elided · microcompact · tool_use_id=grep_12⟩
[turn 13] assistant: grep "verifyToken" src/auth/    (tool_use preserved)
[turn 13] tool_result: ⟨elided · microcompact · tool_use_id=grep_13⟩
...
```

The *request* side survives — the model still knows what it searched for — but the **results** are gone. Savings: 48 KB with no model call. Critically, the prompt cache entry for the system prompt and CLAUDE.md is untouched, so the next `Messages.create` call still hits cache for everything above the compacted region.

**Why split `time-based` and `cached` paths?** The time-based path is the pure-heuristic fallback (no cache editing). The cached path is an optimization available only when `CACHED_MICROCOMPACT` is enabled and the API supports cache-edit operations. Separating them means the feature can be turned off without losing the heuristic.

---

## 6. Layer 4 — Context collapse (`CONTEXT_COLLAPSE`)

**What it does.** A **read-time projection** over the conversation history. Unlike the earlier layers, context collapse **does not mutate the REPL's stored history**. It replaces the `messagesForQuery` array with a projected view via `applyCollapsesIfNeeded()`. The source comment is telling:

> *"Nothing is yielded; the collapsed view is a read-time projection over the REPL's full history. Summary messages live in the collapse store, not the REPL array. This is what makes collapses persist across turns."*

So the model sees the collapsed view, but the REPL transcript — what the user scrolls through in the terminal — still has the original turns. The summaries live in a side store so they persist turn-to-turn without re-running the projection.

**When it triggers.** When all previous layers were still insufficient. Gated by `CONTEXT_COLLAPSE`.

**Concrete effect.**

Turns 15–28 were the "exploration phase" — a stretch of interleaved greps, reads, and short assistant planning blocks occupying ~80 KB. Context collapse folds them into one projected virtual message:

```text
Before (what the REPL has):         What the model sees this turn:
  [turn 15] grep ...                 [collapse · turns 15..28 · key findings:
  [turn 16] read src/auth/...         – JWT verification at session.ts:42
  [turn 17] assistant: ...            – JWT_SECRET read from env
   ...                                – test expects HS256, code uses RS256
  [turn 28] edit src/auth/...        ⟩
                                      [turn 29] ...
```

The 80 KB region becomes ~2 KB in the request. Because the REPL array is unchanged, uncle kun can scroll back and still see every turn; and if a later turn re-visits that exploration, the collapsed store can be replayed or extended without replaying work.

**Why read-time, not destructive?** Two reasons: (1) recoverability — if the user pastes `/resume` or a hook needs to replay, the full transcript is still there; (2) composability with auto-compact — the projection is cheap to re-compute each turn and doesn't fight auto-compact's own boundary writes.

---

## 7. Layer 5 — Auto-compact (`compactConversation()`)

**What it does.** The heavyweight: a **full model-generated summary**. Only fires when the previous four shapers left the window still over threshold (public web docs describe this as roughly 95 % capacity, with the "Context left until auto-compact" indicator counting down to zero). The function (`compact.ts`):

1. Fires **`PreCompact` hooks** — lets plugins or user hooks inject custom summarization instructions, and emit warnings.
2. A **GrowthBook flag** controls whether this call reuses the main conversation's prompt cache. A code comment documents a January 2026 experiment: *"false path is 98 % cache miss, costs ~0.76 % of fleet cache_creation."*
3. Builds a summary prompt via `getCompactPrompt()` and calls the model.
4. Runs `buildPostCompactMessages()` which returns:

   ```text
   [ boundaryMarker,
     ...summaryMessages,
     ...messagesToKeep,
     ...attachments,
     ...hookResults ]
   ```

5. The boundary marker is annotated via `annotateBoundaryWithPreservedSegment()` with `headUuid`, `anchorUuid`, and `tailUuid` so later reads can patch the chain.
6. Attachment builders re-announce runtime state (plans, skills, active async agents) from live app state, because compaction discards prior attachment messages but not the underlying state.
7. `runPostCompactCleanup` resets caches that would be stale; `markPostCompaction()` notifies downstream subsystems.

Crucially the design is **mostly-append**: compaction never modifies or deletes previously written transcript lines. It only appends new boundary and summary events. That preserves audit history on disk.

**Concrete effect.**

Summary produced (toy illustration of what the cookbook-style output looks like for our scenario):

```markdown
<summary>
## Task
Fix failing test auth.test.ts — "InvalidSignature" on login flow.

## Progress (turns 1–44, compacted)
- Identified: JWT verification mismatch. Test expects HS256; production
  path uses RS256 via session.ts:42.
- Patched src/auth/session.ts to branch on env JWT_ALGORITHM.
- Added RS256 path unit test case.
- Re-ran `npm test auth.test.ts` → still fails with different error:
  "JWT_SECRET undefined in test env".

## Outstanding
- Configure JWT_SECRET in the test fixtures / .env.test file.
- Re-run the suite; confirm green; then open PR.

## Preserved state
- Active plan: "auth-test-fix" (3 of 5 items done).
- Skills loaded: python-testing (from py-dev-kit plugin).
- Last edited file: src/auth/session.ts (line 42 region).
</summary>
```

Post-compact message array shrinks from ~45 turns of detail to *boundary + summary + last few kept messages + re-announced plan/skill attachments*. From Claude's cookbook measurement on a comparable sequential workflow, this step alone produced a **58.6 % token reduction** (204 K → 82 K input tokens across a 5-ticket run) — and critically, the input-token count *resets* rather than continuing to grow linearly.

**The cost users should know.** Auto-compact produces a **visible** summary in the transcript (unlike context collapse which operates silently). Microcompact emits a **boundary marker**. Everything above is auditable in the REPL view. Repeated auto-compacts compound information loss — each summary summarizes a partially-summarized history. That is why Claude Code's design runs the cheaper four layers first.

---

## 8. Putting it together — annotated turn 45

Here's what `query.ts` does on the pre-model path for turn 45 of our scenario, with numbers:

```text
incoming: ~400 KB context, ~80 % full

   ↓ applyToolResultBudget()              // always
      turn 7 stderr 80 KB → 30 KB + ref
      turn 22 curl 200 KB → 40 KB + ref
      freed: ~210 KB                              now ~ 48 % full

   ↓ snipCompactIfNeeded()                // HISTORY_SNIP
      drop turns 1..8 (bootstrap noise)
      tokensFreed: ~42 KB                         now ~ 44 % full

   ↓ microcompact (cached path)           // CACHED_MICROCOMPACT
      delete tool_results for turns 12..18 via cache-edit
      cache_deleted_input_tokens: ~48 KB          now ~ 34 % full

   ↓ applyCollapsesIfNeeded()             // CONTEXT_COLLAPSE
      collapse turns 15..28 → virtual summary
      projected savings: ~78 KB                   now ~ 18 % full

   ↓ compactConversation()                // auto-compact
      SKIPPED — below pressure threshold
```

In this case auto-compact never fires, because the four cheaper layers brought the window below threshold. If the scenario had instead been 120 turns into a huge exploration with a 480 KB conversation, auto-compact would step in as the final fallback.

---

## 9. Recovery layer — what if something still fails?

§4.4 covers failure paths that run alongside the shapers:

- **Reactive compaction** (`REACTIVE_COMPACT`): summarizes *just enough* to free space when near capacity. `hasAttemptedReactiveCompact` ensures it fires at most once per turn.
- **`prompt_too_long` handling**: if the API still returns the overflow error, the loop tries **context-collapse overflow recovery** and **reactive compaction** before terminating with `reason: 'prompt_too_long'`.
- **Max output tokens escalation**: up to 3 retries (`MAX_OUTPUT_TOKENS_RECOVERY_LIMIT = 3`) with escalated output cap.
- **Streaming fallback**, **fallback model**: alternate paths for transient API issues.

So the order of defense is: *shapers (cheap → expensive) → recovery (reactive + collapse overflow) → fallback → hard stop*.

---

## 10. Feature-flag cheat sheet

| Flag | Layer it gates | What happens if off |
| --- | --- | --- |
| *(none)* | Budget reduction | — (cannot be disabled) |
| `HISTORY_SNIP` | Snip | No early-turn trimming |
| `CACHED_MICROCOMPACT` | Microcompact cached path | Falls back to time-based path only |
| `CONTEXT_COLLAPSE` | Context collapse | No read-time projection |
| *(user setting)* | Auto-compact | User is prompted to `/compact` manually |
| `REACTIVE_COMPACT` | Reactive compaction | Overflow goes straight to hard stop |

The user-facing command **`/compact [instructions]`** manually triggers the auto-compact path with optional custom summarization instructions — the same code path the shaper calls automatically.

---

## 11. Post-compact cleanup

After **any** compaction event (auto-compact, reactive, or `/compact`):

- `runPostCompactCleanup` resets a wide range of cached state that would be stale or incorrect in the post-compaction conversation (e.g., file-read caches bound to old message IDs).
- `markPostCompaction()` signals to other subsystems that a compaction happened — useful for subagent bookkeeping, the auto-mode classifier, and the transcript renderer.
- Attachment builders re-announce runtime state (plans, skills, async agents) from live app state, since compaction discards prior attachment messages but not the underlying state.

---

## 12. Takeaways

1. **Different layers solve different problems.** Budget reduction is *per-result size control*. Snip is *wholesale age-based trimming*. Microcompact is *cache-preserving result elision*. Context collapse is a *non-destructive projection*. Auto-compact is a *model-assisted summary of last resort*.
2. **Cheap layers run every turn; expensive layers are skipped when unnecessary.** This is the lazy-degradation principle from §7.3.
3. **Mostly-append design.** The stored transcript is an audit log; compaction writes boundary markers and summaries, never edits or deletes prior entries.
4. **Context collapse is the subtle one.** It's the only shaper that doesn't mutate storage — just the model's view.
5. **The cost is complexity.** Five interacting layers, three feature flags, one user setting, plus recovery paths. The benefit is that compression can be graduated finely rather than performing one expensive step whenever pressure hits.

---

## Sources

- Chen, Q., "Dive into Claude Code", §4.3, §4.4, §7.3, arXiv:2604.14228 (primary source — definitions of each layer, function names, feature flags).
- [Automatic context compaction — Claude Cookbook](https://platform.claude.com/cookbook/tool-use-automatic-context-compaction) — concrete ticket-workflow example showing 58.6 % token reduction; structure of the `<summary>` wrapper; threshold guidance (5 K – 150 K).
- [what-is-claude-code-auto-compact — ClaudeLog](https://claudelog.com/faqs/what-is-claude-code-auto-compact/) — ~95 % trigger threshold and the "Context left until auto-compact" progress indicator.
- [Understanding "Context Left Until Auto-Compact: 0%" — Medium](https://lalatenduswain.medium.com/understanding-context-left-until-auto-compact-0-in-claude-cli-b7f6e43a62dc) — user-visible behavior of the auto-compact countdown.
- [Claude Code Compaction — Steve Kinney](https://stevekinney.com/courses/ai-development/claude-code-compaction) — narrative walk-through of the three-tier (microcompact / session memory / full compact) perspective.
- [Context Compression and Compaction — zread.ai (instructkr/claude-code)](https://zread.ai/instructkr/claude-code/15-context-compression-and-compaction) — `runPostCompactCleanup` / `markPostCompaction()` details and cache-edit path semantics.
- [How to Use the /compact Command — MindStudio](https://www.mindstudio.ai/blog/claude-code-compact-command-context-management) — `/compact` UX, cumulative-loss caveat.
- [Context Compaction Research — badlogic gist](https://gist.github.com/badlogic/cd2ef65b0697c4dbe2d13fbecb0a0a5f) — comparative notes across Claude Code, Codex CLI, OpenCode, Amp.
- [How Claude Code works — Claude Code Docs](https://code.claude.com/docs/en/how-claude-code-works) — official overview.
- [Compaction — Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/compaction) — SDK `compaction_control` parameter and threshold config.
