#!/usr/bin/env python3
"""
Interactive Housing Listings Map - Main Page

This is the main page of the application, displaying the interactive map
and a filterable table of housing units from the database.
"""

import pandas as pd
import folium
from folium import plugins
import streamlit as st
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
import time
from typing import Optional, Dict, List
from firestore_service import firestore_service
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
from streamlit_folium import st_folium
import json

# --- Data Processing Class ---
class HousingDataProcessor:
    def __init__(self, batch_size=4, max_workers=4):
        self.geocoder = Nominatim(user_agent="housing_map_generator")
        self.session = requests.Session()
        self.batch_size = batch_size
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def _geocode_address(self, address: str, zip_code: str, retries: int = 3) -> Optional[Dict]:
        """Geocode a single address with retry logic."""
        full_address = f"{address}, {zip_code}, Los Angeles, CA"
        for attempt in range(retries):
            try:
                location = self.geocoder.geocode(full_address, timeout=10)
                if location:
                    return {
                        'latitude': location.latitude,
                        'longitude': location.longitude,
                        'display_name': location.address
                    }
                time.sleep(1)
            except (GeocoderTimedOut, GeocoderUnavailable):
                if attempt < retries - 1:
                    time.sleep(2)
        return None

    def _scrape_listing_data(self, listing_url: str) -> Optional[Dict]:
        """Scrape data from a single listing URL."""
        if not listing_url or not listing_url.startswith('http'):
            return None
        try:
            api_url = f"http://127.0.0.1:8000/scrape?url={listing_url}"
            res = self.session.get(api_url, timeout=30)
            res.raise_for_status()
            return res.json()
        except requests.RequestException as e:
            st.error(f"Scraping failed for {listing_url}: {e}")
            if hasattr(e, 'response') and e.response and e.response.status_code == 404:
                return {'status': 'off_market'}
        return None

    def _process_unit(self, unit_row):
        """Geocode and scrape a single unit."""
        # Handle different types of row objects (Series, dict, etc.)
        if hasattr(unit_row, 'get'):  # Series or dict-like
            unit_id = unit_row.get('id') or getattr(unit_row, 'name', None)
            address = unit_row.get('property_address', '')
            zip_code = str(unit_row.get('zip_code', ''))
            listing_url = unit_row.get('listing_link')
            latitude = unit_row.get('latitude')
        else:  # Handle named tuple or other object types
            unit_id = getattr(unit_row, 'id', None) or getattr(unit_row, 'Index', None)
            address = getattr(unit_row, 'property_address', '')
            zip_code = str(getattr(unit_row, 'zip_code', ''))
            listing_url = getattr(unit_row, 'listing_link', None)
            latitude = getattr(unit_row, 'latitude', None)

        # 1. Geocode if needed
        if pd.isnull(latitude):
            coords = self._geocode_address(address, zip_code)
            if coords:
                firestore_service.update_unit(unit_id, coords)
            else:
                # Convert row to dict for logging
                if hasattr(unit_row, 'to_dict'):
                    row_dict = unit_row.to_dict()
                elif hasattr(unit_row, '_asdict'):
                    row_dict = unit_row._asdict()
                else:
                    row_dict = {'id': unit_id, 'property_address': address, 'zip_code': zip_code}
                firestore_service.log_geocoding_failure(row_dict, "Geocoding failed")
                return unit_id, "Geocoding Failed"

        # 2. Scrape (if listing link exists)
        if listing_url:
            scraped_data = self._scrape_listing_data(listing_url)
            if scraped_data:
                if scraped_data.get('status') == 'off_market':
                    firestore_service.update_unit(unit_id, {'status': 'off_market'})
                else:
                    firestore_service.update_unit(unit_id, scraped_data)
                return unit_id, "Processed"
            return unit_id, "Scraping Failed"
        
        return unit_id, "Processed (No Scrape)"

    def process_all_units(self, units_df: pd.DataFrame, status_text, progress_bar) -> Dict[str, int]:
        """Process all units in batches using multithreading."""
        # Check if latitude column exists and filter units that need geocoding
        if 'latitude' in units_df.columns:
            units_to_process = units_df[
                pd.to_numeric(units_df['latitude'], errors='coerce').isnull()
            ].copy()
        else:
            # If no latitude column, all units need processing
            units_to_process = units_df.copy()

        total_units = len(units_to_process)
        if total_units == 0:
            status_text.info("✅ All units appear to be geocoded.")
            return {"processed": 0, "geocoding_failed": 0, "scraping_failed": 0, "processed_no_scrape": 0}
        
        num_batches = math.ceil(total_units / self.batch_size)
        results = {"processed": 0, "geocoding_failed": 0, "scraping_failed": 0, "processed_no_scrape": 0}
        
        for i in range(num_batches):
            batch_df = units_to_process.iloc[i*self.batch_size:(i+1)*self.batch_size]
            status_text.info(f"Processing Batch {i+1}/{num_batches}...")
            
            # Submit each row for processing
            futures = []
            for idx, row in batch_df.iterrows():
                future = self.executor.submit(self._process_unit, row)
                futures.append(future)
            
            for future in as_completed(futures):
                _, result_status = future.result()
                if result_status == "Processed":
                    results["processed"] += 1
                elif result_status == "Geocoding Failed":
                    results["geocoding_failed"] += 1
                elif result_status == "Scraping Failed":
                    results["scraping_failed"] += 1
                elif result_status == "Processed (No Scrape)":
                    results["processed_no_scrape"] += 1

            progress_bar.progress((i + 1) / num_batches)
        return results

    def create_popup_content(self, row: pd.Series) -> str:
        """Create HTML content for a property's popup."""
        content = f"""
        <div style="width: 300px; font-family: Arial, sans-serif; font-size: 14px;">
            <h4 style="margin: 0 0 10px 0; color: #2c3e50; font-size: 16px;">{row.get('property_address', 'N/A')}</h4>
            <p style="margin: 4px 0;"><strong>Unit:</strong> {row.get('unit', 'N/A')}</p>
            <p style="margin: 4px 0;"><strong>Status:</strong> {str(row.get('status', 'N/A')).replace('_', ' ').title()}</p>
            <p style="margin: 4px 0;"><strong>Bedrooms:</strong> {row.get('bedrooms', 'N/A')}</p>
            <p style="margin: 4px 0;"><strong>Neighborhood:</strong> {row.get('area', 'N/A')}</p>
            <p style="margin: 4px 0;"><strong>Size:</strong> {row.get('square_feet', 'N/A')} sq ft</p>
        </div>
        """
        return content

    def create_map(self, map_data: pd.DataFrame) -> folium.Map:
        """Creates a Folium map with markers for geocoded housing units."""
        center_lat, center_lon = 34.0522, -118.2437 # Default to LA
        m = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles='CartoDB positron')
        
        if map_data.empty:
            plugins.Fullscreen(position='topleft').add_to(m)
            return m
        
        map_data['latitude'] = pd.to_numeric(map_data.get('latitude'), errors='coerce')
        map_data['longitude'] = pd.to_numeric(map_data.get('longitude'), errors='coerce')
        
        geocoded_units = map_data.dropna(subset=['latitude', 'longitude'])
        
        if not geocoded_units.empty:
            center_lat = geocoded_units['latitude'].mean()
            center_lon = geocoded_units['longitude'].mean()
            m.location = [center_lat, center_lon]

        status_styles = {
            'favorite': {'color': 'red', 'icon': 'heart'},
            'available': {'color': 'blue', 'icon': 'home'},
            'not_interested': {'color': 'gray', 'icon': 'remove'},
            'off_market': {'color': 'black', 'icon': 'ban'},
            'default': {'color': 'purple', 'icon': 'question'}
        }
        
        marker_cluster = plugins.MarkerCluster().add_to(m)

        for _, row in geocoded_units.iterrows():
            style_key = row.get('status', 'default')
            style = status_styles.get(style_key, status_styles['default'])
            folium.Marker(
                location=[row['latitude'], row['longitude']],
                popup=folium.Popup(self.create_popup_content(row), max_width=320),
                tooltip=f"{row.get('property_address', 'N/A')} ({str(style_key).title()})",
                icon=folium.Icon(color=style['color'], icon=style['icon'], prefix='fa')
            ).add_to(marker_cluster)
        
        plugins.Fullscreen(position='topleft').add_to(m)
        return m

