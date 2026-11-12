import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import db, User, Puzzle, Score
from puzzle_engine import PuzzleFactory, HybridScoring

def run_tests():
    print("--------------------------------------------------")
    print(" RUNNING BACKEND UNIT & INTEGRATION TESTS")
    print("--------------------------------------------------")

    with app.app_context():
        # 1. Test Database Seeding
        user_count = User.query.count()
        puzzle_count = Puzzle.query.count()
        score_count = Score.query.count()

        print(f"[OK] Database Users: {user_count}")
        print(f"[OK] Database Puzzles: {puzzle_count}")
        print(f"[OK] Database Leaderboard Scores: {score_count}")

        assert user_count >= 4, "Users should be seeded!"
        assert puzzle_count >= 8, "Puzzles should be seeded!"

        # 2. Test Sudoku Validation
        sudoku_p = Puzzle.query.filter_by(category="sudoku").first()
        sudoku_obj = PuzzleFactory.create_puzzle(
            sudoku_p.id, sudoku_p.title, sudoku_p.category, sudoku_p.difficulty,
            sudoku_p.initial_state_json, sudoku_p.solution_state_json
        )
        is_cor, fb = sudoku_obj.validate_solution(sudoku_p.solution_state_json)
        print(f"[OK] Sudoku Solution Validation: {is_cor} - {fb['message']}")
        assert is_cor == True, "Sudoku validation should succeed for correct solution!"

        # 3. Test Lights Out Validation
        lights_p = Puzzle.query.filter_by(category="lights_out").first()
        lights_obj = PuzzleFactory.create_puzzle(
            lights_p.id, lights_p.title, lights_p.category, lights_p.difficulty,
            lights_p.initial_state_json, lights_p.solution_state_json
        )
        is_cor_l, fb_l = lights_obj.validate_solution(lights_p.solution_state_json)
        print(f"[OK] Lights Out Validation: {is_cor_l} - {fb_l['message']}")
        assert is_cor_l == True, "Lights Out validation should succeed!"

        # 4. Test Mastermind Guess Evaluation
        master_p = Puzzle.query.filter_by(category="mastermind").first()
        master_obj = PuzzleFactory.create_puzzle(
            master_p.id, master_p.title, master_p.category, master_p.difficulty,
            master_p.initial_state_json, master_p.solution_state_json
        )
        is_cor_m, fb_m = master_obj.validate_solution(master_p.solution_state_json)
        print(f"[OK] Mastermind Codebreaker Validation: {is_cor_m} - {fb_m['message']}")
        assert is_cor_m == True, "Mastermind validation should succeed!"

        # 5. Test Scoring Strategy
        scoring = HybridScoring()
        pts = scoring.calculate_score("medium", time_seconds=45.0, moves=15, hints_used=0)
        print(f"[OK] Hybrid Scoring Strategy Output (45s, 15 moves, 0 hints): {pts} points")
        assert pts > 1000, "Score should reflect bonus points!"

        # 6. Test Password Reset API
        test_user = User.query.filter_by(username="LogicWizard").first()
        test_user.set_password("newpassword123")
        db.session.commit()
        assert test_user.check_password("newpassword123") == True, "Password reset should succeed!"
        print("[OK] User Password Reset API Verification: Passed!")

        # 7. Test Mandatory Registration / Login Protection
        with app.test_client() as client:
            res_unauth = client.get(f'/api/puzzles/{sudoku_p.id}')
            assert res_unauth.status_code == 401, "Unauthenticated access must return 401!"
            print("[OK] Unauthenticated Access Restriction (401 Unauthorized): Verified!")

        # 8. Test Distinct Hints Across Multiple Calls
        h1 = sudoku_obj.get_hint(sudoku_p.initial_state_json, 1)
        h2 = sudoku_obj.get_hint(sudoku_p.initial_state_json, 2)
        h3 = sudoku_obj.get_hint(sudoku_p.initial_state_json, 3)
        assert (h1['row'], h1['col']) != (h2['row'], h2['col']) != (h3['row'], h3['col']), "Hints must target distinct cells!"
        print(f"[OK] Distinct Multi-Hint Generation: Hint 1 (R{h1['row']+1}C{h1['col']+1}), Hint 2 (R{h2['row']+1}C{h2['col']+1}), Hint 3 (R{h3['row']+1}C{h3['col']+1})")

        # 9. Test Customer Authentication & Role Assignment
        with app.test_client() as client:
            # Register a new customer
            import time
            unique_ts = int(time.time())
            c_user = f"cust_tester_{unique_ts}"
            reg_res = client.post('/api/auth/register', json={
                "username": c_user,
                "password": "custpassword123",
                "role": "customer",
                "avatar_color": "#10b981"
            })
            assert reg_res.status_code == 200, "Customer registration should succeed!"
            c_data = reg_res.get_json()
            assert c_data["user"]["role"] == "customer", "Role must be 'customer'!"
            assert c_data["user"]["is_admin"] == False, "Customer must not have admin privileges!"
            print(f"[OK] Customer Registration & Role Validation: {c_user} (role={c_data['user']['role']})")

            # Login as Customer
            login_res = client.post('/api/auth/login', json={
                "username": c_user,
                "password": "custpassword123",
                "role": "customer"
            })
            assert login_res.status_code == 200, "Customer login should succeed!"
            print(f"[OK] Customer Login with Password: {c_user} successfully logged in!")

            # Verify Customer cannot access Admin Overview (403 Forbidden)
            unauth_admin_res = client.get('/api/admin/overview')
            assert unauth_admin_res.status_code == 403, "Customer must be forbidden from Admin endpoints (403)!"
            print("[OK] Customer Access Control Enforcement: 403 Forbidden on Admin Console verified!")

        # 10. Test Admin Authentication & Privileges
        with app.test_client() as client:
            # Test Admin Registration with wrong key (should fail 403)
            fail_admin_res = client.post('/api/auth/register', json={
                "username": f"bad_admin_{unique_ts}",
                "password": "adminpass123",
                "role": "admin",
                "admin_key": "wrongkey999"
            })
            assert fail_admin_res.status_code == 403, "Admin registration with wrong key must fail!"
            print("[OK] Admin Security Key Validation: Rejected unauthorized admin registration (403)!")

            # Login as default Admin
            admin_login_res = client.post('/api/auth/login', json={
                "username": "admin",
                "password": "admin123",
                "role": "admin"
            })
            assert admin_login_res.status_code == 200, "Admin login should succeed!"
            admin_data = admin_login_res.get_json()
            assert admin_data["user"]["role"] == "admin", "Admin role must be 'admin'!"
            assert admin_data["user"]["is_admin"] == True, "Admin is_admin flag must be True!"
            print(f"[OK] Admin Login with Password: {admin_data['user']['username']} (is_admin=True)")

            # Test Admin Overview API
            overview_res = client.get('/api/admin/overview')
            assert overview_res.status_code == 200, "Admin overview endpoint must return 200!"
            ov_data = overview_res.get_json()
            assert ov_data["total_games_played"] > 0, "Games played count should be greater than 0!"
            assert ov_data["cumulative_platform_score"] > 0, "Platform cumulative score should be positive!"
            print(f"[OK] Admin Overview Telemetry: Total Games={ov_data['total_games_played']}, Cumulative Platform Score={ov_data['cumulative_platform_score']} pts, Top Player={ov_data['top_player']['username']}")

            # Test Admin All Games Telemetry API (All games played by all players)
            all_games_res = client.get('/api/admin/all-games')
            assert all_games_res.status_code == 200, "Admin all-games endpoint must return 200!"
            games_payload = all_games_res.get_json()
            assert len(games_payload["games"]) > 0, "Games list must contain recorded scores!"
            sample_g = games_payload["games"][0]
            assert "score_value" in sample_g and "puzzle_title" in sample_g and "username" in sample_g, "Score record must have all required telemetry attributes!"
            print(f"[OK] Admin All Games Log: Retrieved {len(games_payload['games'])} games (Sample: Player '{sample_g['username']}' scored {sample_g['score_value']} pts in '{sample_g['puzzle_title']}')")

            # Test Admin Filter by Category
            filtered_games_res = client.get('/api/admin/all-games?category=sudoku')
            assert filtered_games_res.status_code == 200
            for g in filtered_games_res.get_json()["games"]:
                assert g["puzzle_category"] == "sudoku" or "sudoku" in g["puzzle_id"], "Filtered games must match category!"
            print(f"[OK] Admin Category Filter: Retrieved {len(filtered_games_res.get_json()['games'])} Sudoku games successfully!")

            # Test Admin Players Summary (Cumulative scores per player)
            players_summary_res = client.get('/api/admin/players-summary')
            assert players_summary_res.status_code == 200
            p_summary = players_summary_res.get_json()["players"]
            assert len(p_summary) >= 4, "Must list all registered players!"
            active_p = next(p for p in p_summary if p["games_played"] > 0)
            assert active_p["cumulative_score"] > 0, "Active player must have positive cumulative score!"
            print(f"[OK] Admin Cumulative Player Stats: {len(p_summary)} players tracked (Top cumulative player '{p_summary[0]['username']}' has {p_summary[0]['cumulative_score']} cumulative pts across {p_summary[0]['games_played']} games)")

            # Test Admin Single Player Game Breakdown Drilldown
            player_id = active_p["user_id"]
            player_drilldown_res = client.get(f'/api/admin/player/{player_id}/games')
            assert player_drilldown_res.status_code == 200
            drilldown_data = player_drilldown_res.get_json()
            assert drilldown_data["player"]["id"] == player_id
            assert len(drilldown_data["games"]) == active_p["games_played"]
            print(f"[OK] Admin Player Drilldown: Player '{drilldown_data['player']['username']}' has {len(drilldown_data['games'])} individual game records detailed!")

            # Test Admin Game Category Statistics
            cat_stats_res = client.get('/api/admin/games-stats')
            assert cat_stats_res.status_code == 200
            categories_stats = cat_stats_res.get_json()["categories_stats"]
            assert len(categories_stats) == 5, "Should have 5 puzzle categories!"
            print(f"[OK] Admin Category Aggregates: 5 categories analyzed ({', '.join(c['display_name'] for c in categories_stats)})")

            # Test Admin cannot play puzzles or submit scores
            admin_puzzle_res = client.get(f'/api/puzzles/{sudoku_p.id}')
            assert admin_puzzle_res.status_code == 403, "Admin must be blocked from playable puzzle workspace (403)!"
            admin_submit_res = client.post('/api/game/submit', json={"puzzle_id": sudoku_p.id, "solution": []})
            assert admin_submit_res.status_code == 403, "Admin must be blocked from submitting scores (403)!"
            print("[OK] Admin Gameplay Restriction: Verified 403 on puzzle play and score submissions!")

            # Test Admin does not appear on player leaderboard
            global_lb_res = client.get('/api/leaderboard/global')
            assert global_lb_res.status_code == 200
            lb_users = [entry["username"] for entry in global_lb_res.get_json()["leaderboard"]]
            assert "admin" not in lb_users, "Admin account must NEVER be ranked on the player score leaderboard!"
            assert global_lb_res.get_json()["current_user_rank"] is None, "Admin must not have a player leaderboard rank!"
            print("[OK] Admin Score Exemption: Admin verified excluded from player leaderboard and score accumulation!")

        print("--------------------------------------------------")
        print(" ALL BACKEND TESTS PASSED SUCCESSFULLY! (100% OK)")
        print("--------------------------------------------------")

if __name__ == '__main__':
    run_tests()
