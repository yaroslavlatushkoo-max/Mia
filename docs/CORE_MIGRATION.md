# Mia — Core Migration Plan

> Architectural contract for the gradual migration of the existing Mia assistant
> from the legacy `main.py`/skills architecture to a modular local-first agent.
>
> Source: `Миграция ядра.docx`, consolidated into an implementation-oriented Markdown document.

## 1. Migration principle

The migration is **not a rewrite**.

```text
Legacy Mia remains usable
        ↓
New core is built beside it
        ↓
Legacy modules are wrapped by adapters
        ↓
Orchestrator gradually takes control
        ↓
Legacy paths are retired only after verification
```

Rules:

- Preserve working legacy functionality during migration.
- Prefer adapters over rewriting working modules.
- Do not connect everything to the new core at once.
- Every migration step must be testable and reversible.
- New architecture becomes the source of truth for new code.
- Legacy remains available until its replacement is verified.

## 2. Target architecture

```text
USER / EVENTS
      ↓
PERCEPTION
(text / voice / vision / events)
      ↓
ROUTER
(intent / mode / domain / complexity)
      ↓
COST ESTIMATOR
(budget / max steps / tool budget)
      ↓
POLICY
(allowed / risk / confirmation / local-vs-cloud)
      ↓
TASK CONTEXT + EXECUTION TRACE
      ↓
 ┌───────────────┐
 │               │
 ▼               ▼
DIRECT RESPONSE  PLANNER
                 ↓
             TOOL REGISTRY
                 ↓
             AGENT LOOP
                 ↓
             OBSERVATION
                 ↓
             VERIFICATION
                 ↓
          NEXT STEP / REPLAN
                 ↓
              RESPONDER
                 ↓
          CHARACTER LAYER
```

Architectural style:

- modular monolith;
- one central agent loop;
- event-driven capability planned for later;
- explicit Policy layer;
- structured tool use;
- local-first model strategy;
- adapters for legacy functionality.

Do **not** introduce microservices or a multi-agent architecture merely to make the system look more modern.

## 3. Separation of responsibilities

### Router

Determines what the request appears to be:

- intent;
- mode;
- domain;
- complexity;
- entities;
- confidence.

Router does **not** decide whether an action is allowed.

### CostEstimator

Turns routing information into an execution budget:

- reasoning budget;
- output budget;
- maximum tool calls;
- maximum execution steps;
- approximate time/cost.

Complexity levels:

```text
C0 — instant
C1 — simple response
C2 — analysis
C3 — one-tool task
C4 — multi-tool task
C5 — autonomous/complex task
```

### Policy

Answers:

- Is this action allowed?
- What is its risk?
- Is confirmation required?
- Is local execution allowed?
- Is cloud fallback allowed?
- What scope/permissions apply?

Policy must influence actual execution, not merely produce metadata.

### TaskContext

Represents the task itself:

- task/session identifiers;
- original request;
- intent;
- mode;
- domain;
- complexity;
- risk;
- budget;
- constraints;
- timestamps;
- routing/policy decisions.

### ExecutionTrace

Represents what happened:

- steps;
- tool calls;
- observations;
- errors;
- artifacts;
- verification results;
- current status;
- current step;
- replan history.

`TaskContext` and `ExecutionTrace` must remain separate.

## 4. Planner

Use two planning levels:

### Fast Plan

For C2–C3:

- one action;
- or a short sequence of actions.

### Deep Plan

For C4–C5:

- multi-step plan;
- dependencies;
- alternatives;
- success criteria;
- verification points.

Planner should use structured output.

LLM is an enhancement to planning, not the only source of truth. Rule-based fallback must remain available.

## 5. Tool Registry

Tool Registry is a **capability layer**, not just a dictionary.

A tool should expose metadata such as:

```text
name
description
input_schema
output_schema
side_effects
risk_level
permissions
requires_confirmation
timeout
cost_hint
fallback
```

Conceptual groups:

```text
safe_read_tools
local_mutation_tools
external_network_tools
dangerous_system_tools
```

During migration, classify legacy-backed tools as:

- `REAL` — implemented and usable;
- `ADAPTER` — delegates to legacy functionality;
- `STUB` — deliberately incomplete;
- `BROKEN` — exists but cannot safely perform its advertised action.

A stub must never silently masquerade as a successful real capability.

## 6. Agent Loop

The core loop is:

```text
plan
  ↓
execute
  ↓
observe
  ↓
verify
  ↓
next step / final
```

On failure:

```text
execute
  ↓
observation = failure
  ↓
replan
  ↓
execute alternative plan
```

The loop must have:

