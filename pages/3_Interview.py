"""
Chatbot interview page — conducts a pre-selection interview question by question.
Navigated to from the Ranking page after clicking "Start Interview".
"""

import os
import sys

import requests
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

CHATBOT_API_URL = os.getenv("CHATBOT_API_URL", "http://localhost:8001")

# ── Guard: must arrive here from the ranking page ────────────────────────────

if "interview_session" not in st.session_state:
    st.warning("No active interview session. Please start one from the Ranking page.")
    if st.button("← Back to Ranking"):
        st.switch_page("pages/2_Ranking.py")
    st.stop()

# ── Helpers ───────────────────────────────────────────────────────────────────

def submit_answer(session_id: str, answer: str) -> dict | None:
    try:
        resp = requests.post(
            f"{CHATBOT_API_URL}/interview/{session_id}/answer",
            json={"answer": answer},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to submit answer: {e}")
    return None

# ── Page ──────────────────────────────────────────────────────────────────────

candidate_name = st.session_state.get("interview_candidate", "Candidate")
session = st.session_state["interview_session"]
session_id = session.get("session_id")
status = session.get("status")

st.title(f"Interview — {candidate_name}")

if st.button("← Back to Ranking"):
    st.switch_page("pages/2_Ranking.py")

st.divider()

# ── In progress ───────────────────────────────────────────────────────────────

if status == "in_progress":
    summary = session.get("summary", {})
    q_count  = summary.get("question_count", 0)
    covered  = summary.get("covered_axes", 0)
    total    = summary.get("total_axes", 0)
    axis     = summary.get("current_axis", "—")

    col1, col2, col3 = st.columns(3)
    col1.metric("Questions asked", q_count)
    col2.metric("Axes covered", f"{covered} / {total}")
    col3.metric("Current axis", axis)

    st.divider()
    st.subheader("Question")
    st.info(session.get("question", ""))

    with st.form("answer_form", clear_on_submit=True):
        answer = st.text_area("Your answer", height=120, placeholder="Type your answer here...")
        submitted = st.form_submit_button("Submit answer →")

    if submitted:
        if not answer.strip():
            st.warning("Please type an answer before submitting.")
        else:
            with st.spinner("Analysing response..."):
                result = submit_answer(session_id, answer)
            if result:
                st.session_state["interview_session"] = result
                st.rerun()

# ── Completed ─────────────────────────────────────────────────────────────────

elif status == "completed":
    result_data = session.get("result", {})
    scoring    = result_data.get("scoring", {})
    evaluation = result_data.get("evaluation", {})
    entretien  = result_data.get("entretien", {})

    recommendation = evaluation.get("recommandation", "N/A")
    color = {"A convoquer": "✅", "A rejeter": "❌"}.get(recommendation, "⚠️")

    st.success(f"{color} Recommendation: **{recommendation}**")

    col1, col2, col3 = st.columns(3)
    col1.metric("Initial score",   f"{scoring.get('score_matching_initial', 0):.0%}")
    col2.metric("Interview score", f"{scoring.get('score_entretien', 0):.0%}")
    col3.metric("Final score",     f"{scoring.get('score_final', 0):.0%}")

    st.divider()
    st.subheader("Summary")
    st.write(evaluation.get("resume", ""))

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Strengths")
        for point in evaluation.get("points_forts", []):
            st.write(f"✔ {point}")
    with col_b:
        st.subheader("Weaknesses")
        for point in evaluation.get("points_faibles", []):
            st.write(f"✘ {point}")

    doubts = evaluation.get("zones_de_doute", [])
    if doubts:
        st.subheader("Areas of doubt")
        for d in doubts:
            st.write(f"• {d}")

    with st.expander("Full interview transcript"):
        for qa in entretien.get("historique_qa", []):
            st.markdown(f"**Q ({qa.get('axe', '')}):** {qa.get('question', '')}")
            st.markdown(f"**A:** {qa.get('reponse', '')}")
            st.divider()

    with st.expander("Raw JSON result"):
        st.json(result_data)
