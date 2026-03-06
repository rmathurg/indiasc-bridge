import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import math
import cv2
import numpy as np
import pytesseract
from PIL import Image
import re

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
    if not isinstance(name_str, str) or not name_str: return None
    if '#' in name_str:
        name_str = name_str.split('#')[0]
    # Remove any accidentally scanned digits at end of name
    clean = name_str.strip().title()
    return clean if clean else None

def extract_data_from_image(image_file, selected_date):
    """
    Uses OCR (Tesseract) to read the Bridge Result Image.
    Target Format: Rank | PairNo | Names | Percentage | MP | Boards
    Example Line: "1 7 Shree G & Ahmed Hasan 63.07% ..."
    """
    try:
        # 1. Convert uploaded file to Image
        img = Image.open(image_file)
        
        # 2. Pre-process for better OCR (Convert to grayscale)
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        
        # 3. Extract Text using Tesseract
        # --psm 6 assumes a single uniform block of text
        text = pytesseract.image_to_string(gray, config='--psm 6')
        
        records = []
        
        # 4. Parse line by line using Regex
        # Looking for: Any digits (Rank) -> Any digits (Pair) -> Text (Names) -> Number followed by %
        # Regex explanation:
        # (?P<rank>\d+)   : Capture Rank digits
        # \s+             : Spaces
        # (?P<pair>\d+)   : Capture Pair Number digits
        # \s+             : Spaces
        # (?P<names>.+?)  : Capture Names (non-greedy)
        # \s+             : Spaces
        # (?P<score>\d+\.\d+)% : Capture Score (digits.digits)%
        pattern = re.compile(r'(?P<rank>\d+)\s+(?P<pair>\d+)\s+(?P<names>.+?)\s+(?P<score>\d+\.\d+)%')

        for line in text.split('\n'):
            match = pattern.search(line)
            if match:
                data = match.groupdict()
                raw_names = data['names']
                pct = float(data['score'])
                
                # Try to find boards at the end of the line (usually last 2 digits)
                # Default to 18 if OCR misses it
                boards = 18
                try:
                    # Look for digits at the very end of the line
                    boards_match = re.search(r'(\d+)\s*$', line)
                    if boards_match:
                        b_val = int(boards_match.group(1))
                        if 10 <= b_val <= 36: # Sanity check for boards
                            boards = b_val
                except: pass

                # Split Names
                p1_name = None
                p2_name = None
                
                if '&' in raw_names:
                    parts = raw_names.split('&')
                    p1_name = parts[0]
                    p2_name = parts[1]
                elif ' and ' in raw_names.lower():
                    parts = raw_names.lower().split(' and ')
                    p1_name = parts[0]
                    p2_name = parts[1]
                else:
                    p1_name = raw_names # Single player?
                
                # Add records
                for p in [p1_name, p2_name]:
                    clean = clean_name(p)
                    if clean:
                        records.append({
                            'Date': str(selected_date),
                            'Player': clean,
                            'Percentage': pct,
                            'Boards': boards
                        })
        
        return pd.DataFrame(records)

    except Exception as e:
        st.error(f"OCR Error: {e}")
        return pd.DataFrame()

# --- HTML TABLE GENERATOR ---
def render_ranking_table(df, score_col_name="Weighted Average"):
    html = """
    <style>
        table {width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 15px;}
        th {background-color: #f0f2f6; padding: 10px 5px; text-align: center; border-bottom: 2px solid #ddd; color: #31333F; font-size: 14px;}
        td {padding: 8px 5px; border-bottom: 1px solid #eee; color: #31333F;}
        tr:hover {background-color: #f9f9f9;}
        .col-rank {text-align: center; width: 5%; font-weight: bold; color: #666;}
        .col-player {text-align: left; width: 50%; font-weight: 500; padding-left: 15px;}
        .col-data {text-align: center; width: 15%;}
    </style>
    <table>
        <thead>
            <tr>
                <th class="col-rank">#</th>
                <th class="col-player" style="text-align: left; padding-left: 15px;">Player</th>
                <th class="col-data">Sessions</th>
                <th class="col-data">Boards</th>
                <th class="col-data">""" + score_col_name + """</th>
            </tr>
        </thead>
        <tbody>
    """
    for index, row in df.iterrows():
        rank = index + 1
        player = row['Player']
        sessions = int(row['Sessions']) if 'Sessions' in row else 1
        boards = int(row['Boards']) if 'Boards' in row else int(row['Total_Boards'])
        score = row['Weighted_Average'] if 'Weighted_Average' in row else row['Percentage']
        html += f"""<tr><td class="col-rank">{rank}</td><td class="col-player">{player}</td><td class="col-data">{sessions}</td><td class="col-data">{boards}</td><td class="col-data" style="font-weight: bold;">{score}</td></tr>"""
    html += "</tbody></table>"
    return html

