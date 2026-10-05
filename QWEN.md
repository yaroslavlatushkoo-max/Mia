# QWEN.md — MIA Project Development Contract

## 1. Project identity

This repository is the source code of **Mia**, a local-first personal AI assistant/agent for Windows.

Project root:

`A:\studia\VoiceAssistant`

Mia is being evolved from an existing working assistant into a modern agentic system inspired by the architecture of **Neurona-style assistants and modern Mega AI agents**, while staying realistic for the project's hardware:

- Windows 11
- Intel Core i5-12450H
- 16 GB RAM
- NVIDIA RTX 3050 Ti Laptop GPU, 4 GB VRAM
- Python 3.12.x
- local-first inference

The project is a **migration**, not a rewrite from zero.

---

## 2. Absolute development principles

### 2.1 Preserve the existing project

Do NOT rewrite the entire project or replace working modules merely to make the architecture look cleaner.

The migration strategy is:

```text
old Mia remains functional
        ↓
new core grows beside it
        ↓
old modules become adapters/tools
        ↓
new orchestrator gradually takes control
        ↓
legacy routing is removed only after replacement is proven
```

### 2.2 Do not destroy working functionality

Before changing an existing module:

1. inspect it;
2. understand its dependencies;
3. determine whether it currently works;
4. identify callers/importers;
5. identify side effects;
6. determine whether it should be kept, adapted, replaced, or retired;
7. make the smallest safe architectural change.

Never delete an old implementation simply because a new abstraction exists.

### 2.3 Never make `main.py` the new brain

The long-term goal is:

```text
main.py
   ↓
bootstrap
   ↓
Mia application/orchestrator
```

The old keyword-routing architecture must NOT be recreated inside a new file.

---

# 3. Target architecture

The target architecture is a modular monolith with an agent loop, event bus, policy layer, memory, character layer and tool system.

High-level flow:

```text
USER / EVENTS
      ↓
  PERCEPTION
      ↓
    ROUTER
      ↓
 COST ESTIMATOR
      ↓
    POLICY
      ↓
TASK CONTEXT + EXECUTION TRACE
      ↓
 ┌────┴─────────────┐
 ↓                  ↓
DIRECT RESPONSE   PLANNER
                    ↓
               TOOL REGISTRY
                    ↓
                AGENT LOOP
                    ↓
                OBSERVATION
                    ↓
                VERIFICATION
                    ↓
             NEXT STEP / FINAL
                    ↓
             CHARACTER LAYER
                    ↓
               RESPONDER
```

Core formula:

```text
MIA =
Perception
+ Policy
+ Planning
+ Tools
+ Memory
+ Character
+ Safety
+ UI
```

---

# 4. Current migration architecture

The migration follows these layers:

```text
training_data_v2
        ↓
      Router
        ↓
 CostEstimator
        ↓
      Policy
        ↓
  TaskContext
        +
 ExecutionTrace
        ↓
 Planner / Direct Response
        ↓
 ToolRegistry / AgentLoop
        ↓
    Verification
        ↓
     Responder
```

Later:

```text
Memory
Character
Speech
Vision
Events
UI
```

must connect to this core rather than creating independent competing brains.

---

# 5. Router

The Router is a deterministic decision layer.

Its job is to classify the request into structured metadata such as:

- intent
- mode
- domain
- complexity
- confidence
- entities
- requested tool/action
- memory requirement
- relevant tags

Important distinction:

```text
"What does the user want?"
    → INTENT

"How should Mia answer?"
    → CHARACTER / STYLE

"Does Mia need to perform an action?"
    → TOOL / AGENT

"Should something be remembered?"
    → MEMORY
```

The Router must not become a giant collection of uncontrolled keyword branches.

Rules and heuristics are appropriate for the first version.

A small local model/classifier may be added later where it provides measurable value.

---

# 6. `training_data_v2`

`training_data_v2.json` is a **structured source of examples**, not the complete behavioral brain of Mia.

Use it for:

- Router examples
- intent/domain/mode classification
- personality examples
- response style examples
- evaluation cases
- future classifier training

Do NOT assume that every future request must match a training example.

The live agent must be able to reason dynamically.

The dataset must not become a hardcoded substitute for the agent architecture.

---

# 7. Required metadata

The architecture should progressively support:

```text
INTENT
DOMAIN
MODE
PERSONALITY
EMOTION
RELATION
MEMORY
TOOL
RISK
PRIORITY
COMPLEXITY
COST/BUDGET
CONFIDENCE
```

These fields should remain structured and machine-readable.

---

# 8. Complexity and cost model

