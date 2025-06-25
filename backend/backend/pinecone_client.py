import re
from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer

pc = Pinecone(api_key="pcsk_4zT1Re_8359xzexpKV4FK3NYzYVv6U6LqNocikdsQeQAmeFQQ8BPYiJVUv8uRa1d81tkfA")  # Replace with your key

# Connect to the index
index_name = "medical"  # Replace with your index
index = pc.Index(index_name)
embedder = SentenceTransformer('all-MiniLM-L6-v2')

def sanitize_patient_name(patient_name):
    """Sanitize patient name for use in vector IDs"""
    if not patient_name:
        return "unknown_patient"
    
    # Remove special characters and replace spaces with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9\s]', '', patient_name)
    sanitized = re.sub(r'\s+', '_', sanitized.strip())
    
    # Limit length to avoid Pinecone ID length issues
    if len(sanitized) > 50:
        sanitized = sanitized[:50]
    
    return sanitized.lower()

def get_relevant_chunks(query, user_id, top_k=10):
    query_vector = embedder.encode(query).tolist()  # Assuming you have `embedder`

    # Handle case where user_id is None or empty
    if not user_id:
        return []

    # Build filter based on user_id (adjust key if your metadata uses "patient_name")
    filter_dict = {"user_id": {"$eq": user_id}}

    # Query Pinecone with metadata filter
    result = index.query(
        vector=query_vector,
        top_k=top_k,
        include_metadata=True,
        filter=filter_dict
    )

    formatted_chunks = []
    for match in result['matches']:
        metadata = match['metadata']
        text = metadata.get('text', '')

        formatted_chunks.append(text)

    return formatted_chunks

def chunk_text(text, max_tokens=300):
    sentences = text.split('.')
    chunks = []
    chunk = ""
    for sentence in sentences:
        if len(chunk + sentence) < max_tokens:
            chunk += sentence.strip() + ". "
        else:
            chunks.append(chunk.strip())
            chunk = sentence.strip() + ". "
    if chunk:
        chunks.append(chunk.strip())
    return chunks


def upsert_chunks(user_id, report_id, text):
    chunks = chunk_text(text)
    vectors = []

    # Sanitize the user_id (patient name) for use in vector IDs
    sanitized_user_id = sanitize_patient_name(user_id)
    
    # Add timestamp to ensure uniqueness even if same patient uploads multiple reports
    import time
    timestamp = int(time.time())
    
    for i, chunk in enumerate(chunks):
        embedding = embedder.encode(chunk).tolist()
        # Create unique vector ID with timestamp to prevent overwrites
        vector_id = f"{sanitized_user_id}_{report_id}_{timestamp}_{i}"
        
        vectors.append({
            "id": vector_id,
            "values": embedding,
            "metadata": {
                "user_id": user_id,  # Keep original patient name in metadata
                "report_id": report_id,
                "text": chunk,
                "timestamp": timestamp,
                "chunk_index": i
            }
        })

    index.upsert(vectors=vectors)

def delete_patient_chunks(user_id):
    """Delete all chunks for a specific patient"""
    if not user_id:
        return
    
    try:
        # Delete vectors by metadata filter
        index.delete(filter={"user_id": {"$eq": user_id}})
        print(f"Deleted all chunks for patient: {user_id}")
    except Exception as e:
        print(f"Error deleting chunks for patient {user_id}: {e}")

def get_patient_chunks_count(user_id):
    """Get the number of chunks stored for a specific patient"""
    if not user_id:
        return 0
    
    try:
        # Query with a dummy vector to get count
        dummy_vector = embedder.encode("dummy").tolist()
        result = index.query(
            vector=dummy_vector,
            top_k=1000,  # Large number to get all chunks
            include_metadata=True,
            filter={"user_id": {"$eq": user_id}}
        )
        return len(result['matches'])
    except Exception as e:
        print(f"Error getting chunk count for patient {user_id}: {e}")
        return 0

def delete_report_chunks(report_id):
    """Delete all chunks for a specific report"""
    if not report_id:
        return
    try:
        index.delete(filter={"report_id": {"$eq": report_id}})
        print(f"Deleted all chunks for report: {report_id}")
    except Exception as e:
        print(f"Error deleting chunks for report {report_id}: {e}")

def query_chunks(query: str, k: int = 50) -> list:
    """
    Get relevant chunks from Pinecone with metadata
    
    Args:
        query: The query string to search for
        k: Number of chunks to return (default: 50)
    
    Returns:
        List of dictionaries containing text and metadata
    """
    # Extract patient name from query if in format "patient:name"
    patient_name = None
    if query.startswith("patient:"):
        patient_name = query.split(":", 1)[1]
        query = patient_name  # Use just the name for semantic search
    
    # Create query vector
    query_vector = embedder.encode(query).tolist()
    
    # Build query params
    query_params = {
        "vector": query_vector,
        "top_k": k,
        "include_metadata": True
    }
    
    # Add filter if patient name is specified
    if patient_name:
        query_params["filter"] = {"user_id": {"$eq": patient_name}}
    
    # Query Pinecone
    result = index.query(**query_params)
    
    # Format results
    chunks = []
    for match in result.matches:
        chunk = {
            'text': match.metadata.get('text', ''),
            'metadata': {
                'report_type': match.metadata.get('report_type', 'Unknown'),
                'report_date': match.metadata.get('report_date', ''),
                'report_id': match.metadata.get('report_id', ''),
                'chunk_index': match.metadata.get('chunk_index', 0)
            }
        }
        chunks.append(chunk)
    
    return chunks