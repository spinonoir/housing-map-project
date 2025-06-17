# Data Structure Migration Guide

This document outlines the new structured data format implemented in the housing map project.

## New Data Structure

### Core Fields (Numeric/Boolean)
- `zip_code`: **Integer** (was string) - 5-digit ZIP code
- `bedrooms`: **Integer** - Number of bedrooms (Studio = 0)
- `bathrooms`: **Float** - Number of bathrooms (allows 1.5, 2.5, etc.)
- `square_feet`: **Integer** - Square footage of the unit (extracted from listings)
- `area`: **String** - Neighborhood/area name (preserved from CSV)
- `rent`: **Integer** - Monthly rent amount
- `parking`: **Integer** - Number of parking spots
- `available`: **Boolean** - Unit availability status
- `favorite`: **Boolean** - User-marked favorite (default: false)

### Structured Objects

#### Subsidy Acceptance
```json
{
  "subsidy": {
    "hacla": true/false,
    "bc": true/false
  }
}
```

#### Utilities (Owner vs Tenant Responsibility)
```json
{
  "utilities": {
    "electricity": "owner" | "tenant" | "unknown",
    "gas": "owner" | "tenant" | "unknown", 
    "water": "owner" | "tenant" | "unknown",
    "sewer": "owner" | "tenant" | "unknown",
    "trash": "owner" | "tenant" | "unknown",
    "internet": "owner" | "tenant" | "unknown",
    "cable": "owner" | "tenant" | "unknown"
  }
}
```

#### Amenities (Categorized Boolean Flags)
```json
{
  "amenities": {
    "community": {
      "clubhouse": true/false,
      "fitness_center": true/false,
      "pool": true/false,
      "spa": true/false,
      // ... all community amenities
    },
    "indoor": {
      "air_conditioning": true/false,
      "hardwood_floors": true/false,
      "fireplace": true/false,
      // ... all indoor amenities
    },
    "kitchen": {
      "dishwasher": true/false,
      "microwave": true/false,
      "granite_counters": true/false,
      // ... all kitchen amenities
    },
    "other": {
      "parking_garage": true/false,
      "laundry_in_unit": true/false,
      "elevator": true/false,
      // ... all other amenities
    }
  }
}
```

### Important Field Distinction
- **`area`**: Neighborhood/location name from CSV (e.g., "Downtown", "Hollywood") - kept as string
- **`square_feet`**: Unit size in sq ft extracted from listings - converted to integer

## Removed Fields
- `flexible_data`: Removed as it was never used

## Migration Process

### For New Data
- All CSV uploads automatically use the new structure
- Data is parsed and converted during the upload process

### For Existing Data
1. **Clear Database**: Use the "Clear Entire Database" button in debug mode (`?debug=true`)
2. **Re-upload Data**: Upload your CSV files again - they will automatically use the new structure
3. **Alternative**: Use "Reprocess Existing Data Types" button to convert existing records

## Benefits

1. **Consistent Data Types**: No more string/number mixing issues
2. **Better Filtering**: Structured data enables reliable filtering and querying
3. **Improved Performance**: Proper types allow database indexing
4. **User Features**: Favorite marking, structured amenity browsing
5. **Maintainable Code**: Predictable data structure reduces complexity

## New Features

- **Favorites**: Mark units as favorites and view them in a dedicated page
- **Structured Amenities**: Browse amenities by category with clear yes/no flags
- **Utility Clarity**: See exactly who pays for each utility
- **Subsidy Tracking**: Clear HACLA and BC acceptance flags

## Code Changes

- `firestore_service.py`: New parsing logic and favorite management
- `Home.py`: Simplified display logic, removed complex filtering
- `pages/2_Unit_Details.py`: Enhanced display for structured data
- `pages/4_Favorites.py`: New page for managing favorite units

## Scraper API Updates

The `listing_scraper_api.py` has been updated to extract additional fields and return data in the new structured format:

### New Extracted Fields
- **Square Footage**: Extracts sq ft from various text patterns (stored as `square_feet`)
- **Bedrooms**: Detects bedroom count (including Studio = 0)
- **Bathrooms**: Extracts bathroom count (supports decimals like 1.5)
- **Rent**: Parses rent amounts (removes $ and commas)
- **Subsidy**: Detects HACLA and Housing Choice acceptance

**Note**: The scraper extracts unit size as `square_feet`, while the CSV `area` field (neighborhood name) is preserved separately.

### Updated Data Format
The scraper now returns data that directly matches our new structure:
- `availability`: Boolean instead of string
- `amenities`: Structured boolean flags by category
- `utilities`: owner/tenant/unknown for each utility type
- `subsidy`: Boolean flags for HACLA and BC

### Backward Compatibility
- The scraper API endpoint remains the same (`/scrape`)
- Data flows seamlessly through the existing processing pipeline
- All scraped data gets processed by the new `_parse_and_clean_data` method
