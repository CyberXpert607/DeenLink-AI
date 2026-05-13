import cloudscraper
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
url = "https://myislam.org/prophet-ibrahim/"
resp = scraper.get(url)
print(f"Status: {resp.status_code}")
print(f"Content Length: {len(resp.text)}")
if "Cloudflare" in resp.text:
    print("Blocked by Cloudflare!")
else:
    print(resp.text[:500])
