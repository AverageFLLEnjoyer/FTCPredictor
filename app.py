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

    def get_event_teams(self, event_code: str):
        """Get all teams participating in the event"""
        return self.make_api_call(f"events/{CURRENT_SEASON}/{event_code}/teams") or []

    def calculate_opr(self, event_code: str):
        """Get OPR data for all teams in the event"""
        # Get all teams in the event
        event_teams = self.get_event_teams(event_code)
        if not event_teams:
            return {}
        
        # Get OPR for each team
        opr_data = {}
        for team_data in event_teams:
            team_number = str(team_data.get('teamNumber'))
            stats = team_data.get('stats', {})
            
            # Check if stats exist and have OPR data
            if stats and 'opr' in stats:
                opr_components = stats['opr']
                # Use totalPointsNp if available, otherwise fall back to 0
                total_opr = opr_components.get('totalPointsNp', 0)
                opr_data[team_number] = total_opr
                print(f"Team {team_number} OPR: {total_opr}")
            else:
                # If no OPR data, set to 0
                opr_data[team_number] = 0
                print(f"Team {team_number} no OPR data")
        
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
        print(f"OPR data for {len(opr_data)} teams: {opr_data}")
        
        predictions = []
        scheduled_matches = 0
        
        for match in matches:
            # Only predict matches without scores
            if not match.get('scores') or not match['scores'].get('red') or not match['scores'].get('blue'):
                scheduled_matches += 1
                
                # Extract teams from match data - handle different possible structures
                red_teams = []
                blue_teams = []
                
                # Handle different team data structures
                teams = match.get('teams', [])
                for team in teams:
                    team_number = str(team.get('teamNumber'))
                    alliance = team.get('alliance')
                    if alliance == 'red':
                        red_teams.append(team_number)
                    elif alliance == 'blue':
                        blue_teams.append(team_number)
                
                # Skip matches that don't have teams assigned yet
                if not red_teams or not blue_teams:
                    print(f"Match {match.get('id', 'unknown')} has incomplete teams: red={red_teams}, blue={blue_teams}")
                    continue
                
                # Calculate OPR sums
                red_opr = sum(opr_data.get(team, 0) for team in red_teams)
                blue_opr = sum(opr_data.get(team, 0) for team in blue_teams)
                
                # Determine winner
                if red_opr > blue_opr:
                    predicted_winner = 'red'
                elif blue_opr > red_opr:
                    predicted_winner = 'blue'
                else:
                    predicted_winner = 'tie'
                
                predictions.append({
                    'match_number': match.get('id', 'unknown'),
                    'red_teams': red_teams,
                    'blue_teams': blue_teams,
                    'red_opr_sum': round(red_opr, 1),
                    'blue_opr_sum': round(blue_opr, 1),
                    'predicted_winner': predicted_winner,
                    'confidence': abs(red_opr - blue_opr)
                })
        
        return jsonify({
            "event_code": event_code,
            "opr_data": opr_data,
            "predictions": predictions,
            "scheduled_matches": scheduled_matches,
            "predicted_matches": len(predictions),
            "total_matches": len(matches)
        })
    except Exception as e:
        import traceback
        print(f"Error in predictions: {str(e)}")
        print(traceback.format_exc())
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
