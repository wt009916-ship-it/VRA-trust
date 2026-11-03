import pypdfium2

from backend.reports import report_pdf


def test_pdf_long_evidence_splits_across_pages_without_losing_tail():
    report = {
        "generated_at": "2026-10-21",
        "project": {"name": "Long evidence fixture", "data_nature": "software_test"},
        "run": {"metrics": None, "carbon": None, "run_id": "fixture", "scheme_id": "baseline",
                "status": "failed", "engine_calls_executed": 0, "warnings_count": 0,
                "error": "Test only", "stale_reasons": [], "limitations": [], "provenance": None},
        "certificate": {"status": "draft", "candidate_schemes": [], "objective": "test",
                        "constraints": [], "stability_status": "not_assessed", "conditions": [],
                        "invalidation_conditions": [], "counterexamples": None,
                        "unresolved_uncertainties": [], "suggested_evidence_actions": [], "engineer_review": None},
        "evidence": [{"name": "Geometry normalization", "evidence_id": "test", "revision": 1,
                      "status": "ASSUMED", "review_state": "confirmed", "source_file": None,
                      "source_locator": "test", "hash": "0"*64, "authority": "test", "permission": "test",
                      "responsible_person": "test", "timestamp": "2026", "acquisition_method": "test",
                      "uncertainty": None, "value": [{"room": i, "original_area": 10, "normalized_area": 10.1}
                                                   for i in range(100)],
                      "unit": None, "confidence": None, "review_note": "END-SENTINEL"}],
    }
    pdf = report_pdf(report)
    with pypdfium2.PdfDocument(pdf) as document:
        assert len(document) >= 5
        texts = []
        for page in document:
            text = page.get_textpage()
            try:
                texts.append(text.get_text_range())
            finally:
                text.close()
                page.close()
        assert "END-SENTINEL" in "\n".join(texts)
