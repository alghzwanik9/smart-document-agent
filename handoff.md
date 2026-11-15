# handoff.md

## 1) goal
Build and maintain an intelligent, secure, interactive document analysis, extraction, correction, and domain governance system (`smart-document-agent`) with self-improving cumulative learning and institutional case management for Taif University HR ("Yahya Intelligent Office System").

Key objectives:
- **Core Document Extraction**: High-accuracy deterministic extraction across PDF (ruled and unruled via PyMuPDF coordinate clustering), Excel (`.xlsx`, `.csv` via openpyxl/pandas), Word (`.docx`), and OCR (Tesseract `ara+eng`).
- **Code-First, Zero-Leakage Architecture**: Local arithmetic column mapping (`basic + allowances - deductions = net`), fuzzy header matching with RapidFuzz ($\ge 82.0$), and layout fingerprint caching to operate 100% locally with zero external API calls or third-party data transmission.
- **Deterministic Quality Assurance**: Validation checks for arithmetic discrepancies (> 0.05), duplicate IDs, negative net salary, non-positive basic salary, and 3-sigma statistical outliers.
- **Yahya Domain Governance & Intake Layer**:
  - Institutional person registry (`PER-xxxx`) with SHA-256 hashed national IDs.
  - Domain-governed case management (`<DOMAIN>-<YEAR>-<SEQ>`) with strict status enums (`NEW`, `ANL`, `WAI`, `RDY`, `CLS`, `HLD`) and priority rating.
  - Append-only event auditing (`EV-xxx`) enforcing Rule 7 (tamper-evident audit logging on document field edits).
  - Deterministic 3-way intake routing (`NO_MATCH`, `SIMILAR_FOUND`, `SAME_PERSON_NEW_TOPIC`).
  - Saudi public sector statutory deadline monitoring ($\le 5$ business days flags P1).
- **Security & Data Sovereignty**: Full compliance with the Saudi Personal Data Protection Law (PDPL), air-gapped readiness, local storage isolation, and strict `X-API-Key` authentication.
- **Future Multi-Agent Hierarchy**: Foundation for an automated hierarchical multi-agent team headed by an Executive Director Agent orchestrating specialized worker agents (Intake, Audit, Drafting).

---

## 2) Carrent State
- **Live Cloud Deployment**: Active and healthy on Streamlit Community Cloud at `https://smart-document-agent-k9.streamlit.app`.
- **Git Repository**: Synced and pushed to `https://github.com/alghzwanik9/smart-document-agent.git` on branch `main` (clean working tree).
- **Test Suite Status**: **265 passed in 25.86s** (100% green, 0 failures, 0 regressions across all unit and integration tests).
- **Live Local Services**:
  - **Backend**: FastAPI running on `http://127.0.0.1:8000` (Swagger documentation active at `http://127.0.0.1:8000/docs`).
  - **Frontend**: Streamlit running on `http://localhost:8501` (RTL Arabic dark theme with Zinc styling).
  - Authentication Key: `dev-key-1234`.
- **Security Documentation**: Published and tracked in repository at `SECURITY_AND_DATA_PRIVACY_AR.md`.
- **Configuration & Secrets**: Streamlit Cloud configured with zero-dependency deterministic mode (`API_KEY = "dev-key-1234"`, `TABLE_EXTRACTION = "1"`).

---

## 3) Active Files
- `streamlit_app.py`: Root entrypoint for Streamlit Community Cloud.
- `packages.txt`: Linux system dependencies (Tesseract OCR, Arabic/English trained data, Poppler) for cloud containers.
- `frontend/app.py`: Streamlit navigation controller supporting both local and cloud path resolution.
- `views/1_Document_Details.py`, `views/2_Analytics.py`, `views/3_Yahya_Intake.py`: Root runner proxies ensuring page availability in Streamlit Cloud.
- `frontend/views/3_Yahya_Intake.py`: Three-tab governance interface: Intake Evaluation & Commit, Hierarchy Search (`PER ➔ CASE ➔ EV`), and Sync Export.
- `frontend/utils/api_client.py`: Frontend HTTP client and auto-starting FastAPI daemon thread for standalone and cloud environments.
- `frontend/utils/strings.py`: Centralized Arabic UI strings and status labels.
- `backend/main.py`: FastAPI application entry point, lifespan management, and router mounting.
- `backend/core/config.py`: Environment configuration loading and settings management.
- `backend/core/schemas.py`: Pydantic schemas for payroll records, validation warnings, field corrections (`reason`), case management, and intake evaluation.
- `backend/database/models.py`: SQLAlchemy ORM models (`Document`, `ExtractedField`, `FeedbackLoop`, `LayoutMapping`, `PersonRecord`, `CaseRecord`, `CaseEvent`, `CaseRelation`).
- `backend/services/intake_matcher.py`: Intake evaluation engine, RapidFuzz matching, and Saudi business day calculation.
- `backend/api/v1/documents.py`: Document ingestion, storage, extraction dispatch, and Rule 7 append-only `CaseEvent` logging.
- `backend/api/v1/yahya_system.py`: Yahya System API router for case evaluation, event logging, relation graph, and sync exports.
- `backend/document_processing/table_extractor.py`: Table parsing, arithmetic inference, and fuzzy header mapping.
- `SECURITY_AND_DATA_PRIVACY_AR.md`: Formal Arabic data security, air-gapped processing, and PDPL compliance documentation for Yahya and executive stakeholders.

