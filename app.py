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

# --- HTML TABLE GENERATOR (Fixed Indentation & Widths) ---
def render_ranking_table(df, score_col_name="Weighted Average"):
    """Creates a HTML table with tighter columns and no Markdown indentation bugs"""
    
    # CSS: Adjusted widths (Player gets 55%, others get 10-15%)
    html = """
    <style>
        table {width: 60%; border-collapse: collapse; font-family: sans-serif; font-size: 15px;}
        th {background-color: #f0f2f6; padding: 10px 5px; text-align: center; border-bottom: 2px solid #ddd; color: #31333F; font-size: 14px;}
        td {padding: 8px 5px; border-bottom: 1px solid #eee; color: #31333F;}
        tr:hover {background-color: #f9f9f9;}
        
        /* Specific Column Styles */
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
        rank = index # Index starts at 1
        player = row['Player']
        sessions = int(row['Sessions']) if 'Sessions' in row else 1
        boards = int(row['Boards']) if 'Boards' in row else int(row['Total_Boards'])
        
        if 'Weighted_Average' in row:
            score = row['Weighted_Average']
        else:
            score = row['Percentage']
            
        # IMPORTANT: No indentation in this f-string to prevent markdown errors
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
            # Check secrets (ensure 'admin_password' is at TOP of secrets.toml)
            if "admin_password" in st.secrets and entered_password == st.secrets["admin_password"]:
                st.session_state["is_admin"] = True
                st.success("Unlocked")
                st.rerun()
            else:
                st.error("Incorrect Password")
    else:
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
                    
                    # Sort
                    leaderboard = leaderboard.sort_values(by='Weighted_Average', ascending=False).reset_index(drop=True)
                    leaderboard.index += 1
                    
                    # Format
                    leaderboard['Weighted_Average'] = leaderboard['Weighted_Average'].map('{:.2f}%'.format)
                    
                    # RENDER HTML
                    st.markdown(render_ranking_table(leaderboard, "Weighted Average"), unsafe_allow_html=True)

        # --- SINGLE SESSION VIEW ---
        else:
            dates = sorted(df['Date'].dt.date.unique(), reverse=True)
            sel_date = st.selectbox("Select Session Date", dates)
            
            session_data = df[df['Date'].dt.date == sel_date].copy()
            if session_data.empty:
                st.warning("No data.")
            else:
                ranking = session_data[['Player', 'Percentage', 'Boards']].sort_values(by='Percentage', ascending=False).reset_index(drop=True)
                ranking.index += 1
                ranking['Percentage'] = ranking['Percentage'].map('{:.2f}%'.format)
                
                # RENDER HTML
                st.markdown(render_ranking_table(ranking, "Percentage"), unsafe_allow_html=True)

# --- TAB 2: UPLOAD (Admin Only) ---
if st.session_state["is_admin"]:
    with active_tabs[1]:
        st.header("Upload XML Result")
        uploaded_file = st.file_uploader("Choose XML File", type=['xml'])
        
        if uploaded_file and st.button("Process & Update"):
            session_date, new_data = parse_xml_usebio(uploaded_file)
            
            if not new_data.empty:
                session_str = str(session_date)
                
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
                st.success(f"✅ Successfully updated results for {session_date}!")
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

