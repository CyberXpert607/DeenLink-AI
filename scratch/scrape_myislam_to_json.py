import sys
import json
import time
import random
from pathlib import Path
import cloudscraper
from bs4 import BeautifulSoup

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Initialize scraper
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

def get_links(index_url):
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
            # Normalize links
            if href.startswith('/'):
                href = "https://myislam.org" + href
            elif not href.startswith('http'):
                href = "https://myislam.org/" + href
            
            # Basic domain filter
            if "myislam.org" in href:
                links.add(href)
        return list(links)
    except Exception as e:
        print(f"Error fetching links: {e}")
        return []

def extract_content(url):
    try:
        response = scraper.get(url)
        if response.status_code != 200:
            print(f"  Failed {url}: {response.status_code}")
            return None, None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get Title
        title = ""
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)
        
        # Get Content - looking for common Divi/WP content classes
        # Find all potential content divs and pick the one with the most text
        potential_divs = soup.find_all('div', class_=['et_builder_inner_content', 'entry-content'])
        if not potential_divs:
            potential_divs = [soup.find('article') or soup.find('main') or soup.find('body')]
            
        # Filter out None and pick the one with max length
        potential_divs = [d for d in potential_divs if d]
        if not potential_divs:
            return title, None
            
        content_div = max(potential_divs, key=lambda d: len(d.get_text(strip=True)))
            
        # Clean up
        for tag in content_div(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
            
        text = content_div.get_text(separator='\n', strip=True)
        return title, text
    except Exception as e:
        print(f"Error extracting {url}: {e}")
        return None, None

def main():
    results = []
    
    # 1. Prophets
    print("=== Scraping Prophets ===")
    all_links = get_links("https://myislam.org/prophet-stories/")
    prophet_links = [l for l in all_links if "/prophet-" in l and "stories" not in l]
    print(f"Found {len(prophet_links)} prophet links.")
    
    for url in prophet_links:
        print(f"Scraping: {url}")
        title, text = extract_content(url)
        if text and len(text) > 200:
            results.append({"category": "article", "title": title, "url": url, "content": text})
            print(f"  Success: {title} ({len(text)} chars)")
        time.sleep(random.uniform(1, 2))

    # 2. Companions
    print("\n=== Scraping Companions ===")
    companion_urls = [
        'https://myislam.org/ali-ibn-abi-talib/', 
        'https://myislam.org/umar-ibn-al-khattab/', 
        'https://myislam.org/uthman-ibn-affan/', 
        'https://myislam.org/abu-bakr/'
    ]
    for url in companion_urls:
        print(f"Scraping: {url}")
        title, text = extract_content(url)
        if text:
            results.append({"category": "article", "title": title, "url": url, "content": text})
            print(f"  Success: {title}")
        time.sleep(random.uniform(1, 2))

    # 3. 99 Names
    print("\n=== Scraping 99 Names ===")
    all_name_links = get_links("https://myislam.org/99-names-of-allah/")
    names_links = [l for l in all_name_links if "/99-names-of-allah/" in l and l != "https://myislam.org/99-names-of-allah/"]
    print(f"Found {len(names_links)} names links.")
    
    for url in names_links:
        print(f"Scraping: {url}")
        title, text = extract_content(url)
        if text and len(text) > 100:
            results.append({"category": "99_names", "title": title, "url": url, "content": text})
            print(f"  Success: {title}")
        time.sleep(random.uniform(0.5, 1.0))

    # Save to JSON
    output_path = Path("src/backend/api/data/myislam_data.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\nDone! Scraped {len(results)} total pages. Saved to {output_path}")

if __name__ == "__main__":
    main()
