import sys
import uuid
import time
from pathlib import Path
import cloudscraper
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
API_DIR = BASE_DIR.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from v2.vectoreStore import client, COLLECTION_NAME, ensure_collection
from v2.embeddings import embed_text

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

def get_links(index_url, filter_func):
    print(f"Fetching links from: {index_url}")
    try:
        response = scraper.get(index_url)
        if response.status_code != 200:
            print(f"Failed to fetch {index_url}. Status: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        links = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            if filter_func(href):
                links.add(href)
        return list(links)
    except Exception as e:
        print(f"Error fetching links: {e}")
        return []

def extract_content(url):
    try:
        response = scraper.get(url)
        if response.status_code != 200:
            return None, None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get Title
        title = ""
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)
        else:
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text(strip=True).split('-')[0].strip()
                
        # Get Content
        content_div = soup.find('div', class_='et_builder_inner_content')
        if not content_div:
            content_div = soup.find('div', class_='entry-content')
        if not content_div:
            content_div = soup.find('body')
            
        # Clean up scripts and styles
        for script in content_div(["script", "style", "nav", "footer", "header"]):
            script.decompose()
            
        text = content_div.get_text(separator='\n', strip=True)
        return title, text
    except Exception as e:
        print(f"Error extracting {url}: {e}")
        return None, None

def ingest_urls(urls, category="article"):
    ensure_collection()
    total_processed = 0
    points = []
    
    for url in urls:
        print(f"Scraping: {url}")
        title, text = extract_content(url)
        
        if not text or len(text) < 100:
            print("  Skipping, insufficient content.")
            continue
            
        # Chunk the text if it's too long (over 4000 characters) to preserve embedding quality
        chunks = [text[i:i+3000] for i in range(0, len(text), 3000)]
        
        for idx, chunk in enumerate(chunks):
            text_for_embedding = f"Title: {title}\n\nContent: {chunk}"
            
            payload = {
                "source_type": category,
                "title": title,
                "url": url,
                "part": idx + 1,
                "total_parts": len(chunks),
                "content_snippet": chunk[:500]
            }
            
            try:
                vector = embed_text(text_for_embedding)
                points.append({
                    "id": str(uuid.uuid4()),
                    "vector": vector,
                    "payload": payload
                })
            except Exception as e:
                print(f"  Error embedding: {e}")
                
        if len(points) >= 10:
            client.upsert(collection_name=COLLECTION_NAME, points=points)
            total_processed += len(points)
            points = []
            
        import random
        time.sleep(random.uniform(1.0, 3.0)) # random delay to be less bot-like
        
    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        total_processed += len(points)
        
    print(f"[{category}] Completed. Total upserted parts: {total_processed}")

def main():
    print("=== Scraping Prophets ===")
    prophet_links = get_links(
        "https://myislam.org/prophet-stories/", 
        lambda x: x.startswith("https://myislam.org/prophet-") and x != "https://myislam.org/prophet-stories/"
    )
    print(f"Found {len(prophet_links)} prophet links.")
    ingest_urls(prophet_links, "article")

    print("\n=== Scraping Companions ===")
    companion_links = get_links(
        "https://myislam.org/companions-of-the-prophet/",
        lambda x: x in [
            'https://myislam.org/ali-ibn-abi-talib/', 
            'https://myislam.org/umar-ibn-al-khattab/', 
            'https://myislam.org/uthman-ibn-affan/', 
            'https://myislam.org/abu-bakr/'
        ]
    )
    print(f"Found {len(companion_links)} companion links.")
    ingest_urls(companion_links, "article")

    print("\n=== Scraping 99 Names of Allah ===")
    names_links = get_links(
        "https://myislam.org/99-names-of-allah/",
        lambda x: x.startswith("https://myislam.org/99-names-of-allah/") and x != "https://myislam.org/99-names-of-allah/"
    )
    print(f"Found {len(names_links)} names links.")
    ingest_urls(names_links, "99_names")

if __name__ == "__main__":
    main()
