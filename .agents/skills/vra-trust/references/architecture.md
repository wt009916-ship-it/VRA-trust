# Architecture
frontend/src → same-origin FastAPI backend/api.py → domain.py + SQLite store.py → core.py → EnergyPlus → native SQL.
schema.py defines contracts. Runtime files/database stay outside Git. Single local worker; queued jobs persist, interrupted jobs fail visibly after restart.
frontend/legacy and legacy/backend_submission preserve prior achievements but are inactive.
Later phases: generalized DAG/selective recomputation; real LLM tools; robustness/actions; drawing/spatial; production hardening.
