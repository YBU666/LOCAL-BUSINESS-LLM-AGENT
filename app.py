import streamlit as st
# Must be the first Streamlit command
st.set_page_config(
    page_title="📍 Local Business Finder",
    page_icon="📍",
    layout="wide"  # Use wide layout for better space utilization
)

import os
import requests
import folium
from streamlit_folium import folium_static                   
import re
import geocoder
import json
from groq import Groq
from dotenv import load_dotenv

# Add custom CSS
st.markdown("""
<style>
    /* Dark theme styles */
    .main {
        background-color: #0E1117;
        color: #FFFFFF;
    }
    .stButton>button {
        width: 100%;
        border-radius: 20px;
        height: 3em;
        background-color: #FF4B4B;
        color: white;
        font-weight: bold;
    }
    .business-card {
        padding: 1.5rem;
        border-radius: 10px;
        border: 1px solid #2D3748;
        margin: 10px 0;
        background-color: #1E2530;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        color: #FFFFFF;
    }
    .business-card h3 {
        color: #FF4B4B;
        margin-bottom: 1rem;
    }
    .business-card p {
        color: #E2E8F0;
        margin: 0.5rem 0;
    }
    .business-card strong {
        color: #A0AEC0;
    }
    .business-card small {
        color: #718096;
    }
    .metric-card {
        background-color: #1E2530;
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        border: 1px solid #2D3748;
    }
    .metric-value {
        font-size: 1.5rem;
        font-weight: bold;
        color: #FF4B4B;
    }
    .metric-label {
        font-size: 0.875rem;
        color: #A0AEC0;
    }
    .rating-badge {
        background-color: #28a745;
        color: white;
        padding: 0.25rem 0.5rem;
        border-radius: 15px;
        font-size: 0.875rem;
    }
    div[data-testid="stSidebarNav"] {
        background-color: #1E2530;
        padding: 1rem;
        border-radius: 10px;
        color: #FFFFFF;
    }
    /* Style for the table */
    div[data-testid="stDataFrame"] {
        background-color: #1E2530;
        border-radius: 10px;
        padding: 1rem;
        color: #FFFFFF;
    }
    .table-container {
        background-color: #1E2530;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
    }
    /* Headers and text */
    h1, h2, h3, h4, h5, h6 {
        color: #FFFFFF !important;
    }
    p {
        color: #E2E8F0;
    }
    /* Input fields */
    div[data-baseweb="input"] {
        background-color: #1E2530;
        border-color: #2D3748;
    }
    input {
        color: #FFFFFF !important;
    }
</style>
""", unsafe_allow_html=True)

# ==== API Key Setup ====
load_dotenv()

# Get Groq API key from environment variables
groq_api_key = os.environ.get("GROQ_API_KEY")

# Configure GROQ client
client = None
if groq_api_key:
    try:
        client = Groq(api_key=groq_api_key)
        st.sidebar.success("Groq API connected successfully!")
    except Exception as e:
        st.sidebar.error(f"Failed to initialize Groq client: {e}")
else:
    st.sidebar.error("Groq API key is missing. Please add it to your .env file.")

def get_groq_response(prompt):
    try:
        if not client:
            return "Error: Groq API key is not configured."
        
        st.write("Sending request to Groq API...")
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a local business finder that provides accurate information about businesses with their exact locations and coordinates."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=1024
        )
        st.write("Received response from Groq API")
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Groq API error: {e}")
        return f"Error occurred: {str(e)}"

def extract_locations(result_text):
    try:
        locations = []
        # Split the text into business entries
        businesses = re.split(r'\d+\.\s+', result_text)[1:]  # Skip the first empty entry
        
        if not businesses:
            st.warning("No business entries found in the response")
            return []
            
        for business in businesses:
            lines = business.strip().split('\n')
            if not lines:
                continue
                
            location_data = {
                "name": lines[0] if lines else "Unknown",
                "type": "",
                "location": "",
                "rating": "",
                "coordinates": None
            }
            
            for line in lines:
                line = line.strip()
                if "Type:" in line:
                    location_data["type"] = line.split(":", 1)[1].strip()
                elif "Location:" in line:
                    location_data["location"] = line.split(":", 1)[1].strip()
                elif "Rating:" in line:
                    location_data["rating"] = line.split(":", 1)[1].strip()
                elif "Coordinates:" in line:
                    coords = line.split(":", 1)[1].strip()
                    try:
                        lat, lng = map(float, coords.split(","))
                        location_data["coordinates"] = (lat, lng)
                    except:
                        pass
            
            if location_data["name"] != "Unknown" and (location_data["location"] or location_data["coordinates"]):
                locations.append(location_data)
        
        return locations
    except Exception as e:
        st.error(f"Error extracting locations: {e}")
        return []

