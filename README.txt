MIA V2 / AGENT BOOTSTRAP

1. Put these files directly into:
   A:\studia\VoiceAssistant\

2. Make sure this source file exists:
   training_data_clean.json

3. Run:
   A:
   cd /d A:\studia\VoiceAssistant
   .venv\Scripts\activate
   python build_training_data_v2.py

4. It creates:
   training_data_v2.json
   training_data_v2_report.txt

Original training_data.json and training_data_clean.json are never modified.

STRUCTURE
- build_training_data_v2.py = dataset compiler
- router.py = deterministic first-pass routing
- agent_core.py = minimal Agent loop skeleton

NEXT ARCHITECTURE
training_data_v2
    -> Router
    -> Context/Memory
    -> Planner
    -> Tool Registry
    -> Tool execution
    -> Observation
    -> Verification
    -> final response

COST
estimated_tokens is an internal routing budget, NOT an exact provider billing amount.
C0-C4 is a complexity class. Later the budget can be calibrated from real model usage.

IMPORTANT
Do not train a model on router metadata as if it were ordinary dialogue.
The metadata is primarily for runtime routing, evaluation and future agent training.
