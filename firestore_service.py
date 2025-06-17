import streamlit as st
import google.auth
from google.cloud import firestore
import pandas as pd
from datetime import datetime
import re
from typing import Dict, Any, Optional

class FirestoreService:
    """
    A service class to manage all interactions with Google Firestore.
    It uses a singleton pattern to ensure a single client instance.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(FirestoreService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'db'):
            self.db = self._initialize_client()

    def _initialize_client(self) -> firestore.Client:
        """Initializes and returns a Firestore client."""
        try:
            gcp_service_account = st.secrets["gcp_service_account"]
            credentials = google.oauth2.service_account.Credentials.from_service_account_info(gcp_service_account)
            return firestore.Client(credentials=credentials)
        except (FileNotFoundError, KeyError):
            # Fallback for local dev without Streamlit secrets
            return firestore.Client()

    @staticmethod
    def _sanitize_unit_id(address: str, unit_number: str, zip_code: str) -> str:
        """Creates a URL-safe and Firestore-safe document ID."""
        raw_id = f"{address}_{unit_number}_{zip_code}".lower().replace(' ', '-')
        sanitized = re.sub(r'[^\w\-_]', '', raw_id)
        sanitized = re.sub(r'--+', '-', sanitized).strip('-')
        # Ensure we have a valid ID, fallback to timestamp if empty
        if not sanitized or len(sanitized) < 3:
            sanitized = f"unit_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return sanitized[:1500]

    @staticmethod
    def _parse_and_clean_data(row_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse and clean data from CSV, converting fields to structured format with proper types.
        """
        cleaned_data = {}
        
        # Define standard amenity categories and options
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
        
        # Define standard utilities
        UTILITIES = ['electricity', 'gas', 'water', 'sewer', 'trash', 'internet', 'cable']
        
        for key, value in row_data.items():
            if pd.isna(value) or value == '' or value is None:
                continue
                
            # Convert key to lowercase with underscores
            clean_key = key.lower().replace(' ', '_')
            
            try:
                if clean_key in ['bedrooms', 'bathrooms', 'parking', 'parking_spots']:
                    # Parse as integers
                    if isinstance(value, str):
                        if 'studio' in value.lower():
                            cleaned_data[clean_key] = 0 if clean_key == 'bedrooms' else value
                        elif clean_key in ['parking', 'parking_spots'] and any(word in value.lower() for word in ['no parking', 'none', 'n/a', 'not available']):
                            # Handle "No Parking" cases
                            cleaned_data[clean_key] = 0
                        else:
                            numbers = re.findall(r'\d+\.?\d*', str(value))
                            if numbers:
                                if clean_key in ['bedrooms', 'parking', 'parking_spots']:
                                    cleaned_data[clean_key] = int(float(numbers[0]))
                                else:
                                    cleaned_data[clean_key] = float(numbers[0])
                            else:
                                # If no numbers found, set parking to 0, others keep as string
                                if clean_key in ['parking', 'parking_spots']:
                                    cleaned_data[clean_key] = 0
                                else:
                                    cleaned_data[clean_key] = str(value)
                    else:
                        cleaned_data[clean_key] = int(value) if clean_key in ['bedrooms', 'parking', 'parking_spots'] else float(value)
                        
                elif clean_key in ['square_feet', 'sqft', 'sq_ft', 'size']:
                    # Parse square footage as integer
                    if isinstance(value, str):
                        cleaned_value = re.sub(r'(sq\.?\s?ft\.?|square\s?feet|\s)', '', str(value), flags=re.IGNORECASE)
                        numbers = re.findall(r'\d+', cleaned_value)
                        if numbers:
                            cleaned_data['square_feet'] = int(numbers[0])
                    else:
                        cleaned_data['square_feet'] = int(value)
                        
                elif clean_key in ['area', 'neighborhood', 'location']:
                    # Keep area as string (neighborhood name)
                    cleaned_data['area'] = str(value).strip()
                        
                elif clean_key in ['rent', 'price', 'monthly_rent', 'cost']:
                    # Parse rent as integer
                    if isinstance(value, str):
                        cleaned_value = re.sub(r'[\$,\s]', '', str(value))
                        numbers = re.findall(r'\d+', cleaned_value)
                        if numbers:
                            cleaned_data[clean_key] = int(numbers[0])
                    else:
                        cleaned_data[clean_key] = int(value)
                        
                elif clean_key in ['zip_code', 'zipcode', 'postal_code']:
                    # ZIP code as integer
                    zip_str = str(value).strip()
                    if '-' in zip_str:
                        zip_str = zip_str.split('-')[0]
                    if zip_str.isdigit() and len(zip_str) == 5:
                        cleaned_data['zip_code'] = int(zip_str)
                        
                elif clean_key in ['subsidy_accepted', 'subsidies', 'subsidy']:
                    # Parse subsidy flags
                    subsidy_data = {'hacla': False, 'bc': False}
                    value_str = str(value).lower()
                    if 'hacla' in value_str:
                        subsidy_data['hacla'] = True
                    if 'bc' in value_str or 'housing choice' in value_str:
                        subsidy_data['bc'] = True
                    cleaned_data['subsidy'] = subsidy_data
                    
                elif clean_key in ['available', 'availability']:
                    # Parse availability as boolean
                    if isinstance(value, str):
                        cleaned_data['available'] = value.lower() in ['true', 'yes', '1', 'y', 'available', 'vacant']
                    else:
                        cleaned_data['available'] = bool(value)
                        
                elif clean_key in ['amenities', 'amenity']:
                    # Parse amenities into structured boolean flags
                    amenities_data = {}
                    for category, amenity_list in AMENITY_CATEGORIES.items():
                        amenities_data[category] = {}
                        for amenity in amenity_list:
                            amenities_data[category][amenity] = False
                    
                    # Check which amenities are present
                    value_str = str(value).lower()
                    for category, amenity_list in AMENITY_CATEGORIES.items():
                        for amenity in amenity_list:
                            # Check various forms of the amenity name
                            amenity_variations = [
                                amenity,
                                amenity.replace('_', ' '),
                                amenity.replace('_', '-'),
                            ]
                            for variation in amenity_variations:
                                if variation in value_str:
                                    amenities_data[category][amenity] = True
                                    break
                    
                    cleaned_data['amenities'] = amenities_data
                    
                elif clean_key in ['utilities', 'utility']:
                    # Parse utilities as owner/tenant structure
                    utilities_data = {}
                    for utility in UTILITIES:
                        utilities_data[utility] = 'unknown'  # default
                    
                    value_str = str(value).lower()
                    for utility in UTILITIES:
                        if utility in value_str:
                            # Try to determine if owner or tenant pays
                            if any(word in value_str for word in ['included', 'owner', 'landlord', 'paid']):
                                utilities_data[utility] = 'owner'
                            elif any(word in value_str for word in ['tenant', 'renter', 'separate']):
                                utilities_data[utility] = 'tenant'
                            else:
                                utilities_data[utility] = 'tenant'  # default assumption
                    
                    cleaned_data['utilities'] = utilities_data
                    
                elif clean_key in ['latitude', 'lat', 'longitude', 'lng', 'lon']:
                    # Parse coordinates as floats
                    cleaned_data[clean_key] = float(value)
                    
                elif clean_key not in ['flexible_data']:  # Skip flexible_data field
                    # Default: keep as string but clean it
                    cleaned_data[clean_key] = str(value).strip()
                    
            except (ValueError, TypeError, AttributeError):
                # If parsing fails, keep as string (except for skipped fields)
                if clean_key not in ['flexible_data']:
                    cleaned_data[clean_key] = str(value)
        
        # Always add favorite field as false for new records
        cleaned_data['favorite'] = False
                
        return cleaned_data

    def upload_from_dataframe(self, df: pd.DataFrame) -> tuple[int, int]:
        """
        Loads data from a pandas DataFrame into Firestore, updating existing
        units and inserting new ones. It normalizes column names.
        """
        units_collection = self.db.collection('units')
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        insert_count = 0
        update_count = 0

        # Normalize column names for flexibility
        df.columns = [c.lower().replace(' ', '_') for c in df.columns]

        for _, row in df.iterrows():
            try:
                address = row.get('property_address', '').strip()
                unit_num = str(row.get('unit', '')).strip()
                zip_code = str(row.get('zip_code', '')).strip()

                if not address or not zip_code:
                    continue
                
                doc_id = self._sanitize_unit_id(address, unit_num, zip_code)
                unit_ref = units_collection.document(doc_id)
                
                # Use the new parsing method to clean and convert data types
                unit_data = self._parse_and_clean_data(row.to_dict())
                
                doc = unit_ref.get()
                if doc.exists:
                    update_data = unit_data.copy()
                    update_data['last_seen_date'] = datetime.now().isoformat()
                    update_data['status'] = 'available'
                    # Preserve existing favorite status if it exists
                    existing_data = doc.to_dict()
                    if 'favorite' in existing_data:
                        update_data['favorite'] = existing_data['favorite']
                    unit_ref.update(update_data)
                    update_count += 1
                else:
                    new_data = unit_data.copy()
                    new_data.update({
                        'id': doc_id,
                        'first_seen_date': datetime.now().isoformat(),
                        'last_seen_date': datetime.now().isoformat(),
                        'status': 'available',
                        'batch_id': batch_id
                    })
                    # Set default empty values for tracking fields
                    for field in ['level_of_interest', 'viewing_scheduled', 
                                  'availability_verified_date', 'amenities', 
                                  'questions_for_agent', 'notes']:
                        if field not in new_data:
                            new_data[field] = ''
                    unit_ref.set(new_data)
                    insert_count += 1
            except Exception as e:
                # Log the error but continue processing other rows
                print(f"Error processing row: {e}")
                continue
                
        return insert_count, update_count

    def get_all_units_as_df(self) -> pd.DataFrame:
        """Retrieves all units and returns them as a pandas DataFrame."""
        try:
            docs = self.db.collection('units').stream()
            units_list = [doc.to_dict() for doc in docs]
            
            if not units_list:
                return pd.DataFrame()
            return pd.DataFrame(units_list)
        except Exception as e:
            print(f"Error fetching units: {e}")
            return pd.DataFrame()

    def get_unit_by_id(self, unit_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single unit's data by its document ID."""
        try:
            doc_ref = self.db.collection('units').document(unit_id)
            doc = doc_ref.get()
            return doc.to_dict() if doc.exists else None
        except Exception as e:
            print(f"Error fetching unit {unit_id}: {e}")
            return None

    def update_unit(self, unit_id: str, data: Dict[str, Any]):
        """Updates a specific unit with the provided data dictionary."""
        if not data:
            return
        try:
            self.db.collection('units').document(unit_id).update(data)
        except Exception as e:
            print(f"Error updating unit {unit_id}: {e}")
            raise  # Re-raise so the UI can handle it

    def log_geocoding_failure(self, unit_data: Dict, reason: str):
        """Logs a geocoding failure to a separate collection."""
        failure_data = {
            'unit_data': unit_data,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        }
        self.db.collection('geocoding_failures').add(failure_data)

    def get_geocoding_failures_df(self) -> pd.DataFrame:
        """Retrieves all geocoding failures."""
        try:
            docs = self.db.collection('geocoding_failures').stream()
            failures = [doc.to_dict() for doc in docs]
            return pd.DataFrame(failures)
        except Exception as e:
            print(f"Error fetching geocoding failures: {e}")
            return pd.DataFrame()
    
    def get_geocoding_failure_count(self) -> int:
        """Counts the number of geocoding failures."""
        try:
            # Note: This iterates through all documents. For very large collections,
            # a distributed counter would be more efficient.
            return len(list(self.db.collection('geocoding_failures').stream()))
        except Exception as e:
            print(f"Error counting geocoding failures: {e}")
            return 0

    def delete_geocoding_failure(self, failure_id: str):
        """Deletes a specific geocoding failure document."""
        self.db.collection('geocoding_failures').document(failure_id).delete()

    def reprocess_existing_data(self) -> tuple[int, int]:
        """
        Reprocess existing units in the database to apply new data parsing rules.
        Returns tuple of (success_count, error_count).
        """
        try:
            docs = self.db.collection('units').stream()
            success_count = 0
            error_count = 0
            
            for doc in docs:
                try:
                    current_data = doc.to_dict()
                    # Reparse the data with new rules
                    parsed_data = self._parse_and_clean_data(current_data)
                    
                    # Only update if there are changes
                    if parsed_data != current_data:
                        # Preserve important metadata
                        parsed_data.update({
                            'id': current_data.get('id'),
                            'first_seen_date': current_data.get('first_seen_date'),
                            'last_seen_date': current_data.get('last_seen_date'),
                            'status': current_data.get('status', 'available'),
                            'batch_id': current_data.get('batch_id')
                        })
                        
                        self.db.collection('units').document(doc.id).set(parsed_data)
                        success_count += 1
                        
                except Exception as e:
                    print(f"Error reprocessing document {doc.id}: {e}")
                    error_count += 1
                    
            return success_count, error_count
            
        except Exception as e:
            print(f"Error during reprocessing: {e}")
            return 0, 1

    def update_favorite_status(self, unit_id: str, is_favorite: bool):
        """Updates the favorite status of a specific unit."""
        try:
            self.db.collection('units').document(unit_id).update({'favorite': is_favorite})
        except Exception as e:
            print(f"Error updating favorite status for unit {unit_id}: {e}")
            raise

    def get_favorite_units_df(self) -> pd.DataFrame:
        """Retrieves only favorite units and returns them as a pandas DataFrame."""
        try:
            docs = self.db.collection('units').where('favorite', '==', True).stream()
            units_list = [doc.to_dict() for doc in docs]
            
            if not units_list:
                return pd.DataFrame()
            return pd.DataFrame(units_list)
        except Exception as e:
            print(f"Error fetching favorite units: {e}")
            return pd.DataFrame()

    def clear_database(self):
        """Clears all units from the database."""
        try:
            # Get all documents in the units collection
            docs = self.db.collection('units').stream()
            
            # Delete in batches for efficiency
            batch = self.db.batch()
            count = 0
            
            for doc in docs:
                batch.delete(doc.reference)
                count += 1
                
                # Commit batch every 500 operations (Firestore limit)
                if count % 500 == 0:
                    batch.commit()
                    batch = self.db.batch()
            
            # Commit remaining operations
            if count % 500 != 0:
                batch.commit()
                
            # Also clear geocoding failures
            failure_docs = self.db.collection('geocoding_failures').stream()
            batch = self.db.batch()
            
            for doc in failure_docs:
                batch.delete(doc.reference)
            
            batch.commit()
            
            return True
        except Exception as e:
            print(f"Error clearing database: {e}")
            return False

    def fix_parking_data(self) -> tuple[int, int]:
        """
        Fix parking data that might be stored as strings like 'No Parking'.
        Returns tuple of (success_count, error_count).
        """
        try:
            docs = self.db.collection('units').stream()
            success_count = 0
            error_count = 0
            
            for doc in docs:
                try:
                    current_data = doc.to_dict()
                    needs_update = False
                    
                    # Check parking field
                    if 'parking' in current_data:
                        parking_value = current_data['parking']
                        if isinstance(parking_value, str):
                            if any(word in parking_value.lower() for word in ['no parking', 'none', 'n/a', 'not available']):
                                current_data['parking'] = 0
                                needs_update = True
                            else:
                                # Try to extract number
                                numbers = re.findall(r'\d+', parking_value)
                                if numbers:
                                    current_data['parking'] = int(numbers[0])
                                    needs_update = True
                                else:
                                    current_data['parking'] = 0
                                    needs_update = True
                    
                    if needs_update:
                        self.db.collection('units').document(doc.id).update({'parking': current_data['parking']})
                        success_count += 1
                        
                except Exception as e:
                    print(f"Error fixing parking data for document {doc.id}: {e}")
                    error_count += 1
                    
            return success_count, error_count
            
        except Exception as e:
            print(f"Error during parking data fix: {e}")
            return 0, 1

# Singleton instance for use across the Streamlit app
firestore_service = FirestoreService()