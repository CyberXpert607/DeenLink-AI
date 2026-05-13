import sys
from bs4 import BeautifulSoup

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

with open("scratch/page.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

print("Title:", soup.title.string if soup.title else "No title")
print("H1:", soup.h1.get_text() if soup.h1 else "No H1")

for div in soup.find_all('div'):
    classes = div.get('class', [])
    if any(c in ['entry-content', 'et_builder_inner_content', 'post-content'] for c in classes):
        text = div.get_text(strip=True)
        print(f"Found div with classes {classes}. Text length: {len(text)}")
        print("First 100 chars:", text[:100])
