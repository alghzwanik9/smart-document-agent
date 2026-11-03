# Smart Document Agent

Uploads payroll sheets (PDF, Word, Excel, CSV), extracts one record per employee with an LLM, and shows them for
review. The full specification is `blueprint.md`; this file says how to run what exists.

Status: phases 1 and 2, both verified with a real model and real OCR on synthetic sheets (upload, background extraction, list, delete; review and correct fields, export with the
corrections), and phase 3 (learning from corrections, analytics), verified with a stand-in LLM and the real embedding model, not yet with a real LLM on real sheets.

## Configure

Copy `.env.example` to `.env`, set `API_KEY`, and set `LLM_BASE_URL` and `LLM_MODEL` (and `LLM_API_KEY` if the provider needs one).
**Payroll sheets are sensitive and their text is sent to the LLM provider you configure.** Nothing is sent until both
`LLM_BASE_URL` and `LLM_MODEL` are set. For a model that stays on this machine, point them at Ollama.

## Run with Docker

```
docker compose up --build
```

Interface: http://localhost:8501. Backend and its API docs: http://localhost:8000/docs.
The files and the database live in the `storage` volume.

## Run without Docker

Python 3.11. Scanned PDFs need Tesseract installed with the `ara` and `eng` language packs; everything else works without it.
On Windows, if the packs cannot be written into `Program Files`, keep `ara.traineddata`, `eng.traineddata` and `osd.traineddata` in a folder of your own,
set `TESSDATA_PREFIX` to it, and make sure `tesseract.exe` is on `PATH`.
Scanned pages: OCR of a table that mixes Arabic and English can misread or reorder a word, so check those fields on the details page.

```
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt -r frontend\requirements.txt

cd backend
set API_KEY=change-me
..\.venv\Scripts\python -m uvicorn main:app --port 8000

cd ..\frontend
set API_KEY=change-me
..\.venv\Scripts\python -m streamlit run app.py
```

Tests (backend): `cd backend && ..\.venv\Scripts\python -m pytest`

## What is stored where

- `backend/storage/` (`STORAGE_DIR`): the original uploads under random names, `app.db`, and `chroma/` (the index of your corrections). An original is never modified.
- Every endpoint but `GET /health` needs the header `X-API-Key`.
- A document that fails (unreadable file, provider down, no payroll found) gets the status `failed` and a short reason; upload it again to retry.

## Decisions taken while building phase 1

- One SQLite file next to the originals, so a single volume holds all the data.
- The LLM client speaks the OpenAI chat-completions format, which Gemini, Groq, OpenRouter and Ollama all accept.
- Confidence is computed from the document, not asked of the model: 0.9 when the value is written in the sheet, 0.4 when it is not,
  0.95 for amounts of a row whose arithmetic holds (basic + allowances - deductions = net), 0.5 when it does not.
- Long sheets are sent in chunks of whole lines (`LLM_CHUNK_CHARS`), each repeating the sheet's first lines as a header.
- Interface text lives in `frontend/utils/strings.py`; fonts are system fonts (Cairo and Noto Sans Arabic when installed), nothing is downloaded.

## Review, correction and export (phase 2)

- Open a completed document from the list (details), edit values in the table, then save. Fields the sheet does not state, or whose
  arithmetic does not add up, are marked for review. Amounts accept `5,400` or Arabic digits and are stored as `5400`.
- Export gives a new file in the original format (XLSX, CSV, DOCX or PDF) with the corrected values; the original is never touched.
  Each record is matched to the row that holds most of its values, and the old value is replaced there. A correction whose place is
  not unique (two cells holding the same value in one row), or that is in text outside a Word table, is **not guessed**: the page lists it
  and the response carries `X-Export-Unplaced`. Edit those in the exported file.
- XLSX: styles and number formats are kept; formulas stay formulas unless that very cell is corrected; charts and images in the workbook are
  not carried over by the library. PDF is best effort: the old text is removed, the new text is drawn in the same box (smaller if it is longer);
  a scanned PDF has no text to replace, so its corrections are reported as not placed.
- The pages live in `frontend/views/` (not `pages/`) and are routed by `st.navigation` in `app.py`, so a direct link or a refresh keeps the
  right-to-left layout. Streamlit 1.66 or newer is required.

## Learning from corrections and analytics (phase 3)

- Every correction saved on the details page is kept as an example (`feedback_loop` in SQLite, and an index in `storage/chroma/`). One example per
  field: correcting it again replaces it, putting the original value back removes it, deleting the document removes its corrections.
- When the next sheet is processed, the corrections that apply are put in front of the model in a `<corrections>` block (as data, never as instructions).
  Which ones is decided in code: a wrong value written verbatim in the sheet always applies; otherwise the cells of the sheet are compared with the wrong
  values by a local embedding model (`LEARNING_MAX_DISTANCE`, at most `LEARNING_EXAMPLES` examples). A field the model returns with its corrected value is
  not flagged for review just because the sheet still shows the old spelling.
- The embedding model is Chroma's default (ONNX, about 80 MB), downloaded once on first use; no document text is sent anywhere for it. It is weak on Arabic,
  so for Arabic the verbatim match is what you can rely on. The distance limit was not tuned on real sheets.
- If the index fails, the correction is still saved and extraction goes on without examples.
- The analytics page (`/Analytics`) shows document, field and correction counts, the average confidence, and the latest corrections.

## Tables are read by code, to spend fewer tokens

A payroll sheet is mostly one table, so its rows are copied by code and the model is not asked to read them.
- **Known column titles need no model.** Common titles in Arabic and English (name, ID, basic, allowances, deductions, net, period, currency)
  are matched in `table_extractor.py`; Excel, CSV, Word tables and PDF tables drawn with ruling lines are read this way, for any number of
  employees, and no LLM needs to be configured for them.
- **An unknown layout costs one small question.** The model sees the column titles and three sample rows (a few hundred characters, whatever the
  length of the sheet) and says which column holds which field. The answer is stored per layout (`layout_mappings` in `app.db`), so the same
  layout in next month's sheet costs nothing. An answer that does not read the table sensibly (the name column holds numbers, or the
  arithmetic fails in most rows) is neither trusted nor stored.
- **Everything else goes whole to the model, as before:** a scanned PDF, a PDF table with no ruling lines, free text, and any table that looks like
  payroll but cannot be read with confidence. Rows that are totals or repeated titles are not employees. Confidence is computed as always.
- Learning from corrections (phase 3) applies to that whole-text path; in the table path values are copied from the sheet, not guessed.
- `TABLE_EXTRACTION=0` switches this off and sends every sheet whole. To forget a layout the model got wrong, delete its row from `layout_mappings`.
