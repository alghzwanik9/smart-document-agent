import streamlit as st

from utils import strings
from utils.api_client import ApiClient, ApiError, Unreachable

ACCEPTED_TYPES = ["pdf", "docx", "xlsx", "csv"]
MAX_UPLOAD_MB = 20


def render_upload(client: ApiClient) -> bool:
    """The drag-and-drop box. Returns True when at least one file was accepted, so the page can refresh its list."""
    st.subheader(strings.UPLOAD_HEADER)
    accepted_any = False
    with st.form("upload_form", clear_on_submit=True, border=True):
        files = st.file_uploader(
            strings.UPLOAD_LABEL, type=ACCEPTED_TYPES, accept_multiple_files=True,
            help=strings.UPLOAD_HELP.format(max_mb=MAX_UPLOAD_MB),
        )
        submitted = st.form_submit_button(strings.UPLOAD_BUTTON, type="primary", icon=":material/upload:")

    if submitted and not files:
        st.warning(strings.UPLOAD_NONE)
    elif submitted:
        for file in files:
            try:
                client.upload(file.name, file.getvalue())
                st.success(strings.UPLOAD_OK.format(name=file.name))
                accepted_any = True
            except Unreachable:
                st.error(strings.ERROR_UNREACHABLE.format(url=client.base_url))
                break
            except ApiError as error:
                st.error(strings.UPLOAD_FAILED.format(name=file.name, reason=error.detail))
    return accepted_any
