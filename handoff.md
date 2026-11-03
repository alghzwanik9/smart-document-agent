# Handoff: smart-document-agent

Written 2026-10-29. This project is self-contained: it no longer depends on any other repository. It is not a git repository yet (first action below).

## 1) Goal

Payroll-sheet analyzer: upload payroll sheets (PDF, Word, Excel, CSV), extract one record per employee, review and correct them, export in the original format, and learn from corrections. Documents are **payroll sheets**; the LLM provider is **configurable** by environment variables; the build goes **one phase at a time** and a phase is done only when its "completion criterion" in `blueprint.md` section 14 holds. `blueprint.md` is the single source of truth; the project skill `smart-document-agent-conventions` forbids changing tables, fields or endpoints without editing it first.

Rules: never touch or print any `.env`; never push to a remote; one commit per item with its tests; run `verification-before-completion` before claiming something is done; payroll data is sensitive, so nothing is sent to an LLM until the user configures a provider; ask before anything outward-facing or irreversible; no emojis in the UI, zinc palette, one accent, correct RTL/LTR mixing, no horizontal overflow on mobile. Do not modify `D:\DEV\ACTIVE\.agents`, `sentinel-qa`, `smart-assistant`.

## 2) Current State

- **Phases 1, 2 and 3 are built and verified**; the table path (tables read by code) is built. `backend` tests: **183 passed** (project venv `D:\DEV\ACTIVE\smart-document-agent\.venv`, Python 3.11).
  - Phase 1: upload, background extraction, list, details, delete. Verified live with a real local model (`qwen2.5:7b` via Ollama, since removed) and real Tesseract (`ara+eng`).
  - Phase 2: `PUT /documents/{id}/fields/{field_id}`, `GET /documents/{id}/export` (original format; `X-Export-Unplaced` header), details page `frontend/views/1_Document_Details.py`.
  - Phase 3: `feedback_loop` (Chroma `CorrectionStore`, `LearningAgent`), `GET /feedback/corrections`, `GET /analytics/summary`, `frontend/views/2_Analytics.py`. Settings `LEARNING_EXAMPLES` (5), `LEARNING_MAX_DISTANCE` (0.35).
  - Table path: `document_processing/table_extractor.py`, `layout_store.py`, table `layout_mappings`. Known titles need no LLM; an unknown layout costs one small question (titles + 3 rows), stored per fingerprint; falls back to the whole-text path. `TABLE_EXTRACTION=0` turns it off.
- **Phase 4 not started** (tests, docs, Docker run, performance by measurement). Docker is not installed.
- **Not verified:** a real model's answer to the column question; real extraction quality on real payroll sheets (only synthetic ones exist); PDFs with unruled tables (go whole to the model); Arabic cell order in real PDF tables; docx/csv/pdf export in the browser; `docker compose up`; the 0.35 distance limit on real Arabic sheets (two unrelated Arabic names measured 0.37).
- No `.env` exists; settings are passed as environment variables. Tesseract 5.4 is installed (its `ara` pack is in a user folder: run with `TESSDATA_PREFIX` pointing to it and the Tesseract folder on PATH). Ollama 0.40.7 is installed but its model list is empty; re-pulling `qwen2.5:7b` is 4.7 GB, ask first. A free Gemini or Groq key in a `.env` the user creates is the cheaper test.
- **Disk:** C: had about 3 GB free at the last check; keep 10 GB free.
- Open questions in `blueprint.md` section 16: real (or anonymized) payroll samples; whether a sheet always holds many employees; which provider and whether payroll text may leave the machine; whether multi-user is needed later.
- `AGENTS.md` and `skills.manifest.json` carry generator markers (`planning-studio:skills:begin/end`, `generated_by`). They are only labels; leave or remove them freely.

## 3) Direction agreed: code first, model last

The user wants the analysis done in Python so the system does not depend on API keys (token cost is the real obstacle). Plan, **not started**, waiting for the user's "go" on step 1:

1. Find the payroll columns by arithmetic (the numeric columns for which basic + allowances - deductions = net holds in most rows; name column = most words; id column = most unique values). Removes the last model call from the table path. Tests first.
2. Read PDF tables without ruling lines by clustering pdfplumber word positions on x.
3. Fuzzy header matching (`rapidfuzz`) instead of a growing dictionary.
4. Code-only checks: net not matching the arithmetic, duplicate employee ids, statistical outliers.
5. Store a corrected column mapping per layout fingerprint.

Limit: free text and scanned PDFs still need the model as a fallback. Ask the user for one or two anonymized payroll sheets (Excel and PDF); otherwise generate sheets with several layouts. Update `blueprint.md` (sections 8, 14, 17), the README and this file with each step.

## 4) Key decisions (full list in `blueprint.md` sections 14 and 17)

- One SQLite file next to the originals in `STORAGE_DIR`; the LLM client speaks OpenAI chat-completions (Gemini, Groq, OpenRouter, Ollama).
- Confidence is computed in code: 0.9 value written in the sheet, 0.4 not, 0.95 amounts of a row whose arithmetic holds, 0.5 when it does not.
- Pages live in `frontend/views/` with `st.navigation` in `app.py` (a `pages/` folder makes Streamlit run the page alone on a direct link: no RTL). Streamlit minimum 1.66.
- Export format equals the original's (no picker); Word text outside tables is reported as not placed; PDF export is best effort.
- Learned corrections apply only to the whole-text path; a mapping not matched by title must pass plausibility checks; Chroma and layout-store failures never block a correction or an extraction.

## 5) Pitfalls

- Heredocs corrupt source files (`\n`, `\t`): write files with the Write tool or Edit.
- curl on Windows mangles Arabic bodies: send Arabic JSON from Python (`httpx`) with `PYTHONIOENCODING=utf-8`. Console printing of Arabic fails under `python -I`: use `ascii()`.
- pytest parametrization with file bytes as values crashes Windows (id too long): use `pytest.param(..., id="...")`.
- A wildcard font rule (`[class*="st-"]`) turns Streamlit Material icons into words; restrict fonts to text elements. Streamlit caches imported modules: restart the frontend after changing a component or `utils/rtl.py`.
- Playwright screenshots right after navigation are blank: wait a few seconds; viewport about 1500 px high.
- `normalize` maps ي to ى, so Arabic literals in regexes are built with `alternatives()`. Table `_key` uses NFD plus an Mn filter. PDF text can store Arabic as presentation forms: `pdf_parser.plain_letters` (NFKC) fixes it.
- OCR of mixed Arabic/English tables can drop or reorder a word while confidence stays 0.9 (idea not built: lower confidence of OCR pages).
- When scripting a provider in tests, assert the number of requests.
- Live runs spend quota; save outputs to a file outside the repo; do not loop.
- A failed `ollama pull` can be DNS (LAN address) rather than disk; the `exit 0` of a background task can come from the wrapper.

## 6) Next steps

1. `git init` in this folder, check `git status` shows no `.env`, `.venv`, storage or sample payroll data, then a first commit.
2. Wait for the user's "go", then code-first step 1 (section 3), tests first.
3. Then steps 2 to 5, then phase 4.
4. Ideas not built: apply learned corrections in the table path; try pdfplumber's text strategy for unruled PDF tables.

Commands:

```bat
cd /d D:\DEV\ACTIVE\smart-document-agent\backend
..\.venv\Scripts\python.exe -m pytest -q
set API_KEY=change-me
..\.venv\Scripts\python.exe -m uvicorn main:app --port 8000
cd ..\frontend
set API_KEY=change-me
set API_URL=http://127.0.0.1:8000
..\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
```
