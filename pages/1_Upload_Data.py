import streamlit as st
import pandas as pd
from firestore_service import firestore_service

st.set_page_config(
    page_title="Upload Data", 
    page_icon=":material/upload_file:"
)

st.title("Upload New Housing Data")
st.markdown("""
Here you can upload a new CSV file containing housing listings. The system will process the file,
add new, unique listings to the database, and update the `last_seen_date` for any existing listings.
""")

# File uploader
uploaded_file = st.file_uploader(
    "Choose a CSV file", 
    type="csv",
    help="CSV should contain at minimum 'Property Address' and 'Zip Code' columns."
)

if uploaded_file is not None:
    try:
        # Read the uploaded CSV into a DataFrame with robust parsing
        df = pd.read_csv(
            uploaded_file, 
            on_bad_lines='skip',  # Skip problematic lines
            skipinitialspace=True,  # Remove leading whitespace
            na_values=['', 'N/A', 'n/a', 'null', 'NULL', '-'],  # Treat these as NaN
            keep_default_na=True
        )
        
        # Check if any rows were skipped due to parsing issues
        uploaded_file.seek(0)  # Reset file pointer
        total_lines = sum(1 for line in uploaded_file) - 1  # Subtract 1 for header
        processed_rows = len(df)
        
        if processed_rows < total_lines:
            skipped_rows = total_lines - processed_rows
            st.warning(f"⚠️ Skipped {skipped_rows} malformed row(s) during CSV parsing. "
                      f"Successfully processed {processed_rows} rows.")
        
        st.subheader("CSV Preview")
        st.dataframe(df.head())
        
        # Display expected columns and which ones are found
        st.subheader("Column Validation")
        expected_cols = [
            'Property Address', 'Unit', 'Zip Code', 'Bedrooms', 'Area', 
            'Parking', 'Subsidy', 'Ground Floor / ADA', 'Listing Link'
        ]
        
        found_cols = [col for col in expected_cols if col in df.columns]
        missing_cols = [col for col in expected_cols if col not in df.columns]
        extra_cols = [col for col in df.columns if col not in expected_cols]
        
        st.info(f"**Found Standard Columns:** {', '.join(found_cols) if found_cols else 'None'}")
        if missing_cols:
            st.warning(f"**Missing Optional Columns:** {', '.join(missing_cols)}")
        if extra_cols:
            st.success(f"**Additional Columns Found:** {', '.join(extra_cols)} - These will be stored as flexible data.")

        # Process the CSV file
        if st.button("Load Data into Database", type="primary"):
            with st.spinner("Processing file... This may take a moment."):
                try:
                    # Load data into the database using the new service
                    inserted, updated = firestore_service.upload_from_dataframe(df)
                    
                    st.success("✅ File processed successfully!")
                    st.metric("New Units Added", inserted)
                    st.metric("Existing Units Updated", updated)
                    
                    st.balloons()
                    
                    # Clear any cached data to show updated results
                    if hasattr(st, 'cache_data'):
                        st.cache_data.clear()
                    
                except Exception as e:
                    st.error(f"An error occurred while loading data into the database: {e}")
                    st.exception(e)
                    
    except Exception as e:
        st.error(f"An error occurred while reading the CSV file: {e}")
        st.warning("Please ensure the file is a valid CSV format. The system will attempt to skip malformed rows.") 