# --- SIDEBAR LOGIN ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/282/282869.png", width=100)
    st.title("Club Menu")
    
    if "is_admin" not in st.session_state:
        st.session_state["is_admin"] = False

    if not st.session_state["is_admin"]:
        entered_password = st.text_input("Director Password", type="password")
        if entered_password:
            if "admin_password" in st.secrets and entered_password == st.secrets["admin_password"]:
                st.session_state["is_admin"] = True
                st.success("Unlocked")
                st.rerun()
            else:
                st.error("Incorrect Password")
    else:
        st.success("Director Mode Active")
        if st.button("Logout"):
            st.session_state["is_admin"] = False
            st.rerun()

# --- DATA LOADING ---
try:
    df = CONN.read(worksheet="Sheet1", ttl=0)
    if df.empty:
        df = pd.DataFrame(columns=['Date', 'Player', 'Percentage', 'Boards'])
    else:
        df['Date'] = pd.to_datetime(df['Date'])
        df['Percentage'] = pd.to_numeric(df['Percentage'], errors='coerce').fillna(0)
        df['Boards'] = pd.to_numeric(df['Boards'], errors='coerce').fillna(0)
except Exception:
    df = pd.DataFrame(columns=['Date', 'Player', 'Percentage', 'Boards'])

# --- MAIN LAYOUT ---
st.title("♠️ ICC Bridge Club Rankings")

tabs = ["🏆 Leaderboards"]
if st.session_state["is_admin"]:
    tabs.append("📤 Director Upload")
    tabs.append("⚙️ Database Admin")

active_tabs = st.tabs(tabs)

