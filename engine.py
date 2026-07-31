import json
import os
import time
import requests
import zipfile
from bs4 import BeautifulSoup

# Headers for crawling
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
}

def crawl_for_context(url):
    """
    Crawls the target URL and extracts a few paragraphs of text to use as dynamic content.
    """
    if not url:
        return "Specialized remote tutoring solutions for families pursuing educational freedom and individualized learning paths."
    try:
        print(f"Crawling {url} for context...")
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            paragraphs = [p.text.strip() for p in soup.find_all('p') if len(p.text.strip()) > 50]
            if paragraphs:
                return " ".join(paragraphs[:3])
            else:
                return f"Stay tuned for the latest updates and requirements regarding the {url} program."
        else:
            return f"Currently reviewing the latest information from {url}."
    except Exception as e:
        print(f"Failed to crawl {url}: {e}")
        return f"Check back soon for the latest news and updates."

def inject_content(html_path, headline, crawled_text):
    """
    Injects the dynamic SEO content into the legacy HTML file right before the </body> tag.
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
        
    # Create the new SEO block
    injection_html = f"""
    <section style="background: #f8fafc; padding: 3rem 1.5rem; text-align: center; border-top: 1px solid #e2e8f0; margin-top: 3rem;">
        <div style="max-width: 800px; margin: 0 auto;">
            <h2 style="font-size: 2rem; color: #1e293b; margin-bottom: 1rem;">{headline}</h2>
            <p style="color: #475569; font-size: 1.1rem; line-height: 1.6; margin-bottom: 2rem; font-style: italic;">
                "{crawled_text}"
            </p>
            <a href="https://allinclusivetutoring.com" style="display: inline-block; background-color: #2563eb; color: white; font-weight: bold; padding: 1rem 2.5rem; border-radius: 8px; text-decoration: none; font-size: 1.1rem; box-shadow: 0 4px 6px rgba(37,99,235,0.2); transition: background-color 0.3s;">
                Book Your Consultation at All Inclusive Tutoring
            </a>
        </div>
    </section>
    """
    injection_soup = BeautifulSoup(injection_html, 'html.parser')
    
    # Find the body tag and insert the new section right before it closes
    if soup.body:
        soup.body.append(injection_soup)
    else:
        # If no body tag exists, just append to the document
        soup.append(injection_soup)
        
    # Save the modified HTML back to the file
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(str(soup))

def build_sites():
    print("Starting the 50-Spoke Legacy Integration Engine...")
    
    # Load Configurations
    with open('config/domains.json', 'r', encoding='utf-8') as f:
        domains_data = json.load(f)
        domain_list = domains_data.get('domains', [])
        
    with open('config/programs.json', 'r', encoding='utf-8') as f:
        programs_data = json.load(f)
        program_list = programs_data.get('programs', [])
        
    # Create a lookup dictionary for programs
    programs_map = { p['id']: p for p in program_list }

    # Setup directories
    output_dir = 'dist'
    templates_dir = 'old_templates'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for item in domain_list:
        domain = item.get('domain')
        headline = item.get('headline', 'Latest Updates')
        program_id = item.get('program_id')
        
        # Determine crawl URL based on program mapping
        crawl_url = ""
        if program_id and program_id in programs_map:
            crawl_url = programs_map[program_id].get('official_url', "")
        
        zip_filename = f"{domain}_V5.zip"
        zip_path = os.path.join(templates_dir, zip_filename)
        site_out_dir = os.path.join(output_dir, domain)
        
        print(f"\n--- Generating site for {domain} ---")
        
        if not os.path.exists(zip_path):
            print(f"WARNING: Legacy zip file {zip_filename} not found! Skipping {domain}.")
            continue
            
        # 1. Unzip the legacy site directly into the dist/<domain> folder
        print(f"Extracting legacy design from {zip_filename}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(site_out_dir)
            
        # 2. Crawl for fresh data
        crawled_text = crawl_for_context(crawl_url)
        
        # 3. Inject into the legacy index.html
        index_path = os.path.join(site_out_dir, 'index.html')
        if os.path.exists(index_path):
            print("Injecting SEO content into index.html...")
            inject_content(index_path, headline, crawled_text)
            print(f"Successfully integrated {domain}")
        else:
            print(f"WARNING: No index.html found inside {zip_filename}!")
            
        time.sleep(1) # Be polite to servers while crawling

    print(f"\nAll spoke sites have been integrated into the '{output_dir}' directory!")

if __name__ == '__main__':
    build_sites()
