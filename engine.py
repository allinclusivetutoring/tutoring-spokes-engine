import json
import os
import time
import requests
from bs4 import BeautifulSoup

# Load existing crawler headers to mimic user's script
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
}

def crawl_for_context(url):
    """
    Crawls the target URL and extracts a few paragraphs of text to use as dynamic content.
    """
    try:
        print(f"Crawling {url} for context...")
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            # Extract paragraphs, filtering out empty ones
            paragraphs = [p.text.strip() for p in soup.find_all('p') if len(p.text.strip()) > 50]
            
            # Take up to 3 paragraphs of actual content
            if paragraphs:
                return " ".join(paragraphs[:3])
            else:
                return f"Stay tuned for the latest updates and requirements regarding the {url} program."
        else:
            return f"Currently reviewing the latest information from {url}."
    except Exception as e:
        print(f"Failed to crawl {url}: {e}")
        return f"Check back soon for the latest news and updates."

def build_sites():
    print("Starting the 50-Spoke Generation Engine...")
    
    # Load Domains
    with open('domains.json', 'r', encoding='utf-8') as f:
        domains = json.load(f)
        
    # Load Template
    with open('template.html', 'r', encoding='utf-8') as f:
        template = f.read()

    # Generate Sites
    output_dir = 'dist'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for item in domains:
        domain = item['domain']
        niche = item['niche']
        crawl_url = item['crawl_url']
        
        print(f"\n--- Generating site for {domain} ---")
        
        # 1. Crawl for fresh data
        crawled_text = crawl_for_context(crawl_url)
        
        # 2. Inject into template
        html_content = template.replace('{{ niche }}', niche)
        html_content = html_content.replace('{{ crawled_text }}', crawled_text)
        
        # 3. Save to output directory
        site_dir = os.path.join(output_dir, domain)
        if not os.path.exists(site_dir):
            os.makedirs(site_dir)
            
        file_path = os.path.join(site_dir, 'index.html')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        print(f"Successfully built {domain}")
        time.sleep(1) # Be polite to servers while crawling

    print(f"\nAll 51 spoke sites have been generated in the '{output_dir}' directory!")

if __name__ == '__main__':
    build_sites()
