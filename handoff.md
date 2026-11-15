# handoff.md

## 1) Goal
Build and maintain an intelligent, interactive document analysis, extraction, correction, and domain governance system (`smart-document-agent`) with self-improving cumulative learning and institutional case management for Taif University HR ("Yahya Intelligent Office System").

Key objectives:
- **Core Document Extraction**: High-accuracy deterministic extraction across PDF (ruled and unruled via PyMuPDF coordinate clustering), Excel (`.xlsx`, `.csv` via openpyxl/pandas), Word (`.docx`), and OCR (Tesseract `ara+eng`).
- **Code-First, Model-Last**: Arithmetic column mapping (`basic + allowances - deductions = net`), fuzzy header matching with RapidFuzz ($\ge 82.0$), and layout fingerprint caching to minimize external LLM token usage and latency.
- **Deterministic Quality Assurance**: Validation checks for arithmetic discrepancies (> 0.05), duplicate IDs, negative net salary, non-positive basic salary, and 3-sigma statistical outliers.
- **Yahya Domain Governance & Intake Layer**:
  - Institutional person registry (`PER-xxxx`) with SHA-256 hashed national IDs.
  - Domain-governed case management (`<DOMAIN>-<YEAR>-<SEQ>`) with strict status enums (`NEW`, `ANL`, `WAI`, `RDY`, `CLS`, `HLD`) and priority rating.
  - Append-only event auditing (`EV-xxx`) enforcing Rule 7 (tamper-evident audit logging on document field edits).
  - Deterministic 3-way intake routing (`NO_MATCH`, `SIMILAR_FOUND`, `SAME_PERSON_NEW_TOPIC`).
  - Saudi public sector statutory deadline monitoring ($\le 5$ business days flags P1).
- **Interface & Standards**: Arabic native RTL, Zinc design palette, zero emojis, and `X-API-Key` security across all endpoints.

---

## 2) Carrent State
- **Test Suite Status**: **265 passed in 54.14s** (100% green, 0 failures, 0 regressions across all unit and integration tests).
- **Git Repository**:
  - Clean working tree on branch `main`.
  - All changes committed under commit `bccc152` (`feat: complete milestones M1-M4 and Yahya domain governance layer (265 tests passing)`).
  - Git remote is currently unconfigured (no remote origin URL configured in `.git/config`).
- **Live Running Services**:
  - **Backend**: FastAPI running on `http://127.0.0.1:8000` (Process ID background task `task-636`, `/health` returning `{"status": "ok"}`, Swagger documentation active at `http://127.0.0.1:8000/docs`).
  - **Frontend**: Streamlit running on `http://localhost:8501` (Process ID background task `task-640`, HTTP 200, active RTL view including Yahya Intake & Governance tabs).
  - Local authentication key: `dev-key-1234`.

---

## 3) Active Files
- `backend/main.py`: FastAPI application entry point, lifespan management, and router mounting (`documents`, `feedback`, `analytics`, `yahya_system`).
- `backend/database/models.py`: SQLAlchemy ORM models (`Document`, `ExtractedField`, `FeedbackLoop`, `LayoutMapping`, `PersonRecord`, `CaseRecord`, `CaseEvent`, `CaseRelation`) and domain constants (`CASE_STATUSES`, `CASE_DOMAINS`, `RELATION_TYPES`).
- `backend/core/schemas.py`: Pydantic schemas for payroll records, validation warnings, field corrections (`reason`), case management, intake evaluation, and hierarchical tree outputs.
- `backend/services/intake_matcher.py`: Intake evaluation engine implementing RapidFuzz name/topic matching, Saudi business day statutory calculation (Sun–Thu workweek), and sequential ID generation (`PER-xxxx`, `<DOMAIN>-<YEAR>-<SEQ>`, `EV-xxx`).
- `backend/api/v1/documents.py`: Document ingestion, storage, extraction dispatch, and Rule 7 append-only `CaseEvent` logging upon field modification.
- `backend/api/v1/yahya_system.py`: Yahya System API router (`/yahya/intake/evaluate`, `/yahya/cases`, `/yahya/cases/{case_id}`, `/yahya/cases/{case_id}/events`, `/yahya/cases/{case_id}/relations`, `/yahya/search`, `/yahya/sync-export`).
- `backend/document_processing/table_extractor.py`: Table parsing, arithmetic inference, fuzzy header mapping, and deterministic data quality checks.
- `backend/document_processing/pdf_parser.py`: Unruled PDF word clustering with RTL reading order reconstruction.
- `backend/document_processing/llm_extractor.py`: Extraction orchestrator prioritizing code-first heuristics before model invocation.
- `frontend/app.py`: Streamlit navigation router including `views/3_Yahya_Intake.py`.
- `frontend/views/3_Yahya_Intake.py`: Three-tab governance interface: Intake Evaluation & Commit, Hierarchy Search (`PER ➔ CASE ➔ EV`), and Sync Export.
- `frontend/utils/api_client.py`: Frontend HTTP client communicating with backend endpoints under `X-API-Key`.
- `frontend/utils/strings.py`: Centralized Arabic UI strings and status labels.
- `backend/tests/test_yahya_system.py`: 10 comprehensive tests covering ID generation, intake routing, P1 statutory deadlines, Rule 7 audit logging, and search/sync exports.
- `.gitignore`: Configured to exclude `.env`, `.venv`, `storage`, and `.agents/teamwork/`.

