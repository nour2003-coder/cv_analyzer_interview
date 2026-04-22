"""
HR Ranking page — rank applicants and launch chatbot pre-selection interviews.
"""

import io
import os
import sys

import requests
import streamlit as st
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, PyMongoError
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import cv_ranking.rank_cv as ranker
from chatbot.cv_adapter import cv_to_candidate_input

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB_NAME", "cv_database")
COLLECTION_NAME = os.getenv("MONGO_COLLECTION", "cvs")
CHATBOT_API_URL = os.getenv("CHATBOT_API_URL", "http://localhost:8001")


# ── MongoDB ──────────────────────────────────────────────────────────────────

@st.cache_resource
def get_mongo_collection():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        return client[DB_NAME][COLLECTION_NAME]
    except ConnectionFailure as e:
        st.error(f"Could not connect to MongoDB: {e}")
        return None


def get_all_cvs():
    collection = get_mongo_collection()
    if collection is None:
        return []
    try:
        return list(collection.find())
    except PyMongoError as e:
        st.error(f"Failed to fetch CVs: {e}")
        return []


# ── PDF generation ────────────────────────────────────────────────────────────

def _safe(value, fallback="—"):
    if value is None:
        return fallback
    s = str(value).strip()
    return s if s else fallback


def normalize_skills(skills):
    cleaned = []
    for s in skills:
        if isinstance(s, dict):
            cleaned.append(s.get("skill") or s.get("name") or str(s))
        else:
            cleaned.append(str(s))
    return cleaned


def generate_cv_pdf(res: dict) -> bytes:
    cv = res["cv"]
    info = cv.get("personal_information", {})
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                             leftMargin=2*cm, rightMargin=2*cm,
                             topMargin=2*cm, bottomMargin=2*cm)

    base = getSampleStyleSheet()
    ACCENT = colors.HexColor("#1E3A5F")
    LIGHT  = colors.HexColor("#EEF2F7")

    h1     = ParagraphStyle("h1", parent=base["Heading1"], fontSize=20, textColor=ACCENT, spaceAfter=2)
    h2     = ParagraphStyle("h2", parent=base["Heading2"], fontSize=12, textColor=ACCENT,
                             spaceBefore=10, spaceAfter=4, backColor=LIGHT)
    normal = ParagraphStyle("normal", parent=base["Normal"], fontSize=9, leading=14)
    small  = ParagraphStyle("small", parent=base["Normal"], fontSize=8,
                             textColor=colors.HexColor("#555555"), leading=12)
    bold9  = ParagraphStyle("bold9", parent=normal, fontName="Helvetica-Bold")

    story = []
    story.append(Paragraph(_safe(info.get("full_name"), "Unknown Candidate"), h1))
    contacts = " · ".join(filter(None, [
        info.get("email"), info.get("phone"),
        cv.get("website_and_social_links", {}).get("linkedin"),
    ]))
    if contacts:
        story.append(Paragraph(contacts, small))
    story.append(HRFlowable(width="100%", thickness=1.5, color=ACCENT, spaceAfter=6))

    story.append(Paragraph("Ranking Scores", h2))

    def _pct(v):
        try:
            return f"{float(v) * 100:.1f}%"
        except Exception:
            return _safe(v)

    score_data = [
        ["Metric", "Score"],
        ["Required skills",  _pct(res.get("required_score",   0))],
        ["Preferred skills", _pct(res.get("preferred_score",  0))],
        ["Experience",       _pct(res.get("experience_score", 0))],
        ["Education",        _pct(res.get("education_score",  0))],
        ["Overall",          _pct(res.get("final_score",      0))],
    ]
    t = Table(score_data, colWidths=[10*cm, 6*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 6))

    matched = res.get("matched_required_skills", [])
    if matched:
        story.append(Paragraph(
            "<b>Matched required skills:</b> " + ", ".join(map(str, normalize_skills(matched))), small))

    summary = cv.get("professional_summary", "")
    if summary:
        story.append(Paragraph("Professional Summary", h2))
        story.append(Paragraph(summary, normal))

    education = cv.get("education", [])
    if education:
        story.append(Paragraph("Education", h2))
        for edu in education:
            story.append(Paragraph(
                f"<b>{_safe(edu.get('degree'))}</b> – {edu.get('field_of_study', '')}", bold9))
            story.append(Paragraph(
                f"{_safe(edu.get('school'))}  |  {_safe(edu.get('end_year'))}", small))
            story.append(Spacer(1, 3))

    work = cv.get("work_experience", [])
    if work:
        story.append(Paragraph("Work Experience", h2))
        for job in work:
            story.append(Paragraph(
                f"<b>{_safe(job.get('job_title'))}</b> · {_safe(job.get('company'))}", bold9))
            story.append(Paragraph(
                f"{job.get('location', '')}  |  {_safe(job.get('start_date'), '')} – {_safe(job.get('end_date'), 'present')}",
                small))
            for resp in job.get("responsibilities", []):
                story.append(Paragraph(f"• {resp}", normal))
            story.append(Spacer(1, 4))

    skills_block = cv.get("skills_and_interests", {})
    tech  = skills_block.get("technical_skills", [])
    soft  = skills_block.get("soft_skills", [])
    langs = skills_block.get("languages", [])
    if tech or soft or langs:
        story.append(Paragraph("Skills", h2))
        if tech:
            story.append(Paragraph("<b>Technical:</b> " + ", ".join(map(str, tech)), normal))
        if soft:
            story.append(Paragraph("<b>Soft skills:</b> " + ", ".join(map(str, soft)), normal))
        if langs:
            story.append(Paragraph("<b>Languages:</b> " + ", ".join(map(str, langs)), normal))

    doc.build(story)
    return buffer.getvalue()


