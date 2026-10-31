import os
import time
import html
import math
import sqlite3
import urllib.parse
from datetime import datetime, timedelta, timezone

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import folium
from streamlit_folium import st_folium
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from PIL import Image
from dotenv import load_dotenv
from geopy.geocoders import Nominatim

# Load local environment variables
load_dotenv()

# =====================================================================
# 0. LOCAL DATABASE MANAGEMENT LAYER (SQLITE)
# =====================================================================
DB_FILE = "community_hero.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            urgency_tier TEXT,
            structural_analysis TEXT,
            recommended_action TEXT,
            location_name TEXT,
            latitude REAL,
            longitude REAL,
            status TEXT DEFAULT 'ACTIVE',
            upvotes INTEGER DEFAULT 1,
            authority_email TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


init_db()


def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # Radius of Earth in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def ist_now_str():
    """Current time in IST as a string."""
    ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    return ist.strftime("%Y-%m-%d %H:%M:%S")


# =====================================================================
# 1. AGENT BLUEPRINTS & SCHEMAS (WITH FAULT-TOLERANT KEY ROTATION)
# =====================================================================
class TriageReport(BaseModel):
    is_valid_infrastructure_hazard: bool = Field(description="True if asset depicts outdoor public infrastructure damage.")
    rejection_reason: str = Field(description="Reason for validation rejection if false.")
    category: str = Field(description="Must be: 'Roads', 'Waste', 'Utilities', 'Water', or 'Infrastructure'.")
    urgency_tier: str = Field(description="CRITICAL, HIGH, MEDIUM, or LOW.")
    structural_analysis: str = Field(description="Detailed engineering-style description of damage. If citizen audio is provided, translate and merge context here.")
    recommended_action: str = Field(description="Immediate safety containment action.")


class MunicipalDraft(BaseModel):
    authority_email: str = Field(description="Simulated target routing email (e.g., pwd.roads@municipal.gov.in).")
    subject_line: str = Field(description="Actionable subject line for the officer.")
    email_body: str = Field(description="Concise, bulleted official notification text.")


