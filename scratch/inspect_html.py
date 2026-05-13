import cloudscraper
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
url = "https://myislam.org/prophet-ibrahim/"
resp = scraper.get(url)
with open("scratch/page.html", "w", encoding="utf-8") as f:
    f.write(resp.text)
print("Saved to scratch/page.html")
