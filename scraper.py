import sys
import os
import time
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

def find_linkedin_column(df):
    """Find the column name that indicates it contains LinkedIn URLs."""
    for col in df.columns:
        if 'linkedin' in str(col).lower():
            return col
    return None

def setup_driver():
    """Set up the Selenium Chrome WebDriver."""
    chrome_options = Options()
    # Using the new headless mode to decrease detection
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # Add a standard user agent to look less like a bot
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.implicitly_wait(5)
    return driver

def extract_location_from_title(title):
    """Attempt to extract location from the page title."""
    # Profile titles usually format like "Name - Headline - Location | LinkedIn"
    # Or "Name - Location | Professional Profile | LinkedIn"
    if not title:
        return None
    
    title = title.replace(" | LinkedIn", "")
    parts = [p.strip() for p in title.split(" - ")]
    
    # Typical: Name - Headline - Location
    if len(parts) >= 3:
        return parts[-1]
    elif len(parts) == 2:
        return parts[-1]
    
    return None


def extract_location(driver, url):
    """Navigate to the LinkedIn URL and extract the profile's location."""
    try:
        driver.get(url)
        # Random sleep to mimic human behavior and wait for page to load
        time.sleep(3)
        
        # Method 1: Try <title> parsing first as it's the cleanest for public endpoints
        title = driver.title
        loc_from_title = extract_location_from_title(title)
        if loc_from_title and loc_from_title not in ["LinkedIn", "Sign in", "Sign Up"]:
             return loc_from_title

        # Method 2: Fallback to checking elements specific to the public profile layout
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')

        # Try to find location in common public profile elements
        location_elements = soup.find_all('div', class_=re.compile(r'top-card__subline-item'))
        if location_elements:
            for el in location_elements:
                text = el.get_text(separator=' ', strip=True)
                if text and 'followers' not in text.lower() and 'connections' not in text.lower() and len(text) < 60:
                    return text
                    
        # Try finding by h3 with location class
        h3_loc = soup.find('h3', class_=re.compile(r'top-card-layout__first-subline'))
        if h3_loc:
            # Often the location is within a child div
            child_divs = h3_loc.find_all('div')
            for div in child_divs:
                text = div.get_text(separator=' ', strip=True)
                if text and 'followers' not in text.lower() and 'connections' not in text.lower() and len(text) < 60:
                    return text

        if title and ('Sign In' in title or 'Sign up' in title or 'authwall' in driver.current_url.lower()):
            return "Authwall blocked viewing"

        return "Location Not Found"
        
        
    except Exception as e:
        print(f"Error extracting location for {url}: {e}")
        return "Error"

def main():
    if len(sys.argv) < 2:
        print("Usage: python scraper.py <path_to_csv>")
        sys.exit(1)
        
    input_csv = sys.argv[1]
    if not os.path.exists(input_csv):
        print(f"File not found: {input_csv}")
        sys.exit(1)
        
    print(f"Reading CSV: {input_csv}")
    df = pd.read_csv(input_csv)
    
    linkedin_col = find_linkedin_column(df)
    if not linkedin_col:
        print("Error: Could not find a column header containing 'linkedin'.")
        print(f"Available columns: {list(df.columns)}")
        sys.exit(1)
        
    print(f"Found LinkedIn sequence column: '{linkedin_col}'")
    
    # Initialize the new column
    df['Location'] = ""
    
    print("Setting up browser...")
    driver = setup_driver()
    
    try:
        total_rows = len(df)
        for index, row in df.iterrows():
            url = row[linkedin_col]
            if pd.isna(url) or not str(url).strip():
                df.at[index, 'Location'] = "URL Missing"
                continue
                
            print(f"[{index+1}/{total_rows}] Scraping {url} ...", end=" ", flush=True)
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