# --- Helper Functions ---
@st.cache_data(ttl=300)
def get_all_units_cached():
    """Cached function to get all units."""
    return firestore_service.get_all_units_as_df()

def safe_json_loads(s):
    try:
        return json.loads(s) if isinstance(s, str) else s
    except (json.JSONDecodeError, TypeError):
        return {}

def display_unit_details_modal(unit_id: str):
    """Display unit details in a modal-like interface using session state."""
    try:
        unit_data = firestore_service.get_unit_by_id(unit_id)
        
        if not unit_data:
            st.error(f"No unit found with ID: {unit_id}")
            return
            
        # Display unit details in an expander that's automatically expanded
        with st.expander(f"📋 **Unit Details: {unit_data.get('property_address', 'N/A')} - Unit {unit_data.get('unit', 'N/A')}**", expanded=True):
            
            # Close button at the top
            if st.button("❌ Close Details", key=f"close_details_top_{unit_id}", type="secondary"):
                if 'selected_unit_id' in st.session_state:
                    del st.session_state.selected_unit_id
                st.rerun()
            
            # Basic info in columns
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Status", str(unit_data.get('status', 'N/A')).replace('_', ' ').title())
                st.metric("Bedrooms", unit_data.get('bedrooms', 'N/A'))
            with col2:
                st.metric("Square Feet", f"{unit_data.get('square_feet', 'N/A')}" if unit_data.get('square_feet') else 'N/A')
                st.metric("Bathrooms", unit_data.get('bathrooms', 'N/A'))
            with col3:
                st.metric("Area/Neighborhood", unit_data.get('area', 'N/A'))
                st.metric("Zip Code", unit_data.get('zip_code', 'N/A'))
            with col4:
                if unit_data.get('parking'):
                    st.metric("Parking", unit_data.get('parking', 'N/A'))
                if unit_data.get('rent'):
                    st.metric("Rent", f"${unit_data.get('rent')}")
            
            # Quick actions in a single row
            st.subheader("⚡ Quick Actions")
            action_col1, action_col2, action_col3 = st.columns(3)
            
            with action_col1:
                # Status update
                status_options = ['available', 'favorite', 'not_interested', 'off_market']
                current_status = unit_data.get('status', 'available')
                try:
                    status_index = status_options.index(current_status)
                except ValueError:
                    status_index = 0
                    
                new_status = st.selectbox(
                    "Update Status",
                    options=status_options,
                    index=status_index,
                    key=f"status_select_{unit_id}",
                    format_func=lambda x: x.replace('_', ' ').title()
                )
                if st.button("💾 Save Status", key=f"save_status_{unit_id}"):
                    firestore_service.update_unit(unit_id, {'status': new_status})
                    st.success(f"Status updated to '{new_status.replace('_', ' ').title()}'!")
                    st.cache_data.clear()
                    st.rerun()
            
            with action_col2:
                # Favorite toggle
                current_favorite = unit_data.get('favorite', False)
                if st.button(f"{'💔 Remove from' if current_favorite else '⭐ Add to'} Favorites", 
                           key=f"fav_toggle_{unit_id}", use_container_width=True):
                    firestore_service.update_favorite_status(unit_id, not current_favorite)
                    st.success(f"Unit {'removed from' if current_favorite else 'added to'} favorites!")
                    st.cache_data.clear()
                    st.rerun()
            
            with action_col3:
                # External link
                if unit_data.get('listing_link'):
                    st.link_button("🔗 View Original Listing", unit_data.get('listing_link'), use_container_width=True)
            
            # Additional details in collapsible sections
            if any([unit_data.get('notes'), unit_data.get('questions_for_agent'), 
                   unit_data.get('subsidy'), unit_data.get('utilities'), unit_data.get('amenities')]):
                st.subheader("📄 Additional Details")
                
                detail_col1, detail_col2 = st.columns(2)
                
                with detail_col1:
                    # Notes and questions
                    if unit_data.get('notes'):
                        st.markdown("**📝 Notes:**")
                        st.write(unit_data.get('notes'))
                        st.markdown("---")
                    
                    if unit_data.get('questions_for_agent'):
                        st.markdown("**❓ Questions for Agent:**")
                        st.write(unit_data.get('questions_for_agent'))
                        st.markdown("---")
                    
                    # Subsidy information
                    if 'subsidy' in unit_data and isinstance(unit_data['subsidy'], dict):
                        st.markdown("**💰 Subsidy Acceptance:**")
                        subsidy_data = unit_data['subsidy']
                        hacla_status = "✅ Accepted" if subsidy_data.get('hacla', False) else "❌ Not Accepted"
                        bc_status = "✅ Accepted" if subsidy_data.get('bc', False) else "❌ Not Accepted"
                        st.write(f"**HACLA:** {hacla_status}")
                        st.write(f"**BC (Housing Choice):** {bc_status}")
                        st.markdown("---")
                
                with detail_col2:
                    # Utilities
                    if 'utilities' in unit_data and isinstance(unit_data['utilities'], dict):
                        st.markdown("**🔌 Utilities:**")
                        utilities_data = unit_data['utilities']
                        owner_paid = [k for k, v in utilities_data.items() if v == 'owner']
                        tenant_paid = [k for k, v in utilities_data.items() if v == 'tenant']
                        
                        if owner_paid:
                            st.write("**Owner Pays:** " + ", ".join(owner_paid).replace('_', ' ').title())
                        if tenant_paid:
                            st.write("**Tenant Pays:** " + ", ".join(tenant_paid).replace('_', ' ').title())
                        st.markdown("---")
                    
                    # Amenities
                    if 'amenities' in unit_data and isinstance(unit_data['amenities'], dict):
                        st.markdown("**🏠 Amenities:**")
                        amenities_data = unit_data['amenities']
                        for category, amenity_dict in amenities_data.items():
                            if isinstance(amenity_dict, dict):
                                available = [k for k, v in amenity_dict.items() if v is True]
                                if available:
                                    st.write(f"**{category.replace('_', ' ').title()}:**")
                                    for amenity in available:
                                        st.write(f"• {amenity.replace('_', ' ').title()}")
                    
    except Exception as e:
        st.error(f"Error loading unit details: {e}")