- bounded replans;
- bounded execution steps;
- explicit failure state;
- execution trace;
- observations;
- tool errors;
- verification before final success.

Replanning must be real control flow, not dead code.

## 7. Verification

Verification has three conceptual levels.

### Tool-level

The tool reports:

- success/failure;
- exit code where applicable;
- stdout/stderr;
- returned data;
- artifacts.

### Task-level

The agent checks:

- Did the result actually satisfy the goal?
- Were side effects expected?
- Is another action needed?

### User-level

For important/high-risk operations:

- present a summary;
- request confirmation where policy requires it.

For complex tasks, semantic verification through an LLM may supplement deterministic checks, but deterministic evidence remains preferable.

## 8. Responder and Character

Responder is a real architectural component.

Its responsibility is to convert:

```text
execution result
+ verification
+ relevant context
```

into a final response.

Character/ResponseStylist is separate from reasoning.

Character controls:

- tone;
- style;
- emotional expression;
- concise vs detailed presentation;
- personality.

It must not decide which tool to execute or whether an operation is safe.

The intended Mia personality is warm, attentive, slightly playful, supportive, and capable of switching to serious technical communication.

Avoid making dependency or romantic attachment the foundation of the architecture.

## 9. Memory

Memory is selective, not a dump of everything into every prompt.

Planned layers:

```text
Working Memory
Profile Memory
Episodic Memory
Semantic Memory
Procedural Memory
```

Retrieval should eventually combine:

```text
keyword/filter
+ vector similarity
+ recency
+ importance
+ task relevance
```

Memory writing should be selective:

- explicit user request;
- stable preference;
- important project context;
- recurring pattern.

Do not automatically retain temporary or sensitive information without an appropriate policy.

## 10. Legacy migration

The legacy system currently revolves around:

```text
main.py
 ↓
sequential checks
 ↓
skills
 ↓
AI fallback
```

The target is:

```text
orchestrator
 ↓
router
 ↓
cost estimator
 ↓
policy
 ↓
task context
 ↓
planner / direct response
 ↓
tools / agent loop
 ↓
verifier
 ↓
responder
```

Migration strategy:

### Phase 1 — New core beside legacy

Keep the old application usable while the new packages are developed and tested independently.

### Phase 2 — Legacy adapters

Convert useful legacy capabilities into adapters:

```text
Legacy BrowserSkill
      ↓
BrowserToolAdapter
      ↓
ToolRegistry
```

Apply the same principle to:

- system;
- files;
- browser;
- web;
- memory;
- speech;
- vision.

### Phase 3 — Core execution

Make the new Orchestrator + AgentLoop reliable before mass migration of skills.

### Phase 4 — Transfer control

Move application entry-point control from `main.py` toward a small bootstrap that starts the new application/orchestrator.

### Phase 5 — Retire legacy paths

Remove or archive legacy routing only after replacement functionality is verified.

## 11. What to preserve

Preserve and reuse where practical:

- Silero V5;
- Qwen3-TTS;
- common VoiceProfile direction;
- browser/system/file/web capabilities;
- ChromaDB and existing memory knowledge;
- useful skills through adapters;
- training datasets;
- local-first operation;
- historical voice material as reference where appropriate.

Do not restore:

- RVC WebUI;
- keyword routing as the main intelligence;
- the huge `main.py` as the central brain;
- unstructured skills as the primary capability interface;
- an architecture where the LLM decides everything without deterministic controls.

## 12. AI/model strategy

The RTX 3050 Ti 4 GB VRAM and 16 GB RAM favor a disciplined local-first strategy.

Use:

```text
deterministic routing / small local logic
        ↓
small local model for simple tasks
        ↓
coder/reasoning model for complex tasks
        ↓
cloud fallback only when policy permits and it is actually needed
```

Avoid keeping multiple large models resident in VRAM simultaneously.

The model router should load/use the appropriate provider on demand.

## 13. Structured outputs

Structured contracts should be used for:

- Router;
- Planner;
- Verifier;
- Tool calls where applicable.

Validate model output rather than trusting free-form text.

Example routing contract:

```json
{
  "intent": "OPEN_APPLICATION",
  "mode": "AGENT",
  "domain": "SYSTEM",
  "complexity": "C3",
  "entities": {
    "app_name": "Discord"
  },
  "confidence": 0.91
}
```

## 14. Tool-result compression

Do not send huge tool results directly into model context.

Apply:

```text
truncate
→ extract relevant content
→ summarize when necessary
→ preserve important errors/artifacts
```

This is particularly important on local hardware with limited VRAM/RAM.

## 15. Safety

Risk should be explicit.

Example:

```text
LOW
read file
search web
screenshot

MEDIUM
open app
edit file
safe command

HIGH
delete files
arbitrary shell
install software
modify system settings
```