Complexity is a **routing/execution budget**, not an exact prediction of real token billing.

Use:

```text
C0 — instant
C1 — simple response
C2 — analysis
C3 — one/simple tool execution
C4 — multi-tool task
C5 — autonomous complex task
```

The CostEstimator may estimate:

```text
estimated_input_tokens
estimated_output_tokens
reasoning_budget
tool_budget
total_budget
max_steps
estimated_time
requires_llm
requires_tool
requires_planner
confidence
reasons
```

Do not pretend these values are exact.

Their purpose is to prevent wasting local resources and to choose an appropriate execution path.

General routing:

```text
C0/C1 → direct response
C2    → analysis / lightweight reasoning
C3    → tool path
C4    → planner + multi-step execution
C5    → deep plan + autonomous agent loop
```

---

# 9. Policy layer

Router decides what a request appears to be.

Policy decides what is allowed and how it may be executed.

Examples of Policy questions:

```text
Is this action allowed?
Is confirmation required?
Is the operation local?
Does it have side effects?
Is it high risk?
Should cloud fallback be allowed?
What scope is permitted?
```

Risk examples:

```text
LOW
- read file
- list files
- screenshot
- web search

MEDIUM
- open application
- write/edit a file
- safe command

HIGH
- delete files
- unrestricted shell commands
- install software
- system configuration changes
```

High-risk actions should have explicit confirmation/safety handling.

Never bypass the Policy layer simply because an LLM requested a tool.

---

# 10. TaskContext and ExecutionTrace

The migration should evolve toward two separate concepts.

## TaskContext

Stable description of the current task:

```text
task_id
session_id
original request
source
language
intent
mode
domain
complexity
risk
budget
constraints
entities
confidence
```

## ExecutionTrace

Mutable execution history:

```text
steps
tool calls
observations
errors
artifacts
verification results
current status
timestamps
final result
```

Do not mix permanent task metadata with an ever-growing execution log.

This separation is important for:

- debugging
- observability
- persistence
- task resumption
- evaluation
- future autonomous execution

---

# 11. Planner

Use two planning levels.

### Fast Plan

For C2–C3:

- one step;
- short sequence;
- minimal overhead.

### Deep Plan

For C4–C5:

- multiple steps;
- dependencies;
- success criteria;
- verification points;
- alternatives;
- replanning if an action fails.

Do not invoke an expensive deep planner for trivial C0/C1 requests.

---

# 12. Tool Registry

The Tool Registry is a **capability layer**, not merely a dictionary of functions.

Every mature tool should expose concepts such as:

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
executor
```

Tools should have structured results.

Conceptual result:

```text
success
data
error
metadata
artifacts
```

Prefer adapters over rewriting existing functionality.

Example:

```text
old BrowserSkill
      ↓
BrowserToolAdapter
      ↓
ToolRegistry
      ↓
AgentLoop
```

---

# 13. Verification

Verification is a separate control layer.

Use three levels:

### Tool-level verification

Did the tool itself succeed?

```text
success
exit_code
stdout
stderr
artifact
```

### Task-level verification

Did the result actually satisfy the requested goal?

### User-level verification

For important operations, provide a concise result summary and request confirmation where appropriate.

Important:

```text
"command executed successfully"
```

does NOT necessarily mean:

```text
"task completed successfully"
```

---

# 14. Agent loop

The eventual execution loop is:

```text
LLM / Planner
     ↓
Action
     ↓
Tool
     ↓
Observation
     ↓
Trace update
     ↓
Verification
     ↓
Next action / Replan / Final
```

Internal reasoning must not be exposed as raw chain-of-thought.

Expose useful progress and results instead.

For complex tasks, the agent should have explicit:

- maximum steps;
- tool timeout;
- failure handling;
- observation limits;
- context limits;
- verification;
- termination criteria.

---

# 15. Tool result compression

Never blindly send huge outputs back to the local model.

Examples:

- enormous stdout → truncate/extract relevant lines;
- large files → read relevant ranges;
- large HTML → extract useful content;
- screenshots → process only when needed;
- logs → summarize and retain errors/warnings.

This is especially important on the project's 4 GB VRAM / 16 GB RAM hardware.

---

# 16. AI / model strategy

Mia is local-first.

Use deterministic Python logic where possible.

Do not call an LLM for a task that can be reliably solved with simple code.

Long-term model strategy may include:

```text
rules / lightweight routing
        ↓
small local model
        ↓
coding model for coding tasks
        ↓
larger local reasoning when practical
        ↓
