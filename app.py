from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import requests
import numpy as np
import os

app = Flask(__name__, static_folder='static')
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
    
    def calculate_opr(self, matches):
        """Calculate OPR from match data"""
        if not matches:
            return {}
        
        # Get all teams
        teams = set()
        for match in matches:
            for team_data in match.get('teams', []):
                team_num = str(team_data.get('teamNumber'))
                if team_num:
                    teams.add(team_num)
        
        teams = list(teams)
        if not teams:
            return {}
            
        team_to_index = {team: idx for idx, team in enumerate(teams)}
        
        # Build matrices for OPR calculation
        A = []  # Alliance matrix
        b = []  # Score vector
        
        for match in matches:
            if 'scores' not in match:
                continue
                
            for alliance_color in ['red', 'blue']:
                alliance_teams = []
                alliance_score = None
                
                # Find teams for this alliance
                for team_data in match.get('teams', []):
                    if team_data.get('alliance') == alliance_color:
                        team_num = str(team_data.get('teamNumber'))
                        alliance_teams.append(team_num)
                
                # Find score for this alliance
                alliance_scores = match['scores'].get(alliance_color, {})
                if alliance_scores and alliance_scores.get('totalPoints') is not None:
                    alliance_score = alliance_scores['totalPoints']
                
                if alliance_teams and alliance_score is not None:
                    row = [0] * len(teams)
                    for team in alliance_teams:
                        if team in team_to_index:
                            row[team_to_index[team]] = 1
                    A.append(row)
                    b.append(alliance_score)
        
        if len(A) < len(teams):
            return {}
        
        try:
            A_array = np.array(A)
            b_array = np.array(b)
            opr_values = np.linalg.lstsq(A_array, b_array, rcond=None)[0]
            return {team: float(opr_values[idx]) for idx, team in enumerate(teams)}
        except:
            return {}

calculator = FTCStatsCalculator()

# Serve frontend
@app.route('/')
def serve_frontend():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

# API Routes
@app.route('/api/event/<event_code>/predictions')
def get_event_predictions(event_code: str):
    """Get match predictions for an event"""
    matches = calculator.get_event_matches(event_code)
    if not matches:
        return jsonify({"error": f"No matches found for event {event_code}"}), 404
    
    opr_data = calculator.calculate_opr(matches)
    
    predictions = []
    for match in matches:
        # Only predict matches without scores
        if not match.get('scores') or not match['scores'].get('red') or not match['scores'].get('blue'):
            red_teams = [str(t['teamNumber']) for t in match.get('teams', []) if t.get('alliance') == 'red']
            blue_teams = [str(t['teamNumber']) for t in match.get('teams', []) if t.get('alliance') == 'blue']
            
            red_opr = sum(opr_data.get(team, 0) for team in red_teams)
            blue_opr = sum(opr_data.get(team, 0) for team in blue_teams)
            
            predictions.append({
                'match_number': match.get('id'),
                'red_teams': red_teams,
                'blue_teams': blue_teams,
                'red_opr_sum': red_opr,
                'blue_opr_sum': blue_opr,
                'predicted_winner': 'red' if red_opr > blue_opr else 'blue'
            })
    
    return jsonify({
        "event_code": event_code,
        "opr_data": opr_data,
        "predictions": predictions
    })

@app.route('/api/team/<team_number>')
def get_team_stats(team_number: str):
    """Get basic team info"""
    team_info = calculator.make_api_call(f"teams/{team_number}")
    if not team_info:
        return jsonify({"error": "Team not found"}), 404
    
    return jsonify({
        "team_info": team_info,
        "message": "Team data loaded - more features coming soon!"
    })

if __name__ == '__main__':
    # Create static directory if it doesn't exist
    if not os.path.exists('static'):
        os.makedirs('static')
    
    print("🚀 Starting FTC Stats Server...")
    print("📊 Backend API: http://localhost:5000/api/")
    print("🌐 Frontend: http://localhost:5000/")
    print("Press Ctrl+C to stop the server")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