# --- Main App ---
def main_app():
    st.set_page_config(
        page_title="Housing Map", 
        page_icon=":material/map:", 
        layout="wide",
        initial_sidebar_state="expanded"
    )
    st.title("Housing Listings Map")
    
    # --- Debug Mode ---
    is_debug_mode = st.query_params.get("debug", "false").lower() == "true"

    all_db_units = get_all_units_cached()

    if all_db_units.empty:
        st.info("Welcome! Your database is currently empty.")
        st.page_link("pages/1_Upload_Data.py", label="Upload your first housing CSV")
        st.stop()

    failure_count = firestore_service.get_geocoding_failure_count()
    if failure_count > 0:
        st.warning(f"**{failure_count} units could not be geocoded.**")
        st.page_link("pages/3_Geocoding_Failures.py", label="Resolve Geocoding Failures")

    # --- Data Pre-processing ---
    df = all_db_units.copy()
    
    # --- Sidebar ---
    with st.sidebar:
        st.header("🛠️ Data Management")

        if st.button("🔄 Process New/Uncoded Units", use_container_width=True):
            st.cache_data.clear() # Clear cache before processing
            with st.spinner("Checking for units to process..."):
                all_data = get_all_units_cached()
            
            # Check if any units need processing (geocoding)
            if 'latitude' not in all_data.columns:
                needs_processing = len(all_data) > 0  # Need processing if we have data but no latitude column
            else:
                needs_processing = pd.to_numeric(all_data['latitude'], errors='coerce').isnull().any()
            
            if not needs_processing:
                st.toast("No new units to process.")
            else:
                progress_bar = st.progress(0, "Starting processing...")
                status_text = st.empty()
                processor = HousingDataProcessor()
                results = processor.process_all_units(all_data, status_text, progress_bar)
                
                st.success("Processing complete!")
                st.metric("Processed/Geocoded", results['processed'] + results['processed_no_scrape'])
                st.metric("Geocoding Failures", results['geocoding_failed'], delta_color="inverse")
                st.metric("Scraping Failures", results['scraping_failed'], delta_color="inverse")
                
                progress_bar.empty()
                status_text.empty()
                st.cache_data.clear() # Clear cache again to show new data
                st.rerun()


                
        st.divider()
        st.header("📊 How to Use")
        st.markdown("""
        **🔍 Advanced Filtering:**
        - **Multi-select**: Hold Ctrl/Cmd to select multiple options
        - **Bedrooms**: Select multiple bedroom counts
        - **Status**: Include "favorites" to see favorited units
        - **Neighborhoods**: Select multiple areas
        - **Amenities**: Filter by specific amenities
        
        **📋 Viewing Unit Details:**
        1. Apply filters above the unit cards
        2. Click "View Details" on any unit card
        3. Details appear below all cards
        4. Click "Close Details" to select another unit
        
        **🗺️ Map Integration:**
        - Map automatically updates with filtered results
        - Click markers for quick property info
        """)
        
        st.header("📈 Data Overview")
        st.write(f"Total units in database: **{len(df)}**")
        
        # Quick stats
        if 'status' in df.columns:
            status_counts = df['status'].value_counts()
            for status, count in status_counts.items():
                st.write(f"• {status.replace('_', ' ').title()}: {count}")
        
        # Show favorites count
        if 'favorite' in df.columns:
            favorites_count = df['favorite'].sum() if df['favorite'].dtype == bool else len(df[df['favorite'] == True])
            st.write(f"• ⭐ Favorited: {favorites_count}")
                
        st.header("🔗 Quick Links")
        st.page_link("pages/1_Upload_Data.py", label="📁 Upload New Data", icon="📁")
        
        # Add quick filter buttons
        st.markdown("**Quick Filters:**")
        if st.button("⭐ Show Favorites Only", use_container_width=True):
            # Set the status filter to favorites
            st.session_state.status_filter = ['favorites']
            st.rerun()
        
        if st.button("🟢 Show Available Only", use_container_width=True):
            # Set the status filter to available
            st.session_state.status_filter = ['available']
            st.rerun()
        
        # --- Debug/Dev View ---
        if is_debug_mode:
            st.divider()
            with st.expander("🛠️ Debug/Developer Mode", expanded=False):
                st.subheader("Database Management")
                if st.button("🚨 Clear Entire Database", type="primary"):
                    with st.spinner("Clearing database..."):
                        success = firestore_service.clear_database()
                    if success:
                        st.success("Database cleared successfully!")
                    else:
                        st.error("Failed to clear database.")
                    st.cache_data.clear()
                    st.rerun()
                    
                st.subheader("Data Debug Info")
                st.write(f"DataFrame shape: {df.shape}")
                st.write(f"Available columns: {list(df.columns)}")
                if 'area' in df.columns:
                    st.write(f"Area column info: min={df['area'].min()}, max={df['area'].max()}, non-null count={df['area'].count()}")
                    st.write(f"Area sample values: {df['area'].dropna().head().tolist()}")
                if 'bedrooms' in df.columns:
                    st.write(f"Bedrooms column info: unique values={sorted(df['bedrooms'].dropna().unique().tolist())}")
        else:
            # Show basic data info even in non-debug mode to help troubleshoot
            with st.expander("📊 Data Summary", expanded=False):
                st.write(f"Total units loaded: {len(df)}")
                st.write(f"Columns available: {', '.join(df.columns)}")

    # --- Main Page Layout ---
    # Use all data without filtering initially
    base_df = df.copy()
    
    # Clean data types for display to prevent Arrow conversion issues
    for col in base_df.columns:
        if col in ['bedrooms', 'parking', 'zip_code', 'square_feet']:
            # Ensure numeric columns are properly typed
            base_df[col] = pd.to_numeric(base_df[col], errors='coerce').fillna(0).astype(int)
        elif col in ['bathrooms']:
            # Bathrooms can be float
            base_df[col] = pd.to_numeric(base_df[col], errors='coerce').fillna(0.0)
        elif col in ['amenities', 'utilities', 'subsidy']:
            # Convert complex objects to strings for display
            base_df[col] = base_df[col].astype(str)
    
    # Add filters and sorting in the main content area
    st.subheader("📋 Housing Units")
    
    # Create filter row
    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([2, 2, 3, 2])
    
    with filter_col1:
        # Bedroom filter
        if 'bedrooms' in base_df.columns:
            bedroom_options = sorted([int(x) for x in base_df['bedrooms'].dropna().unique() if x > 0])
            selected_bedrooms = st.multiselect("🛏️ Bedrooms", bedroom_options, key="bedroom_filter")
        else:
            selected_bedrooms = []
    
    with filter_col2:
        # Status filter - now includes favorites
        if 'status' in base_df.columns:
            status_options = sorted(base_df['status'].dropna().unique().tolist())
            # Add favorites option
            if 'favorite' in base_df.columns:
                status_options.append('favorites')
            selected_statuses = st.multiselect("📊 Status", status_options, key="status_filter")
        else:
            selected_statuses = []
    
    with filter_col3:
        # Area/Neighborhood multi-select
        if 'area' in base_df.columns:
            area_options = sorted(base_df['area'].dropna().unique().tolist())
            selected_areas = st.multiselect("📍 Neighborhoods", area_options, key="area_filter")
        else:
            selected_areas = []
    
    with filter_col4:
        # Zip code multi-select
        if 'zip_code' in base_df.columns:
            zip_options = sorted([int(x) for x in base_df['zip_code'].dropna().unique() if x > 0])
            selected_zips = st.multiselect("📮 Zip Codes", zip_options, key="zip_filter")
        else:
            selected_zips = []
    
    # Additional filters row
    amenity_col, sort_col, clear_col = st.columns([4, 2, 2])
    
    with amenity_col:
        # Amenities filter
        amenity_options = []
        if 'amenities' in base_df.columns:
            # Extract all unique amenities from the data
            for _, row in base_df.iterrows():
                if isinstance(row.get('amenities'), dict):
                    for category, amenity_dict in row['amenities'].items():
                        if isinstance(amenity_dict, dict):
                            for amenity, has_amenity in amenity_dict.items():
                                if has_amenity:
                                    amenity_display = f"{category.replace('_', ' ').title()}: {amenity.replace('_', ' ').title()}"
                                    if amenity_display not in amenity_options:
                                        amenity_options.append(amenity_display)
            amenity_options = sorted(amenity_options)
        selected_amenities = st.multiselect("🏠 Amenities", amenity_options, key="amenity_filter")
    
    with sort_col:
        # Sort options
        sort_options = ['Address', 'Bedrooms', 'Square Feet', 'Status', 'Area']
        selected_sort = st.selectbox("📈 Sort by", sort_options, key="sort_filter")
    
    with clear_col:
        if st.button("🗑️ Clear All Filters", use_container_width=True):
            # Clear all filters by removing them from session state
            for key in ['bedroom_filter', 'status_filter', 'area_filter', 'zip_filter', 'amenity_filter']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
    
    # Apply filters
    filtered_df = base_df.copy()
    
    # Apply bedroom filter
    if selected_bedrooms:
        filtered_df = filtered_df[filtered_df['bedrooms'].isin(selected_bedrooms)]
    
    # Apply status filter (including favorites)
    if selected_statuses:
        if 'favorites' in selected_statuses:
            # Filter for favorites
            favorites_condition = filtered_df.get('favorite', False) == True
            other_statuses = [s for s in selected_statuses if s != 'favorites']
            if other_statuses:
                status_condition = filtered_df['status'].isin(other_statuses)
                filtered_df = filtered_df[favorites_condition | status_condition]
            else:
                filtered_df = filtered_df[favorites_condition]
        else:
            filtered_df = filtered_df[filtered_df['status'].isin(selected_statuses)]
    
    # Apply area filter
    if selected_areas:
        filtered_df = filtered_df[filtered_df['area'].isin(selected_areas)]
    
    # Apply zip code filter
    if selected_zips:
        filtered_df = filtered_df[filtered_df['zip_code'].isin(selected_zips)]
    
    # Apply amenities filter
    if selected_amenities:
        def has_selected_amenities(row):
            if not isinstance(row.get('amenities'), dict):
                return False
            for selected_amenity in selected_amenities:
                if ':' in selected_amenity:
                    category_part, amenity_part = selected_amenity.split(':', 1)
                    category = category_part.strip().lower().replace(' ', '_')
                    amenity = amenity_part.strip().lower().replace(' ', '_')
                    
                    amenities_data = row['amenities']
                    if category in amenities_data and isinstance(amenities_data[category], dict):
                        if amenity in amenities_data[category] and amenities_data[category][amenity]:
                            continue
                    return False
            return True
        
        filtered_df = filtered_df[filtered_df.apply(has_selected_amenities, axis=1)]
    
    # Apply sorting
    if selected_sort == 'Address':
        filtered_df = filtered_df.sort_values('property_address', na_position='last')
    elif selected_sort == 'Bedrooms':
        filtered_df = filtered_df.sort_values('bedrooms', na_position='last')
    elif selected_sort == 'Square Feet':
        filtered_df = filtered_df.sort_values('square_feet', ascending=False, na_position='last')
    elif selected_sort == 'Status':
        filtered_df = filtered_df.sort_values('status', na_position='last')
    elif selected_sort == 'Area':
        filtered_df = filtered_df.sort_values('area', na_position='last')
    
    # Display count
    st.write(f"**Showing {len(filtered_df)} of {len(base_df)} units**")
    
    # Create main layout with map and listings
    map_col, data_col = st.columns([1, 1])

    with map_col:
        st.subheader("🗺️ Map View")
        processor = HousingDataProcessor()
        m = processor.create_map(filtered_df)  # Use filtered data for map
        st_folium(m, width='100%', height=600, returned_objects=[])

    with data_col:
        st.subheader("📋 Unit Cards")
        
        # Check if a unit is selected for details view
        if 'selected_unit_id' in st.session_state:
            st.info("💡 **Unit details are shown below the cards.** Click 'Close Details' to select another unit.")
        
        if is_debug_mode:
            st.dataframe(filtered_df)
        else:
            # Display units as cards
            if len(filtered_df) == 0:
                st.info("🔍 No units match your current filters. Try adjusting the filters above.")
            else:
                for idx, row in filtered_df.iterrows():
                    unit_id = row.get('id')
                    is_selected = st.session_state.get('selected_unit_id') == unit_id
                    
                    # Use different border style for selected card
                    border_color = "blue" if is_selected else None
                    
                    with st.container(border=True):
                        if is_selected:
                            st.markdown("🔍 **Selected Unit**")
                        
                        # Display key info in columns
                        info_col1, info_col2, info_col3, action_col = st.columns([3, 2, 2, 1])
                        
                        with info_col1:
                            st.write(f"**{row.get('property_address', 'N/A')}** - Unit {row.get('unit', 'N/A')}")
                            st.write(f"📍 {row.get('area', 'N/A')} • {row.get('zip_code', 'N/A')}")
                        
                        with info_col2:
                            st.write(f"🛏️ {row.get('bedrooms', 'N/A')} BR")
                            st.write(f"📐 {row.get('square_feet', 'N/A')} sq ft")
                        
                        with info_col3:
                            status_display = str(row.get('status', 'N/A')).replace('_', ' ').title()
                            status_color = {
                                'Available': '🟢',
                                'Favorite': '⭐',
                                'Not Interested': '⚪',
                                'Off Market': '⚫'
                            }.get(status_display, '🟣')
                            st.write(f"{status_color} {status_display}")
                            if row.get('parking'):
                                st.write(f"🚗 {row.get('parking')} parking")
                        
                        with action_col:
                            if is_selected:
                                # Show close button for selected unit
                                if st.button("Close Details", key=f"close_{unit_id}", use_container_width=True):
                                    if 'selected_unit_id' in st.session_state:
                                        del st.session_state.selected_unit_id
                                    st.rerun()
                            else:
                                # Show view details button
                                if st.button("View Details", key=f"details_{unit_id}", use_container_width=True):
                                    st.session_state.selected_unit_id = unit_id
                                    st.rerun()
    
    # Display unit details OUTSIDE the columns, below everything
    if 'selected_unit_id' in st.session_state:
        st.divider()
        display_unit_details_modal(st.session_state.selected_unit_id)

if __name__ == "__main__":
    main_app()