# ── Chatbot integration ───────────────────────────────────────────────────────

def start_chatbot_interview(cv: dict, job_data: dict, score: float) -> dict | None:
    """Call the FastAPI chatbot to start an interview session."""
    candidate_input = cv_to_candidate_input(cv, float(score))
    payload = {
        "cv": candidate_input,
        "job": job_data,
        "score_matching_initial": float(score),
    }
    try:
        resp = requests.post(f"{CHATBOT_API_URL}/interview/start", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error("Chatbot API is not running. Start it with: `uvicorn api:app --reload --port 8001`")
    except Exception as e:
        st.error(f"Failed to start interview: {e}")
    return None



# ── UI ────────────────────────────────────────────────────────────────────────

st.title("CV Ranking & Pre-selection")
st.write("Enter a job description to rank all applicants, then optionally launch a chatbot interview.")

with st.form("job_form"):
    job_title       = st.text_input("Job Title")
    job_description = st.text_area("Job Description", height=150)
    submitted       = st.form_submit_button("Rank CVs")

if submitted:
    if not job_description.strip():
        st.warning("Please enter a job description.")
    else:
        with st.spinner("Ranking CVs..."):
            try:
                cvs = get_all_cvs()
                if not cvs:
                    st.warning("No CVs in database yet.")
                    st.session_state.pop("ranking_results", None)
                    st.session_state.pop("job_data", None)
                else:
                    st.session_state["ranking_results"] = ranker.rank(job_description, cvs)
                    st.session_state["job_data"] = {
                        "titre_poste": job_title,
                        "competences_obligatoires": [],
                        "competences_tres_appreciees": [],
                        "soft_skills_requis": [],
                        "description": job_description,
                    }
                    st.success("Ranking complete.")
            except Exception as e:
                st.error(f"Error: {e}")

# ── Results ───────────────────────────────────────────────────────────────────

if "ranking_results" in st.session_state:
    for i, res in enumerate(st.session_state["ranking_results"], 1):
        info = res["cv"].get("personal_information", {})
        candidate_key = f"candidate_{i}"

        with st.container():
            col_rank, col_info, col_pdf, col_chat = st.columns([0.5, 4.5, 1.5, 2])

            with col_rank:
                st.markdown(f"### #{i}")

            with col_info:
                st.write(f"**{res['name']}**")
                st.write(info.get("email", ""))
                st.write(f"Score: `{res['final_score']}`")

            with col_pdf:
                pdf_bytes = generate_cv_pdf(res)
                safe_name = (res["name"] or "candidate").replace(" ", "_")
                st.download_button(
                    label="📄 PDF",
                    data=pdf_bytes,
                    file_name=f"{safe_name}_report.pdf",
                    mime="application/pdf",
                    key=f"dl_{i}",
                )

            with col_chat:
                if st.button("💬 Start Interview", key=f"chat_{i}"):
                    session = start_chatbot_interview(
                        cv=res["cv"],
                        job_data=st.session_state.get("job_data", {}),
                        score=res["final_score"],
                    )
                    if session:
                        st.session_state["interview_session"] = session
                        st.session_state["interview_candidate"] = res["name"]
                        st.switch_page("pages/3_Interview.py")

        st.divider()
