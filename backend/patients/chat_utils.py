from pinecone import Pinecone, ServerlessSpec
import requests
from openai import OpenAI
import os

OPENROUTER_API_KEY="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"

pc = Pinecone(api_key="pcsk_4zT1Re_8359xzexpKV4FK3NYzYVv6U6LqNocikdsQeQAmeFQQ8BPYiJVUv8uRa1d81tkfA")  # Replace with your key
index_name = "medical"  # Replace with your index
index = pc.Index(index_name)

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
    
    prompt = f"""You are MediBot 🤖, a friendly but professional medical chatbot designed to help patients access their own health data (reports, vitals, appointments) and answer basic queries.

    Rules:

    Strictly answer only what’s asked—no unsolicited advice or over-explaining.

    Tone: Warm but concise (use emojis sparingly for empathy 🩺💙).

    Format dynamically:

    Use bold/code for critical values.

    Bullets/tables for lists.

    Headers (---) to separate topics.

    Data Privacy: Never disclose hypothetical/other patients’ info.

    Patient Data Context : {report_text}
    Current User Query: {query}
        """
    
    response = ask_mistral(prompt)
    
    return response