class DeepCommunityHeroEngine:
    def __init__(self):
        # Gather all provided API keys into an indexed fallback array
        self.api_keys = [
            os.getenv("GEMINI_KEY_1"),
            os.getenv("GEMINI_KEY_2"),
            os.getenv("GEMINI_API_KEY"),
        ]
        # Filter out any keys that are empty or None
        self.api_keys = [k for k in self.api_keys if k]

        if not self.api_keys:
            raise RuntimeError("Configuration Error: No valid Gemini API Keys located in environment maps.")

        self.current_key_index = 0
        self.models_pool = ["gemini-2.5-flash"]

        # Initialize the initial client wrapper
        self.client = genai.Client(api_key=self.api_keys[self.current_key_index])

    def _rotate_api_key(self):
        """Swaps the current exhausted key with the next fresh token block."""
        if len(self.api_keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            next_key = self.api_keys[self.current_key_index]
            self.client = genai.Client(api_key=next_key)
            st.toast("🛡️ Quota boundary bypassed. Key pool rotated successfully.", icon="🔄")

    def _generate_with_retry(self, contents, response_schema, prompt_purpose="Agent Execution"):
        last_error = None
        for model_name in self.models_pool:
            retries = 3
            delay = 2
            for attempt in range(retries):
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config={"response_mime_type": "application/json", "response_schema": response_schema},
                    )
                    return response.parsed
                except Exception as e:
                    last_error = e
                    # Catch Quota Exhaustion (429) or Server Limit errors
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        self._rotate_api_key()
                        time.sleep(1)  # Brief pause before immediate auto-retry
                    elif "503" in str(e) or "UNAVAILABLE" in str(e):
                        time.sleep(delay)
                        delay *= 2
                    else:
                        break
        raise RuntimeError(f"Engine failure after maximum pool exhaustion: {last_error}")

    def run_triage_agent(self, image_input, audio_bytes=None) -> TriageReport:
        """Agent 1: Ingests imagery and voice clips to run strict multimodal safety validations."""
        img = Image.open(image_input)
        prompt = """
        You are an expert civil infrastructure inspection and security guardrail agent.
        Analyze the provided image and accompanying voice description asset.

        First, perform a strict validation check to confirm if this asset depicts an actual
        public civilian infrastructure issue/damage. If it is a personal photo, selfie, or irrelevant, flag it immediately.

        If an audio file payload is present, transcribe its contents, process user contexts regardless of native language choice,
        and explicitly integrate that feedback loop context straight into the structural_analysis field.
        """
        contents = [img, prompt]

        if audio_bytes is not None:
            contents.append(
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type="audio/wav",
                )
            )
        return self._generate_with_retry(contents=contents, response_schema=TriageReport, prompt_purpose="Agent 1 (Triage)")

    def run_resolution_agent(self, triage_data: TriageReport, location_name: str, lat: float, lon: float) -> MunicipalDraft:
        prompt = (
            f"Draft an official municipal escalation notice. Category: {triage_data.category} | "
            f"Location: {location_name} | GPS: {lat}, {lon} | Context: {triage_data.structural_analysis}"
        )
        return self._generate_with_retry(contents=prompt, response_schema=MunicipalDraft, prompt_purpose="Agent 3 (Liaison)")

    def check_duplicate_agent(self, category: str, lat: float, lon: float, radius_meters: float = 100.0):
        """Agent 2: Scans database metrics within localized boundaries to block repeating threads."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, latitude, longitude, upvotes, location_name FROM tickets WHERE category = ? AND status = 'ACTIVE'",
            (category,),
        )
        active_tickets = cursor.fetchall()
        conn.close()

        for ticket_id, t_lat, t_lon, current_upvotes, loc_name in active_tickets:
            distance = calculate_haversine_distance(lat, lon, t_lat, t_lon)
            if distance <= radius_meters:
                return {
                    "is_duplicate": True,
                    "ticket_id": ticket_id,
                    "location_name": loc_name,
                    "distance_meters": round(distance, 1),
                    "current_upvotes": current_upvotes,
                }
        return {"is_duplicate": False}


# =====================================================================
# 2. STREAMLIT GLOBAL WORKFLOW PORTAL
# =====================================================================
st.set_page_config(page_title="Community Hero Engine", page_icon="🏙️", layout="centered")

if "admin_authenticated" not in st.session_state:
    st.session_state["admin_authenticated"] = False

app_mode = st.sidebar.selectbox(
    "🔄 Select Operational Portal Interface:",
    ["👤 Citizen Reporting Portal", "🔍 Public Progress Tracker", "🛠️ Municipal Admin Dashboard"],
)

st.markdown("""
    <style>
    .report-title { font-size:34px !important; font-weight: 800; color: #1E3A8A; text-align: center; margin-bottom: 0px; }
    .subtitle { text-align: center; font-size: 15px; color: #4B5563; margin-bottom: 25px; font-style: italic; }
    .action-box { background-color: #1E293B; padding: 20px; border-radius: 12px; border-left: 6px solid #10B981; color: #F8FAFC; margin-top: 15px; }
    .dispatch-btn { display: inline-block; background-color: #10B981; color: white !important; padding: 12px 24px; text-align: center; text-decoration: none; font-size: 16px; font-weight: bold; border-radius: 8px; width: 100%; margin-top: 10px; }
    .stButton > button { width: 100% !important; height: 48px; font-weight: bold !important; }
    </style>
""", unsafe_allow_html=True)


# =====================================================================
# INTERFACE ONE: CITIZEN REPORTING PORTAL
# =====================================================================
if app_mode == "👤 Citizen Reporting Portal":
    st.markdown('<p class="report-title">🏙️ Community Hero</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Secure Hyperlocal Problem Solver — Vibe2Ship Platform</p>', unsafe_allow_html=True)

    loc_html = """
    <script>
    navigator.geolocation.getCurrentPosition(function(position) {
        const lat = position.coords.latitude; const lon = position.coords.longitude;
        const url = new URL(window.parent.location.href);
        if(url.searchParams.get("lat") != lat || url.searchParams.get("lon") != lon) {
            url.searchParams.set("lat", lat); url.searchParams.set("lon", lon);
            window.parent.location.href = url.href;
        }
    });
    </script>
    """
    components.html(loc_html, height=0, width=0)

    query_params = st.query_params
    try:
        lat_fetched = float(query_params.get("lat", 26.8200))
        lon_fetched = float(query_params.get("lon", 75.8100))
    except (TypeError, ValueError):
        lat_fetched, lon_fetched = 26.8200, 75.8100

    @st.cache_data(show_spinner=False)
    def reverse_geocode_location(lat, lon):
        try:
            geolocator = Nominatim(user_agent="vibe2ship_community_hero_agent")
            location = geolocator.reverse((lat, lon), timeout=5)
            if location and "address" in location.raw:
                address = location.raw["address"]
                parts = [p for p in [address.get("road", ""), address.get("suburb", ""), address.get("city", "")] if p]
                if parts:
                    return ", ".join(parts)
            return "Ward 24, Civic Zone"
        except Exception:
            return "Ward 24, Civic Zone"

    resolved_address_name = reverse_geocode_location(lat_fetched, lon_fetched)

    st.markdown("### 📷 Capture & Submit Evidence")
    input_method = st.radio("Select Input Source:", ["📸 Use Live Camera", "🖼️ Choose from Gallery"], horizontal=True)

    final_image_source = None
    if input_method == "📸 Use Live Camera":
        final_image_source = st.camera_input("Snap a live photo of the active issue")
    else:
        final_image_source = st.file_uploader("Select image file from device library", type=["jpg", "jpeg", "png"])

    # --- VOICE INTAKE PIPELINE LAYER (native Streamlit recorder, returns WAV) ---
    st.markdown("🎙️ **Optional: Record a Voice Description**")
    st.caption("Describe the incident out loud in your native tongue (e.g., Hindi, English) to augment tracking context.")
    audio_value = st.audio_input("Click the mic to record voice notes")
    audio_bytes_payload = audio_value.getvalue() if audio_value else None

    st.markdown("---")
    st.markdown("### 📍 Location Verification")
    location_name = st.text_input("Auto-Detected Street Address", value=resolved_address_name)

    submit_btn = st.button("🚀 GENERATE AUTHORITY ESCALATION NOTICE", type="primary")

    if submit_btn and not final_image_source:
        st.warning("📷 Please capture or upload a photo of the issue first.")

    if final_image_source and submit_btn:
        # Clear any previous duplicate prompt when a new submission starts
        st.session_state.pop("dup", None)

        with st.spinner("🛡️ Running Multimodal Engines & Conflict Core..."):
            try:
                engine = DeepCommunityHeroEngine()
                triage_output = engine.run_triage_agent(final_image_source, audio_bytes=audio_bytes_payload)

                if not triage_output.is_valid_infrastructure_hazard:
                    st.error("🚨 **Security Verification Failed: Report Blocked**")
                    st.info(f"📋 **Reason for Rejection:** {triage_output.rejection_reason}")
                else:
                    duplicate_check = engine.check_duplicate_agent(triage_output.category, lat_fetched, lon_fetched)

                    if duplicate_check["is_duplicate"]:
                        # Persist across reruns so the upvote button below actually works
                        st.session_state["dup"] = {
                            "category": triage_output.category,
                            "ticket_id": duplicate_check["ticket_id"],
                            "location_name": duplicate_check["location_name"],
                            "distance_meters": duplicate_check["distance_meters"],
                        }
                    else:
                        letter_output = engine.run_resolution_agent(triage_output, location_name, lat_fetched, lon_fetched)

                        conn = sqlite3.connect(DB_FILE)
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO tickets (category, urgency_tier, structural_analysis, recommended_action, location_name, latitude, longitude, status, authority_email, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
                        """, (
                            triage_output.category,
                            triage_output.urgency_tier,
                            triage_output.structural_analysis,
                            triage_output.recommended_action,
                            location_name,
                            lat_fetched,
                            lon_fetched,
                            letter_output.authority_email,
                            ist_now_str(),
                        ))
                        new_ticket_id = cursor.lastrowid
                        conn.commit()
                        conn.close()

                        st.success("📝 Fresh Incident Successfully Registered in Central Database Core!")

                        st.markdown(f"""
                        <div style="background-color: #0F172A; padding: 15px; border-radius: 8px; border: 2px dashed #34D399; text-align: center; margin-bottom: 20px;">
                            <span style="color: #9CA3AF; font-size: 13px; text-transform: uppercase; font-weight: bold;">Your Unique Reference Number</span>
                            <h2 style="color: #34D399; margin: 5px 0 5px 0; font-size: 32px;">🎫 TICKET #{new_ticket_id}</h2>
                            <p style="color: #E2E8F0; font-size: 14px; margin: 0;">Copy this ID to track live updates inside the <b>Public Progress Tracker</b> tab.</p>
                        </div>
                        """, unsafe_allow_html=True)

                        safe_email = html.escape(letter_output.authority_email)
                        safe_subject = html.escape(letter_output.subject_line)
                        safe_body = html.escape(letter_output.email_body)

                        st.markdown(f"""
                        <div class="action-box">
                            <b style="color: #34D399; font-size: 14px;">📨 TARGET RECIPIENT DEPARTMENT:</b>
                            <div style="background-color: #0F172A; padding: 8px 12px; border-radius: 6px; font-family: monospace; color: #38BDF8; margin-top: 5px; margin-bottom: 15px; border: 1px solid #334155;">
                                {safe_email}
                            </div>

                            <b style="color: #34D399; font-size: 14px;">📌 NOTICE HEADING / SUBJECT:</b>
                            <p style="font-size: 16px; font-weight: bold; color: #FFFFFF; margin-top: 5px; margin-bottom: 15px;">
                                {safe_subject}
                            </p>

                            <b style="color: #34D399; font-size: 14px;">📋 STRUCTURED NOTICE CONTENT:</b>
                            <div style="background-color: #0F172A; padding: 15px; border-radius: 8px; color: #E2E8F0; font-size: 14px; line-height: 1.6; margin-top: 5px; border: 1px solid #334155; white-space: pre-wrap;">{safe_body}</div>
                        </div>
                        """, unsafe_allow_html=True)

                        mailto_url = (
                            f"mailto:{letter_output.authority_email}"
                            f"?subject={urllib.parse.quote(letter_output.subject_line)}"
                            f"&body={urllib.parse.quote(letter_output.email_body)}"
                        )
                        st.markdown(
                            f'<a href="{mailto_url}" class="dispatch-btn" style="text-align: center; color: white !important;">📧 DISPATCH NOTICE TO MUNICIPAL BOARD</a>',
                            unsafe_allow_html=True,
                        )

                        st.markdown("### 🗺️ Verification Coordinate Target")
                        st.map(pd.DataFrame({"lat": [lat_fetched], "lon": [lon_fetched]}), zoom=15)

            except Exception as e:
                st.error(f"Execution Error: {e}")

    # --- DUPLICATE UPVOTE PROMPT (rendered outside the submit block so it survives reruns) ---
    if "dup" in st.session_state:
        d = st.session_state["dup"]
        st.warning("🛑 **Agent 2 (Conflict Resolution): Duplicate Incident Detected!**")
        st.info(
            f"An active **{d['category']}** report already exists **{d['distance_meters']} meters** away "
            f"at *{d['location_name']}*."
        )
        if st.button(f"👍 Upvote Existing Ticket #{d['ticket_id']} (+1 Civic Pressure)", key="dup_upvote_btn"):
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("UPDATE tickets SET upvotes = upvotes + 1 WHERE id = ?", (d["ticket_id"],))
            conn.commit()
            conn.close()
            del st.session_state["dup"]
            st.success("🎉 Upvote cataloged securely! Local database tier synchronized.")


# =====================================================================
# INTERFACE TWO: PUBLIC PROGRESS TRACKER
# =====================================================================
elif app_mode == "🔍 Public Progress Tracker":
    st.markdown('<p class="report-title">🔍 Public Incident Feed & Tracker</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Real-time Transparent Lifecycle Auditing for Smart Wards</p>', unsafe_allow_html=True)

    st.markdown("### 🎫 Track a Specific Ticket")
    search_id = st.text_input("Enter your unique Ticket ID:", placeholder="e.g., 1, 2, 3...")

    if search_id:
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, category, urgency_tier, location_name, status, upvotes, timestamp FROM tickets WHERE id = ?",
                (int(search_id),),
            )
            ticket = cursor.fetchone()
            conn.close()

            if ticket:
                t_id, t_cat, t_urg, t_loc, t_status, t_votes, t_time = ticket
                status_color = "#10B981" if t_status == "CLOSED" else "#3B82F6"
                st.markdown(f"""
                <div style="background-color: #1E293B; padding: 20px; border-radius: 10px; border-left: 6px solid {status_color}; color: #F8FAFC; margin-bottom: 20px;">
                    <h4 style="margin: 0 0 10px 0; color: #FFFFFF;">📋 Ticket #{t_id} — {html.escape(str(t_cat))} Department</h4>
                    <p>📍 <b>Location:</b> {html.escape(str(t_loc))}</p>
                    <p>🕒 <b>Reported On (IST):</b> {t_time}</p>
                    <p>🔥 <b>Community Support:</b> {t_votes} Upvotes</p>
                    <hr style="border-color: #334155; margin: 15px 0;">
                    <p style="font-size: 16px; margin: 0;">⚡ <b>Current Status:</b>
                        <span style="background-color: {status_color}; padding: 4px 10px; border-radius: 4px; font-weight: bold; color: white;">
                            {t_status}
                        </span>
                    </p>
                </div>
                """, unsafe_allow_html=True)

                if t_status == "ACTIVE":
                    st.info("🕒 **Current Progress Stage:** Report Verified & Forwarded to Municipal Board. Awaiting Crew Dispatch.")
                else:
                    st.success("🏁 **Current Progress Stage:** Resolution Finalized! Field Inspection Team verified patchwork completion.")
            else:
                st.error("❌ No matching record located for that Ticket ID sequence.")
        except ValueError:
            st.warning("Please input a valid numeric index character.")

    st.markdown("---")
    st.markdown("### 📰 Live Ward Hazard Activity Feed")

    conn = sqlite3.connect(DB_FILE)
    df_feed = pd.read_sql_query(
        "SELECT id, category, urgency_tier, location_name, upvotes, status FROM tickets WHERE status = 'ACTIVE' ORDER BY upvotes DESC",
        conn,
    )
    conn.close()

    if df_feed.empty:
        st.success("🎉 Incredible! No open infrastructure failures flagged across this zone.")
    else:
        for index, row in df_feed.iterrows():
            with st.container():
                st.markdown(f"""
                <div style="background-color: #111827; padding: 15px; border-radius: 8px; border: 1px solid #374151; margin-bottom: 10px;">
                    <span style="float: right; background-color: #EF4444; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{html.escape(str(row['urgency_tier']))}</span>
                    <strong style="color: #38BDF8; font-size: 16px;">#{row['id']} — Open {html.escape(str(row['category']))} Issue</strong>
                    <p style="margin: 5px 0 10px 0; color: #9CA3AF; font-size: 13px;">📍 {html.escape(str(row['location_name']))}</p>
                </div>
                """, unsafe_allow_html=True)

                if st.button(f"👍 Upvote Ticket #{row['id']} (Current Support: {row['upvotes']})", key=f"feed_upvote_{row['id']}"):
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE tickets SET upvotes = upvotes + 1 WHERE id = ?", (int(row["id"]),))
                    conn.commit()
                    conn.close()
                    st.success("Civic metric successfully registered!")
                    st.rerun()


# =====================================================================
# INTERFACE THREE: MUNICIPAL ADMIN DASHBOARD (SECURED ACCESS LAYER)
# =====================================================================
elif app_mode == "🛠️ Municipal Admin Dashboard":
    st.markdown('<p class="report-title">🛠️ Municipal Command Center</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Official Ward Resolution & Ticket Closure Panel</p>', unsafe_allow_html=True)

    if not st.session_state["admin_authenticated"]:
        st.markdown("### 🔒 Administrative Login Required")
        st.info("💡 **Hackathon Evaluator Notice:** For your convenience, the official department credentials have been securely pre-filled below.")

        admin_email = st.text_input("Registered Department Email:", value="admin@municipal.gov.in")
        admin_password = st.text_input("Password:", value="Vibe2Ship2026", type="password")
        login_btn = st.button("🔓 Authenticate Command Session", type="primary")

        if login_btn:
            if admin_email == "admin@municipal.gov.in" and admin_password == "Vibe2Ship2026":
                st.session_state["admin_authenticated"] = True
                st.success("🔒 Session authorized successfully!")
                st.rerun()
            else:
                st.error("❌ Access Denied: Invalid parameters.")

    else:
        if st.sidebar.button("🔒 Terminate Session (Logout)"):
            st.session_state["admin_authenticated"] = False
            st.rerun()

        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query(
            "SELECT id, category, urgency_tier, location_name, upvotes, status, latitude, longitude, timestamp FROM tickets ORDER BY timestamp DESC",
            conn,
        )
        conn.close()

        if "last_closed_ticket" in st.session_state:
            st.success(f"✅ **Administrative Confirmation:** Ticket #{st.session_state['last_closed_ticket']} has been successfully set to 'CLOSED'. Work order marked as complete.")
            del st.session_state["last_closed_ticket"]

        if df.empty:
            st.info("🍃 No reported civic hazard rows available.")
        else:
            # --- VISUAL ANALYTICS INTERFACE SUB-LAYER ---
            st.markdown("### 📊 Ward Infrastructure Health Metrics")
            col1, col2, col3 = st.columns(3)
            with col1:
                total_active = df[df["status"] == "ACTIVE"].shape[0]
                st.metric(label="⚠️ Open Active Requests", value=total_active)
            with col2:
                total_closed = df[df["status"] == "CLOSED"].shape[0]
                st.metric(label="✅ Resolved Actions", value=total_closed)
            with col3:
                total_upvotes = int(df["upvotes"].sum()) if not df.empty else 0
                st.metric(label="🔥 Citizen Pressure Points", value=total_upvotes)

            st.markdown("---")

            # --- GEO-SPATIAL MAPPING LAYOUT ---
            st.markdown("### 🗺️ Hyperlocal Hotspot Distribution Map")

            map_df = df[["latitude", "longitude", "category", "urgency_tier"]].dropna()
            if not map_df.empty:
                india_center = [22.9734, 78.6568]
                m = folium.Map(location=india_center, zoom_start=5, tiles="Cartodb Positron", attr="CartoDB")

                for _, row in map_df.iterrows():
                    color = "#DC2626" if row["urgency_tier"] == "CRITICAL" else "#F97316" if row["urgency_tier"] == "HIGH" else "#2563EB"
                    folium.CircleMarker(
                        location=[row["latitude"], row["longitude"]],
                        radius=7,
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.85,
                        popup=f"<b>{row['category']}</b> ({row['urgency_tier']})",
                    ).add_to(m)

                st_folium(m, width=700, height=450, returned_objects=[])
            else:
                st.info("No spatial coordinates registered to map.")

            st.markdown("---")
            st.markdown("### 📋 Active Ward Complaints Queue")
            st.dataframe(df, width="stretch", hide_index=True)

            st.markdown("---")
            st.markdown("### ⚡ Fast Resolution Tool")

            active_ids = df[df["status"] == "ACTIVE"]["id"].tolist()

            if not active_ids:
                st.success("✅ Marvelous! All recorded ward infrastructure complaints are marked as CLOSED/RESOLVED.")
            else:
                ticket_to_close = st.selectbox("Select Ticket ID to mark as RESOLVED (Work Completed):", active_ids)
                closure_notes = st.text_area("Administrative Completion Action Log:", placeholder="e.g., Cold-patching asphalt layer finalized.")

                if st.button("🏁 CLOSE TICKET & RESOLVE COMPLAINT", type="primary"):
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE tickets SET status = 'CLOSED' WHERE id = ?", (int(ticket_to_close),))
                    conn.commit()
                    conn.close()

                    st.toast(f"🏁 Ticket #{ticket_to_close} officially marked as CLOSED! Queue updated.", icon="✅")

                    # Short buffer so the admin can read the toast before the UI redraws
                    time.sleep(1.5)
                    st.rerun()