# Validation of XLSX and CSV imports

Date: 2026-09-10. Baseline: `4002a0a31c2fe50887f6d2b8e0a4b1999b327eef`.

- All 59 automated tests pass (64.7 seconds). Six new synthetic import tests cover MAXQDA-style columns, quotes and newlines, explicit sheet selection, invalid headers/formulas, blank cells, bounded input size, unchanged XLSX originals, both input formats and validation with 50 coding rows / 43 passages.
- The browser import was checked with a synthetic two-sheet XLSX export and a CSV category system, including sheet selection and automatic column mapping.
- XLSX ingestion runs locally and requires no model call. No additional Cloud or local GPU inference was used for this change. This release adds `openpyxl` to setup requirements; the command-line runner continues to consume CSV.

## Earlier validation of the local desktop interface

Date: 2026-09-10. Baseline: `90e0ff38fe0da214b6259b4c63a7bd93a6ec689a`.

- 53 automated tests cover the previous workflow and the new local interface. New tests exercise immutable project revisions, synthetic demo validation (50 rows / 43 passages / 12 paths), dependency selection, column errors, path confinement, HTTP session/Origin/Host checks, token redaction and the actual runner with mocked inference through pause and resume.
- Telegram tests use fabricated tokens and a mocked network. They verify session-only persistence, replacement, removal, current-user Windows DPAPI encryption/decryption, event selection, content-free messages and sanitized transport errors. DPAPI was verified outside the restricted sandbox under the normal Windows account. No live Telegram message was sent: no real Telegram bot token or destination was provided.
- A real `gemma4:31b` Cloud smoke test used a configuration produced by the new project interface, with an isolated Cloud override and two artificial input rows. Cluster analysis and summarization completed with three successful model requests. The shipped interface and YAML defaults remain local; no local GPU inference or real study data was used.
- Browser checks exercised demo creation, default column mappings, validation, disabled Telegram settings with a fabricated token, token removal and result/review preview. This is a Windows development-machine validation, not an installer test across multiple PCs.

## Earlier validation of partial checkpoints

Date: 2026-09-10. Baseline: `6110780a325ad793eaf7b9939b106cf568f1bfdd`.

- All 46 automated tests pass. Seven complete 15-module workflow scenarios interrupt the second request in cluster analysis, summarization, SWOT, meta-SWOT, person analysis, ambiguity analysis or hierarchical reduction. Each resumed workflow finishes and the first successful request is not repeated.
- Targeted relation and evidence-audit tests interrupt the second batch and verify reuse of the first batch, complete audit IDs and stable global relation IDs. Integrity tests reject changed inputs/model settings, corrupted results and failed partial work; disabled checkpoints do not write or reuse results.
- A real `gemma4:31b` Cloud probe reduced four artificial findings in two batches. An intentional interruption before the second network request left one validated checkpoint. Resume reused that batch, completed the other and preserved all four source records in the reference graph. This required two successful Cloud requests in total. It tests recovery, not interpretive accuracy.
- Public and private defaults remain local Ollama. No local GPU inference or real study data was used. Program upgrades still require a new run; this release does not migrate older checkpoints.

## Earlier validation of multi-label coding, offline review and hierarchical synthesis

Date: 2026-09-10. Extension baseline: `f2e939ec0f1a32a12cb23d24998fffb2eccd1a87`.

