"""
Candidate CV upload and extraction page.
"""

import os
from datetime import datetime, timezone

import streamlit as st
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, PyMongoError

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import cv_extraction.extraire_cv as extractor

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB_NAME", "cv_database")
COLLECTION_NAME = os.getenv("MONGO_COLLECTION", "cvs")
SAVE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploaded_cvs")


@st.cache_resource
def get_mongo_collection():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        return client[DB_NAME][COLLECTION_NAME]
    except ConnectionFailure as e:
        st.error(f"Could not connect to MongoDB: {e}")
        return None


def save_cv_to_mongo(cv: dict) -> bool:
    collection = get_mongo_collection()
    if collection is None:
        return False
    try:
        result = collection.insert_one({**cv, "uploaded_at": datetime.now(timezone.utc)})
        return result.acknowledged
    except PyMongoError as e:
        st.error(f"Failed to save CV: {e}")
        return False


st.title("Apply — Upload your CV")
st.write("Upload your CV in PDF format. Your information will be extracted and stored securely.")

os.makedirs(SAVE_DIR, exist_ok=True)

cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])

if cv_file is not None:
    file_path = os.path.join(SAVE_DIR, cv_file.name)
    with open(file_path, "wb") as f:
        f.write(cv_file.read())

    st.success("CV uploaded successfully.")

    with st.spinner("Extracting CV information..."):
        cv = extractor.extract_cv(file_path)

    if cv:
        st.subheader("Extracted Information")
        st.json(cv)

        with st.spinner("Saving to database..."):
            saved = save_cv_to_mongo(cv)

        if saved:
            st.success("CV saved to database.")
        else:
            st.error("Extraction succeeded but saving to database failed.")
    else:
        st.error("CV extraction failed. Please try a different file.")
