# API contract
backend/schema.py and generated shared/schemas/openapi.json define Phase 1.
Projects carry typed building declarations. Uploaded files become evidence with locators and hashes. IDs are server generated; updates retain history. Run submissions lock revisions.
States: queued/running/succeeded/failed/stale. GET run/result validates current dependencies; UI/JSON/HTML/PDF share that view.
409 evidence/version conflict; 422 schema rejection; 413 upload limit.
Agent and general decision endpoints are unimplemented until their phases; never expose fake-success endpoints.