def geocode_address(address):
    try:
        g = geocoder.osm(address, headers={
            'User-Agent': 'LocalBusinessFinder/1.0 (yashwanth.b.u@example.com)'
        })
        if g.ok:
            return (g.lat, g.lng)
        else:
            st.debug(f"Geocoding failed: {g.status}")
    except Exception as e:
        st.debug(f"Geocoding error: {e}")
    return None

# Backup geocoding function using different provider if OSM fails
def backup_geocode_address(address):
    try:
        g = geocoder.arcgis(address)  # Using ArcGIS as backup
        if g.ok:
            return (g.lat, g.lng)
    except Exception as e:
        st.debug(f"Backup geocoding error: {e}")
    return None

def create_map(locations, location_name):
    try:
        # Try to geocode the specified location for map centering
        coords = geocode_address(location_name)
        
        # Try backup geocoding if primary fails
        if not coords:
            coords = backup_geocode_address(location_name)
        
        # Default coordinates (Bangalore) if geocoding fails
        default_lat, default_lng = 12.9716, 77.5946
        if coords:
            default_lat, default_lng = coords
        
        # Create the map
        m = folium.Map(location=[default_lat, default_lng], zoom_start=13)
        
        # Add markers for each business
        markers_added = False
        
        for loc in locations:
            coords = None
            
            # First try to use provided coordinates
            if loc.get("coordinates"):
                coords = loc["coordinates"]
            
            # If no coordinates, try to geocode the address
            if not coords and loc.get("location"):
                coords = geocode_address(loc["location"])
                if not coords:
                    coords = backup_geocode_address(loc["location"])
            
            if coords:
                markers_added = True
                popup_content = f"""
                <div style="font-family: Arial, sans-serif; min-width: 200px;">
                    <h4 style="color: #FF4B4B; margin: 0 0 10px 0;">{loc.get('name', 'Business')}</h4>
                    <p style="margin: 5px 0;"><strong>Type:</strong> {loc.get('type', '')}</p>
                    <p style="margin: 5px 0;"><strong>Location:</strong> {loc.get('location', '')}</p>
                    <p style="margin: 5px 0;"><strong>Rating:</strong> {loc.get('rating', 'N/A')}</p>
                </div>
                """
                
                folium.Marker(
                    location=coords,
                    popup=folium.Popup(popup_content, max_width=300),
                    tooltip=loc.get("name", "Business"),
                    icon=folium.Icon(color="red", icon="info-sign")
                ).add_to(m)
        
        return m, markers_added
    except Exception as e:
        st.error(f"Error creating map: {e}")
        return None, False

def perform_task(query, location):
    prompt = f"""
Find 3-5 local businesses in {location} related to: "{query}"

For each business, provide:
1. Business name
2. Type of business
3. Location (full address)
4. Rating (out of 5 stars)
5. Coordinates (latitude, longitude)

Format each listing as:
1. [Business Name]
Type: [business type]
Location: [full address]
Rating: [X.X/5]
Coordinates: [latitude], [longitude]

Ensure all coordinates are real and accurate for the specified location.
"""
    return get_groq_response(prompt)

def format_business_card(business):
    """Format a business as an HTML card"""
    rating_color = "#28a745" if float(business['rating'].split('/')[0]) >= 4.0 else "#ffc107"
    return f"""
    <div class="business-card">
        <h3>{business['name']}</h3>
        <p><strong>Type:</strong> {business['type']}</p>
        <p><strong>Location:</strong> {business['location']}</p>
        <p><span style="background-color: {rating_color}; color: white; padding: 4px 8px; border-radius: 15px;">
            {business['rating']}
        </span></p>
        <p><small>📍 Coordinates: {business['coordinates'][0]}, {business['coordinates'][1]}</small></p>
    </div>
    """

# === Streamlit UI ===
st.title("📍 Local Business Search Agent")