High-risk actions should support confirmation.

Important operations should be auditable:

```text
who
what
when
why
result
```

For shell execution, progressively introduce:

- whitelist;
- timeout;
- working-directory restrictions;
- dry-run;
- confirmation.

## 16. Event-driven direction

The long-term assistant should be able to react to:

- user input;
- filesystem changes;
- application state;
- schedules;
- errors;
- other approved events.

An event bus is a planned part of the architecture, but it should not delay completion of the core agent loop.

## 17. UI direction

Do not prioritize a complex UI before the core works.

Eventually useful surfaces include:

- tray;
- chat window;
- overlay;
- voice activation;
- task progress;
- confirmation dialogs;
- debug/log panel.

Agent tasks should expose useful progress such as:

```text
1. Finding project
2. Checking changed files
3. Analyzing errors
Progress: 2/5
```

## 18. Evaluation and observability

Maintain an evaluation harness for representative tasks:

```text
"Привет"                    → C0 / companion
"Что ты помнишь?"           → memory query
"Открой браузер"            → tool task
"Проверь проект"            → C5 agent
"Удали папку"               → high risk / confirmation
```

After substantial changes, inspect:

- routing decision;
- planner output;
- policy decision;
- tool calls;
- observations;
- errors;
- verification;
- latency;
- model used;
- token/resource usage.

## 19. Current implementation order

The architecture must be implemented in this order unless a concrete dependency requires otherwise:

```text
Router
  ↓
CostEstimator
  ↓
TaskContext + ExecutionTrace
  ↓
Policy
  ↓
Planner
  ↓
ToolRegistry
  ↓
AgentLoop
  ↓
Verification
  ↓
Responder
  ↓
Adapters
  ↓
Memory integration
  ↓
Character integration
  ↓
Speech / Vision / Events / UI
  ↓
Legacy main.py retirement
```

The current repository already contains a first implementation of much of this structure. The next work should **repair integration gaps in the existing implementation**, not replace the architecture.

## 20. Current migration state

At the current baseline:

- the new `mia/` architecture exists beside legacy code;
- Router, CostEstimator, TaskContext, ExecutionTrace, Planner, ToolRegistry, AgentLoop and Verifier exist;
- integration is incomplete;
- Policy must affect actual execution;
- AgentLoop must have real bounded replanning;
- Verification needs deterministic task-level semantics;
- Responder must be a real component;
- legacy entry points remain untouched until the new core is stable.

This is an intermediate migration state, not the finished assistant.

## 21. Definition of success

The migration succeeds when:

- legacy Mia remains usable during migration;
- new core handles structured requests;
- complexity controls resource usage;
- Policy controls risky actions;
- TaskContext and ExecutionTrace remain separate;
- Planner handles multi-step work;
- ToolRegistry exposes capabilities through schemas;
- AgentLoop performs observe/act/replan cycles;
- Verification confirms actual completion;
- memory is selectively integrated;
- character is separated from reasoning;
- legacy modules are reused through adapters where sensible;
- `main.py` eventually becomes a bootstrap;
- Mia behaves as one coherent local-first personal AI rather than a collection of keyword skills.

## 22. Explicit non-goals

Do not introduce:

- multi-agent swarm architecture;
- microservices;
- a giant replacement `main.py`;
- training as the sole source of intelligence;
- RVC WebUI;
- romantic dependency as an architectural mechanism;
- mass legacy rewrites before adapters and tests exist.

## 23. Change discipline

Before substantial migration:

```text
working tree clean
→ checkpoint/commit
→ inspect relevant code/docs
→ make one coherent change
→ test
→ inspect diff
→ commit
```

For every migration step:

1. Read the relevant architecture.
2. Inspect the existing implementation.
3. Identify the migration target.
4. Make the smallest coherent change.
5. Update tests.
6. Run syntax/tests.
7. Review the diff.
8. Record remaining limitations.

When uncertain, inspect the existing implementation and `migration/legacy_map.json` before choosing a direction.

---

## Appendix A — Original source context

The original migration document is a working design/history document generated during the project's architecture planning. This Markdown file is the **implementation-oriented architectural contract** derived from it.

The source document contains exploratory discussion and earlier intermediate code proposals. When source examples conflict with the current repository implementation, prefer:

1. the architectural principles above;
2. the current repository's tested contracts;
3. a minimal migration path;
4. preservation of working legacy behavior.

Never copy an old intermediate implementation blindly merely because it appears in the historical document.

## Appendix B — Core rule

> **Do not make the repository look modern. Make Mia gradually become a reliable local-first autonomous assistant without losing the working parts of the existing project.**