# --- TAB 1: LEADERBOARDS (Public) ---
with active_tabs[0]:
    if df.empty:
        st.info("No rankings available yet.")
    else:
        view_mode = st.radio("Select View:", ["Monthly Accumulator", "Single Session"], horizontal=True)
        st.divider()

        # --- MONTHLY VIEW ---
        if view_mode == "Monthly Accumulator":
            col1, col2 = st.columns(2)
            years = sorted(df['Date'].dt.year.unique(), reverse=True)
            sel_year = col1.selectbox("Year", years)
            
            df_year = df[df['Date'].dt.year == sel_year]
            if df_year.empty:
                st.warning("No data.")
            else:
                months = sorted(df_year['Date'].dt.month_name().unique(), 
                              key=lambda m: datetime.strptime(m, "%B").month)
                sel_month = col2.selectbox("Month", months, index=len(months)-1)
                
                mask = (df['Date'].dt.year == sel_year) & (df['Date'].dt.month_name() == sel_month)
                monthly_data = df[mask].copy()
                
                if monthly_data.empty:
                    st.warning("No data.")
                else:
                    monthly_data['Score_Mass'] = monthly_data['Percentage'] * monthly_data['Boards']
                    
                    leaderboard = monthly_data.groupby('Player').agg(
                        Sessions=('Date', 'nunique'),
                        Total_Mass=('Score_Mass', 'sum'),
                        Total_Boards=('Boards', 'sum')
                    ).reset_index()
                    
                    leaderboard = leaderboard[leaderboard['Total_Boards'] > 0]
                    leaderboard['Weighted_Average'] = leaderboard['Total_Mass'] / leaderboard['Total_Boards']
                    
                    total_sessions_in_month = monthly_data['Date'].nunique()
                    min_req = math.ceil(total_sessions_in_month / 2)
                    
                    if not st.session_state["is_admin"]:
                        # PUBLIC
                        qualified_leaderboard = leaderboard[leaderboard['Sessions'] >= min_req]
                        qualified_leaderboard = qualified_leaderboard.sort_values(by='Weighted_Average', ascending=False).reset_index(drop=True)
                        final_display = qualified_leaderboard.head(10)
                        st.caption(f"**Ranking Rules:** Must play {min_req}+ sessions. Showing Top 10.")
                        if final_display.empty:
                            st.info("No players meet attendance requirements yet.")
                    else:
                        # DIRECTOR
                        leaderboard = leaderboard.sort_values(by='Weighted_Average', ascending=False).reset_index(drop=True)
                        final_display = leaderboard
                        st.caption(f"**Director Mode:** Showing all players.")

                    final_display['Weighted_Average'] = final_display['Weighted_Average'].map('{:.2f}%'.format)
                    st.markdown(render_ranking_table(final_display, "Weighted Average"), unsafe_allow_html=True)

        # --- SINGLE SESSION VIEW ---
        else:
            dates = sorted(df['Date'].dt.date.unique(), reverse=True)
            sel_date = st.selectbox("Select Session Date", dates)
            
            session_data = df[df['Date'].dt.date == sel_date].copy()
            if session_data.empty:
                st.warning("No data.")
            else:
                ranking = session_data[['Player', 'Percentage', 'Boards']].sort_values(by='Percentage', ascending=False).reset_index(drop=True)
                ranking['Percentage'] = ranking['Percentage'].map('{:.2f}%'.format)
                st.markdown(render_ranking_table(ranking, "Percentage"), unsafe_allow_html=True)

# --- TAB 2: UPLOAD (Admin Only) ---
if st.session_state["is_admin"]:
    with active_tabs[1]:
        st.header("Upload Results Image")
        st.info("Upload the Score Table image (PNG/JPG). The app will try to read the names and scores.")
        
        # 1. DATE PICKER
        upload_date = st.date_input("Session Date", datetime.today())
        
        # 2. FILE UPLOADER (Images only)
        uploaded_file = st.file_uploader("Choose Image File", type=['png', 'jpg', 'jpeg'])
        
        if uploaded_file and st.button("Scan & Update"):
            with st.spinner("Scanning image... this takes a few seconds..."):
                new_data = extract_data_from_image(uploaded_file, upload_date)
            
            if new_data.empty:
                st.error("Could not read data! Please ensure image is clear and contains a table.")
            else:
                st.write("### Preview of Scanned Data")
                st.dataframe(new_data)
                
                if st.button("Looks Good - Save to Database"):
                    session_str = str(upload_date)
                    
                    # OVERWRITE LOGIC
                    existing_dates = df['Date'].dt.date.astype(str).unique() if not df.empty else []
                    
                    if session_str in existing_dates:
                        st.warning(f"⚠️ Overwriting existing results for {session_str}...")
                        df = df[df['Date'].dt.date.astype(str) != session_str]
                    
                    new_data['Date'] = new_data['Date'].astype(str)
                    if not df.empty:
                        df['Date'] = df['Date'].dt.date.astype(str)
                    
                    updated_df = pd.concat([df, new_data], ignore_index=True)
                    
                    CONN.update(worksheet="Sheet1", data=updated_df)
                    st.success(f"✅ Successfully updated results for {upload_date}!")
                    st.balloons()
                    st.cache_data.clear()

# --- TAB 3: ADMIN (Admin Only) ---
if st.session_state["is_admin"]:
    with active_tabs[2]:
        st.header("Maintenance")
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            if st.button("🗑️ Wipe Entire Database"):
                empty_df = pd.DataFrame(columns=['Date', 'Player', 'Percentage', 'Boards'])
                CONN.update(worksheet="Sheet1", data=empty_df)
                st.success("Database reset.")
                st.rerun()
        with col_a2:
            st.write("Current Database Preview:")
            st.dataframe(df)