# App information in sidebar with improved styling
with st.sidebar:
    st.markdown("""
    <div style='background-color: #1E2530; padding: 1rem; border-radius: 10px; margin-bottom: 1rem;'>
        <h2 style='color: #FF4B4B; margin-bottom: 1rem;'>About</h2>
        <div style='background-color: #2D3748; padding: 1.5rem; border-radius: 8px; margin-bottom: 1rem;'>
            <h4 style='color: #FF4B4B; margin-bottom: 0.5rem;'>🔍 How it works</h4>
            <p style='color: #E2E8F0; margin-bottom: 1rem;'>This app uses advanced AI to find local businesses and display them on an interactive map.</p>
            <ol style='color: #E2E8F0; margin-left: 1.5rem;'>
                <li style='margin-bottom: 0.5rem;'>Enter what you're looking for</li>
                <li style='margin-bottom: 0.5rem;'>Specify the location</li>
                <li style='margin-bottom: 0.5rem;'>Get detailed results with exact locations</li>
            </ol>
        </div>
    </div>
    <div style='text-align: center; padding: 1rem; background-color: #1E2530; border-radius: 10px;'>
        <p style='color: #A0AEC0; margin-bottom: 0.5rem;'>Powered by</p>
        <h4 style='color: #FF4B4B; margin: 0;'>LLaMA 3 via Groq</h4>
    </div>
    """, unsafe_allow_html=True)

# Main content area
main_container = st.container()
with main_container:
    # Search form with improved styling
    search_col1, search_col2, search_col3 = st.columns([3, 2, 1])
    with search_col1:
        query = st.text_input("🔍 What are you looking for?", 
                            placeholder="e.g., coffee shops, restaurants, etc.",
                            help="Enter the type of business you want to find")
    with search_col2:
        location = st.text_input("📍 Where?", 
                               placeholder="e.g., Bangalore, New York, Tokyo",
                               help="Enter the city or area to search in")
    with search_col3:
        st.write("")  # Add some spacing
        st.write("")  # Add some spacing
        search_button = st.button("🔍 Search", type="primary")

    if search_button:
        if query and location:
            with st.spinner(f"🔍 Searching for {query} in {location}..."):
                try:
                    result = perform_task(query, location)
                    
                    if "Error" in result:
                        st.error(result)
                    else:
                        # Create two columns for results
                        col1, col2 = st.columns([1, 1])
                        
                        with col1:
                            st.markdown("### 📋 Search Results")
                            locations = extract_locations(result)
                            
                            if locations:
                                # Display metrics
                                metric1, metric2 = st.columns(2)
                                with metric1:
                                    st.markdown(f"""
                                    <div class="metric-card">
                                        <div class="metric-value">{len(locations)}</div>
                                        <div class="metric-label">Businesses Found</div>
                                    </div>
                                    """, unsafe_allow_html=True)
                                with metric2:
                                    avg_rating = sum([float(loc['rating'].split('/')[0]) for loc in locations]) / len(locations)
                                    st.markdown(f"""
                                    <div class="metric-card">
                                        <div class="metric-value">{avg_rating:.1f}/5</div>
                                        <div class="metric-label">Average Rating</div>
                                    </div>
                                    """, unsafe_allow_html=True)
                                
                                # Display business cards
                                for business in locations:
                                    st.markdown(format_business_card(business), unsafe_allow_html=True)
                                
                                # Create a DataFrame for tabular view
                                st.markdown("### 📊 Tabular View")
                                df_data = [{
                                    'Name': loc['name'],
                                    'Type': loc['type'],
                                    'Rating': loc['rating'],
                                    'Location': loc['location']
                                } for loc in locations]
                                st.dataframe(df_data, use_container_width=True)
                            else:
                                st.warning("No valid business locations could be extracted from the response.")
                        
                        with col2:
                            st.markdown("### 🗺️ Map View")
                            if locations:
                                map_fig, markers_added = create_map(locations, location)
                                if map_fig and markers_added:
                                    folium_static(map_fig, width=600, height=600)
                                elif map_fig:
                                    st.warning("Map created but no markers could be added. Check the business coordinates.")
                                else:
                                    st.error("Could not create map view.")
                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")
                    st.write("Please try again or contact support if the issue persists.")
        else:
            st.warning("Please enter both a search query and location.")

# Footer with improved styling
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #6c757d; padding: 1rem;'>
    <p><small>⚠️ Note: This app uses AI to generate business information which may not always be accurate. 
    Please verify details before visiting.</small></p>
    <p><small>Made with ❤️ using Streamlit and LLaMA 3</small></p>
</div>
""", unsafe_allow_html=True)