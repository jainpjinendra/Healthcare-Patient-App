from backend.pinecone_client import Pinecone, index
import requests
from openai import OpenAI
import os

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')


def ask_mistral(prompt: str, max_tokens: int = 1024) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [
            {
                "role": "system",
                "content": "You are a medical lab assistant. Use markdown with emojis/tables."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": max_tokens
    }
    
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        return f"⚠️ API Error: {str(e)}"


def get_patient_reports(user_id):
    
    # Query Pinecone for all vectors with this user_id as metadata
    results = index.query(
        vector=[0]*384,  # Dummy vector for metadata-only search
        filter={"user_id": {"$eq": user_id}},
        top_k=1000,
        include_metadata=True
    )
    
    # Extract and concatenate all report chunks
    reports = [match.metadata['text'] for match in results.matches]
    return "\n\n".join(reports)


def get_patient_summary(report_text):
    
    prompt = f"""
    Analyze the following patient medical reports and generate a structured health summary 
    in markdown format similar to this example:
    
    # AI health summary of [Patient Name]
    
    ## Medical profile
    
    | Condition 1 | Condition 2 | Medication |
    |---|---|---|
    | Details | Details | Details |
    
    ### Detailed Findings
    - Condition details
    - Timeline of diagnoses
    - Prescribed treatments
    
    ## Recommended Tests
    - Test 1 (Reason)
    - Test 2 (Reason)
    
    Here are the patient reports to analyze:
    {report_text}
    """
    
    response = ask_mistral(prompt)
    
    return response

