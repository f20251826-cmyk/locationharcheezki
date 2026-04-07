import sys
import os
import time
import argparse
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import re
import urllib.parse

def find_column_by_keywords(df, keywords):
    """Find a column matching any of the provided keywords."""
    for col in df.columns:
        col_lower = str(col).lower()
        if any(k in col_lower for k in keywords):
            return col
    return None

def setup_driver():
    """Set up the Selenium Chrome WebDriver."""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.implicitly_wait(5)
    return driver

def find_linkedin_url_via_google(driver, name, position, company):
    """Search Google for the person's LinkedIn profile."""
    # Build query: Name Position Company site:linkedin.com/in
    query_parts = [p for p in [name, position, company] if p and str(p).strip() != 'nan']
    query = " ".join(query_parts) + " site:linkedin.com/in"
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded_query}"
    
    try:
        driver.get(url)
        time.sleep(2)  # Wait for results to load
        
        # Check for CAPTCHA
        if "sorry/index" in driver.current_url or "captcha" in driver.page_source.lower():
            print("\nHit Google CAPTCHA. Unable to search Google.")
            return None
            
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Look for any link that contains linkedin.com/in/
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Sometimes google links are wrapped in /url?q=...
            match = re.search(r'(https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[^&?\s]+)', href)
            if match:
                return match.group(1)
        return None
    except Exception as e:
        print(f"\nError searching Google: {e}")
        return None

def find_linkedin_url_via_ddg(driver, name, position, company):
    """Search DuckDuckGo for the person's LinkedIn profile."""
    # Build query: Name Position Company site:linkedin.com/in
    query_parts = [p for p in [name, position, company] if p and str(p).strip() != 'nan']
    query = " ".join(query_parts) + " site:linkedin.com/in"
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://duckduckgo.com/html/?q={encoded_query}"
    
    try:
        driver.get(url)
        time.sleep(2)  # Wait for results to load
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Look for any link that contains linkedin.com/in/
        for a in soup.find_all('a', href=True):
            href = a['href']
            # DDG redirects urls, but the actual requested URL is often passed in 'uddg=' or we can regex the raw URL
            # e.g., //duckduckgo.com/l/?uddg=https://www.linkedin.com/in/tim-cook...
            decoded_href = urllib.parse.unquote(href)
            match = re.search(r'(https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[^&?\s]+)', decoded_href)
            if match:
                return match.group(1)
        return None
    except Exception as e:
        print(f"\nError searching DDG: {e}")
        return None

def extract_location_from_title(title):
    """Attempt to extract location from the page title."""
    if not title:
        return None
    
    title = title.replace(" | LinkedIn", "")
    parts = [p.strip() for p in title.split(" - ")]
    
    if len(parts) >= 3:
        return parts[-1]
    elif len(parts) == 2:
        return parts[-1]
    
    return None

def extract_location(driver, url):
    """Navigate to the LinkedIn URL and extract the profile's location."""
    try:
        driver.get(url)
        time.sleep(3)
        
        title = driver.title
        loc_from_title = extract_location_from_title(title)
        if loc_from_title and loc_from_title not in ["LinkedIn", "Sign in", "Sign Up"]:
             return loc_from_title

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        location_elements = soup.find_all('div', class_=re.compile(r'top-card__subline-item'))
        if location_elements:
            for el in location_elements:
                text = el.get_text(separator=' ', strip=True)
                if text and 'followers' not in text.lower() and 'connections' not in text.lower() and len(text) < 60:
                    return text
                    
        h3_loc = soup.find('h3', class_=re.compile(r'top-card-layout__first-subline'))
        if h3_loc:
            child_divs = h3_loc.find_all('div')
            for div in child_divs:
                text = div.get_text(separator=' ', strip=True)
                if text and 'followers' not in text.lower() and 'connections' not in text.lower() and len(text) < 60:
                    return text

        if title and ('Sign In' in title or 'Sign up' in title or 'authwall' in driver.current_url.lower()):
            return "Authwall blocked viewing"

        return "Location Not Found"
        
    except Exception as e:
        print(f"\nError extracting location for {url}: {e}")
        return "Error"

def main():
    parser = argparse.ArgumentParser(description="LinkedIn Location Scraper")
    parser.add_argument("csv_path", help="Path to the input CSV file")
    parser.add_argument("--engine", choices=["ddg", "google"], default="ddg", 
                        help="Search engine to use for fallback search (default: ddg)")
    args = parser.parse_args()
    
    input_csv = args.csv_path
    engine = args.engine
    
    if not os.path.exists(input_csv):
        print(f"File not found: {input_csv}")
        sys.exit(1)
        
    print(f"Reading CSV: {input_csv}")
    df = pd.read_csv(input_csv)
    
    linkedin_col = find_column_by_keywords(df, ['linkedin', 'url'])
    if not linkedin_col:
        print("Warning: Could not find a column header containing 'linkedin'. Will create one.")
        linkedin_col = 'LinkedIn URL'
        df[linkedin_col] = ''
        
    name_col = find_column_by_keywords(df, ['name'])
    pos_col = find_column_by_keywords(df, ['position', 'title', 'role'])
    comp_col = find_column_by_keywords(df, ['company', 'organization'])
    
    print(f"Detected Columns -> LinkedIn: '{linkedin_col}', Name: '{name_col}', Position: '{pos_col}', Company: '{comp_col}'")
    
    # Initialize the new column
    if 'Location' not in df.columns:
         df['Location'] = ""
    
    print("Setting up browser...")
    driver = setup_driver()
    
    try:
        total_rows = len(df)
        for index, row in df.iterrows():
            url = row[linkedin_col] if linkedin_col in df.columns else None
            
            # If URL is missing, attempt to use DDG search
            if pd.isna(url) or not str(url).strip():
                if name_col:
                    name = str(row.get(name_col, ""))
                    pos = str(row.get(pos_col, "")) if pos_col else ""
                    comp = str(row.get(comp_col, "")) if comp_col else ""
                    
                    if name.strip() and name.strip() != 'nan':
                        print(f"[{index+1}/{total_rows}] Searching ({engine.upper()}) for missing URL -> {name} ({pos} at {comp}) ...", end=" ", flush=True)
                        if engine == "google":
                            new_url = find_linkedin_url_via_google(driver, name, pos, comp)
                        else:
                            new_url = find_linkedin_url_via_ddg(driver, name, pos, comp)
                            
                        if new_url:
                            print(f"Found: {new_url}")
                            df.at[index, linkedin_col] = new_url
                            url = new_url
                        else:
                            print("Failed to find URL.")
                            df.at[index, 'Location'] = "URL Missing & Search Failed"
                            continue
            
            # If still missing, skip
            if pd.isna(url) or not str(url).strip():
                print(f"[{index+1}/{total_rows}] Skipping row (No Name/URL available).")
                df.at[index, 'Location'] = "URL Missing"
                continue
                
            print(f"[{index+1}/{total_rows}] Scraping location at {url} ...", end=" ", flush=True)
            location = extract_location(driver, str(url).strip())
            df.at[index, 'Location'] = location
            print(f"Location: {location}")
            
    finally:
        driver.quit()
        
    # Construct output filename
    base_name, ext = os.path.splitext(input_csv)
    output_csv = f"{base_name}_with_locations{ext}"
    
    df.to_csv(output_csv, index=False)
    print(f"Scraping completed. Results saved to: {output_csv}")

if __name__ == "__main__":
    main()
