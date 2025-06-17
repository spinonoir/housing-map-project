#!/usr/bin/env python3
"""
Test script to verify URL generation is working correctly
"""

import pandas as pd
from Home import HousingDataProcessor

# Create a sample row
sample_data = {
    'id': 'test_unit_123',
    'property_address': '123 Test St',
    'unit': 'A1',
    'status': 'available',
    'bedrooms': 2,
    'area': 'Downtown'
}

# Create a pandas Series to simulate a row
row = pd.Series(sample_data)

# Test the popup generation
processor = HousingDataProcessor()
popup_content = processor.create_popup_content(row)

print("Generated popup content:")
print(popup_content)
print("\n" + "="*50 + "\n")

# Check for malformed HTML
if '<a href="<a href=' in popup_content:
    print("❌ ERROR: Found malformed nested anchor tags!")
else:
    print("✅ SUCCESS: No malformed anchor tags found!")

# Check for proper URL format
if "./2_Unit_Details?unit_id=" in popup_content:
    print("✅ SUCCESS: Proper URL format found!")
else:
    print("❌ ERROR: Proper URL format not found!")
