
import os
import logging
from pinecone import Pinecone, ServerlessSpec
import time

logger = logging.getLogger("rag-client")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = "travel-agent-rag"

def get_pinecone_client():
    if not PINECONE_API_KEY:
        raise ValueError("PINECONE_API_KEY not found in environment")
    return Pinecone(api_key=PINECONE_API_KEY)

def get_index():
    pc = get_pinecone_client()
    
    # Check if index exists
    existing_indexes = [i.name for i in pc.list_indexes()]
    
    if INDEX_NAME not in existing_indexes:
        logger.info(f"Creating index {INDEX_NAME}...")
        try:
            pc.create_index(
                name=INDEX_NAME,
                dimension=384, # all-MiniLM-L6-v2 dimension
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                ) 
            )
            # Wait for index to be ready
            while not pc.describe_index(INDEX_NAME).status['ready']:
                time.sleep(1)
            logger.info("Index created.")
        except Exception as e:
            logger.error(f"Error creating index: {e}")
            raise e

    return pc.Index(INDEX_NAME)
