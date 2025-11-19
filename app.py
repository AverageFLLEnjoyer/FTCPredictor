from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import requests
import os

app = Flask(__name__)
CORS(app)

# FTC Scout API configuration
FTC_SCOUT_BASE = "https://api.ftcscout.org/rest/v1"
CURRENT_SEASON = 2025

class FTCStatsCalculator:
    def __init__(self):
        self.cache = {}
    
    def make_api_call(self, endpoint: str):
        """Make API call to FTC Scout"""
        try:
            url = f"{FTC_SCOUT_BASE}/{endpoint.lstrip('/')}"
            print(f"Fetching: {url}")
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"API Error: {e}")
            return None

    def get_event_matches(self, event_code: str):
        """Fetch matches for an event"""
        return self.make_api_call(f"events/{CURRENT_SEASON}/{event_code}/matches") or []

    def get_team_event_stats(self, team_number: str, event_code: str):
        """Get team stats for a specific event"""
        team_events = self.make_api_call(f"teams/{team_number}/events/{CURRENT_SEASON}")
        if team_events:
            for event in team_events:
                if event.get('eventCode') == event_code:
                    return event.get('stats', {})
        return {}

    def calculate_opr(self, event_code: str):
        """Get OPR data for all teams in the event"""
        # First, get all teams in the event
        matches = self.get_event_matches(event_code)
        if not matches:
            return {}
        
        # Get unique teams
        teams = set()
        for match in matches:
            for team_data in match.get('teams', []):
                team_num = str(team_data.get('teamNumber'))
                if team_num:
                    teams.add(team_num)
        
        # Get OPR for each team
        opr_data = {}
        for team in teams:
            stats = self.get_team_event_stats(team, event_code)
            if stats and 'opr' in stats:
                # Get the totalPointsNp OPR value (82.72 for team 14380)
                opr_components = stats['opr']
                total_opr = opr_components.get('totalPointsNp', 0)
                opr_data[team] = total_opr
                print(f"Team {team} OPR: {total_opr}")
            else:
                opr_data[team] = 0
                print(f"Team {team} no OPR data")
        
        return opr_data

calculator = FTCStatsCalculator()

# Serve frontend
@app.route('/')
def serve_frontend():
    try:
        return send_from_directory('static', 'index.html')
    except Exception as e:
        return f"Error loading frontend: {str(e)}", 500

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

# API Routes
@app.route('/api/event/<event_code>/predictions')
def get_event_predictions(event_code: str):
    """Get match predictions for an event"""
    try:
        matches = calculator.get_event_matches(event_code)
        if not matches:
            return jsonify({"error": f"No matches found for event {event_code}"}), 404
        
        print(f"Found {len(matches)} matches for event {event_code}")
        
        # Get OPR data
        opr_data = calculator.calculate_opr(event_code)
        print(f"OPR data: {opr_data}")
        
        predictions = []
        scheduled_matches = 0
        
        for match in matches:
            # Only predict matches without scores
            if not match.get('scores') or not match['scores'].get('red') or not match['scores'].get('blue'):
                scheduled_matches += 1
                red_teams = [str(t['teamNumber']) for t in match.get('teams', []) if t.get('alliance') == 'red']
                blue_teams = [str(t['teamNumber']) for t in match.get('teams', []) if t.get('alliance') == 'blue']
                
                red_opr = sum(opr_data.get(team, 0) for team in red_teams)
                blue_opr = sum(opr_data.get(team, 0) for team in blue_teams)
                
                predictions.append({
                    'match_number': match.get('id'),
                    'red_teams': red_teams,
                    'blue_teams': blue_teams,
                    'red_opr_sum': round(red_opr, 1),
                    'blue_opr_sum': round(blue_opr, 1),
                    'predicted_winner': 'red' if red_opr > blue_opr else 'blue'
                })
        
        return jsonify({
            "event_code": event_code,
            "opr_data": opr_data,
            "predictions": predictions,
            "scheduled_matches": scheduled_matches,
            "total_matches": len(matches)
        })
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/api/team/<team_number>')
def get_team_stats(team_number: str):
    """Get basic team info"""
    try:
        team_info = calculator.make_api_call(f"teams/{team_number}")
        if not team_info:
            return jsonify({"error": "Team not found"}), 404
        
        return jsonify({
            "team_info": team_info,
            "message": f"Team {team_number} data loaded!"
        })
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

# Add a basic health check
@app.route('/api/health')
def health_check():
    return jsonify({"status": "ok", "message": "Server is running!"})

# This is needed for Vercel
app = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
