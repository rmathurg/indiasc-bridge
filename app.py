import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURATION ---
st.set_page_config(page_title="ICC Bridge Club", layout="wide", page_icon="♠️")

# Connect to Google Sheets
try:
    CONN = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Configuration Error: {e}")
    st.stop()

# --- HELPER FUNCTIONS ---
def clean_name(name_str):
    if not name_str: return None
    if '#' in name_str:
        name_str = name_str.split('#')[0]
    clean = name_str.strip().title()
    return clean if clean else None

def parse_xml_usebio(uploaded_file):
    try:
        tree = ET.parse(uploaded_file)
        root = tree.getroot()
        
        # 1. Extract Date
        date_node = root.find('.//DATE')
        if date_node is None or not date_node.text:
            return None, pd.DataFrame() 
        
        raw_date = date_node.text
        # Handle date formats
        try:
            session_date = datetime.strptime(raw_date, "%d/%m/%Y").date()
        except ValueError:
            try:
                session_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
            except:
                return None, pd.DataFrame()
        
        # 2. Extract Scores & Boards
        records = []
        for pair in root.findall('.//PARTICIPANTS/PAIR'):
            try:
                pct_node = pair.find('PERCENTAGE')
                boards_node = pair.find('BOARDS_PLAYED')
                
                if pct_node is None: continue
                
                pct = float(pct_node.text)
                boards = int(boards_node.text) if boards_node is not None else 0
                
                for player in pair.findall('PLAYER'):
                    p_name = player.find('PLAYER_NAME')
                    if p_name is not None:
                        clean_p = clean_name(p_name.text)
                        if clean_p and boards > 0:
                            records.append({
                                'Date': str(session_date),
                                'Player': clean_p,
                                'Percentage': pct,
                                'Boards': boards
                            })
            except: continue
            
        return session_date, pd.DataFrame(records)

    except Exception as e:
        st.error(f"XML Parsing Error: {e}")
        return None, pd.DataFrame()

# --- SIDEBAR LOGIN ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/282/282869.png", width=100)
    st.title("Club Menu")
    
    # Password Logic
    if "is_admin" not in st.session_state:
        st.session_state["is_admin"] = False

    entered_password = st.text_input("Director Password", type="password")
    
    if entered_password:
        if entered_password == st.secrets["admin_password"]:
            st.session_state["is_admin"] = True
            st.success("Admin Unlocked")
        else:
            st.session_state["is_admin"] = False
            st.error("Incorrect Password")

# --- DATA LOADING ---
try:
    df = CONN.read(worksheet="Sheet1", ttl=0)
    if df.empty:
        df = pd.DataFrame(columns=['Date', 'Player', 'Percentage', 'Boards'])
    else:
        df['Date'] = pd.to_datetime(df['Date'])
        # Ensure numeric columns
        cols = ['Percentage', 'Boards']
        for col in cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
except Exception:
    df = pd.DataFrame(columns=['Date', 'Player', 'Percentage', 'Boards'])

# --- MAIN LAYOUT ---
st.title("♠️ ICC Bridge Club Rankings")

# Tabs visible depend on login status
if st.session_state["is_admin"]:
    tab1, tab2, tab3 = st.tabs(["🏆 Leaderboards", "📤 Director Upload", "⚙️ Database Admin"])
else:
    tab1 = st.tabs(["🏆 Leaderboards"])[0] # Only show first tab to public