---

## 4) Changes Made
1. **Database & Schemas**:
   - Added tables `person_records`, `case_records`, `case_events`, `case_relations`.
   - Added Pydantic request/response schemas for Yahya domain objects.
   - Updated `FieldCorrection` schema to optionally accept `reason: str | None = None`.
2. **Rule 7 Append-Only Audit Trail**:
   - Modified `correct_field` in `backend/api/v1/documents.py` to query cases linked to `document_id`. For each linked case, an append-only `CaseEvent` is registered recording `old_value`, `new_value`, timestamp, and reason with a sequential `EV-xxx` identifier.
3. **Intake & Matching Engine**:
   - Created `backend/services/intake_matcher.py`.
   - Implemented `calculate_statutory_priority`: computes remaining Saudi business days (Sunday–Thursday), automatically assigning `P1` priority if $\le 5$ days.
   - Implemented `evaluate_intake`: evaluates person existence by employee number, hashed national ID, or RapidFuzz name score ($\ge 85.0$), then checks case references and subject similarity ($\ge 85.0$), producing deterministic routing decisions (`NO_MATCH`, `SIMILAR_FOUND`, or `SAME_PERSON_NEW_TOPIC`).
4. **API Router & Endpoints**:
   - Created `backend/api/v1/yahya_system.py` and mounted under prefix `/yahya` in `main.py`.
   - Added endpoints for evaluating intake, creating cases with initial `EV-001` events, appending subsequent events, managing case relations, hierarchical search, and exporting sync logs in Markdown and JSON.
5. **Streamlit UI**:
   - Added `frontend/views/3_Yahya_Intake.py` with full Arabic RTL support and Zinc palette.
   - Updated `frontend/utils/api_client.py` with methods `evaluate_intake`, `create_case`, `get_case`, `add_case_event`, `search_yahya`, and `export_yahya_sync`.
   - Updated `frontend/app.py` navigation to include the Yahya Intake page.
6. **Git Versioning & Background Execution**:
   - Added `.agents/teamwork/` to `.gitignore`.
   - Staged and committed all 25 modified and new production files (`commit bccc152`).
   - Started FastAPI server and Streamlit frontend in the background.

---

## 5) Failed Attempts
1. **Arabic Singular vs. Plural Synonym Mismatch**:
   - *Problem*: In fuzzy header matching, singular terms like `بدل` and `خصم` scored below the strict 82.0 threshold against plural canonical targets (`بدلات` and `خصومات`).
   - *Fix*: Enriched canonical synonym mappings in `SYNONYMS` with base singular forms (`بدل`, `خصم`, `البدل`, `الخصم`).
2. **RapidFuzz Test Boundary Assertion**:
   - *Problem*: `bask salary` scored 90.91 against `base salary`, causing a test expecting rejection at threshold 90.0 to fail.
   - *Fix*: Adjusted test boundary condition to evaluate threshold 92.0 where ratio < 92.0 returns `None`.
3. **LLM Extractor Layout Caching Test Bypass**:
   - *Problem*: Initial test for fuzzy layout caching used exact synonyms already registered in `SYNONYMS`, which resolved via exact match and bypassed the fuzzy branch.
   - *Fix*: Updated test headers with authentic typographical variations and plurals (`اسماء الموظفين`, `رقم العاملين`), successfully validating `map_by_fuzzy_headers` and layout persistence.
4. **TDD Initial Schema Import Failure**:
   - *Problem*: Initial execution of `test_yahya_system.py` failed during collection due to missing `IntakeEvaluationRequest` schema.
   - *Fix*: Expected TDD "Red" verification step; resolved by implementing required models and schemas in `core/schemas.py`.
5. **Git Remote Push Attempt**:
   - *Problem*: User requested pushing to Git ("ارفع كل شيء للقيت"), but `git remote -v` revealed no configured remote repository origin.
   - *Fix*: Committed all changes cleanly to local `main` branch and flagged the need for the user's remote repository URL to execute `git push`.

---

## 6) Next Steps
1. **Configure Git Remote & Push**:
   - Obtain remote GitHub repository URL from the user (e.g., `git remote add origin https://github.com/alghzwanik9/smart-document-agent.git`).
   - Execute `git push -u origin main`.
2. **Review Live Interface**:
   - Navigate to `http://localhost:8501` to test the new "نظام يحيى الذكي للإدارة" view (evaluate intake, commit a case, test hierarchy search, download Markdown/JSON sync export).
   - Test field correction audit trail on `http://localhost:8501/Document_Details` to verify automatic creation of `CaseEvent` entries.
3. **Optional Enhancements**:
   - Run end-to-end container check using `docker compose up --build`.
   - Set up GitHub Actions CI workflow to automate running `pytest backend/tests` on future pushes.
