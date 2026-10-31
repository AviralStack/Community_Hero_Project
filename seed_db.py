import sqlite3

DB_FILE = "community_hero.db"

def seed_nationwide_data():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Comprehensive, realistic nationwide mock dataset spanning the true sovereign borders of India
    mock_tickets = [
        # --- FAR NORTH (Jammu & Kashmir & Ladakh) ---
        (
            'Utilities', 'HIGH', 
            'Public water distribution line fracture causing heavy ice slick hazard on the road alignment during freezing temperatures.', 
            'Deploy mechanical municipal warming crew to thaw surface and seal line joints.', 
            'Lal Chowk, Srinagar, Jammu and Kashmir, India', 34.0837, 74.7973, 'ACTIVE', 38, 'smc.water@municipal.gov.in'
        ),
        (
            'Infrastructure', 'CRITICAL', 
            'Severe rockfall accumulation blocking the main highway link corridor, obstructing heavy utility vehicles.', 
            'Dispatch heavy border-clearance earthmovers for immediate route clearing.', 
            'Main Market Road, Leh, Ladakh, India', 34.1642, 77.5847, 'ACTIVE', 52, 'ladakh.pwd@municipal.gov.in'
        ),
        
        # --- NORTH & WEST ---
        (
            'Roads', 'CRITICAL', 
            'Severe asphalt disintegration and large deep potholes forming across the main arterial lane near Connaught Place.', 
            'Deploy emergency road maintenance crew for immediate cold-mix filling.', 
            'Connaught Place, New Delhi, Delhi, India', 28.6304, 77.2177, 'ACTIVE', 24, 'ndmc.roads@municipal.gov.in'
        ),
        (
            'Roads', 'HIGH', 
            'Severe localized asphalt distress forming a large, deep pothole currently filled with rainwater near Chauradia Petrol Pump.', 
            'Deploy road crew for cold-mix asphalt patch filling immediately.', 
            'Sanganer area, Jagatpura, Jaipur, Rajasthan, India', 26.8200, 75.8100, 'ACTIVE', 14, 'pwd.roadrepair@jaipur.gov.in'
        ),
        (
            'Waste', 'CRITICAL', 
            'Massive commercial solid waste and garbage overflow blocking the pedestrian sidewalk near Andheri station.', 
            'Dispatch a heavy skip loader and cleanup crew for immediate sanitation clearing.', 
            'Andheri West, Mumbai, Maharashtra, India', 19.1197, 72.8468, 'ACTIVE', 42, 'bmc.sanitation@municipal.gov.in'
        ),
        
        # --- SOUTH ---
        (
            'Utilities', 'HIGH', 
            'Public distribution transformer unit panel doors damaged with exposed high-voltage wiring near a tech park corridor.', 
            'Alert grid safety dispatch teams to isolate circuits and secure the structural enclosure.', 
            'Whitefield, Bengaluru, Karnataka, India', 12.9698, 77.7500, 'ACTIVE', 19, 'bescom.safety@municipal.gov.in'
        ),
        (
            'Water', 'MEDIUM', 
            'Subsurface water main joint rupture causing clean freshwater accumulation and flooding along the access road entry.', 
            'Isolate water district zone valves and weld structural pipeline casing.', 
            'Adyar, Chennai, Tamil Nadu, India', 13.0033, 80.2550, 'CLOSED', 5, 'cmwssb.repairs@municipal.gov.in'
        ),
        
        # --- EAST & NORTHEAST ---
        (
            'Infrastructure', 'HIGH', 
            'Structural concrete deterioration and rebar exposure on a public pedestrian footbridge layout.', 
            'Restrict heavy access loads and execute immediate structural structural concrete reinforcement patching.', 
            'Salt Lake Sector V, Kolkata, West Bengal, India', 22.5735, 88.4331, 'ACTIVE', 31, 'kmc.engineering@municipal.gov.in'
        ),
        (
            'Water', 'HIGH', 
            'Drainage system overflow causing localized urban waterlogging along major commercial market streets.', 
            'Deploy municipal suction pump units and clear blockages from drainage mains.', 
            'Ganeshguri, Guwahati, Assam, India', 26.1534, 91.7878, 'ACTIVE', 27, 'gmc.drainage@municipal.gov.in'
        )
    ]
    
    # Wipe old records to prevent overlapping entries
    cursor.execute("DELETE FROM tickets")
    
    # Ingest the fresh data rows safely
    cursor.executemany("""
        INSERT INTO tickets (
            category, urgency_tier, structural_analysis, recommended_action, 
            location_name, latitude, longitude, status, upvotes, authority_email
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, mock_tickets)
    
    conn.commit()
    print(f"🚀 Sovereign Nationwide Grid Achieved! Injected {len(mock_tickets)} records up to Srinagar & Leh into '{DB_FILE}'!")
    conn.close()

if __name__ == "__main__":
    seed_nationwide_data()