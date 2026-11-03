import streamlit as st

from components.document_table import render_document_table
from components.upload_widget import render_upload
from utils import strings
from utils.api_client import shared_client
from utils.rtl import inject_rtl

st.set_page_config(page_title=strings.APP_TITLE, layout="wide")
inject_rtl()


def home() -> None:
    st.title(strings.APP_TITLE)
    st.caption(strings.APP_CAPTION)
    render_upload(shared_client())
    render_document_table(shared_client())


navigation = st.navigation([
    st.Page(home, title=strings.NAV_HOME, icon=":material/folder_open:", url_path="", default=True),
    st.Page("views/1_Document_Details.py", title=strings.NAV_DETAILS, icon=":material/table_view:",
            url_path="Document_Details"),
    st.Page("views/2_Analytics.py", title=strings.NAV_ANALYTICS, icon=":material/monitoring:",
            url_path="Analytics"),
])

if not shared_client().has_key:
    st.error(strings.ERROR_NO_KEY)
    st.stop()

navigation.run()
