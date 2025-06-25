import requests
import os
import json
from datetime import datetime
from backend.pinecone_client import get_relevant_chunks, embedder, index, query_chunks
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Pinecone instance


OPENROUTER_API_KEY="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"


def ask_gemma(prompt: str, max_tokens: int = 1024) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "google/gemma-3-27b-it:free",
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

def general_lab_query(query):
    if not query:
        return "Query parameter required"

    prompt = f"""You are an expert medical assistant system helping a lab technician understand various medical lab tests and procedures performed on patients.

    The lab technician may ask questions about lab tests, procedures, abnormalities, or result interpretations. Always assume they are referring to a **patient** (not themselves), and answer in a third-party perspective.

    When responding, make sure to:

    - 🎯 Focus on the **patient** as the subject
    - 🧬 Clearly explain the **purpose** of the test
    - 🧪 Describe the **procedure** the patient will go through
    - 📋 Mention any **pre-test preparations** or precautions needed by the patient
    - 📈 If relevant, include **normal range values** in markdown tables
    - 🧾 Add **post-test recommendations** or technician-specific considerations

    Maintain a professional and informative tone. Use simple formatting like lists or tables when helpful.
    Include: emoji, tables, and markdown formatting to enhance readability.(where applicable)

    **Lab Technician's Query:** "{query}"
    """
    
    response = ask_gemma(prompt)
    return response


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

def patient_specific_query(report_text, query):
    
    prompt = f"""**Context:**  
    You are a medical chatbot assistant designed to help lab technicians interpret patient reports. You're having a conversation with a lab technician about a specific patient whose lab report data is provided below.

    **Patient Report Data :{report_text}**  

    **Current User Query:**  
    {query}

    **Response Requirements:**  
    1. Format as a natural conversation between chatbot (you) and technician
    2. Begin by confirming which patient you're discussing
    3. For numerical values, always show:
    - The patient's value
    - The normal reference range
    - Interpretation (high/normal/low)
    4. Use appropriate medical terminology but explain when needed
    5. Highlight critical values that need immediate attention
    6. Suggest possible next steps when relevant
    7. Format with clear sections using markdown:

    **Example Response Structure:**

    **Chatbot:** [Confirm patient] "We're reviewing the lab results for [Patient Name], [Age]. What specific aspect would you like to discuss?"

    **Technician:** [Restate or summarize their query]

    **Chatbot:**  
    - **Test Name:** [Value] (Reference Range: [X-Y])  
    **Interpretation:** [Explanation]  
    **Clinical Significance:** [Relevance to patient]  
    [Additional details if needed]  

    **Follow-up Question:** [Optional suggested question technician might want to ask next]

    **Visual Elements to Include When Appropriate:**
    - Bold text for critical values
    - Bullet points for multiple findings
    - Tables for comparative data
    - Horizontal rules between different test groups
        """
    
    response = ask_mistral(prompt)
    
    return response
