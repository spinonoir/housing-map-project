import streamlit as st
import pandas as pd
from firestore_service import firestore_service
from datetime import datetime

# Import the modal function from Home.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

def display_unit_details_modal(unit_id: str):
    """Display unit details in a modal-like interface using session state."""
    try:
        unit_data = firestore_service.get_unit_by_id(unit_id)
        
        if not unit_data:
            st.error(f"No unit found with ID: {unit_id}")
            return
            
        # Display unit details in an expander that's automatically expanded
        with st.expander(f"📋 Details: {unit_data.get('property_address', 'N/A')} - Unit {unit_data.get('unit', 'N/A')}", expanded=True):
            
            # Basic info in columns
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Status", str(unit_data.get('status', 'N/A')).replace('_', ' ').title())
                st.metric("Bedrooms", unit_data.get('bedrooms', 'N/A'))
            with col2:
                st.metric("Square Feet", f"{unit_data.get('square_feet', 'N/A')} sq ft" if unit_data.get('square_feet') else 'N/A')
                st.metric("Area/Neighborhood", unit_data.get('area', 'N/A'))
            with col3:
                st.metric("Zip Code", unit_data.get('zip_code', 'N/A'))
                if unit_data.get('parking'):
                    st.metric("Parking", unit_data.get('parking', 'N/A'))
            
            # Additional details
            details_col1, details_col2 = st.columns(2)
            
            with details_col1:
                # Show other important fields
                if unit_data.get('bathrooms'):
                    st.write(f"**Bathrooms:** {unit_data.get('bathrooms')}")
                if unit_data.get('rent'):
                    st.write(f"**Rent:** ${unit_data.get('rent')}")
                if unit_data.get('listing_link'):
                    st.markdown(f"**Original Listing:** [View]({unit_data.get('listing_link')})")
                    
                # Subsidy information
                if 'subsidy' in unit_data and isinstance(unit_data['subsidy'], dict):
                    st.write("**Subsidy Acceptance:**")
                    subsidy_data = unit_data['subsidy']
                    hacla_status = "✅ HACLA" if subsidy_data.get('hacla', False) else "❌ HACLA"
                    bc_status = "✅ BC" if subsidy_data.get('bc', False) else "❌ BC"
                    st.write(f"{hacla_status}, {bc_status}")
            
            with details_col2:
                # Notes and other text fields
                if unit_data.get('notes'):
                    st.write(f"**Notes:** {unit_data.get('notes')}")
                if unit_data.get('questions_for_agent'):
                    st.write(f"**Questions for Agent:** {unit_data.get('questions_for_agent')}")
                    
                # Amenities
                if 'amenities' in unit_data and isinstance(unit_data['amenities'], dict):
                    st.write("**Amenities:**")
                    for category, amenity_dict in unit_data['amenities'].items():
                        if isinstance(amenity_dict, dict):
                            available = [k for k, v in amenity_dict.items() if v is True]
                            if available:
                                st.write(f"• {category.replace('_', ' ').title()}: {', '.join(available).replace('_', ' ')}")
            
            # Quick actions
            st.subheader("Quick Actions")
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
                    key=f"status_select_{unit_id}"
                )
                if st.button("Save Status", key=f"save_status_{unit_id}"):
                    firestore_service.update_unit(unit_id, {'status': new_status})
                    st.success(f"Status updated to '{new_status}'!")
                    st.cache_data.clear()
                    st.rerun()
            
            with action_col2:
                # Favorite toggle
                current_favorite = unit_data.get('favorite', False)
                if st.button(f"{'Remove from' if current_favorite else 'Add to'} Favorites", 
                           key=f"fav_toggle_{unit_id}"):
                    firestore_service.update_favorite_status(unit_id, not current_favorite)
                    st.success(f"Unit {'removed from' if current_favorite else 'added to'} favorites!")
                    st.cache_data.clear()
                    st.rerun()
            
            with action_col3:
                # Close modal
                if st.button("Close Details", key=f"close_details_{unit_id}"):
                    if 'selected_unit_id' in st.session_state:
                        del st.session_state.selected_unit_id
                    st.rerun()
                    
    except Exception as e:
        st.error(f"Error loading unit details: {e}")

st.set_page_config(
    page_title="Favorite Units", 
    page_icon="⭐",
    layout="wide"
)

st.title("⭐ Favorite Units")

# Load favorite units
try:
    favorites_df = firestore_service.get_favorite_units_df()
    
    if favorites_df.empty:
        st.info("You haven't marked any units as favorites yet.")
        st.page_link("Home.py", label="Browse Units")
        st.stop()
        
except Exception as e:
    st.error("Failed to load favorite units:")
    st.exception(e)
    st.stop()

# Display favorites
st.write(f"**{len(favorites_df)} favorite unit(s)**")

# Create display columns
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("⭐ Favorite Units")
    
    # Check if a unit is selected for details view
    if 'selected_unit_id' in st.session_state:
        st.info("💡 **Unit details are shown below the cards.** Click 'Close Details' to select another unit.")
    
    # Prepare display data
    display_df = favorites_df.copy()
    
    # Clean data types for display to prevent Arrow conversion issues
    for col in display_df.columns:
        if col in ['bedrooms', 'parking', 'zip_code', 'square_feet']:
            # Ensure numeric columns are properly typed
            display_df[col] = pd.to_numeric(display_df[col], errors='coerce').fillna(0).astype(int)
        elif col in ['bathrooms']:
            # Bathrooms can be float
            display_df[col] = pd.to_numeric(display_df[col], errors='coerce').fillna(0.0)
        elif col in ['amenities', 'utilities', 'subsidy']:
            # Convert complex objects to strings for display
            display_df[col] = display_df[col].astype(str)
    
    # Display units as cards instead of a table
    for idx, row in display_df.iterrows():
        unit_id = row.get('id')
        is_selected = st.session_state.get('selected_unit_id') == unit_id
        
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
                st.write(f"⭐ {status_display}")
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

with col2:
    st.subheader("Quick Actions")
    
    if st.button("🔄 Refresh Favorites", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    if st.button("🏠 View All Units", use_container_width=True):
        st.switch_page("Home.py")
    
    # Show some stats
    if not favorites_df.empty:
        st.subheader("Favorites Summary")
        
        if 'bedrooms' in favorites_df.columns:
            bedroom_counts = favorites_df['bedrooms'].value_counts().sort_index()
            st.write("**Bedrooms:**")
            for bedrooms, count in bedroom_counts.items():
                st.write(f"• {bedrooms} BR: {count} unit(s)")
        
        if 'zip_code' in favorites_df.columns:
            zip_counts = favorites_df['zip_code'].value_counts().head(5)
            st.write("**Top Zip Codes:**")
            for zip_code, count in zip_counts.items():
                st.write(f"• {zip_code}: {count} unit(s)")
        
        if 'area' in favorites_df.columns:
            avg_area = favorites_df['area'].mean()
            if not pd.isna(avg_area):
                st.metric("Average Area", f"{int(avg_area)} sq ft")

# Display unit details OUTSIDE the columns, below everything
if 'selected_unit_id' in st.session_state:
    st.divider()
    display_unit_details_modal(st.session_state.selected_unit_id)

# Back to main page link
st.divider()
st.page_link("Home.py", label="🏠 Back to Main Map", icon="🏠")
