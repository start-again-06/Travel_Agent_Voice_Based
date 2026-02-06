
import os
import requests
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
from langchain.text_splitter import RecursiveCharacterTextSplitter
from .client import get_index
import logging
import uuid
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag-ingest")

# Load model locally
model = SentenceTransformer('all-MiniLM-L6-v2')

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()

def scrape_wikivoyage(city_name: str):
    url = f"https://en.wikivoyage.org/wiki/{city_name}"
    resp = requests.get(url)
    if resp.status_code != 200:
        logger.error(f"Failed to fetch {url}")
        return {}

    soup = BeautifulSoup(resp.content, "html.parser")
    content = soup.find("div", {"class": "mw-parser-output"})
    
    if not content:
        return {}
    
    sections = {}
    current_section = "Intro"
    sections[current_section] = []
    
    for element in content.children:
        if element.name in ['h2', 'h3']:
            header_text = element.get_text().replace('[edit]', '').strip()
            current_section = header_text
            sections[current_section] = []
        elif element.name == 'p':
            text = element.get_text().strip()
            if text:
                sections[current_section].append(text)
        elif element.name in ['ul', 'ol']:
            items = [li.get_text().strip() for li in element.find_all('li')]
            if items:
                 sections[current_section].extend(items)
                
    # Combine text
    final_sections = {}
    for sec, lines in sections.items():
        if lines:
            final_sections[sec] = "\n".join(lines)
            
    return final_sections

def ingest_city(city_name: str):
    logger.info(f"Ingesting {city_name} from Wikivoyage...")
    sections = scrape_wikivoyage(city_name)
    
    if not sections:
        logger.warning(f"No data found for {city_name}")
        return

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    
    vectors = []
    
    index = get_index()
    
    for section_name, text in sections.items():
        # Skip irrelevant sections
        if section_name.lower() in ["contents", "navigation menu", "footer"]:
            continue
            
        chunks = text_splitter.split_text(text)
        
        for i, chunk in enumerate(chunks):
            # Embed
            emb = model.encode(chunk).tolist()
            
            # Metadata
            metadata = {
                "city": city_name,
                "section": section_name,
                "text": chunk,
                "source": "wikivoyage"
            }
            
            # ID
            id = str(uuid.uuid4())
            
            vectors.append((id, emb, metadata))
            
    # Batch upsert
    batch_size = 100
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i:i+batch_size]
        try:
            index.upsert(vectors=batch)
            logger.info(f"Upserted batch {i//batch_size + 1}")
        except Exception as e:
            logger.error(f"Error upserting batch: {e}")

    logger.info(f"Ingestion complete for {city_name}")

if __name__ == "__main__":
    # Test ingestion
    ingest_city("Jaipur")
