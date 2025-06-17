from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import List, Dict, Optional, Union
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI()

# ---------- Data Model ----------
class ScrapedListingData(BaseModel):
    url: str
    availability: Optional[bool]  # Changed to boolean
    square_feet: Optional[int]  # Renamed from area to avoid confusion with neighborhood
    bedrooms: Optional[int]  # Added bedrooms
    bathrooms: Optional[float]  # Added bathrooms
    rent: Optional[int]  # Added rent
    subsidy: Dict[str, bool]  # HACLA and BC flags
    amenities: Dict[str, Dict[str, bool]]  # Structured amenities
    utilities: Dict[str, str]  # owner/tenant/unknown for each utility
    photos: List[str]

# ---------- Scraper Core ----------

def fetch_listing_data(url: str) -> ScrapedListingData:
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, 'html.parser')

    return ScrapedListingData(
        url=url,
        availability=get_availability(soup),
        square_feet=get_square_feet(soup),
        bedrooms=get_bedrooms(soup),
        bathrooms=get_bathrooms(soup),
        rent=get_rent(soup),
        subsidy=get_subsidy(soup),
        amenities=get_amenities(soup),
        utilities=get_utilities(soup),
        photos=get_photos(soup)
    )

def get_availability(soup):
    """Extract availability as boolean."""
    tag = soup.find('span', {'id': 'spanAvailable'})
    if tag and tag.text.strip():
        text = tag.text.strip().lower()
        return 'available' in text or 'vacant' in text
    return None

def get_square_feet(soup):
    """Extract square footage/size of the unit."""
    # Look for square footage in various possible locations
    sqft_patterns = [
        r'(\d+)\s*sq\.?\s*ft\.?',
        r'(\d+)\s*square\s*feet',
        r'size:?\s*(\d+)',
        r'(\d+)\s*sqft'
    ]
    
    # Check in text content
    text = soup.get_text()
    for pattern in sqft_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            try:
                return int(matches[0])
            except ValueError:
                continue
    
    # Check in specific elements that might contain square footage
    sqft_elements = soup.find_all(['span', 'div', 'td'], string=re.compile(r'\d+\s*sq', re.IGNORECASE))
    for elem in sqft_elements:
        text = elem.get_text()
        numbers = re.findall(r'\d+', text)
        if numbers:
            try:
                return int(numbers[0])
            except ValueError:
                continue
    
    return None

def get_bedrooms(soup):
    """Extract number of bedrooms."""
    # Look for bedroom information
    bedroom_patterns = [
        r'(\d+)\s*bed',
        r'(\d+)\s*br',
        r'bedroom[s]?:?\s*(\d+)',
        r'studio'
    ]
    
    text = soup.get_text().lower()
    
    # Check for studio
    if 'studio' in text:
        return 0
    
    for pattern in bedroom_patterns[:-1]:  # Exclude studio pattern
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            try:
                return int(matches[0])
            except ValueError:
                continue
    
    return None

def get_bathrooms(soup):
    """Extract number of bathrooms."""
    bathroom_patterns = [
        r'(\d+\.?\d*)\s*bath',
        r'(\d+\.?\d*)\s*ba',
        r'bathroom[s]?:?\s*(\d+\.?\d*)'
    ]
    
    text = soup.get_text()
    for pattern in bathroom_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            try:
                return float(matches[0])
            except ValueError:
                continue
    
    return None

def get_rent(soup):
    """Extract rent amount."""
    rent_patterns = [
        r'\$(\d{1,4}),?(\d{3})',  # $1,500 or $1500
        r'\$(\d{3,4})',           # $500-$9999
        r'rent:?\s*\$(\d{1,4}),?(\d{3})?'
    ]
    
    text = soup.get_text()
    for pattern in rent_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            try:
                if len(matches[0]) == 2 and matches[0][1]:  # Handle comma-separated amounts
                    return int(matches[0][0] + matches[0][1])
                else:
                    return int(matches[0] if isinstance(matches[0], str) else matches[0][0])
            except (ValueError, IndexError):
                continue
    
    return None

def get_subsidy(soup):
    """Extract subsidy acceptance information."""
    subsidy_data = {'hacla': False, 'bc': False}
    
    text = soup.get_text().lower()
    
    # Look for HACLA acceptance
    if any(term in text for term in ['hacla', 'housing authority']):
        subsidy_data['hacla'] = True
    
    # Look for Housing Choice/Section 8 acceptance
    if any(term in text for term in ['housing choice', 'section 8', 'voucher']):
        subsidy_data['bc'] = True
    
    return subsidy_data

