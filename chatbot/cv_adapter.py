"""
Converts an extracted CV dict (from cv_extraction.extraire_cv)
into the CandidateInputModel shape expected by the chatbot.
"""

from typing import Any, Dict


def cv_to_candidate_input(cv: Dict[str, Any], score: float = 0.78) -> Dict[str, Any]:
    """
    Map the CV extraction schema → chatbot CandidateInputModel schema.

    CV extraction schema keys used:
      personal_information.full_name / email / phone
      skills_and_interests.technical_skills / soft_skills / languages
      work_experience[].job_title / company / responsibilities / start_date / end_date
      projects[].name / description
    """
    info = cv.get("personal_information", {})
    skills = cv.get("skills_and_interests", {})

    # Build experiences list
    experiences = []
    for job in cv.get("work_experience", []):
        start = job.get("start_date", "")
        end = job.get("end_date", "") or "present"
        desc = job.get("responsibilities", [])
        if isinstance(desc, list):
            desc = " ".join(desc)
        experiences.append({
            "titre": job.get("job_title", ""),
            "entreprise": job.get("company", ""),
            "description": desc,
            "duree_mois": None,
        })

    # Build projects list
    projects = [
        {"nom": p.get("name", ""), "description": p.get("description", "")}
        for p in cv.get("projects", [])
    ]

    # Languages as list of strings
    raw_langs = skills.get("languages", [])
    langs = []
    for lang in raw_langs:
        if isinstance(lang, dict):
            langs.append(lang.get("name", ""))
        else:
            langs.append(str(lang))

    return {
        "nom": info.get("full_name") or "Candidat",
        "email": info.get("email"),
        "telephone": info.get("phone"),
        "competences": {
            "techniques": skills.get("technical_skills", []),
            "soft_skills": skills.get("soft_skills", []),
        },
        "experiences": experiences,
        "projets_personnels": projects,
        "langues": [l for l in langs if l],
        "score_matching_init": score,
    }
