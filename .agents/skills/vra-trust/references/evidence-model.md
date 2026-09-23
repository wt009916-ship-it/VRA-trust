# Evidence model
Evidence binds project, file ID/SHA, locator, value/unit, timestamp, authority, permission, uncertainty, confidence, acquisition method, responsible person, status and review.
MEASURED / DOCUMENTED / IMPORTED / ASSUMED / AI_INFERRED / MISSING are distinct. Human confirmation does not turn assumptions into measurements.
History is append-only. Updating an input invalidates runs consuming that version. Immutable-by-API files are rehashed at gate and result access.
Hashes detect local corruption, not malicious re-signing. Phase 1 dependency views are not the complete generic Claim DAG.
