import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import os
from datetime import datetime

# --- CONFIGURATION ---
DB_FILE = 'icc_bridge_rankings.csv'

# --- HELPER FUNCTIONS ---
def clean_name(name_str):
    """Cleans raw names from XML."""
    if not name_str:
        return None
    # Title case (e.g., "ANIL PATEL" -> "Anil Patel")
    clean = name_str.strip().title()
    if clean == "":
        return None
    return clean

def parse_xml_usebio(uploaded_file):
    """Parses USEBIO XML files and extracts scores."""
    try:
        tree = ET.parse(uploaded_file)
        root = tree.getroot()
        
        # 1. Extract Date
        date_node = root.find('.//DATE')
        if date_node is None or not date_node.text:
            st.error("❌ Error: Could not find a date in the XML file.")
            return pd.DataFrame()
            
        raw_date = date_node.text
        # USEBIO standard is DD/MM/YYYY
        try:
            session_date = datetime.strptime(raw_date, "%d/%m/%Y")
        except ValueError:
            # Fallback if date format is different
            session_date = datetime.strptime(raw_date, "%Y-%m-%d")
        
        # 2. Extract Participants and Scores
        records = []
        for pair in root.findall('.//PARTICIPANTS/PAIR'):
            try:
                pct_str = pair.find('PERCENTAGE').text
                percentage = float(pct_str)
                
                # Get Players in this pair
                for player in pair.findall('PLAYER'):
                    p_name_node = player.find('PLAYER_NAME')
                    if p_name_node is not None:
                        clean_p = clean_name(p_name_node.text)
                        if clean_p:
                            records.append({
                                'Date': session_date,
                                'Player': clean_p,
                                'Percentage': percentage
                            })
            except Exception:
                continue 
                
        return pd.DataFrame(records)

    except Exception as e:
        st.error(f"Error parsing XML: {e}")
        return pd.DataFrame()

def load_database():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Date'] = pd.to_datetime(df['Date'])
        return df
    return pd.DataFrame(columns=['Date', 'Player', 'Percentage'])

def save_to_database(new_df):
    if new_df.empty:
        return False
        
    if os.path.exists(DB_FILE):
        existing_df = pd.read_csv(DB_FILE)
        existing_df['Date'] = pd.to_datetime(existing_df['Date'])
        
        # Check if date exists
        new_date = pd.to_datetime(new_df['Date'].iloc[0])
        existing_dates = existing_df['Date'].dt.date.unique()
        
        if new_date.date() in existing_dates:
            st.warning(f"⚠️ Data for {new_date.date()} already exists.")
            return False
            
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        combined_df = new_df
        
    combined_df.to_csv(DB_FILE, index=False)
    return True

# --- APP LAYOUT ---
st.set_page_config(page_title="ICC Bridge Admin", layout="wide", page_icon="♠️")

st.title("♠️ ICC Bridge Club Director Console")

# Create Tabs
tab1, tab2, tab3 = st.tabs(["🏆 View Rankings", "📤 Upload XML", "⚙️ Database Admin"])

# --- TAB 1: RANKINGS ---
with tab1:
    df = load_database()
    
    if df.empty:
        st.info("No data found. Please upload an XML file in the Upload tab.")
    else:
        # Date Selection
        col1, col2 = st.columns(2)
        with col1:
            years = sorted(df['Date'].dt.year.unique(), reverse=True)
            selected_year = st.selectbox("Select Year", years)
        
        with col2:
            df_year = df[df['Date'].dt.year == selected_year]
            months = sorted(df_year['Date'].dt.month_name().unique(), 
                          key=lambda m: datetime.strptime(m, "%B").month)
            selected_month = st.selectbox("Select Month", months, index=len(months)-1)
            
        # Filter Data
        mask = (df['Date'].dt.year == selected_year) & (df['Date'].dt.month_name() == selected_month)
        monthly_data = df[mask]
        
        st.markdown("---")
        
        # Calculate Stats
        rankings = monthly_data.groupby('Player').agg(
            Sessions_Played=('Date', 'nunique'),
            Average_Score=('Percentage', 'mean')
        ).reset_index()
        
        # Sort by Average
        rankings = rankings.sort_values(by='Average_Score', ascending=False).reset_index(drop=True)
        rankings.index += 1  # Start rank at 1
        
        # Format
        rankings['Average_Score'] = rankings['Average_Score'].map('{:.2f}%'.format)
        
        st.subheader(f"Rankings for {selected_month} {selected_year}")
        st.dataframe(rankings, use_container_width=True)

# --- TAB 2: UPLOAD ---
with tab2:
    st.header("Upload Session XML")
    st.write("Upload the USEBIO XML file from your scoring software.")
    
    uploaded_file = st.file_uploader("Choose XML File", type=['xml'])
    
    if uploaded_file:
        if st.button("Process & Save Session"):
            new_scores = parse_xml_usebio(uploaded_file)
            
            if not new_scores.empty:
                extracted_date = new_scores['Date'].iloc[0].date()
                st.write(f"📅 **Date Detected:** {extracted_date}")
                st.write(f"👥 **Players Found:** {len(new_scores)}")
                
                if save_to_database(new_scores):
                    st.success("✅ Database updated successfully!")
                    st.balloons()
                    st.rerun()

# --- TAB 3: ADMIN ---
with tab3:
    st.subheader("Manage Database")
    df = load_database()
    
    if not df.empty:
        st.write("Delete a session if it was uploaded incorrectly.")
        dates = sorted(df['Date'].dt.date.unique(), reverse=True)
        to_delete = st.selectbox("Select Session Date to Delete", dates)
        
        if st.button(f"🗑️ Delete All Records for {to_delete}"):
            df = df[df['Date'].dt.date != to_delete]
            df.to_csv(DB_FILE, index=False)
            st.success("Session deleted.")
            st.rerun()
    else:
        st.write("Database is empty.")