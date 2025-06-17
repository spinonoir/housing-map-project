import streamlit as st
from firestore_service import firestore_service
from datetime import datetime

st.set_page_config(
    page_title="Unit Details", 
    page_icon=":material/apartment:"
)

st.title("Unit Details")

# Get unit ID from query parameters
query_params = st.query_params
unit_id = query_params.get("unit_id")
# Handle both string and list cases
if isinstance(unit_id, list):
    unit_id = unit_id[0] if unit_id else None

if not unit_id:
    st.warning("No Unit ID found in URL. Please select a unit from the map view.")
    st.page_link("Home.py", label="Back to Map")
    st.stop()

# Fetch unit data from the database
try:
    unit_data = firestore_service.get_unit_by_id(unit_id)
    
    if not unit_data:
        st.error(f"No unit found in the database with ID `{unit_id}`.")
        st.page_link("Home.py", label="Back to Map")
        st.stop()
except Exception as e:
    st.error("An exception occurred while fetching data from the database:")
    st.exception(e)
    st.page_link("Home.py", label="Back to Map")
    st.stop()

# --- Display Unit Information ---
st.header(f"{unit_data.get('property_address', 'N/A')} - Unit {unit_data.get('unit', 'N/A')}")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Status", str(unit_data.get('status', 'N/A')).replace('_', ' ').title())
    st.metric("Bedrooms", unit_data.get('bedrooms', 'N/A'))
with col2:
    st.metric("Square Feet", f"{unit_data.get('square_feet', 'N/A')} sq ft" if unit_data.get('square_feet') else 'N/A')
    st.metric("Area/Neighborhood", unit_data.get('area', 'N/A'))
with col3:
    st.metric("Zip Code", unit_data.get('zip_code', 'N/A'))
    if unit_data.get('first_seen_date'):
        try:
            first_seen = datetime.fromisoformat(unit_data['first_seen_date']).strftime('%Y-%m-%d')
            st.metric("Date Added", first_seen)
        except (ValueError, TypeError):
            st.metric("Date Added", "Invalid Date")
    
    if unit_data.get('last_seen_date'):
        try:
            last_seen = datetime.fromisoformat(unit_data['last_seen_date']).strftime('%Y-%m-%d')
            st.metric("Last Seen", last_seen)
        except (ValueError, TypeError):
            st.metric("Last Seen", "Invalid Date")

# --- Display Additional CSV Fields ---
st.subheader("📋 Property Information")
info_col1, info_col2 = st.columns(2)

# Display all non-standard fields from the unit data
standard_fields = {'id', 'property_address', 'unit', 'zip_code', 'bedrooms', 'area', 
                  'status', 'first_seen_date', 'last_seen_date', 'latitude', 'longitude',
                  'level_of_interest', 'viewing_scheduled', 'availability_verified_date',
                  'amenities', 'questions_for_agent', 'notes', 'batch_id', 'display_name'}

additional_fields = {}
for k, v in unit_data.items():
    if k not in standard_fields and v is not None:
        str_v = str(v).strip()
        if str_v:  # Only include non-empty strings
            additional_fields[k] = str_v

if additional_fields:
    col_toggle = 0
    for key, value in additional_fields.items():
        with info_col1 if col_toggle % 2 == 0 else info_col2:
            st.text(f"**{key.replace('_', ' ').title()}:** {value}")
        col_toggle += 1
else:
    st.info("No additional property information available.")

# --- Structured Data Display ---
col1, col2 = st.columns(2)

with col1:
    # Subsidy Information
    if 'subsidy' in unit_data and isinstance(unit_data['subsidy'], dict):
        st.subheader("Subsidy Acceptance")
        subsidy_data = unit_data['subsidy']
        
        hacla_status = "✅ Accepted" if subsidy_data.get('hacla', False) else "❌ Not Accepted"
        bc_status = "✅ Accepted" if subsidy_data.get('bc', False) else "❌ Not Accepted"
        
        st.write(f"**HACLA:** {hacla_status}")
        st.write(f"**BC (Housing Choice):** {bc_status}")
    
    # Utilities Information
    if 'utilities' in unit_data and isinstance(unit_data['utilities'], dict):
        st.subheader("Utilities")
        utilities_data = unit_data['utilities']
        
        owner_paid = [k for k, v in utilities_data.items() if v == 'owner']
        tenant_paid = [k for k, v in utilities_data.items() if v == 'tenant']
        unknown = [k for k, v in utilities_data.items() if v == 'unknown']
        
        if owner_paid:
            st.write("**Owner Pays:** " + ", ".join(owner_paid).replace('_', ' ').title())
        if tenant_paid:
            st.write("**Tenant Pays:** " + ", ".join(tenant_paid).replace('_', ' ').title())
        if unknown:
            st.write("**Unknown:** " + ", ".join(unknown).replace('_', ' ').title())

