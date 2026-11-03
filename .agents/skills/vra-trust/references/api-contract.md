# API contract
backend/schema.py and generated shared/schemas/openapi.json define Phase 1.
Projects carry typed building declarations. Uploaded files become evidence with locators and hashes. IDs are server generated; updates retain history. Run submissions lock revisions.
States: queued/running/succeeded/failed/stale. GET run/result validates current dependencies; UI/JSON/HTML/PDF share that view.
409 evidence/version conflict; 422 schema rejection; 413 upload limit.
Agent, materials, decision, building model and project-token routes are implemented; inspect generated OpenAPI and docs/BUILDING_WORKBENCH.md. Never expose fake-success endpoints. Model publication pins the reviewed revision; replacing a scheme IDF invalidates its old results. MCP uses the public API and project token scopes.