- 41 automated tests cover both coding modes, explicit passage identity, independent multi-label calls, set metrics, abstention/failure coverage, checkpoints, the complete 15-module workflow, review decisions, HTML escaping, multi-level reduction, reference graphs and bounded failure cases.
- A real `gemma4:31b` Cloud workflow completed all 15 modules on 50 synthetic coding rows representing 43 passages. All 43 passages were evaluated without coding failures or abstentions. All 50 reference code assignments were found, with 10 additional model assignments: micro-precision 83.3%, recall 100%, F1 90.9%, mean Jaccard 88.8%, and exact set agreement 33/43 (76.7%). The review queue contains 14 disputed cases; verification can flag a case even when its predicted code set matches.
- The full workflow exercised hierarchical synthesis with 13 reduction calls. A separate real Cloud stress test used an 8500 context budget and completed two reduction levels (eight reduction calls plus final synthesis). The final references resolve through the recorded nodes to all nine input records, including the synthetic source note.
- Browser testing verified required review fields, exported a separate decision JSON file, reloaded the page and imported that downloaded file with the decision, note and reviewer intact. The offline page was visually inspected. Original codings and model results remain unchanged.
- These were development runs with documented continuations: a relation request timed out, the first hierarchy implementation lost model-generated reference lists, and a later response exceeded the summary length limit. Reference provenance is now assigned deterministically from actual batch inputs. A diagnostic run and retry completed successfully. An intentionally undersized 6000-context stress run reached the level bound; a new preflight rejects an impossible static prompt before any reduction requests. The added guard was verified not to affect the completed full-run configuration, and its output hashes were retained through an archived compatibility migration.
- The full extension workflow and its continuations used 207 successful requests; additional targeted diagnostics and stress tests are separate. The standard configurations still use local Granite. No real interview data, private study context or local GPU inference was used for these tests.

Interpretation: the examples are artificial and partly overlap with codebook anchors. These values are illustrative, not an independent accuracy benchmark. The stricter set-level results are not directly comparable to the earlier row-level rate. Local Granite inference and real interviews remain untested. Hierarchical reduction applies to the final synthesis; upstream modules retain their documented context limits. Provenance links document inputs, not semantic completeness of every generated summary.

## Earlier robustness stage

Date: 2026-09-10. Baseline: `6f5c9f5b959156fbd224baef68a3f5de171ad797`.

- 30 automated tests pass with Python 3.12 and UTF-8 enabled on Windows.
- The full YAML integration test executes all 14 module entry points with a replaced model transport. It verifies external IDs, fourth-level code paths, source/person metadata, evidence auditing, generated reports, an intentional interruption and subsequent resume. Changed input is rejected on resume.
- Regression tests cover transport errors, invalid cluster output, incomplete audits, claims without evidence, original text preservation, mapping mismatch, stale outputs, checkpoint integrity, paired relation sampling, conservative context budgets, structured-output routing and agreement coverage.
- The public input passes `--validate-only`: 38 synthetic coding rows, 12 paths, 14 modules, zero model calls.
- Six real cloud requests using `gemma4:31b` completed successfully: verification and blind coding for one trivial synthetic example and two examples from the public dataset with opposed fourth-level codes. All responses passed structural and code/ID validation. These are connection and integration smoke tests, not a model-quality benchmark; the selected public examples also occur as codebook anchors.
- A subsequent real Cloud workflow with `gemma4:31b`, temperature 0, context 131072 and output limit 4000 completed all 14 modules on the public 38-row dataset. Exact row-level code agreement was 35/38 (92.1%), assignment coverage 38/38, with no failed verification/blind-coding cases or abstentions. Kappa remained disabled. There were 36 audited findings, 13 with counterexamples, and 30 validated relations from 58 submitted candidate pairs.
- The three code disagreements concern overlapping practice/transfer, practice/group-conflict, and support/group-exchange interpretations (SYN008, SYN009, SYN037). One passage deliberately has two coding rows. These are illustrative outcomes, not independent accuracy estimates: the dataset is small, artificial and shares material with its codebook anchors.
- This was a development run with controlled continuations, not a clean uninterrupted benchmark. It exposed a wrong person-comparison schema key, a contradictory audit omission instruction, and an oversized synthesis prompt. Corrections were applied before continuing. Completed upstream outputs were reused only after verifying their hashes and the exact relevant source/configuration changes; each migration and prior manifest was archived. A final synthesis-only rerun verified retained source identifiers. The production runner still rejects ordinary resume after code/configuration changes.
- The earlier workflow and its targeted continuations used 166 successful model requests, in addition to the six preliminary smoke requests. A workflow contains multiple requests; this is not 166 complete test runs.
- No local Ollama inference was used. No real interviews or private study configuration were sent to Ollama Cloud.

The earlier stage's metrics were row-based. The extension above replaces that behavior in multi-label mode with independent passage-level predictions and set metrics. Refer to `ROBUSTNESS.md` and `EXTENSIONS.md` for current behavior.