with col2:
    # Amenities Information
    if 'amenities' in unit_data and isinstance(unit_data['amenities'], dict):
        st.subheader("Amenities")
        amenities_data = unit_data['amenities']
        
        for category, amenity_dict in amenities_data.items():
            if isinstance(amenity_dict, dict):
                available_amenities = [k for k, v in amenity_dict.items() if v is True]
                if available_amenities:
                    st.write(f"**{category.replace('_', ' ').title()}:**")
                    for amenity in available_amenities:
                        st.write(f"• {amenity.replace('_', ' ').title()}")

# --- Actions ---
with st.container(border=True):
    st.subheader("Quick Actions")
    status_options = ['available', 'favorite', 'not_interested', 'off_market']
    current_status = unit_data.get('status', 'available')
    try:
        status_index = status_options.index(current_status)
    except ValueError:
        status_index = 0  # Default to 'available' if current status is not in options
        
    new_status = st.selectbox(
        "Update Status",
        options=status_options,
        index=status_index,
        key=f"status_select_{unit_id}"
    )
    if st.button("Save Status Change"):
        firestore_service.update_unit(unit_id, {'status': new_status})
        st.toast(f"Status updated to '{new_status}'!", icon="✅")
        st.rerun()

# --- Favorite Toggle ---
current_favorite = unit_data.get('favorite', False)
if st.button(f"{'⭐ Remove from Favorites' if current_favorite else '⭐ Add to Favorites'}", 
            type="primary" if not current_favorite else "secondary"):
    try:
        firestore_service.update_favorite_status(unit_id, not current_favorite)
        st.success(f"Unit {'removed from' if current_favorite else 'added to'} favorites!")
        st.rerun()
    except Exception as e:
        st.error(f"Failed to update favorite status: {e}")

# --- Tracking Information Form ---
with st.form("unit_details_form"):
    st.header("📝 Tracking & Notes")
    
    details_to_update = {}
    
    # Left column for structured data
    form_col1, form_col2 = st.columns(2)
    with form_col1:
        st.subheader("Details")
        interest_levels = ["Not Set", "Low", "Medium", "High", "Very High"]
        current_interest = unit_data.get('level_of_interest', 'Not Set')
        current_interest_index = interest_levels.index(current_interest) if current_interest in interest_levels else 0
        details_to_update['level_of_interest'] = st.selectbox("Level of Interest", interest_levels, index=current_interest_index)
        
        # Handle viewing scheduled date
        current_viewing_date = None
        if unit_data.get('viewing_scheduled'):
            try:
                # Handle both ISO format and date format
                viewing_str = str(unit_data['viewing_scheduled'])
                if viewing_str and viewing_str != 'None':
                    current_viewing_date = datetime.fromisoformat(viewing_str).date()
            except (ValueError, TypeError):
                pass
        new_viewing_date = st.date_input("Viewing Scheduled", value=current_viewing_date)
        details_to_update['viewing_scheduled'] = new_viewing_date.isoformat() if new_viewing_date else ''

        # Handle availability verified date
        current_verified_date = None
        if unit_data.get('availability_verified_date'):
            try:
                # Handle both ISO format and date format
                verified_str = str(unit_data['availability_verified_date'])
                if verified_str and verified_str != 'None':
                    current_verified_date = datetime.fromisoformat(verified_str).date()
            except (ValueError, TypeError):
                pass
        new_verified_date = st.date_input("Availability Verified On", value=current_verified_date)
        details_to_update['availability_verified_date'] = new_verified_date.isoformat() if new_verified_date else ''

        details_to_update['amenities'] = st.text_area("Amenities", value=unit_data.get('amenities', ''), height=150)

    # Right column for free-form text
    with form_col2:
        st.subheader("Notes")
        details_to_update['questions_for_agent'] = st.text_area(
            "Questions for Agent/Manager", 
            value=unit_data.get('questions_for_agent', ''), 
            height=150
        )
        details_to_update['notes'] = st.text_area(
            "General Notes", 
            value=unit_data.get('notes', ''), 
            height=250
        )

    # Photos section (placeholder)
    st.subheader("📷 Photos")
    st.info("Photo upload functionality is not yet implemented. You can paste image URLs in the notes section for now.")

    submitted = st.form_submit_button("Save All Changes")
    if submitted:
        try:
            # Filter out unchanged values to avoid unnecessary DB writes
            final_details = {}
            for k, v in details_to_update.items():
                current_value = str(unit_data.get(k, '') or '')
                new_value = str(v or '')
                if new_value != current_value:
                    final_details[k] = v
            
            if final_details:
                firestore_service.update_unit(unit_id, final_details)
                st.toast("Details updated successfully!", icon="💾")
                st.rerun()
            else:
                st.toast("No changes were made.", icon="🤷")
        except Exception as e:
            st.error(f"Failed to save changes: {e}")

st.divider()
st.page_link("Home.py", label="Back to Main Map")