def get_amenities(soup):
    """Extract amenities in structured format matching our data model."""
    # Define the same amenity categories as in firestore_service.py
    AMENITY_CATEGORIES = {
        'community': [
            'clubhouse', 'fitness_center', 'gym', 'pool', 'spa', 'hot_tub', 'sauna',
            'business_center', 'conference_room', 'rooftop_deck', 'courtyard',
            'playground', 'dog_park', 'barbecue_area', 'fire_pit', 'game_room',
            'theater_room', 'library', 'concierge', 'doorman', 'security'
        ],
        'indoor': [
            'air_conditioning', 'heating', 'hardwood_floors', 'carpet', 'tile_floors',
            'walk_in_closet', 'ceiling_fans', 'fireplace', 'balcony', 'patio',
            'bay_windows', 'high_ceilings', 'loft', 'den', 'office_space'
        ],
        'kitchen': [
            'dishwasher', 'garbage_disposal', 'microwave', 'refrigerator', 'stove',
            'oven', 'granite_counters', 'stainless_steel_appliances', 'island',
            'breakfast_bar', 'pantry', 'wine_fridge'
        ],
        'other': [
            'parking_garage', 'covered_parking', 'laundry_in_unit', 'laundry_on_site',
            'elevator', 'wheelchair_accessible', 'storage_unit', 'bike_storage'
        ]
    }
    
    # Initialize all amenities as False
    amenities_data = {}
    for category, amenity_list in AMENITY_CATEGORIES.items():
        amenities_data[category] = {}
        for amenity in amenity_list:
            amenities_data[category][amenity] = False
    
    # Get all text from the page for amenity checking
    page_text = soup.get_text().lower()
    
    # Also check structured amenity sections
    categories = soup.select('div.prop--cont--row')
    structured_amenities = []
    
    for cat in categories:
        title_tag = cat.find('h2', class_='dtl--cmn--ttl')
        ul_tag = cat.find('ul', class_='accessibility--list')
        if not title_tag or not ul_tag:
            continue

        for li in ul_tag.find_all('li'):
            item = li.text.strip().lower()
            if item and 'line-through' not in li.get('class', []):
                structured_amenities.append(item)
    
    # Combine page text with structured amenities
    all_amenity_text = page_text + ' ' + ' '.join(structured_amenities)
    
    # Check which amenities are present
    for category, amenity_list in AMENITY_CATEGORIES.items():
        for amenity in amenity_list:
            # Create variations of the amenity name to check
            amenity_variations = [
                amenity,
                amenity.replace('_', ' '),
                amenity.replace('_', '-'),
                amenity.replace('_', '')
            ]
            
            # Add common synonyms
            synonyms = {
                'fitness_center': ['gym', 'fitness room', 'workout room'],
                'air_conditioning': ['ac', 'a/c', 'central air'],
                'garbage_disposal': ['disposal', 'garbage disposal'],
                'laundry_in_unit': ['washer dryer', 'w/d', 'laundry hookup'],
                'parking_garage': ['garage', 'covered parking'],
                'wheelchair_accessible': ['ada', 'accessible', 'handicap accessible']
            }
            
            if amenity in synonyms:
                amenity_variations.extend(synonyms[amenity])
            
            # Check if any variation is found
            for variation in amenity_variations:
                if variation in all_amenity_text:
                    amenities_data[category][amenity] = True
                    break

    return amenities_data

def get_utilities(soup):
    """Extract utilities in structured format (owner/tenant/unknown)."""
    UTILITIES = ['electricity', 'gas', 'water', 'sewer', 'trash', 'internet', 'cable']
    
    utilities_data = {}
    for utility in UTILITIES:
        utilities_data[utility] = 'unknown'  # default
    
    # Look for structured utilities section
    utilities_section = soup.find('div', {'data-section': 'utilities'})
    
    if utilities_section:
        for col in utilities_section.select('div.utilities--col'):
            header = col.find('h4')
            items = col.find_all('li')
            if header and items:
                header_text = header.text.strip().lower()
                
                for li in items:
                    utility_text = li.text.strip().lower()
                    
                    for utility in UTILITIES:
                        if utility in utility_text or utility.replace('_', ' ') in utility_text:
                            if 'owner' in header_text or 'landlord' in header_text or 'included' in header_text:
                                utilities_data[utility] = 'owner'
                            elif 'tenant' in header_text or 'renter' in header_text:
                                utilities_data[utility] = 'tenant'
    
    # Also check general page text for utility information
    page_text = soup.get_text().lower()
    
    for utility in UTILITIES:
        if utilities_data[utility] == 'unknown':  # Only update if not already set
            utility_variations = [utility, utility.replace('_', ' ')]
            
            for variation in utility_variations:
                if variation in page_text:
                    # Look for context clues
                    if any(phrase in page_text for phrase in [f'{variation} included', f'{variation} paid by owner']):
                        utilities_data[utility] = 'owner'
                    elif any(phrase in page_text for phrase in [f'{variation} separate', f'tenant pays {variation}']):
                        utilities_data[utility] = 'tenant'
                    else:
                        # Default assumption if mentioned but unclear
                        utilities_data[utility] = 'tenant'
                    break

    return utilities_data

def get_photos(soup):
    photo_urls = []
    gallery = soup.find('div', {'data-section': 'photos'})
    if not gallery:
        return photo_urls

    imgs = gallery.find_all('img')
    for img in imgs:
        url = img.get('data-src') or img.get('src')
        if url and 'no-photo' not in url:
            if url.startswith('/'):
                url = 'https://www.affordablehousing.com' + url
            photo_urls.append(url)

    return list(set(photo_urls))  # Deduplicate

# ---------- FastAPI Endpoint ----------

@app.get("/scrape", response_model=ScrapedListingData)
def scrape_listing(url: str = Query(..., description="Full listing URL from affordablehousing.com")):
    return fetch_listing_data(url) 