cloud fallback only when actually necessary
```

Avoid keeping several heavy models in VRAM simultaneously.

Avoid multi-agent architectures that waste resources.

Prefer:

```text
one central agent loop
+
deterministic tools
+
specialized model selection when useful
```

---

# 17. Existing project: preserve and migrate

The following existing functionality is valuable and should be preserved/adapted where practical:

### Voice

- Silero V5
- Qwen3-TTS
- audio caching
- VoiceProfile concept

F5-TTS is planned as a future voice engine.

All future Mia TTS engines should converge on a common VoiceProfile so that switching engines does not change Mia's identity.

### System

- application launching
- system functionality
- file operations

### Browser / Web

- browser opening
- search
- web access
- page reading where already supported

### Memory

- ChromaDB
- existing memory modules as migration sources

### Vision

- screenshots
- screen observation

### Training

- `training_data.json`
- `training_data_clean.json`
- `training_data_v2.json`

---

# 18. Explicitly retired architecture

Do NOT restore or build the new architecture around:

- RVC WebUI
- old keyword-routing as the main decision mechanism
- giant `main.py` as the central brain
- unstructured skills without schemas
- "if skill doesn't understand → send everything to AI"
- multiple independent LLM agents merely for the sake of being multi-agent
- microservices for components that can remain local modules

RVC WebUI is intentionally abandoned.

---

# 19. Migration strategy

Six phases:

## Phase 1 — New structure beside legacy

Create and develop the new `mia/` architecture without breaking the old project.

Recommended structure:

```text
mia/
├── core/
├── ai/
├── tools/
├── memory/
├── character/
└── adapters/

migration/
├── notes/
├── compatibility/
└── legacy_map.json
```

Legacy files remain where they are until migration is proven.

## Phase 2 — Inventory

Maintain `migration/legacy_map.json`.

For each legacy component record:

- what it does;
- dependencies;
- current working state;
- keep/adapt/replace/retire status;
- target location;
- side effects;
- fallback requirements.

## Phase 3 — Independent new core

Build and test the new core without immediately connecting every legacy module.

First target:

```text
text input
→ Router
→ CostEstimator
→ Policy
→ TaskContext/Trace
→ direct response OR mock tool path
```

## Phase 4 — Adapters

Convert useful legacy modules into tools.

Priority:

```text
1. system.open_app
2. files.list
3. files.read
4. browser.open
5. web.search

then:
6. files.write
7. shell.safe_run
8. vision.screenshot
```

## Phase 5 — Transfer control

Move control from legacy `main.py` to the new orchestrator.

Temporary dual-run/fallback architecture is acceptable:

```text
request
   ↓
new orchestrator
   ↓
confident enough?
 ┌─┴──────────┐
YES           NO
 ↓             ↓
new path    legacy fallback
```

This must be temporary.

## Phase 6 — Legacy cleanup

Only after the new path is stable:

- remove obsolete keyword branches;
- remove unused skills;
- reduce legacy fallback;
- move retained modules into their final packages;
- leave `main.py` as a thin bootstrap.

---

# 20. Migration order

Do not jump randomly between subsystems.

Recommended order:

```text
1. Router
2. CostEstimator
3. TaskContext
4. ExecutionTrace
5. Policy
6. Planner
7. ToolRegistry
8. AgentLoop
9. Verifier
10. Responder
11. tools/adapters
12. memory
13. character
14. speech / vision / events / UI
```

Current work should remain focused on the decision/execution foundation before expanding into UI or voice.

---

# 21. Testing requirements

Every architectural change should be tested.

At minimum:

```text
python -m py_compile ...
```

and the relevant test suite.

The core must have deterministic tests for cases such as:

```text
"Привет"
→ C0 / COMPANION

"Что ты помнишь обо мне?"
→ MEMORY_QUERY

"Открой браузер"
→ TOOL/AGENT path

"Проверь мой Unity проект"
→ TECHNICAL / AGENT

"Удали папку ..."
→ HIGH RISK / confirmation
```

Add regression tests whenever a routing bug is found.

Do not connect a new core directly to the production `main.py` before its isolated tests pass.

---

# 22. Observability

The architecture should eventually record:

```text
router decision
cost estimate
policy decision
model used
planner output
tool calls
tool results
verification
errors
latency
token usage
final result
```

Do not log secrets, API keys, passwords or credentials.

---

# 23. Character layer

The character layer must be separate from the agent's reasoning.

Core brain:

```text
understand
plan
act
verify
```

Character:

```text
tone
style
emotion
humor
wording
response personality
```

Mia should remain:

- warm;
- attentive;
- slightly playful;
- natural;
- technically competent;
- concise when appropriate.

Character behavior must never be allowed to override tool correctness or safety.

---

# 24. Memory architecture

Long-term target:

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
+
vector search
+
recency
+
importance
+
task relevance
```

