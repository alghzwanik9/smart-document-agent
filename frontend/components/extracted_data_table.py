import pandas as pd
import streamlit as st

from utils import strings
from utils.api_client import ApiClient, ApiError, Unreachable

LOW_CONFIDENCE = 0.6    # below the 0.9 of a value found in the sheet: 0.4 not found, 0.5 arithmetic does not add up


def effective_value(field: dict) -> str:
    """What the document should say: the user's correction when there is one."""
    return field["corrected_value"] if field["is_corrected"] else (field["original_value"] or "")


def needs_review(field: dict) -> bool:
    return not field["is_corrected"] and field["confidence"] is not None and field["confidence"] < LOW_CONFIDENCE


def group_records(fields: list[dict]) -> dict[int, dict[str, dict]]:
    """{record_index: {field_name: field}}: one entry per employee."""
    records: dict[int, dict[str, dict]] = {}
    for field in fields:
        records.setdefault(field["record_index"], {})[field["field_name"]] = field
    return records


def record_label(index: int, record: dict[str, dict], position: int) -> str:
    for name in ("employee_name", "employee_id"):
        if name in record and effective_value(record[name]):
            return effective_value(record[name])
    return strings.RECORD_FALLBACK.format(number=position + 1)


def build_frame(fields: list[dict]) -> pd.DataFrame:
    """One row per extracted field. `id` is the key the edits are matched by."""
    labels = {index: record_label(index, record, position)
              for position, (index, record) in enumerate(group_records(fields).items())}
    rows = []
    for field in fields:
        note = strings.NOTE_CORRECTED if field["is_corrected"] else strings.NOTE_REVIEW if needs_review(field) else ""
        rows.append({
            "id": field["id"],
            strings.COLUMN_RECORD: labels[field["record_index"]],
            strings.COLUMN_FIELD: strings.FIELD_LABELS.get(field["field_name"], field["field_name"]),
            strings.COLUMN_ORIGINAL: field["original_value"] or "",
            strings.COLUMN_VALUE: effective_value(field),
            strings.COLUMN_CONFIDENCE: field["confidence"],
            strings.COLUMN_NOTE: note,
        })
    return pd.DataFrame(rows)


def render_extracted_data(client: ApiClient, document_id: int, fields: list[dict]) -> None:
    """The editable table. Saving sends only the cells that changed and reloads the page."""
    st.subheader(strings.FIELDS_HEADER)
    st.caption(strings.FIELDS_HELP)
    if not fields:
        st.info(strings.FIELDS_EMPTY)
        return

    frame = build_frame(fields)
    review_only = st.toggle(strings.FILTER_REVIEW, key=f"review_only_{document_id}")
    if review_only:
        frame = frame[frame[strings.COLUMN_NOTE] == strings.NOTE_REVIEW]
        if frame.empty:
            st.info(strings.FILTER_REVIEW_EMPTY)
            return

    edited = st.data_editor(
        frame, hide_index=True, width="stretch", key=f"editor_{document_id}_{int(review_only)}",
        disabled=[column for column in frame.columns if column != strings.COLUMN_VALUE],
        column_config={
            "id": None,
            strings.COLUMN_CONFIDENCE: st.column_config.ProgressColumn(
                strings.COLUMN_CONFIDENCE, min_value=0, max_value=1, format="percent"),
        },
    )

    changed = edited[edited[strings.COLUMN_VALUE] != frame[strings.COLUMN_VALUE]]
    if st.button(strings.SAVE, type="primary", icon=":material/save:", key=f"save_{document_id}"):
        _save(client, document_id, changed)


def _save(client: ApiClient, document_id: int, changed: pd.DataFrame) -> None:
    if changed.empty:
        st.info(strings.SAVE_NONE)
        return
    saved = 0
    for _, row in changed.iterrows():
        try:
            client.update_field(document_id, int(row["id"]), str(row[strings.COLUMN_VALUE] or ""))
            saved += 1
        except Unreachable:
            st.error(strings.ERROR_UNREACHABLE.format(url=client.base_url))
            return
        except ApiError as error:
            st.error(strings.SAVE_FAILED.format(field=row[strings.COLUMN_FIELD], record=row[strings.COLUMN_RECORD],
                                                reason=error.detail))
    if saved:
        st.session_state["flash"] = strings.SAVE_DONE.format(count=saved)
        st.session_state.pop(f"export_{document_id}", None)     # a prepared file no longer holds the corrections
        st.rerun()
