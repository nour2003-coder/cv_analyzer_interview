from dotenv import load_dotenv
import os
import requests
import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from uuid import uuid4
from json_repair import repair_json
import json
import re

load_dotenv()

model_name = os.getenv("model_name")
api_key  = os.getenv("api_key")
api_key2 = os.getenv("api_key2")
api_key3 = os.getenv("api_key3")
API_URL  = os.getenv("API_URL")
API_KEY  = os.getenv("API_KEY")
API_HOST = os.getenv("API_HOST")

failed_job_details = {
    "required_skills": [],
    "preferred_skills": [],
    "min_experience": None,
    "education": ""
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

model = SentenceTransformer("all-MiniLM-L6-v2")


# ─────────────────────────────────────────────
# Text utilities
# ─────────────────────────────────────────────

def clean_text(ch):
    ch = ch.replace('json', "")
    ch = ch.replace('```', "")
    ch = re.sub(r'[^\w\s]', '', ch)
    ch = re.sub(r'\s+', ' ', ch)
    ch = ch.encode('ascii', 'ignore').decode('ascii')
    ch = ch.lower()
    ch = re.sub(r'http\S+', '', ch)
    return ch.strip()


def extract_year(date_str):
    if date_str:
        match = re.search(r'(\d{4})', str(date_str))
        if match:
            return int(match.group(1))
    return None


# ─────────────────────────────────────────────
# CV feature extraction
# ─────────────────────────────────────────────

def get_cv_text_features(cv):
    skills      = cv["skills_and_interests"]["technical_skills"]
    soft_skills = cv["skills_and_interests"].get("soft_skills", [])
    all_skills  = skills + soft_skills

    projects   = [p["description"] for p in cv.get("projects", [])]
    experience = [" ".join(w.get("responsibilities", [])) for w in cv.get("work_experience", [])]
    education  = " ".join([e.get("field_of_study", "") for e in cv.get("education", [])])

    return {
        "skills":     all_skills,
        "projects":   " ".join(projects),
        "experience": " ".join(experience),
        "education":  education,
    }


def extract_cv_experience_years(cv):
    total_years = 0
    for job in cv.get("work_experience", []):
        start_year = extract_year(job.get("start_date"))
        end_year   = extract_year(job.get("end_date"))
        if start_year is None:
            continue
        if end_year is None:
            end_year = 2026
        duration = end_year - start_year
        if duration > 0:
            total_years += duration
    return total_years


# ─────────────────────────────────────────────
# Scoring helpers
# ─────────────────────────────────────────────

def semantic_match(text1, text2):
    if not text1 or not text2:
        return 0
    emb1 = model.encode(text1)
    emb2 = model.encode(text2)
    return cosine_similarity([emb1], [emb2])[0][0]


def skill_match_count(cv_skills, jd_skills, threshold=0.75):
    if not jd_skills:
        return 0, 0, set()

    cv_skills = [s.lower() for s in cv_skills]
    jd_skills = [s.lower() for s in jd_skills]

    matched = set(cv_skills) & set(jd_skills)   # exact matches first

    cv_embs = model.encode(cv_skills)
    jd_embs = model.encode(jd_skills)

    for i, jd_skill in enumerate(jd_skills):
        best_score, best_match = 0, None
        for j, cv_skill in enumerate(cv_skills):
            sim = cosine_similarity([cv_embs[j]], [jd_embs[i]])[0][0]
            if sim > best_score:
                best_score, best_match = sim, cv_skill
        if best_score >= threshold and best_match:
            matched.add(best_match)

    return len(matched), len(jd_skills), matched


def experience_score(cv_exp_years, required_exp):
    if not required_exp:
        return 1.0
    return min(cv_exp_years / required_exp, 1.0)


def education_score(cv_edu, jd_edu):
    s=semantic_match(cv_edu, jd_edu)
    if s>0:
        return s
    return 0


# ─────────────────────────────────────────────
# Ranking
# ─────────────────────────────────────────────

def rank_cvs(cvs, jd):
    results = []

    for cv in cvs:
        features = get_cv_text_features(cv)

        matched_req, total_req, matched_skills = skill_match_count(
            features["skills"], jd["required_skills"]
        )
        req_score = matched_req / total_req if total_req else 0

        matched_pref, total_pref, _ = skill_match_count(
            features["skills"] + features["projects"].split(),
            jd["preferred_skills"]
        )
        pref_score = matched_pref / total_pref if total_pref else 0

        skills_score = 0.7 * req_score + 0.3 * pref_score

        cv_exp = extract_cv_experience_years(cv)
        if cv.get("work_experience") and cv_exp == 0:
            cv_exp = 1

        exp_score = experience_score(cv_exp, jd.get("min_experience") or 0)
        edu_score = education_score(features["education"], jd.get("education", ""))

        final_score = 0.5 * skills_score + 0.3 * exp_score + 0.2 * edu_score

        results.append({
            "name":                    cv["personal_information"]["full_name"],
            "matched_required_skills": list(matched_skills),
            "required_score":          round(req_score,    3),
            "preferred_score":         round(pref_score,   3),
            "experience_score":        round(exp_score,    3),
            "education_score":         round(edu_score,    3),
            "final_score":             round(final_score,  3),
            "cv":                      cv,
        })

    return sorted(results, key=lambda x: x["final_score"], reverse=True)


# ─────────────────────────────────────────────
# LLM setup — no vector store needed
# ─────────────────────────────────────────────

def setup_llm(key):
    """Return a simple prompt | LLM | parser chain.
    The job description is injected directly into the prompt,
    so no retriever / vector store is required at all."""
    llm = ChatOpenAI(
        model=model_name,
        api_key=key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0,
        max_retries=3,
        request_timeout=60,
    )

    prompt = ChatPromptTemplate.from_template("""
You are an expert HR information extraction assistant.

Extract the following fields from the job description below:
- required_skills
- preferred_skills
- min_experience (integer number of years, or null if not specified)
- education (degree / field requirement as a short string, or "" if not specified)

Return ONLY valid JSON — no explanation, no markdown fences:
{{
  "required_skills": [],
  "preferred_skills": [],
  "min_experience": null,
  "education": ""
}}

Job Description:
{job_description}
""")

    return prompt | llm | StrOutputParser()


# ─────────────────────────────────────────────
# JSON parsing
# ─────────────────────────────────────────────

def json_parser(ch, failed_json):
    for attempt in (
        lambda: json.loads(ch),
        lambda: json.loads(repair_json(ch)),
        lambda: json.loads(clean_text(ch)),
    ):
        try:
            result = attempt()
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    logger.warning("json_parser: all strategies failed.")
    return failed_json


def extract_info(job_description, llm_chain, failed_json):
    try:
        raw = llm_chain.invoke({"job_description": job_description})
        result = json_parser(raw, failed_json)
        return failed_json if result == {} else result
    except Exception as e:
        logger.error(f"LLM invocation failed: {e}")
        return failed_json


def extract_with_fallback(job_description, chains, failed_json):
    for i, chain in enumerate(chains):
        if chain is None:
            continue
        result = extract_info(job_description, chain, failed_json)
        if result not in (failed_json, {}):
            logger.info(f"LLM chain #{i + 1} succeeded.")
            return result
        logger.warning(f"LLM chain #{i + 1} failed, trying next...")
    return failed_json


# ─────────────────────────────────────────────
# RapidAPI CV parser (unchanged)
# ─────────────────────────────────────────────

def parse_with_rapidapi(data_path, api_key, api_host, api_url, timeout=30):
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": api_host,
    }
    try:
        with open(data_path, "rb") as f:
            files = {"resume": (data_path, f, "application/pdf")}
            response = requests.post(api_url, headers=headers, files=files, timeout=timeout)
        response.raise_for_status()
        try:
            return response.json()
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON from RapidAPI.")
            return None
    except FileNotFoundError:
        logger.error(f"File not found: {data_path}")
    except requests.exceptions.Timeout:
        logger.error("RapidAPI request timed out.")
    except requests.exceptions.RequestException as e:
        logger.error(f"RapidAPI request failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected RapidAPI error: {e}")
    return None


# ─────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────

def rank(job_description, cvs):
    chains = [
        setup_llm(api_key),
        setup_llm(api_key2),
        setup_llm(api_key3),
    ]

    job_details = extract_with_fallback(job_description, chains, failed_job_details)
    logger.info(f"Extracted JD details: {job_details}")

    return rank_cvs(cvs, job_details)