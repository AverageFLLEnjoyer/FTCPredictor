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
        matches = self.get_event_matches(event_code)
        if not matches:
            return {}
        
        teams = set()
        for match in matches:
            for team_data in match.get('teams', []):
                team_num = str(team_data.get('teamNumber'))
                if team_num:
                    teams.add(team_num)
        
        opr_data = {}
        for team in teams:
            stats = self.get_team_event_stats(team, event_code)
            if stats and 'opr' in stats:
                opr_components = stats['opr']
                total_opr = opr_components.get('totalPointsNp', 0)
                opr_data[team] = total_opr
                print(f"Team {team} OPR: {total_opr}")
            else:
                opr_data[team] = 0
                print(f"Team {team} no OPR data")
        
        return opr_data

    def calculate_rp_simple(self, event_code: str):
        """Simple RP calculation using team event stats"""
        matches = self.get_event_matches(event_code)
        if not matches:
            return {}
        
        teams = set()
        for match in matches:
            for team_data in match.get('teams', []):
                team_num = str(team_data.get('teamNumber'))
                if team_num:
                    teams.add(team_num)
        
        rp_data = {}
        for team in teams:
            stats = self.get_team_event_stats(team, event_code)
            if stats and 'avg' in stats:
                avg_stats = stats['avg']
                # Get the actual RP averages from the stats
                movement_avg = avg_stats.get('movementRp', 0)
                goal_avg = avg_stats.get('goalRp', 0) 
                pattern_avg = avg_stats.get('patternRp', 0)
                
                rp_data[team] = {
                    'movement_rp': movement_avg > 0.5,  # If average > 0.5, they usually get it
                    'movement_avg': movement_avg,
                    'goal_rp': goal_avg > 0.5,
                    'goal_avg': goal_avg,
                    'pattern_rp': pattern_avg > 0.5,
                    'pattern_avg': pattern_avg
                }
                print(f"Team {team} RP: movement={movement_avg:.2f}, goal={goal_avg:.2f}, pattern={pattern_avg:.2f}")
            else:
                # No stats available
                rp_data[team] = {
                    'movement_rp': False,
                    'movement_avg': 0,
                    'goal_rp': False, 
                    'goal_avg': 0,
                    'pattern_rp': False,
                    'pattern_avg': 0
                }
                print(f"Team {team} no RP data")
        
        return rp_data

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
        
        # Get RP data
        rp_data = calculator.calculate_rp_simple(event_code)
        
        predictions = []
        scheduled_matches = 0
        
        for match in matches:
            if not match.get('scores') or not match['scores'].get('red') or not match['scores'].get('blue'):
                scheduled_matches += 1
                red_teams = [str(t['teamNumber']) for t in match.get('teams', []) if t.get('alliance') == 'Red']
                blue_teams = [str(t['teamNumber']) for t in match.get('teams', []) if t.get('alliance') == 'Blue']
                
                # Calculate OPR sums
                red_opr = sum(opr_data.get(team, 0) for team in red_teams)
                blue_opr = sum(opr_data.get(team, 0) for team in blue_teams)
                
                # Calculate confidence
                total_opr = red_opr + blue_opr
                if total_opr > 0:
                    confidence = (abs(red_opr - blue_opr) / total_opr) * 100
                else:
                    confidence = 0
                
                # Simple RP prediction for alliance
                def predict_alliance_rps(teams):
                    if len(teams) != 2:
                        return {'movement_rp': False, 'goal_rp': False, 'pattern_rp': False}
                    
                    # Get RP data for both teams
                    team1_rp = rp_data.get(teams[0], {})
                    team2_rp = rp_data.get(teams[1], {})
                    
                    # Average the RP values and check if > 0.5
                    movement_avg = (team1_rp.get('movement_avg', 0) + team2_rp.get('movement_avg', 0)) / 2
                    goal_avg = (team1_rp.get('goal_avg', 0) + team2_rp.get('goal_avg', 0)) / 2
                    pattern_avg = (team1_rp.get('pattern_avg', 0) + team2_rp.get('pattern_avg', 0)) / 2
                    
                    return {
                        'movement_rp': movement_avg > 0.5,
                        'movement_avg': round(movement_avg * 100),
                        'goal_rp': goal_avg > 0.5,
                        'goal_avg': round(goal_avg * 100),
                        'pattern_rp': pattern_avg > 0.5,
                        'pattern_avg': round(pattern_avg * 100)
                    }
                
                red_rps = predict_alliance_rps(red_teams)
                blue_rps = predict_alliance_rps(blue_teams)
                
                predicted_winner = 'red' if red_opr > blue_opr else 'blue'
                winner_confidence = min(100, max(50, round(confidence + 50)))
                
                predictions.append({
                    'match_number': match.get('id'),
                    'red_teams': red_teams,
                    'blue_teams': blue_teams,
                    'red_opr_sum': round(red_opr, 1),
                    'blue_opr_sum': round(blue_opr, 1),
                    'predicted_winner': predicted_winner,
                    'confidence_percentage': round(confidence, 1),
                    'winner_confidence': winner_confidence,
                    'red_rp_predictions': red_rps,
                    'blue_rp_predictions': blue_rps
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

@app.route('/api/health')
def health_check():
    return jsonify({"status": "ok", "message": "Server is running!"})

app = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
