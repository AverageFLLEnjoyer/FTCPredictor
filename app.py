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
        try:
            # Use the correct API endpoint
            team_events = self.make_api_call(f"teams/{team_number}/events/{CURRENT_SEASON}")
            
            if team_events:
                # Handle both list and dict responses
                events_list = team_events if isinstance(team_events, list) else [team_events]
                
                for event in events_list:
                    if event.get('eventCode') == event_code:
                        stats = event.get('stats')
                        if stats:  # Check if stats exists and is not None
                            return stats
                        else:
                            # If stats is None, return empty dict
                            return {}
            
            return {}
        except Exception as e:
            print(f"Error getting team event stats: {e}")
            return {}

    def get_team_season_stats(self, team_number: str):
        """Get all events for a team in current season to find highest OPR"""
        team_events = self.make_api_call(f"teams/{team_number}/events/{CURRENT_SEASON}")
        if not team_events:
            return None
        
        highest_opr = 0
        highest_event = None
        
        # Handle both list and dict responses
        events_list = team_events if isinstance(team_events, list) else [team_events]
        
        for event in events_list:
            stats = event.get('stats', {})
            if stats and 'opr' in stats:
                opr_components = stats['opr']
                total_opr = opr_components.get('totalPointsNp', 0)
                if total_opr > highest_opr:
                    highest_opr = total_opr
                    highest_event = event.get('eventCode', 'Unknown')
        
        return {
            'highest_opr': highest_opr,
            'event_achieved': highest_event,
            'total_events': len(events_list)
        }

    def calculate_opr(self, event_code: str, use_highest_season_opr: bool = False):
        """Get OPR data for all teams in the event"""
        matches = self.get_event_matches(event_code)
        if not matches:
            return {}, {}
        
        teams = set()
        for match in matches:
            # Skip non-qual matches (match numbers > 10000)
            match_id = match.get('id', 0)            
            for team_data in match.get('teams', []):
                team_num = str(team_data.get('teamNumber'))
                if team_num:
                    teams.add(team_num)
        
        opr_data = {}
        highest_opr_info = {}
        
        for team in teams:
            if use_highest_season_opr:
                # Get highest OPR from season
                season_stats = self.get_team_season_stats(team)
                if season_stats:
                    opr_data[team] = season_stats['highest_opr']
                    highest_opr_info[team] = {
                        'opr': season_stats['highest_opr'],
                        'event_achieved': season_stats['event_achieved']
                    }
                else:
                    opr_data[team] = 0
                    highest_opr_info[team] = {
                        'opr': 0,
                        'event_achieved': 'N/A'
                    }
            else:
                # Use current event OPR
                stats = self.get_team_event_stats(team, event_code)
                if stats and 'opr' in stats:
                    opr_components = stats['opr']
                    # Get the totalPointsNp value which is the OPR
                    total_opr = opr_components.get('totalPointsNp', 0)
                    opr_data[team] = total_opr
                else:
                    opr_data[team] = 0
        
        return opr_data, highest_opr_info
    
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
                movement_avg = avg_stats.get('movementRp', 0) * 100
                goal_avg = avg_stats.get('goalRp', 0) * 100
                pattern_avg = avg_stats.get('patternRp', 0) * 100
                
                rp_data[team] = {
                    'movement_rp': movement_avg > 50,
                    'movement_avg': round(movement_avg),
                    'goal_rp': goal_avg > 50,
                    'goal_avg': round(goal_avg),
                    'pattern_rp': pattern_avg > 50,
                    'pattern_avg': round(pattern_avg),
                    'movement_prob': round(movement_avg),  # Add these for compatibility
                    'goal_prob': round(goal_avg),
                    'pattern_prob': round(pattern_avg)
                }
            else:
                # Try to get from different structure if 'avg' doesn't exist
                if stats and 'movementRp' in stats:
                    movement_avg = stats.get('movementRp', 0) * 100
                    goal_avg = stats.get('goalRp', 0) * 100
                    pattern_avg = stats.get('patternRp', 0) * 100
                    
                    rp_data[team] = {
                        'movement_rp': movement_avg > 50,
                        'movement_avg': round(movement_avg),
                        'goal_rp': goal_avg > 50,
                        'goal_avg': round(goal_avg),
                        'pattern_rp': pattern_avg > 50,
                        'pattern_avg': round(pattern_avg),
                        'movement_prob': round(movement_avg),
                        'goal_prob': round(goal_avg),
                        'pattern_prob': round(pattern_avg)
                    }
                else:
                    rp_data[team] = {
                        'movement_rp': False,
                        'movement_avg': 0,
                        'goal_rp': False, 
                        'goal_avg': 0,
                        'pattern_rp': False,
                        'pattern_avg': 0,
                        'movement_prob': 0,
                        'goal_prob': 0,
                        'pattern_prob': 0
                    }
        
        return rp_data

    def calculate_leaderboard(self, event_code: str, opr_data: dict, rp_data: dict, matches: list):
        """Calculate leaderboard based on event status - ONLY QUAL MATCHES"""
        teams = {}
        
        # Initialize team data structure
        for team in opr_data.keys():
            teams[team] = {
                'team_number': team,
                'total_rp': 0,
                'total_wins': 0,
                'total_matches': 0,
                'scores': [],
                'is_predicted': False  # Track if this is actual or predicted
            }
        
        # Process all matches (but skip non-qual matches)
        for match in matches:
            # Skip non-qual matches (match numbers > 10000) - ONLY for leaderboard
            match_id = match.get('id', 0)
            if isinstance(match_id, str):
                try:
                    match_num = int(match_id)
                    if match_num > 10000:
                        continue  # Skip non-qual matches for leaderboard only
                except:
                    # If can't parse as int, assume it's a qual match
                    pass                        
            red_teams = [str(t['teamNumber']) for t in match.get('teams', []) if t.get('alliance') == 'Red']
            blue_teams = [str(t['teamNumber']) for t in match.get('teams', []) if t.get('alliance') == 'Blue']
            
            # Skip if not a proper match (should have 2 teams per alliance)
            if len(red_teams) != 2 or len(blue_teams) != 2:
                continue
            
            # Check if match has been played
            if match.get('scores') and match['scores'].get('red') and match['scores'].get('blue'):
                # ACTUAL MATCH RESULTS
                red_score = match['scores']['red'].get('totalPoints', 0)
                blue_score = match['scores']['blue'].get('totalPoints', 0)
                actual_winner = 'red' if red_score > blue_score else 'blue' if blue_score > red_score else 'tie'
                
                # Calculate actual RPs from scores (FTC 2025 rules)
                red_rp_total = 0
                blue_rp_total = 0
                
                # Movement RP (from scores) - +1 RP
                red_movement = match['scores']['red'].get('movementBonus', False)
                blue_movement = match['scores']['blue'].get('movementBonus', False)
                if red_movement: red_rp_total += 1
                if blue_movement: blue_rp_total += 1
                
                # Goal RP (from scores) - +1 RP
                red_goal = match['scores']['red'].get('goalBonus', False)
                blue_goal = match['scores']['blue'].get('goalBonus', False)
                if red_goal: red_rp_total += 1
                if blue_goal: blue_rp_total += 1
                
                # Pattern RP (from scores) - +1 RP
                red_pattern = match['scores']['red'].get('patternBonus', False)
                blue_pattern = match['scores']['blue'].get('patternBonus', False)
                if red_pattern: red_rp_total += 1
                if blue_pattern: blue_rp_total += 1
                
                # Win/Tie RP (FTC 2025: +3 for win, +1 for tie)
                if actual_winner == 'red':
                    red_rp_total += 3
                    red_win = 1
                    blue_win = 0
                elif actual_winner == 'blue':
                    blue_rp_total += 3
                    red_win = 0
                    blue_win = 1
                else:  # tie
                    red_rp_total += 1
                    blue_rp_total += 1
                    red_win = 0.5
                    blue_win = 0.5
                
                # Update team stats (ACTUAL)
                for team in red_teams:
                    if team in teams:
                        teams[team]['total_rp'] += red_rp_total
                        teams[team]['total_wins'] += red_win
                        teams[team]['total_matches'] += 1
                        teams[team]['scores'].append(red_rp_total)
                
                for team in blue_teams:
                    if team in teams:
                        teams[team]['total_rp'] += blue_rp_total
                        teams[team]['total_wins'] += blue_win
                        teams[team]['total_matches'] += 1
                        teams[team]['scores'].append(blue_rp_total)
                        
            else:
                # PREDICTED MATCH RESULTS
                red_opr = sum(opr_data.get(team, 0) for team in red_teams)
                blue_opr = sum(opr_data.get(team, 0) for team in blue_teams)
                
                # Predict winner
                predicted_winner = 'red' if red_opr > blue_opr else 'blue' if blue_opr < red_opr else 'tie'
                
                # Calculate predicted RPs for each alliance using team RP probabilities
                def calculate_alliance_rps(teams_list):
                    if len(teams_list) != 2:
                        return {'movement': 0, 'goal': 0, 'pattern': 0, 'total': 0}
                    
                    team1_rp = rp_data.get(teams_list[0], {})
                    team2_rp = rp_data.get(teams_list[1], {})
                    
                    movement_prob = (team1_rp.get('movement_prob', 0) + team2_rp.get('movement_prob', 0)) / 200  # Convert percentage to probability
                    goal_prob = (team1_rp.get('goal_prob', 0) + team2_rp.get('goal_prob', 0)) / 200
                    pattern_prob = (team1_rp.get('pattern_prob', 0) + team2_rp.get('pattern_prob', 0)) / 200
                    
                    # Each bonus RP is worth +1 point if probability > 50%
                    movement_rp = 1 if movement_prob > 0.5 else 0
                    goal_rp = 1 if goal_prob > 0.5 else 0
                    pattern_rp = 1 if pattern_prob > 0.5 else 0
                    
                    total_rp = movement_rp + goal_rp + pattern_rp
                    
                    return {
                        'movement': movement_rp,
                        'goal': goal_rp,
                        'pattern': pattern_rp,
                        'total': total_rp,
                        'movement_prob': round(movement_prob * 100),
                        'goal_prob': round(goal_prob * 100),
                        'pattern_prob': round(pattern_prob * 100)
                    }
                
                red_rps = calculate_alliance_rps(red_teams)
                blue_rps = calculate_alliance_rps(blue_teams)
                
                # Add win/tie RP (FTC 2025: +2 for win, +1 for tie)
                if predicted_winner == 'red':
                    red_rps['total'] += 3
                    red_rps['win'] = 1
                    blue_rps['win'] = 0
                elif predicted_winner == 'blue':
                    blue_rps['total'] += 3
                    red_rps['win'] = 0
                    blue_rps['win'] = 1
                else:  # tie
                    red_rps['total'] += 1
                    blue_rps['total'] += 1
                    red_rps['win'] = 0.5
                    blue_rps['win'] = 0.5
                
                # Update team stats (PREDICTED)
                for team in red_teams:
                    if team in teams:
                        teams[team]['total_rp'] += red_rps['total']
                        teams[team]['total_wins'] += red_rps['win']
                        teams[team]['total_matches'] += 1
                        teams[team]['scores'].append(red_rps['total'])
                        teams[team]['is_predicted'] = True
                
                for team in blue_teams:
                    if team in teams:
                        teams[team]['total_rp'] += blue_rps['total']
                        teams[team]['total_wins'] += blue_rps['win']
                        teams[team]['total_matches'] += 1
                        teams[team]['scores'].append(blue_rps['total'])
                        teams[team]['is_predicted'] = True
        
        # Calculate averages and prepare leaderboard
        leaderboard = []
        total_played_matches = sum(1 for match in matches if match.get('scores'))
        total_upcoming_matches = len(matches) - total_played_matches
        
        for team_num, team_data in teams.items():
            if team_data['total_matches'] > 0:
                avg_rp = team_data['total_rp'] / team_data['total_matches']
                win_rate = (team_data['total_wins'] / team_data['total_matches']) * 100
                
                # Sort scores to find median
                sorted_scores = sorted(team_data['scores'])
                median_rp = sorted_scores[len(sorted_scores) // 2] if sorted_scores else 0
                
                leaderboard.append({
                    'team_number': team_num,
                    'avg_rp': round(avg_rp, 2),
                    'total_rp': team_data['total_rp'],
                    'total_matches': team_data['total_matches'],
                    'win_rate': round(win_rate, 1),
                    'median_rp': median_rp,
                    'has_predictions': team_data['is_predicted']
                })
        
        # Determine event status
        event_status = "completed"
        if total_upcoming_matches > 0:
            if total_played_matches > 0:
                event_status = "in_progress"
            else:
                event_status = "not_started"
        
        # Sort by total RP (descending), then by average RP
        leaderboard.sort(key=lambda x: (x['total_rp'], x['avg_rp']), reverse=True)
        
        return {
            'leaderboard': leaderboard,
            'event_status': event_status,
            'played_matches': total_played_matches,
            'upcoming_matches': total_upcoming_matches,
            'total_matches': len(matches)
        }

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
    """Get match predictions AND past match results for an event"""
    try:
        # Get OPR source from query parameter (default to current event)
        use_highest_season_opr = request.args.get('opr_source', 'current') == 'highest'
        
        matches = calculator.get_event_matches(event_code)
        if not matches:
            return jsonify({"error": f"No matches found for event {event_code}"}), 404
        
        print(f"Found {len(matches)} matches for event {event_code}")
        print(f"Using OPR source: {'Highest Season OPR' if use_highest_season_opr else 'Current Event OPR'}")
        
        # Get OPR data
        opr_data, highest_opr_info = calculator.calculate_opr(event_code, use_highest_season_opr)
        
        # Get RP data
        rp_data = calculator.calculate_rp_simple(event_code)
        
        # Calculate comprehensive leaderboard
        leaderboard_result = calculator.calculate_leaderboard(event_code, opr_data, rp_data, matches)
        
        predictions = []
        past_matches = []
        scheduled_matches = 0
        played_matches = 0
        
        for match in matches:
            match_id = match.get('id', 0)
            
            # Skip non-qual matches for display too (match numbers > 10000)
            if isinstance(match_id, str):
                try:
                    match_num = int(match_id)
                    if match_num > 10000:
                        continue
                except:
                    # If can't parse as int, assume it's a qual match
                    pass
            
            red_teams = [str(t['teamNumber']) for t in match.get('teams', []) if t.get('alliance') == 'Red']
            blue_teams = [str(t['teamNumber']) for t in match.get('teams', []) if t.get('alliance') == 'Blue']
            
            # Check if match has been played (has scores)
            if match.get('scores') and match['scores'].get('red') and match['scores'].get('blue'):
                played_matches += 1
                red_score = match['scores']['red'].get('totalPoints', 0)
                blue_score = match['scores']['blue'].get('totalPoints', 0)
                actual_winner = 'red' if red_score > blue_score else 'blue' if blue_score > red_score else 'tie'
                
                # Calculate what the prediction would have been
                red_opr = sum(opr_data.get(team, 0) for team in red_teams)
                blue_opr = sum(opr_data.get(team, 0) for team in blue_teams)
                predicted_winner = 'red' if red_opr > blue_opr else 'blue'
                
                # Calculate actual RP for display
                red_rp_total = 0
                blue_rp_total = 0
                
                # Movement RP
                red_movement = match['scores']['red'].get('movementBonus', False)
                blue_movement = match['scores']['blue'].get('movementBonus', False)
                if red_movement: red_rp_total += 1
                if blue_movement: blue_rp_total += 1
                
                # Goal RP
                red_goal = match['scores']['red'].get('goalBonus', False)
                blue_goal = match['scores']['blue'].get('goalBonus', False)
                if red_goal: red_rp_total += 1
                if blue_goal: blue_rp_total += 1
                
                # Pattern RP
                red_pattern = match['scores']['red'].get('patternBonus', False)
                blue_pattern = match['scores']['blue'].get('patternBonus', False)
                if red_pattern: red_rp_total += 1
                if blue_pattern: blue_rp_total += 1
                
                # Win/Tie RP
                if actual_winner == 'red':
                    red_rp_total += 3
                elif actual_winner == 'blue':
                    blue_rp_total += 3
                else:  # tie
                    red_rp_total += 1
                    blue_rp_total += 1
                
                past_matches.append({
                    'match_number': match.get('id'),
                    'red_teams': red_teams,
                    'blue_teams': blue_teams,
                    'red_score': red_score,
                    'blue_score': blue_score,
                    'actual_winner': actual_winner,
                    'predicted_winner': predicted_winner,
                    'red_opr_sum': round(red_opr, 1),
                    'blue_opr_sum': round(blue_opr, 1),
                    'correct_prediction': actual_winner != 'tie' and actual_winner == predicted_winner,
                    'red_rp': red_rp_total,
                    'blue_rp': blue_rp_total,
                    'red_movement_rp': red_movement,
                    'blue_movement_rp': blue_movement,
                    'red_goal_rp': red_goal,
                    'blue_goal_rp': blue_goal,
                    'red_pattern_rp': red_pattern,
                    'blue_pattern_rp': blue_pattern
                })
            else:
                # This is an upcoming match - make prediction WITH RP
                scheduled_matches += 1
                red_opr = sum(opr_data.get(team, 0) for team in red_teams)
                blue_opr = sum(opr_data.get(team, 0) for team in blue_teams)
                
                total_opr = red_opr + blue_opr
                if total_opr > 0:
                    confidence = (abs(red_opr - blue_opr) / total_opr) * 100
                else:
                    confidence = 0
                
                def predict_alliance_rps(teams):
                    if len(teams) != 2:
                        return {
                            'movement_rp': False, 
                            'goal_rp': False, 
                            'pattern_rp': False,
                            'movement_avg': 0,
                            'goal_avg': 0,
                            'pattern_avg': 0,
                            'movement_prob': 0,
                            'goal_prob': 0,
                            'pattern_prob': 0
                        }
                    
                    team1_rp = rp_data.get(teams[0], {})
                    team2_rp = rp_data.get(teams[1], {})
                    
                    movement_avg = (team1_rp.get('movement_avg', 0) + team2_rp.get('movement_avg', 0)) / 2
                    goal_avg = (team1_rp.get('goal_avg', 0) + team2_rp.get('goal_avg', 0)) / 2
                    pattern_avg = (team1_rp.get('pattern_avg', 0) + team2_rp.get('pattern_avg', 0)) / 2
                    
                    # Calculate probabilities (convert percentage to decimal)
                    movement_prob = movement_avg / 100
                    goal_prob = goal_avg / 100
                    pattern_prob = pattern_avg / 100
                    
                    return {
                        'movement_rp': movement_avg > 50,
                        'movement_avg': round(movement_avg),
                        'goal_rp': goal_avg > 50,
                        'goal_avg': round(goal_avg),
                        'pattern_rp': pattern_avg > 50,
                        'pattern_avg': round(pattern_avg),
                        'movement_prob': round(movement_prob * 100),
                        'goal_prob': round(goal_prob * 100),
                        'pattern_prob': round(pattern_prob * 100)
                    }
                
                red_rps = predict_alliance_rps(red_teams)
                blue_rps = predict_alliance_rps(blue_teams)
                
                # Calculate total predicted RP for each alliance
                red_total_rp = 0
                blue_total_rp = 0
                
                if red_rps['movement_rp']: red_total_rp += 1
                if red_rps['goal_rp']: red_total_rp += 1
                if red_rps['pattern_rp']: red_total_rp += 1
                
                if blue_rps['movement_rp']: blue_total_rp += 1
                if blue_rps['goal_rp']: blue_total_rp += 1
                if blue_rps['pattern_rp']: blue_total_rp += 1
                
                predicted_winner = 'red' if red_opr > blue_opr else 'blue'
                winner_confidence = min(100, max(50, round(confidence + 50)))
                
                # Add win/tie RP to totals
                if predicted_winner == 'red':
                    red_total_rp += 3
                elif predicted_winner == 'blue':
                    blue_total_rp += 3
                else:  # tie
                    red_total_rp += 1
                    blue_total_rp += 1
                
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
                    'blue_rp_predictions': blue_rps,
                    'red_total_rp': red_total_rp,
                    'blue_total_rp': blue_total_rp
                })
        
        # Calculate prediction accuracy for past matches
        correct_predictions = sum(1 for match in past_matches if match['correct_prediction'])
        total_predictable = sum(1 for match in past_matches if match['actual_winner'] != 'tie')
        accuracy = (correct_predictions / total_predictable * 100) if total_predictable > 0 else 0
        
        return jsonify({
            "event_code": event_code,
            "opr_data": opr_data,
            "opr_source": "highest_season" if use_highest_season_opr else "current_event",
            "highest_opr_info": highest_opr_info if use_highest_season_opr else {},
            "predictions": predictions,
            "past_matches": past_matches,
            "leaderboard": leaderboard_result['leaderboard'],
            "event_status": leaderboard_result['event_status'],
            "played_matches": leaderboard_result['played_matches'],
            "upcoming_matches": leaderboard_result['upcoming_matches'],
            "total_matches": leaderboard_result['total_matches'],
            "scheduled_matches": scheduled_matches,
            "prediction_accuracy": round(accuracy, 1)
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
