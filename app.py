import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import math
import io

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
    # Remove # codes or numbers that might accidentally stick to names
    if '#' in name_str:
        name_str = name_str.split('#')[0]
    clean = name_str.strip().title()
    return clean if clean else None

def parse_csv_text(csv_text, selected_date):
    """
    Parses CSV text directly from the text area.
    Robustly handles splitting names with '&'.
    """
    try:
        # Convert string to a virtual file
        csv_file = io.StringIO(csv_text)
        df_input = pd.read_csv(csv_file)
        
        # Normalize headers to lowercase/strip
        df_input.columns = [c.strip().lower() for c in df_input.columns]
        
        # Identify columns
        # FIX: We removed 'pair' from the combined search so it doesn't grab the Pair Number column
        col_map = {
            'p1': next((c for c in df_input.columns if 'player 1' in c or 'n/s' in c), None),
            'p2': next((c for c in df_input.columns if 'player 2' in c or 'e/w' in c), None),
            'combined': next((c for c in df_input.columns if 'names' in c or 'players' in c or 'partners' in c), None),
            'score': next((c for c in df_input.columns if 'percentage' in c or 'score' in c or 'average' in c or '%' in c), None),
            'boards': next((c for c in df_input.columns if 'board' in c or 'bds' in c), None)
        }
        
        if not col_map['score']:
            st.error("Error: Could not find a 'Percentage' column. Please check the CSV format.")
            return pd.DataFrame()

        records = []
        
        for _, row in df_input.iterrows():
            try:
                # 1. Get Score
                raw_score = str(row[col_map['score']]).replace('%', '').strip()
                pct = float(raw_score)
                
                # 2. Get Boards (Default 18)
                boards = 18
                if col_map['boards'] and pd.notna(row[col_map['boards']]):
                    try:
                        boards = int(row[col_map['boards']])
                    except: pass
                
                # 3. Get Players
                p1_name = None
                p2_name = None
                
                # Logic: If we found a "Names" column, use it and split by &
                if col_map['combined']:
                    raw_name = str(row[col_map['combined']])
                    # Clean up common separators
                    if '&' in raw_name:
                        parts = raw_name.split('&')
                        p1_name = parts[0]
                        p2_name = parts[1] if len(parts) > 1 else None
                    elif ' and ' in raw_name.lower():
                        parts = raw_name.lower().split(' and ')
                        p1_name = parts[0]
                        p2_name = parts[1] if len(parts) > 1 else None
                    else:
                        p1_name = raw_name 
                
                # Logic: If we have Player 1 / Player 2 columns
                elif col_map['p1']:
                    p1_name = row[col_map['p1']]
                    if col_map['p2']: 
                        p2_name = row[col_map['p2']]
                
                # 4. Add to records
                for p in [p1_name, p2_name]:
                    clean = clean_name(p)
                    # Ignore empty names or placeholders like 'Sitout'
                    if clean and "sitout" not in clean.lower():
                        records.append({
                            'Date': str(selected_date),
                            'Player': clean,
                            'Percentage': pct,
                            'Boards': boards
                        })
                        
            except Exception as e:
                continue
                
        return pd.DataFrame(records)

    except Exception as e:
        st.error(f"Parsing Error: {e}")
        return pd.DataFrame()

# --- HTML TABLE GENERATOR ---
def render_ranking_table(df, score_col_name="Weighted Average"):
    html = """
    <style>
        table {width: 60%; border-collapse: collapse; font-family: sans-serif; font-size: 15px;}
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
                    # CALCULATION
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
        st.header("Upload Results")
        st.info("Format: Paste CSV data extracted from your image.")
        
        # 1. DATE PICKER
        upload_date = st.date_input("Session Date", datetime.today())
        
        # 2. TEXT AREA FOR COPY-PASTE
        csv_text = st.text_area("Paste CSV Text Here", height=200, placeholder="Pair, Names, Percentage, Boards\n1, John & Jane, 55.5, 18...")
        
        if st.button("Process & Update"):
            if not csv_text:
                st.error("Please paste CSV text first.")
            else:
                new_data = parse_csv_text(csv_text, upload_date)
                
                if not new_data.empty:
                    session_str = str(upload_date)
                    
                    # OVERWRITE LOGIC
                    existing_dates = df['Date'].dt.date.astype(str).unique() if not df.empty else []
                    
                    if session_str in existing_dates:
                        st.warning(f"⚠️ Results for {session_str} already exist. Overwriting...")
                        df = df[df['Date'].dt.date.astype(str) != session_str]
                    
                    new_data['Date'] = new_data['Date'].astype(str)
                    if not df.empty:
                        df['Date'] = df['Date'].dt.date.astype(str)
                    
                    updated_df = pd.concat([df, new_data], ignore_index=True)
                    
                    CONN.update(worksheet="Sheet1", data=updated_df)
                    st.success(f"✅ Successfully updated results for {upload_date}!")
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

