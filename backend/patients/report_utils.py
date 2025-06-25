import re
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from datetime import datetime 
import requests
import json
import fitz
from sentence_transformers import SentenceTransformer
from backend.pinecone_client import upsert_chunks
import os
import uuid
import demjson3
import logging

# Global variable for the model, to be loaded lazily
model = None
MODEL_NAME = 'all-MiniLM-L6-v2'

AZURE_ENDPOINT = os.environ.get('AZURE_ENDPOINT')
AZURE_KEY = os.environ.get('AZURE_KEY')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')

def get_sentence_transformer_model():
    """
    Loads the SentenceTransformer model if it hasn't been loaded yet.
    """
    global model
    if model is None:
        logging.info("Loading SentenceTransformer model...")
        model = SentenceTransformer(MODEL_NAME)
        logging.info("SentenceTransformer model loaded.")
    return model

def extract_report_date(text: str) -> str:
    """
    Enhanced function to extract report date from medical report text
    Handles multiple date formats and locations
    """
    # Common date patterns in medical reports
    date_patterns = [
        # Pattern 1: "Report Time:" followed by date (from your sample)
        r'(?:Report\s*Time|Date\s*of\s*Report)[:\s]*([A-Za-z]{3}\s\d{1,2},\s\d{4}(?:,\s\d{1,2}:\d{2}\s[AP]M)?)',
        # Pattern 2: Standalone dates in common formats
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s\d{1,2},\s\d{4}\b',
        r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
        r'\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b',
        # Pattern 3: Dates near signature/authorization areas
        r'(?:Signed|Date|Reported)\s*:\s*([A-Za-z]{3}\s\d{1,2},\s\d{4})'
    ]
    
    # Try each pattern in order
    for pattern in date_patterns:
        matches = re.search(pattern, text, re.IGNORECASE)
        if matches:
            date_str = matches.group(1) if matches.groups() else matches.group(0)
            try:
                # Standardize the date format (adjust as needed)
                if ',' in date_str and ':' in date_str:
                    # Handle datetime format like "Apr 14, 2025, 08:22 PM"
                    dt = datetime.strptime(date_str, '%b %d, %Y, %I:%M %p')
                    return dt.strftime('%Y-%m-%d')
                elif ',' in date_str:
                    # Handle date format like "Apr 14, 2025"
                    dt = datetime.strptime(date_str, '%b %d, %Y')
                    return dt.strftime('%Y-%m-%d')
                else:
                    # Handle other formats (DD/MM/YYYY, etc.)
                    return date_str
            except ValueError:
                # If parsing fails, return the raw string
                return date_str
    
    return None

