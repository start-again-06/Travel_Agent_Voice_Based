from sentence_transformers import SentenceTransformer
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Union
from .client import get_index
import logging
import os

logger = logging.getLogger("rag-retrieve")

# Lazy-loaded model (singleton pattern)
_model = None

def get_model():
    """
    Get or initialize the sentence transformer model.
    Uses lazy loading to avoid blocking server startup.
    Model is cached after first load.
    """
    global _model
    if _model is None:
        logger.info("Loading sentence-transformers model (first time)...")
        cache_folder = os.environ.get('SENTENCE_TRANSFORMERS_HOME', './models')
        _model = SentenceTransformer('all-MiniLM-L6-v2', cache_folder=cache_folder)
        logger.info("Model loaded successfully")
    return _model

class RetrieveContextInput(BaseModel):
    """Input schema for retrieve_context tool."""
    query: str = Field(..., description="The search query for retrieving travel information")
    city: Optional[str] = Field(None, description="Optional city name to filter results")
    top_k: Union[str, int] = Field(3, description="Number of top results to retrieve")
    
    @field_validator('top_k', mode='before')
    @classmethod
    def convert_top_k(cls, v):
        """Convert top_k to int if it's a string."""
        if isinstance(v, str):
            return int(v)
        return v

def retrieve_context(query: str, city: str = None, top_k: int = 3) -> str:
    """Retrieve relevant context for the query."""
    try:
        model = get_model()  # Lazy load model on first use
        xq = model.encode(query).tolist()
        index = get_index()
        
        filter_dict = {}
        if city:
            filter_dict["city"] = city
            
        res = index.query(vector=xq, top_k=top_k, include_metadata=True, filter=filter_dict if filter_dict else None)
        
        contexts = []
        for match in res['matches']:
            meta = match['metadata']
            score = match['score']
            # Only include if relevance is decent (e.g. > 0.3 depending on metric, cosine usually 0-1)
            contexts.append(f"[Source: Wikivoyage - {meta['city']} - {meta['section']}]\n{meta['text']}")
            
        return "\n\n".join(contexts)
        
    except Exception as e:
        logger.error(f"Retrieval error: {e}")
        return ""
