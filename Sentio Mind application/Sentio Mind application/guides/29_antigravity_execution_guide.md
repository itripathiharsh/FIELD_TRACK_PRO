# FieldTrack Pro — Antigravity Execution Guide
### How the agent should actually work through these 28 documents

This is not another planning doc — it's the operating manual *for the agent itself*. Read this first, before Phase 1.

---

## 1. Context-Loading Protocol (Before Any Code)

Antigravity should NOT be handed all 28 files at once and told "build this." That's exactly the setup for hallucinated shortcuts and silent scope drift. Instead:

### Step 0 — Memory Anchor (once, at the very start)
Feed the agent these 5 files first, and only these, with an explicit instruction to summarize them back before proceeding:
```
01_requirements.md
02_user_flows.md
03_features.md
04_tech_stack.md
05_architecture.md
```
Prompt: *"Read these 5 documents. Before doing anything else, summarize back to me: (1) the product's core purpose in 2 sentences, (2) the 4 locked product decisions from Requirements Section 4, (3) the tech stack choices. Do not proceed to any build task until this summary is confirmed correct."*

This forces the agent to actually process the grounding context rather than skim it, and gives you one checkpoint to catch a misread before any code exists.

### Step 1 — Per-Phase Loading (repeated for every phase)
When starting a new phase, feed **only that phase's folder** plus the "Key Business Rules Index" from `27_documentation.md` Section 5 (small, cheap, and it's the one artifact that prevents the agent from re-deriving — or worse, mis-deriving — a decision that was already made three phases ago). Do not re-feed the entire 28-doc set every time — it wastes context and increases the odds the agent latches onto an outdated or superseded detail from an early draft.

---

## 2. Phase Execution Order (Non-Negotiable Sequence)

```
Phase 1 → Phase 2 → Phase 2.5 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 8 → Phase 9 → Phase 10
```
Phase 11 (Future Roadmap) is reference-only — never fed to the agent as a build task unless you explicitly decide to pull a specific item forward.

**Do not let the agent skip ahead or batch phases**, even if it offers to "save time" by building Android and Web in parallel. The reordering work already done (Maps/Location and File/Media moved before Android specifically so Android isn't built against stubs) only holds if the sequence is respected. An agent optimizing for speed will naturally want to parallelize — this is the one instruction worth repeating at the start of every phase.

---

## 3. Task Boundaries — Breaking Each Phase Into Bounded Units

This is the core fix for "does it all itself and hallucinates." A phase folder is not one task — it's a checklist of tasks, executed one at a time, each with its own stop-and-verify point.

### Rule: One Module/Screen/Endpoint Group Per Task
Never prompt "build Phase 6." Instead, break it into the sub-sections the doc already has:
```
Task 6.1 — UI/UX shell + navigation graph
Task 6.2 — Authentication (login, token storage, interceptor)
Task 6.3 — Dashboard + Visit Detail screens
Task 6.4 — GPS check-in flow
Task 6.5 — Geofencing registration
Task 6.6 — Requirement form
Task 6.7 — Uploads (photos, docs, signatures)
Task 6.8 — Screen-by-screen real-backend verification (per the testing table already in the doc)
```
Each task = one prompt, one review, one commit. Do not let the agent chain multiple tasks in a single unsupervised run.

### Rule: Every Task Ends With a Stated Diff, Not Just "Done"
Require the agent to explicitly state: which files it created/changed, which endpoints/screens it touched, and which of the doc's feature IDs (e.g., `E5`, `G3`, `I6`) it believes it satisfied. If it can't map its own output back to a feature ID from `03_features.md`, that's a signal it drifted from spec — stop and check before continuing.

### Rule: Non-Negotiables Get Their Own Verification Prompt
These four items (from Security Design's summary) are the ones where a subtle agent shortcut would silently break the product's core value — after any task that touches them, explicitly ask the agent to confirm, in its own words, that it did NOT take a shortcut:
1. Server-side geo-verification (never client-trusted)
2. Insert-only, immutable `geo_verification_logs`
3. Resource-ownership checks on every visit-scoped endpoint
4. Mock-location detection at check-in

An agent under implicit pressure to "make it work" will sometimes quietly loosen a security check to get a test passing. Asking it to restate what it did, rather than just asking "does this work," is more likely to surface that kind of shortcut.

### Rule: No New Decisions Without Flagging
If the agent hits an ambiguity not covered by the docs, the instruction is: **stop and ask, do not assume and proceed.** Every open question in this project so far got resolved by you as product owner, on the record, in a doc — the agent should follow that same discipline rather than silently picking its own default the way it might on an unscoped task.

---

## 4. Suggested Prompt Template (Per Task)

```
Context: [paste relevant phase doc section, e.g. "23_android_application.md, Section 4 (GPS)"]
Also load: Key Business Rules Index (27_documentation.md, Section 5)

Task: Implement Task 6.4 — GPS check-in flow, exactly as specified in the section above.

Constraints:
- Do not modify files outside what this task requires.
- Do not skip ahead to other tasks even if related code seems adjacent.
- If anything is ambiguous or not covered by the doc, stop and ask rather than assuming.
- When done, list: files changed, feature IDs satisfied (cross-reference 03_features.md),
  and explicitly confirm you did not weaken any of the 4 non-negotiables from Security Design.
```

---

## 5. Phase Completion Checkpoint (Before Moving to the Next Phase)

At the end of every phase folder, before loading the next one:
- [ ] Every task in that phase's checklist has been completed and reviewed individually (not batch-approved)
- [ ] The phase's own smoke-test/verification section (where one exists — Phase 3, Phase 6, Phase 8 all have explicit tables) has actually been run, not assumed
- [ ] Any new gap discovered mid-phase (like the idempotency key column, or the missing unique constraint) has been logged somewhere durable — a running `DECISIONS_LOG.md` is worth starting now if you don't have one, since this project has already generated several of these mid-build discoveries and will likely generate more

---

## 6. What This Guide Deliberately Does Not Cover

Feature-level pass/fail criteria (what "actually working" means for each of the 63 features, checked via both API and UI) is intentionally a separate document — see the Definition of Done doc. This guide governs *process discipline*; that one governs *acceptance criteria*. Keeping them separate means you can hand the DoD doc to a human tester independently of whether they understand the agent workflow at all.