Do not dump all memory into every prompt.

Memory writing should be selective.

Do not store secrets or sensitive information unnecessarily.

---

# 25. Events and proactive behavior

Mia should eventually support events from:

- user interaction;
- filesystem;
- applications;
- schedules;
- errors;
- other local signals.

Proactive behavior must be useful and non-intrusive.

Examples:

```text
unfinished task detected
scheduled reminder
important application event
project error notification
```

Do not create autonomous behavior without clear scope, termination conditions and logging.

---

# 26. Performance rules for this hardware

The machine has only 4 GB VRAM.

Therefore:

- avoid unnecessary model loading;
- avoid simultaneous heavy models;
- keep contexts bounded;
- compress tool outputs;
- prefer deterministic routing;
- use smaller models for simple work;
- use specialized models only when useful;
- unload/offload models when appropriate;
- do not create a swarm of LLM agents.

Architecture quality must not depend on having server-class hardware.

---

# 27. Coding rules for Qwen

When modifying this repository:

1. Inspect before editing.
2. Understand imports and dependencies.
3. Preserve working behavior.
4. Prefer incremental migration.
5. Do not silently delete functionality.
6. Do not create duplicate implementations without a migration reason.
7. Keep interfaces typed and structured.
8. Prefer dataclasses / typed schemas where appropriate.
9. Keep modules focused.
10. Avoid unnecessary dependencies.
11. Avoid premature abstractions.
12. Add tests for new core behavior.
13. Run syntax/tests after changes.
14. Report changed files and test results.
15. If a migration decision is uncertain, inspect the existing code and `migration/legacy_map.json` before choosing.
16. Do not modify unrelated files just to "clean up" the repository.
17. Do not change model architecture, voice architecture or legacy behavior without checking the migration plan.

---

# 28. Git rules

Use Git as a safety mechanism.

Before substantial migration work:

```text
working tree clean
→ create commit/checkpoint
→ make change
→ test
→ review diff
→ commit
```

Never commit:

```text
.env
API keys
passwords
tokens
private credentials
large model caches
.venv
__pycache__
*.pyc
temporary generated files
large generated audio/model artifacts unless intentionally versioned
```

Keep the GitHub repository private.

Do not expose credentials in source code.

If an old source file contains an API key, remove it from the repository history where appropriate and rotate/revoke the key.

---

# 29. What Qwen should do when asked to implement a feature

Use this process:

```text
1. Read relevant architecture/docs
2. Inspect existing implementation
3. Identify migration target
4. Make a minimal coherent change
5. Update related tests
6. Run tests
7. Inspect git diff
8. Report:
   - files changed
   - architectural effect
   - tests run
   - remaining limitations
```

For larger tasks:

```text
analyze
→ plan
→ implement
→ test
→ verify
→ summarize
```

Do not rewrite large parts of the project merely because a cleaner implementation is possible.

---

# 30. Definition of success

The migration is successful when:

- old Mia remains usable during migration;
- new core handles requests through structured routing;
- complexity controls resource usage;
- Policy controls risky actions;
- TaskContext and ExecutionTrace separate task state from execution history;
- Planner handles multi-step work;
- ToolRegistry exposes capabilities through schemas;
- AgentLoop performs observe/act cycles;
- Verification confirms actual task completion;
- memory is selectively integrated;
- character is separated from reasoning;
- legacy modules are reused through adapters where sensible;
- `main.py` eventually becomes only a bootstrap;
- the resulting Mia behaves as a coherent personal AI agent rather than a collection of keyword skills.

---

# 31. Current priority

Do not jump ahead.

The immediate architectural priority is:

```text
Router
+
CostEstimator
+
TaskContext / AgentState migration
+
Policy
```

Then:

```text
Planner
→ ToolRegistry
→ AgentLoop
→ Verification
```

Only after the core foundation is stable should large numbers of legacy tools be connected.

---

# 32. Final instruction

Treat this file and the project's migration documentation as architectural constraints.

When a newer implementation conflicts with an older legacy implementation:

- prefer the new architecture for new code;
- preserve the old implementation until its replacement is verified;
- use adapters where possible;
- never destroy working functionality without a migration path.

The goal is not to make the repository look modern.

The goal is to **gradually turn the existing Mia into a real, reliable, local-first autonomous AI assistant without losing what already works.**