---

## 4) Changes Made
1. **Cloud Deployment Architecture**:
   - Created `streamlit_app.py` root entrypoint and `packages.txt` for Debian Tesseract OCR dependencies.
   - Created root view wrappers in `views/` (`1_Document_Details.py`, `2_Analytics.py`, `3_Yahya_Intake.py`) and updated `_view_path` in `frontend/app.py` to resolve paths seamlessly across cloud and local workspaces.
   - Updated `frontend/utils/api_client.py` to automatically copy `st.secrets` into `os.environ` and initialize `load_settings(env)` inside the background daemon thread.
2. **Git & Remote Tracking**:
   - Initialized Git remote pointing to `https://github.com/alghzwanik9/smart-document-agent.git`.
   - Committed and pushed cloud deployment setup, view resolution fixes, secrets loading, and security documentation to `origin/main`.
3. **Security & Data Privacy Governance**:
   - Formulated `SECURITY_AND_DATA_PRIVACY_AR.md` detailing the zero external data transmission, air-gapped execution capability, strict `X-API-Key` enforcement, and local storage isolation.
4. **Hierarchical Multi-Agent Blueprint**:
   - Designed the conceptual architecture for a multi-agent system (Executive Orchestrator Director + Intake Agent + Audit Agent + Drafting Agent) with Human-in-the-Loop approval checkpoints.

---

## 5) Failed Attempts
1. **GitHub Remote Authorization**:
   - *Issue*: `git ls-remote` failed with `Repository not found`.
   - *Cause*: The repository was initially created as Private without user token authorization configured in the local git environment.
   - *Resolution*: User switched repository visibility to Public in GitHub repository settings; push succeeded immediately.
2. **Streamlit Cloud Page Path Resolution**:
   - *Issue*: Streamlit Cloud showed `StreamlitPageNotFoundError: '1_Document_Details.py' could not be found`.
   - *Cause*: `st.Page` on Streamlit Cloud evaluated relative to repo root (`/mount/src/smart-document-agent`), whereas view files were in `frontend/views/`.
   - *Resolution*: Created root runner files in `views/` and implemented dual fallback path detection in `frontend/app.py`.
3. **Backend Daemon Configuration in Cloud**:
   - *Issue*: `_ensure_backend_running` passed only `api_key` to `Settings(...)`, omitting LLM endpoints and custom flags defined in `st.secrets`.
   - *Resolution*: Updated `_ensure_backend_running` in `frontend/utils/api_client.py` to copy `st.secrets` into `os.environ` and call `load_settings(env)`.

---

## 6) Next Steps
1. **Field Discovery Meeting with Yahya**:
   - Conduct the structured workflow discovery interview using the 5 core lifecycle questions (intake criteria, rejection rules, financial validation rules, output templates, and escalation triggers).
   - Collect authentic sample document templates (payrolls, administrative decrees, case files).
2. **Hierarchical Multi-Agent Implementation**:
   - Define concrete agent personas and schemas:
     - `ExecutiveOrchestratorAgent`: Workflow planning, task delegation, and final approval gate.
     - `IntakeTriageAgent`: Document completeness verification and category routing.
     - `AuditComplianceAgent`: Arithmetic verification, discrepancy flagging, and person-case linking.
     - `DraftingReportingAgent`: Automated generation of structured executive summaries and referral letters.
   - Implement the workflow execution graph in the backend with state persistence.
3. **Streamlit UI Agent Trace & Control Center**:
   - Add an interactive Agent Execution view in Streamlit to show real-time step-by-step agent progress, extracted evidence, and one-click human approval buttons.
4. **End-to-End Field Validation**:
   - Run end-to-end processing with real Yahya office files to calibrate extraction accuracy, fuzzy header thresholds, and statutory deadline calculations.