# --- TAB 1: LEADERBOARDS (Public) ---
with tab1:
    if df.empty:
        st.info("No rankings available yet.")
    else:
        # 1. VIEW TOGGLE
        view_mode = st.radio("Select View:", 
                             ["Monthly Accumulator", "Single Session"], 
                             horizontal=True)
        
        st.divider()

        # LOGIC: MONTHLY ACCUMULATOR
        if view_mode == "Monthly Accumulator":
            col1, col2 = st.columns(2)
            years = sorted(df['Date'].dt.year.unique(), reverse=True)
            sel_year = col1.selectbox("Year", years)
            
            df_year = df[df['Date'].dt.year == sel_year]
            months = sorted(df_year['Date'].dt.month_name().unique(), 
                          key=lambda m: datetime.strptime(m, "%B").month)
            
            if not months:
                st.warning("No data for this year.")
            else:
                sel_month = col2.selectbox("Month", months, index=len(months)-1)
                
                # Filter Data
                mask = (df['Date'].dt.year == sel_year) & (df['Date'].dt.month_name() == sel_month)
                monthly_data = df[mask].copy()
                
                if monthly_data.empty:
                    st.warning("No data.")
                else:
                    # WEIGHTED AVG CALCULATION
                    monthly_data['Score_Mass'] = monthly_data['Percentage'] * monthly_data['Boards']
                    
                    leaderboard = monthly_data.groupby('Player').agg(
                        Sessions=('Date', 'nunique'),
                        Total_Mass=('Score_Mass', 'sum'),
                        Total_Boards=('Boards', 'sum')
                    ).reset_index()
                    
                    leaderboard = leaderboard[leaderboard['Total_Boards'] > 0]
                    leaderboard['Weighted_Average'] = leaderboard['Total_Mass'] / leaderboard['Total_Boards']
                    
                    # Sort & Format
                    leaderboard = leaderboard.sort_values(by='Weighted_Average', ascending=False).reset_index(drop=True)
                    leaderboard.index += 1
                    leaderboard['Weighted_Average'] = leaderboard['Weighted_Average'].map('{:.2f}%'.format)
                    
                    # Display
                    st.dataframe(
                        leaderboard[['Player', 'Sessions', 'Total_Boards', 'Weighted_Average']], 
                        use_container_width=True
                    )

        # LOGIC: SINGLE SESSION
        else:
            dates = sorted(df['Date'].dt.date.unique(), reverse=True)
            sel_date = st.selectbox("Select Session Date", dates)
            
            session_data = df[df['Date'].dt.date == sel_date].copy()
            
            if session_data.empty:
                st.warning("No data.")
            else:
                # Simple sort by Percentage for single session
                ranking = session_data[['Player', 'Percentage', 'Boards']].sort_values(
                    by='Percentage', ascending=False
                ).reset_index(drop=True)
                
                ranking.index += 1
                ranking['Percentage'] = ranking['Percentage'].map('{:.2f}%'.format)
                
                st.write(f"### Results for {sel_date}")
                st.dataframe(ranking, use_container_width=True)

# --- TAB 2: UPLOAD (Admin Only) ---
if st.session_state["is_admin"]:
    with tab2:
        st.header("Upload XML Result")
        uploaded_file = st.file_uploader("Choose XML File", type=['xml'])
        
        if uploaded_file and st.button("Process & Add"):
            session_date, new_data = parse_xml_usebio(uploaded_file)
            
            if not new_data.empty:
                existing_dates = df['Date'].dt.date.astype(str).unique() if not df.empty else []
                
                if str(session_date) in existing_dates:
                    st.error(f"⚠️ Results for {session_date} are already in the database.")
                else:
                    new_data['Date'] = new_data['Date'].astype(str)
                    if not df.empty:
                        df['Date'] = df['Date'].dt.date.astype(str)
                    
                    updated_df = pd.concat([df, new_data], ignore_index=True)
                    CONN.update(worksheet="Sheet1", data=updated_df)
                    st.success(f"✅ Added {session_date}!")
                    st.balloons()
                    st.cache_data.clear()

# --- TAB 3: ADMIN (Admin Only) ---
if st.session_state["is_admin"]:
    with tab3:
        st.header("Maintenance")
        st.warning("Be careful.")
        
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            if st.button("🗑️ Wipe Database (Reset Columns)"):
                empty_df = pd.DataFrame(columns=['Date', 'Player', 'Percentage', 'Boards'])
                CONN.update(worksheet="Sheet1", data=empty_df)
                st.success("Database reset.")
                st.rerun()
        with col_a2:
            if st.button("🔄 Refresh Cache"):
                st.cache_data.clear()
                st.rerun()
        
        st.write("Current Data Preview:")
        st.dataframe(df)
