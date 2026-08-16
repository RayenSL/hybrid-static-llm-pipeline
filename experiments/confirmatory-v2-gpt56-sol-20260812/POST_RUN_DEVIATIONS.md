# Post-run deviations

## D1 — transient endpoint DNS failure

Assignments 278 and 279 were committed while DNS resolution for the configured Azure OpenAI endpoint was unavailable. Both records have `error_status=api_failure` and are non-evaluable. They were not replayed. The runner was resumed from the ledger, so no committed assignment was repeated.

## D2 — iterative trajectory filename collision

The 312 iterative assignments reference 78 trajectory paths. For each target and repetition, the four iterative factorial conditions used the same filename because `AgenticRunner.WriteTrajectoryArtefactAsync` derives the path only from the relative source path and run number. Each path was consequently written four times. The last trajectory survives; the preceding three references are stale. This yields 78 surviving matching references and 234 overwritten references.

This defect affects the supplementary full-turn trajectory JSON only. The per-assignment JSONL traces contain 624 distinct run IDs and retain the authoritative final outcome, first-build snapshot, prompts and final response, build and visible-test status, detector outcome, materialised-source reference, duration, call count and token count. All 623 materialised-source payload hashes verify. The campaign must not be replayed to reconstruct the overwritten files, and the affected trajectory JSON must not be used for condition-level trajectory analysis.

## D3 — unavailable visible suite

`InvoiceRenderer.Render` remained in the intention-to-treat corpus, but its generated visible suite was rejected during the frozen test-admission stage. Its twelve visible-test-enabled assignments therefore record `visible_test_available=false`. Of 300 available visible-test assignments, 299 executed and passed; the remaining available suite belongs to DNS-failed assignment 278 and did not execute. No executed visible test failed.

## Audit disposition

The campaign is complete and suitable for private Layer-3 evaluation using the authoritative traces and materialised-source artefacts, subject to the trajectory limitation above. Private evaluation had not been run when this audit was sealed.