def analyze_medical_report(pdf_path):
    """Analyze medical report using Azure Form Recognizer"""
    if not AZURE_ENDPOINT or not AZURE_KEY:
        raise ValueError("Azure Form Recognizer endpoint or key not configured")
    
    document_analysis_client = DocumentAnalysisClient(
        endpoint=AZURE_ENDPOINT,
        credential=AzureKeyCredential(AZURE_KEY),
        api_version="2023-07-31"
    )

    with open(pdf_path, "rb") as f:
        poller = document_analysis_client.begin_analyze_document(
            "prebuilt-document", 
            document=f
        )
    
    result = poller.result()
    
    # Initialize structured data container
    report_data = {
        "patient_name": None,
        "age": None,
        "sex": None,
        "report_date": None,
        "report_type": None,
        "parameters": [],
        "observations": [],
        "advise": []
    }

    # Extract data from key-value pairs
    for kv_pair in result.key_value_pairs:
        key = kv_pair.key.content.lower() if kv_pair.key else ""
        value = kv_pair.value.content if kv_pair.value else ""
        flag = 1
        if "name" in key:
            report_data["patient_name"] = value
        elif "sex" in key or "gender" in key:
            report_data["sex"] = "Male" if "male" in value.lower() else "Female"
            if "age" in key:
                report_data["age"] = int(re.findall(r"-?\d+\.?\d*", value)[0])
                flag = 0
        elif "age" in key and flag:
            report_data["age"] = re.findall(r"-?\d+\.?\d*", value)

    # Extract tables (for numerical parameters)
    for table_idx, table in enumerate(result.tables):
        cells = [cell.content for cell in table.cells]
        flag = 1
        if table.row_count > 1:
            headers = cells[:table.column_count]
            for row_idx in range(1, table.row_count):
                row_start = row_idx * table.column_count
                row_data = cells[row_start:row_start + table.column_count]
                if flag:
                    report_data["report_type"] = row_data[0]
                    flag = 0
                elif len(row_data) >= 3 and not flag:
                    if row_data[3]:
                        if '-' in row_data[3]:
                            report_data["parameters"].append({
                        "name": row_data[0],
                        "value": row_data[1],
                        "unit": row_data[2] if len(row_data) > 2 else "",
                        "normal_range": row_data[3] if len(row_data) > 3 else "",
                        "status": "low" if float(row_data[1]) < float(row_data[3].split(' ')[0]) else "high" if float(row_data[1]) > float(row_data[3].split(' ')[2]) else "normal"
                            })
                        elif "<" in row_data[3]:
                            report_data["parameters"].append({
                                "name": row_data[0],
                                "value": row_data[1],
                                "unit": row_data[2] if len(row_data) > 2 else "",
                                "normal_range": row_data[3] if len(row_data) > 3 else "",
                                "status": "high" if float(row_data[1]) > float(row_data[3].replace('<', '').strip()) else "normal"
                            })
                        elif "<" in row_data[3]:
                            report_data["parameters"].append({
                                "name": row_data[0],
                                "value": row_data[1],
                                "unit": row_data[2] if len(row_data) > 2 else "",
                                "normal_range": row_data[3] if len(row_data) > 3 else "",
                                "status": "low" if float(row_data[1]) < float(row_data[3].replace('<', '').strip()) else "normal"
                            })


    # Extract findings and advise
    findings_keywords = ["finding", "impression", "observation"]
    advise_keywords = ["advise", "recommendation", "plan"]
    
    for paragraph in result.paragraphs:
        content = paragraph.content.lower()
        if any(keyword in content for keyword in findings_keywords):
            report_data["observations"].append(paragraph.content)
        elif any(keyword in content for keyword in advise_keywords):
            report_data["advise"].append(paragraph.content)
    report_data["report_date"] = extract_report_date(result.content)
    
    return report_data

def extract_json_block(text):
    # Try to find the first {...} block
    match = re.search(r'(\{[\s\S]*\})', text)
    if match:
        return match.group(1)
    return text  # fallback

def clean_and_load_json(content):
    # Extract the first JSON object or array from the string
    match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', content)
    if not match:
        raise ValueError("No JSON object or array found in content")
    json_str = match.group(0)
    # Replace single quotes with double quotes
    json_str = json_str.replace("'", '"')
    # Replace Python None/True/False with JSON null/true/false
    json_str = json_str.replace('None', 'null')
    json_str = json_str.replace('True', 'true')
    json_str = json_str.replace('False', 'false')
    # Remove trailing commas before } or ]
    json_str = re.sub(r',([ \t\r\n]*[}\]])', r'\1', json_str)
    # Remove any trailing commas in arrays/objects
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    # Remove newlines and excessive whitespace
    json_str = re.sub(r'\n+', '\\n', json_str)
    json_str = re.sub(r'\s+', ' ', json_str)
    # Try to fix missing commas between items (very basic, not perfect)
    json_str = re.sub(r'"\s*([}\]])', r'"\1', json_str)
    # Convert normalized_value: number / number to normalized_value: "number / number"
    json_str = re.sub(
        r'("normalized_value"\s*:\s*)(-?\d+\.?\d*)\s*/\s*(-?\d+\.?\d*)',
        r'\1"\2 / \3"',
        json_str
    )
    # Escape unescaped double quotes inside string values
    def escape_inner_quotes(match):
        value = match.group(2)
        # Only escape quotes that are not already escaped
        value = re.sub(r'(?<!\\)"', r'\\"', value)
        return f'{match.group(1)}"{value}"'
    # This regex finds all "key": "value" pairs and escapes quotes inside value
    json_str = re.sub(r'(".*?":\s*)"((?:[^"\\]|\\.)*)"', escape_inner_quotes, json_str)
    # Try standard json.loads
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error: {e}\nProblematic string: {json_str}")
        # Try demjson3 as a fallback if available
        try:
            return demjson3.decode(json_str)
        except Exception as e2:
            logging.error(f"demjson3 fallback also failed: {e2}")
            raise ValueError(f"Failed to parse JSON: {e}\nProblematic string: {json_str}")

