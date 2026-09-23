# Architecture
frontend/src → same-origin FastAPI backend/api.py → domain.py + SQLite store.py → core.py → EnergyPlus → native SQL.
schema.py defines contracts. Runtime files/database stay outside Git. Single local worker; queued jobs persist, interrupted jobs fail visibly after restart.
auth.py manages local accounts, hashed sessions, CSRF and project ownership. api.py authorizes all business routes/downloads. The first account atomically adopts pre-account projects; later accounts get no access. UI uses a project sidebar, task workspace, separate work views and optional inspector. Commands are bounded UI actions, not LLM tool calling.
frontend/legacy and legacy/backend_submission preserve prior achievements but are inactive.
Later phases: generalized DAG/selective recomputation; real LLM tools; robustness/actions; drawing/spatial; production hardening.
