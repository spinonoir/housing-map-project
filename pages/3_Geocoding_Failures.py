import streamlit as st
from firestore_service import firestore_service
import pandas as pd

st.set_page_config(
    page_title="Geocoding Failures", 
    page_icon=":material/wrong_location:"
)

st.title("Geocoding Failures")
st.markdown("""
This page lists all the addresses that could not be geocoded automatically. 
You can review them here, manually find their coordinates, and then perhaps 
use a database tool to update them. Alternatively, you can resolve them by removing them.
""")

def load_failures():
    return firestore_service.get_geocoding_failures_df()

failures_df = load_failures()

if failures_df.empty:
    st.success("🎉 No geocoding failures to report. All units were located successfully!")
    st.stop()

st.info(f"Found **{len(failures_df)}** unresolved geocoding failures.")

# Display failures in an editable data editor
st.subheader("Unresolved Records")

for index, row in failures_df.iterrows():
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            # Handle unit_data field which might be a dict
            unit_data = row.get('unit_data', {})
            if isinstance(unit_data, dict):
                address = unit_data.get('property_address', 'N/A')
                unit = unit_data.get('unit', 'N/A')
                zip_code = unit_data.get('zip_code', 'N/A')
            else:
                # Fallback for old format
                address = row.get('property_address', 'N/A')
                unit = row.get('unit', 'N/A')
                zip_code = row.get('zip_code', 'N/A')
            
            st.write(f"**Address:** {address}")
            st.write(f"**Unit:** {unit}, **Zip:** {zip_code}")
            st.write(f"**Reason:** {row.get('reason', 'Unknown')}")
            st.caption(f"Logged on: {row.get('timestamp', 'Unknown time')}")
        with col2:
            st.write("") # Spacer
            failure_id = row.get('failure_id') or index  # Use failure_id if available, otherwise index
            if st.button("Mark as Resolved", key=f"delete_{failure_id}", help="This will remove the item from this list."):
                try:
                    firestore_service.delete_geocoding_failure(str(failure_id))
                    st.toast(f"Record for '{address}' marked as resolved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to delete record: {e}")

st.divider()
if st.button("Refresh List"):
    st.rerun() 