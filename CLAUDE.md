# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
Community Hero is a Streamlit-based civic infrastructure reporting platform that allows citizens to submit geotagged photos of infrastructure issues (roads, waste, utilities, water, infrastructure) with optional voice descriptions. The system uses Google's Gemini AI for multimodal analysis, duplicate detection via Haversine distance, and generates municipal escalation notices.

## Key Commands

### Running the Application
```bash
streamlit run app.py
```
The app runs on port 8501 by default. Access the citizen portal, public tracker, or admin dashboard via sidebar navigation.

### Database Operations
```bash
# Seed the database with sample nationwide data
python seed_db.py
```
The SQLite database `community_hero.db` is auto-initialized on first run.

### Environment Setup
```bash
# System dependencies (required for audio processing)
sudo apt update && sudo apt install -y ffmpeg portaudio19-dev build-essential

# Python dependencies
pip install -r requirements.txt
```

## Architecture

### Single-File Application (`app.py`)
The entire application is contained in `app.py` with three distinct portals:
1. **Citizen Reporting Portal** - Image/audio upload, AI triage, duplicate checking, ticket creation
2. **Public Progress Tracker** - Ticket search and live feed with upvoting
3. **Municipal Admin Dashboard** - Secure login, analytics, map visualization, ticket closure

### Core Components

#### Database Layer
- SQLite database with single `tickets` table
- Schema includes: id, category, urgency_tier, structural_analysis, recommended_action, location_name, latitude, longitude, status, upvotes, authority_email, timestamp
- Direct SQLite connections throughout (no ORM)

#### AI Engine (`DeepCommunityHeroEngine`)
- **Key Rotation**: Multiple Gemini API keys (`GEMINI_KEY_1`, `GEMINI_KEY_2`, `GEMINI_API_KEY`) with automatic fallback on quota exhaustion
- **Triage Agent**: Multimodal analysis of images + audio, outputs `TriageReport` (Pydantic model)
- **Resolution Agent**: Generates `MunicipalDraft` escalation notices
- **Duplicate Agent**: Haversine distance calculation (100m radius) to detect similar active tickets

#### Geospatial Features
- Browser geolocation API for automatic coordinates
- Geopy Nominatim for reverse geocoding
- Folium maps for hotspot visualization in admin dashboard
- Haversine formula for distance calculations between tickets

#### Audio Processing
- Streamlit audio recorder component
- Pydub/FFmpeg for WAV export
- Audio bytes sent directly to Gemini API for transcription/analysis

### External Services
- **Google Gemini API** (`gemini-2.5-flash` model) for AI analysis
- **Nominatim API** (OpenStreetMap) for geocoding
- **Streamlit Components**: camera input, file uploader, audio recorder, JS eval for geolocation

### Data Flow
1. Citizen uploads image + optional audio → AI validates infrastructure hazard
2. System checks for duplicates within 100m radius using Haversine formula
3. If unique: AI generates escalation notice → ticket created in database
4. Admin can view analytics, map hotspots, and close resolved tickets

### Authentication
- Admin dashboard uses hardcoded credentials (`admin@municipal.gov.in` / `Vibe2Ship2026`)
- Session state manages authentication flag

## Development Notes

### Database Schema Changes
The `init_db()` function runs on every app startup and creates the table if missing. Schema changes should be made here.

### AI Prompt Engineering
The `TriageReport` and `MunicipalDraft` Pydantic models define the structured output format. Modifying these fields changes what the AI extracts from images/audio.

### Duplicate Detection Radius
The 100-meter threshold for duplicate detection is hardcoded in `check_duplicate_agent()`. Adjust `radius_meters` parameter to change sensitivity.

### Timezone Handling
Timestamps are manually converted to IST (UTC+5:30) in the ticket creation flow.

### Dependencies
Key packages: Streamlit, Google GenAI SDK, Pydantic, SQLite3, Pydub, Geopy, Folium, Streamlit components for audio/JS evaluation.