def enhance_medical_data(report_data, full_text):
    """Enhanced medical report analysis using Mistral-7B-Instruct model"""
    if not OPENROUTER_API_KEY:
        raise ValueError("OpenRouter API key not configured")
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://your-medical-app.com",
        "X-Title": "Medical Report Analysis"
    }

    prompt = """<s>[INST] <<SYS>>
    You are a medical analysis AI. Analyze this report and return JSON with:
    1. Parameter analysis (status, normalized values)
    2. Observation classification (normal/abnormal)
    3. Clinical recommendations
    <</SYS>>

    Patient Context:
    {patient_context}

    Report Excerpt:
    {report_excerpt}

    Return ONLY this JSON structure:
    {{
        "patient_name": None,
        "age": None,
        "sex": None,
        "report_date": None,
        "report_type": None,
        "parameters": [],
        "observations": [],
        "advise": []
    }}[/INST]"""

    formatted_prompt = prompt.format(
        patient_context=json.dumps({
            'name': report_data.get('patient_name'),
            'age': report_data.get('age'),
            'sex': report_data.get('sex'),
            'report_date': report_data.get('report_date')
        }, indent=2),
        report_excerpt=full_text[:7500]
    )


    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json={
            "model": "mistralai/mistral-7b-instruct",
            "messages": [{"role": "user", "content": formatted_prompt}],
            "temperature": 0.3,
            "max_tokens": 2500,
            "stop": ["</s>", "[INST]"]
        },
        timeout=60
    )

    if response.status_code == 200:
        content = response.json()['choices'][0]['message']['content']
        # Try to extract the first {...} block
        content = extract_json_block(content)
        # Remove trailing commas before } or ]
        content = re.sub(r',([ \t\r\n]*[}\]])', r'\1', content)
        try:
            enhanced_analysis = clean_and_load_json(content.strip())
        except json.JSONDecodeError as e:
            print("JSON decode error:", e)
            print("Content was:", repr(content))
            raise
        final_output = {
            "patient_name": report_data.get("patient_name"),
            "age": report_data.get("age"),
            "sex": report_data.get("sex"),
            "report_date": report_data.get("report_date"),
            "report_type": report_data.get("report_type"),
            "parameters": report_data.get("parameters"),
            "observations": enhanced_analysis["observations"],
            "advise": enhanced_analysis["advise"],
        }
        return final_output

def process_pdf_report(report_file_path):
    """
    Process PDF report, extract text, enhance it, and upsert to Pinecone.
    """
    # 1. Extract text and analyze with Azure Form Recognizer
    report_data = analyze_medical_report(report_file_path)
    
    # 2. Extract full text with PyMuPDF for context
    full_text = ""
    with fitz.open(report_file_path) as doc:
        for page in doc:
            full_text += page.get_text()
    
    # 3. Enhance data with OpenRouter
    enhanced_data = enhance_medical_data(report_data, full_text)

    # 4. Generate embeddings and upsert to Pinecone
    # Use the lazy-loaded model
    model = get_sentence_transformer_model()
    
    chunks = [str(v) for k, v in enhanced_data.items() if v]
    embeddings = model.encode(chunks)
    
    patient_id = enhanced_data.get('patient_id', str(uuid.uuid4()))
    report_id = str(uuid.uuid4())
    
    metadata_list = [{
        "patient_id": patient_id,
        "report_id": report_id,
        "document_part": k,
        "text_chunk": chunk
    } for k, chunk in zip(enhanced_data.keys(), chunks)]
    
    upsert_chunks(
        f"{patient_id}_{report_id}", 
        list(zip(embeddings, metadata_list))
    )
    
    return enhanced_data
