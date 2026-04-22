"""
Main entry point for the merged RH platform.
Run with: streamlit run app.py
The FastAPI chatbot API runs separately: uvicorn api:app --reload --port 8001
"""

import streamlit as st

st.set_page_config(
    page_title="RH Platform",
    page_icon="🧑‍💼",
    layout="wide",
)

st.title("RH Pre-selection Platform")
st.write("Use the sidebar to navigate between the candidate application portal and the HR ranking dashboard.")

col1, col2 = st.columns(2)
with col1:
    st.info("**Candidates** — go to *Apply* to upload your CV.")
with col2:
    st.info("**HR Team** — go to *Ranking* to rank applicants and launch chatbot interviews.")
