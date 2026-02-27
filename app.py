import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURATION ---
# Connect to Google Sheets using the secrets you just saved
try:
    CONN = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Configuration Error: {e}")
    st.stop()

# --- HELPER FUNCTIONS ---
def clean_name(name_str):
    """Standardizes names (Title Case, removes extra spaces)"""
    if not name_str: return None
    # Remove # codes if present (e.g. Name#123)
    if '#' in name_str:
        name_str = name_str.split('#')[0]
    clean = name_str.strip().title()
    return clean if clean else None

def parse_xml_usebio(uploaded_file):
    """Parses the XML file and extracts Date + Scores"""
    try:
        tree = ET.parse(uploaded_file)
        root = tree.getroot()
        
        # 1. Extract Date
        date_node = root.find('.//DATE')
        if date_node is None or not date_node.text:
            return None, pd.DataFrame() 
            
        raw_date = date_node.text
        # Handle DD/MM/YYYY or YYYY-MM-DD
        try:
            session_date = datetime.strptime(raw_date, "%d/%m/%Y").date()
        except ValueError:
            try:
                session_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
            except:
                return None, pd.DataFrame()
        
        # 2. Extract Scores
        records = []
        for pair in root.findall('.//PARTICIPANTS/PAIR'):
            try:
                # Get Percentage
                pct_node = pair.find('PERCENTAGE')
                if pct_node is None: continue
                pct = float(pct_node.text)
                
                # Get Players
                for player in pair.findall('PLAYER'):
                    p_name = player.find('PLAYER_NAME')
                    if p_name is not None:
                        clean_p = clean_name(p_name.text)
                        if clean_p:
                            records.append({
                                'Date': str(session_date), # Store as string for Sheets compatibility
                                'Player': clean_p,
                                'Percentage': pct
                            })
            except: continue
            
        return session_date, pd.DataFrame(records)

    except Exception as e:
        st.error(f"XML Parsing Error: {e}")
        return None, pd.DataFrame()

# --- APP LAYOUT ---
st.set_page_config(page_title="ICC Bridge Admin", layout="wide", page_icon="♠️")
st.title("♠️ ICC Bridge Club - Director Console")

# Tabs
tab1, tab2, tab3 = st.tabs(["🏆 Running Rankings", "📤 Upload Session", "⚙️ Admin Tools"])

# --- DATA LOADER ---
# Read data from Google Sheet "Sheet1"
try:
    # ttl=0 means "don't cache", get fresh data every time
    df = CONN.read(worksheet="Sheet1", ttl=0)
    # If sheet is empty/new, create structure
    if df.empty:
        df = pd.DataFrame(columns=['Date', 'Player', 'Percentage'])
    else:
        # Ensure Date column is datetime for filtering
        df['Date'] = pd.to_datetime(df['Date'])
except Exception:
    df = pd.DataFrame(columns=['Date', 'Player', 'Percentage'])

# --- TAB 1: RANKINGS ---
with tab1:
    if df.empty:
        st.info("The database is empty. Please upload an XML file in the Upload tab.")
    else:
        st.write("### Monthly Accumulator")
        
        # 1. Select Year & Month
        col1, col2 = st.columns(2)
        
        years = sorted(df['Date'].dt.year.unique(), reverse=True)
        if not years: years = [datetime.now().year]
        sel_year = col1.selectbox("Select Year", years)
        
        # Filter df to selected year first
        df_year = df[df['Date'].dt.year == sel_year]
        
        if df_year.empty:
            st.warning("No data for this year.")
        else:
            months = sorted(df_year['Date'].dt.month_name().unique(), 
                          key=lambda m: datetime.strptime(m, "%B").month)
            sel_month = col2.selectbox("Select Month", months, index=len(months)-1)
            
            # 2. Filter Data
            mask = (df['Date'].dt.year == sel_year) & (df['Date'].dt.month_name() == sel_month)
            monthly_data = df[mask]
            
            if monthly_data.empty:
                st.warning("No data found for this month.")
            else:
                # 3. Show Stats
                sessions_found = sorted(monthly_data['Date'].dt.date.unique())
                st.success(f"Found {len(sessions_found)} sessions: {', '.join(map(str, sessions_found))}")
                
                # 4. Calculate Leaderboard
                # Group by Player Name
                leaderboard = monthly_data.groupby('Player').agg(
                    Sessions=('Date', 'nunique'),
                    Average_Score=('Percentage', 'mean')
                ).reset_index()
                
                # Sort by Average Score
                leaderboard = leaderboard.sort_values(by='Average_Score', ascending=False).reset_index(drop=True)
                leaderboard.index += 1 # Start rank at 1
                
                # Format Percentage
                leaderboard['Average_Score'] = leaderboard['Average_Score'].map('{:.2f}%'.format)
                
                st.dataframe(leaderboard, use_container_width=True)

# --- TAB 2: UPLOAD ---
with tab2:
    st.header("Upload XML Result")
    st.write("Upload the XML file from your scoring software. The date will be detected automatically.")
    
    uploaded_file = st.file_uploader("Choose XML File", type=['xml'])
    
    if uploaded_file is not None:
        if st.button("Process & Add to Rankings"):
            with st.spinner("Processing..."):
                session_date, new_data = parse_xml_usebio(uploaded_file)
                
                if new_data.empty:
                    st.error("Could not extract data. Is this a valid USEBIO XML file?")
                else:
                    # Check for duplicates (prevent uploading same session twice)
                    existing_dates = df['Date'].dt.date.astype(str).unique() if not df.empty else []
                    
                    if str(session_date) in existing_dates:
                        st.error(f"⚠️ Stop! Results for {session_date} are already in the database.")
                    else:
                        # Append new data to old data
                        # We convert date to string before sending to Google Sheets
                        new_data['Date'] = new_data['Date'].astype(str)
                        if not df.empty:
                            df['Date'] = df['Date'].dt.date.astype(str)
                            updated_df = pd.concat([df, new_data], ignore_index=True)
                        else:
                            updated_df = new_data
                            
                        # Update Google Sheet
                        CONN.update(worksheet="Sheet1", data=updated_df)
                        
                        st.success(f"✅ Success! Added results for {session_date}.")
                        st.balloons()
                        st.cache_data.clear() # Clear cache to force refresh
                        # Optional: Auto-rerun
                        # st.rerun() 

# --- TAB 3: ADMIN ---
with tab3:
    st.header("Database Maintenance")
    st.warning("Use these buttons with caution.")
    
    col_a1, col_a2 = st.columns(2)
    
    with col_a1:
        st.subheader("Clear Database")
        if st.button("🗑️ Wipe All Data"):
            empty_df = pd.DataFrame(columns=['Date', 'Player', 'Percentage'])
            CONN.update(worksheet="Sheet1", data=empty_df)
            st.success("Database wiped clean.")
            st.rerun()
            
    with col_a2:
        st.subheader("View Raw Data")
        if st.checkbox("Show Google Sheet Data"):
            st.dataframe(df)
