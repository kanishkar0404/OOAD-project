import os
import json
from functools import wraps
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from sqlalchemy import func, desc, or_
from models import db, User, Puzzle, GameSession, Score
from database import DatabaseManager
from puzzle_engine import PuzzleFactory, BasePuzzle, HybridScoring

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['SECRET_KEY'] = 'super-secret-ooad-logic-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///logic_puzzles.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

ADMIN_REGISTRATION_KEY = os.environ.get("ADMIN_KEY", "admin2026")

CORS(app)
DatabaseManager.init_db(app)

def admin_required(f):
    """
    Decorator to restrict administrative routes to verified Admin accounts.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication required. Please log in as an Admin."}), 401
        user = User.query.get(user_id)
        if not user or not user.is_admin:
            return jsonify({"error": "Administrator privileges required to access this resource."}), 403
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------------------------------------------
# WEB APP MAIN ENTRYPOINT
# -------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


# -------------------------------------------------------------------
# AUTHENTICATION API
# -------------------------------------------------------------------
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'customer').strip().lower()
    admin_key = data.get('admin_key', '').strip()
    avatar_color = data.get('avatar_color', '#6366f1')

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters."}), 400

    if role == 'admin':
        if admin_key != ADMIN_REGISTRATION_KEY:
            return jsonify({"error": "Invalid Admin Secret Key. Enter 'admin2026' to create an Admin account."}), 403
    else:
        role = 'customer'

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists. Please login."}), 400

    user = User(username=username, role=role, avatar_color=avatar_color)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id
    return jsonify({
        "message": f"Registration successful as {role.capitalize()}!",
        "user": user.to_dict()
    })


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    requested_role = data.get('role', '').strip().lower()

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid username or password."}), 401

    if requested_role == 'admin' and not user.is_admin:
        return jsonify({
            "error": f"Access denied: Account '{username}' does not have Administrator privileges. Please log in as a Customer."
        }), 403

    session['user_id'] = user.id
    return jsonify({
        "message": f"Login successful! Welcome {user.username}.",
        "user": user.to_dict()
    })


@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"user": None})

    user = User.query.get(user_id)
    if not user:
        session.pop('user_id', None)
        return jsonify({"user": None})

    return jsonify({"user": user.to_dict()})


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({"message": "Logged out successfully."})


@app.route('/api/auth/change-password', methods=['POST'])
def change_password():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Unauthorized. Please log in first."}), 401

    data = request.get_json() or {}
    current_password = data.get('current_password', '').strip()
    new_password = data.get('new_password', '').strip()

    if not current_password or not new_password:
        return jsonify({"error": "Current password and new password are required."}), 400

    if len(new_password) < 4:
        return jsonify({"error": "New password must be at least 4 characters."}), 400

    user = User.query.get(user_id)
    if not user or not user.check_password(current_password):
        return jsonify({"error": "Incorrect current password."}), 400

    user.set_password(new_password)
    db.session.commit()
    return jsonify({"message": "Password changed successfully!"})


@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    new_password = data.get('new_password', '').strip()

    if not username or not new_password:
        return jsonify({"error": "Username and new password are required."}), 400

    if len(new_password) < 4:
        return jsonify({"error": "New password must be at least 4 characters."}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "Account username not found."}), 404

    user.set_password(new_password)
    db.session.commit()
    return jsonify({"message": "Password reset successfully! You can now log in with your new password."})


# -------------------------------------------------------------------
# PUZZLES CATALOG & GENERATION API
# -------------------------------------------------------------------
@app.route('/api/puzzles', methods=['GET'])
def list_puzzles():
    category = request.args.get('category')
    difficulty = request.args.get('difficulty')

    query = Puzzle.query
    if category and category != 'all':
        query = query.filter_by(category=category)
    if difficulty and difficulty != 'all':
        query = query.filter_by(difficulty=difficulty)

    puzzles = query.all()
    return jsonify([p.to_dict() for p in puzzles])


@app.route('/api/puzzles/<puzzle_id>', methods=['GET'])
def get_puzzle(puzzle_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Authentication required. Please register or login to play puzzles."}), 401

    user = User.query.get(user_id)
    if user and user.is_admin:
        return jsonify({"error": "Admin accounts cannot participate in puzzle gameplay."}), 403

    puzzle_model = Puzzle.query.get(puzzle_id)
    if not puzzle_model:
        return jsonify({"error": "Puzzle not found."}), 404

    # Build polymorphic puzzle object via Factory
    puzzle_obj = PuzzleFactory.create_puzzle(
        puzzle_id=puzzle_model.id,
        title=puzzle_model.title,
        puzzle_type=puzzle_model.category,
        difficulty=puzzle_model.difficulty,
        initial_state=puzzle_model.initial_state_json,
        solution_state=puzzle_model.solution_state_json,
        instructions=puzzle_model.instructions
    )

    response_data = puzzle_model.to_dict()
    response_data["board_data"] = puzzle_obj.get_initial_board()
    return jsonify(response_data)


@app.route('/api/puzzles/procedural/<category>', methods=['GET'])
def generate_procedural_puzzle(category):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Authentication required. Please register or login to play puzzles."}), 401

    user = User.query.get(user_id)
    if user and user.is_admin:
        return jsonify({"error": "Admin accounts cannot participate in puzzle gameplay."}), 403

    difficulty = request.args.get('difficulty', 'medium')
    try:
        puzzle_obj = PuzzleFactory.generate_random_puzzle(category, difficulty)
        return jsonify({
            "id": puzzle_obj.puzzle_id,
            "title": puzzle_obj.title,
            "category": puzzle_obj.puzzle_type,
            "difficulty": puzzle_obj.difficulty,
            "initial_state": puzzle_obj.initial_state,
            "instructions": puzzle_obj.instructions,
            "board_data": puzzle_obj.get_initial_board()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# -------------------------------------------------------------------
# GAMEPLAY & SOLUTION VALIDATION API
# -------------------------------------------------------------------
@app.route('/api/game/submit', methods=['POST'])
def submit_solution():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Authentication required. Please register or login to play."}), 401

    user = User.query.get(user_id)
    if user and user.is_admin:
        return jsonify({"error": "Admin accounts cannot participate in puzzle gameplay or record scores."}), 403

    data = request.get_json() or {}
    puzzle_id = data.get('puzzle_id')
    user_solution = data.get('solution')
    time_seconds = float(data.get('time_seconds', 0))
    moves_count = int(data.get('moves_count', 0))
    hints_used = int(data.get('hints_used', 0))

    # 1. Fetch puzzle record
    puzzle_model = Puzzle.query.get(puzzle_id)
    if not puzzle_model and not puzzle_id.startswith("proc_"):
        return jsonify({"error": "Invalid puzzle ID."}), 400

    if puzzle_model:
        puzzle_obj = PuzzleFactory.create_puzzle(
            puzzle_id=puzzle_model.id,
            title=puzzle_model.title,
            puzzle_type=puzzle_model.category,
            difficulty=puzzle_model.difficulty,
            initial_state=puzzle_model.initial_state_json,
            solution_state=puzzle_model.solution_state_json,
            instructions=puzzle_model.instructions
        )
    else:
        # Procedural puzzle dynamically stored in session or payload
        puzzle_type = data.get('category', 'lights_out')
        puzzle_obj = PuzzleFactory.create_puzzle(
            puzzle_id=puzzle_id,
            title="Procedural Game",
            puzzle_type=puzzle_type,
            difficulty=data.get('difficulty', 'medium'),
            initial_state=data.get('initial_state', '[]'),
            solution_state=data.get('solution_state', '[]')
        )

    # 2. Polymorphic solution validation
    is_correct, feedback = puzzle_obj.validate_solution(user_solution)

    if not is_correct:
        return jsonify({
            "is_correct": False,
            "feedback": feedback
        })

    # 3. Strategy Pattern Score Calculation
    scoring_strategy = HybridScoring()
    calculated_score = scoring_strategy.calculate_score(
        difficulty=puzzle_obj.difficulty,
        time_seconds=time_seconds,
        moves=moves_count,
        hints_used=hints_used
    )

    # 4. Save Score & Update User aggregate stats
    user = User.query.get(user_id)
    if user:
        user.total_score += calculated_score
        user.puzzles_solved += 1
        
        # Save Score Entry
        score_entry = Score(
            user_id=user.id,
            puzzle_id=puzzle_id if puzzle_model else "procedural",
            score_value=calculated_score,
            time_seconds=time_seconds,
            moves_count=moves_count,
            hints_used=hints_used
        )
        db.session.add(score_entry)
        db.session.commit()

        # Calculate user position & percentile
        user_rank_info = get_user_rank_metadata(user.id)

    return jsonify({
        "is_correct": True,
        "feedback": feedback,
        "score_earned": calculated_score,
        "user_rank_info": user_rank_info
    })


@app.route('/api/game/hint', methods=['POST'])
def get_game_hint():
    if not session.get('user_id'):
        return jsonify({"error": "Authentication required. Please register or login to play."}), 401

    data = request.get_json() or {}
    puzzle_id = data.get('puzzle_id')
    category = data.get('category')
    current_state = data.get('current_state')

    puzzle_model = Puzzle.query.get(puzzle_id) if puzzle_id else None

    if puzzle_model:
        puzzle_obj = PuzzleFactory.create_puzzle(
            puzzle_id=puzzle_model.id,
            title=puzzle_model.title,
            puzzle_type=puzzle_model.category,
            difficulty=puzzle_model.difficulty,
            initial_state=puzzle_model.initial_state_json,
            solution_state=puzzle_model.solution_state_json
        )
    elif category:
        # Support procedural dynamically generated puzzles
        puzzle_obj = PuzzleFactory.create_puzzle(
            puzzle_id=puzzle_id or "proc_puzzle",
            title="Procedural Game",
            puzzle_type=category,
            difficulty=data.get('difficulty', 'medium'),
            initial_state=data.get('initial_state', '[]'),
            solution_state=data.get('solution_state', '[]')
        )
    else:
        return jsonify({"error": "Puzzle not found."}), 404

    hint_number = int(data.get('hint_number') or (int(data.get('hints_used', 0)) + 1) or 1)
    hint = puzzle_obj.get_hint(current_state, hint_number=hint_number)
    return jsonify(hint)


# -------------------------------------------------------------------
# LEADERBOARD & POSITION RANKING API
# -------------------------------------------------------------------
@app.route('/api/leaderboard/global', methods=['GET'])
def global_leaderboard():
    limit = int(request.args.get('limit', 20))
    # Exclude admin accounts from player score leaderboard
    users = User.query.filter(User.role != 'admin').order_by(User.total_score.desc()).limit(limit).all()
    
    leaderboard = []
    for rank, u in enumerate(users, start=1):
        leaderboard.append({
            "rank": rank,
            "user_id": u.id,
            "username": u.username,
            "avatar_color": u.avatar_color,
            "total_score": u.total_score,
            "puzzles_solved": u.puzzles_solved
        })

    user_id = session.get('user_id')
    current_user_rank = get_user_rank_metadata(user_id) if user_id else None

    return jsonify({
        "leaderboard": leaderboard,
        "current_user_rank": current_user_rank
    })


@app.route('/api/leaderboard/puzzle/<puzzle_id>', methods=['GET'])
def puzzle_leaderboard(puzzle_id):
    scores = Score.query.join(User, Score.user_id == User.id)\
                        .filter(Score.puzzle_id == puzzle_id, User.role != 'admin')\
                        .order_by(Score.score_value.desc(), Score.time_seconds.asc())\
                        .limit(15).all()

    return jsonify([s.to_dict() for s in scores])


@app.route('/api/leaderboard/user-position/<int:user_id>', methods=['GET'])
def user_position(user_id):
    rank_info = get_user_rank_metadata(user_id)
    if not rank_info:
        return jsonify({"error": "User not found or is an Administrator."}), 404
    return jsonify(rank_info)


def get_user_rank_metadata(user_id):
    if not user_id:
        return None
    user = User.query.get(user_id)
    if not user or user.is_admin:
        return None  # Admin accounts do not participate in rankings or scores

    # Calculate exact global rank among player customers
    higher_users = User.query.filter(User.role != 'admin', User.total_score > user.total_score).count()
    global_rank = higher_users + 1
    total_users = User.query.filter(User.role != 'admin').count()

    percentile = round(((total_users - global_rank + 1) / total_users) * 100, 1) if total_users > 0 else 100.0

    return {
        "user_id": user.id,
        "username": user.username,
        "global_rank": global_rank,
        "total_users": total_users,
        "percentile": percentile,
        "total_score": user.total_score,
        "puzzles_solved": user.puzzles_solved
    }


# -------------------------------------------------------------------
# ADMIN MANAGEMENT & COMPREHENSIVE SCORE TRACKING API
# -------------------------------------------------------------------
@app.route('/api/admin/overview', methods=['GET'])
@admin_required
def admin_overview():
    """
    Returns platform-wide administrative statistics: player counts, games played,
    cumulative scores, category distributions, and top performers.
    """
    total_customers = User.query.filter(User.role != 'admin').count()
    total_admins = User.query.filter(User.role == 'admin').count()
    total_games_played = Score.query.count()

    cumulative_platform_score = db.session.query(
        func.coalesce(func.sum(Score.score_value), 0)
    ).scalar() or 0

    avg_game_score = round(
        db.session.query(func.coalesce(func.avg(Score.score_value), 0)).scalar() or 0, 1
    )

    top_player = User.query.filter(User.role != 'admin').order_by(User.total_score.desc()).first()

    # Category distribution breakdown
    cat_counts = {}
    for p in Puzzle.query.all():
        score_count = Score.query.filter_by(puzzle_id=p.id).count()
        cat_counts[p.category] = cat_counts.get(p.category, 0) + score_count

    # Also count procedural games
    procedural_count = Score.query.filter(Score.puzzle_id.like("proc%")).count()
    if procedural_count > 0:
        cat_counts["procedural"] = procedural_count

    return jsonify({
        "total_customers": total_customers,
        "total_admins": total_admins,
        "total_players": total_customers,
        "total_games_played": total_games_played,
        "cumulative_platform_score": int(cumulative_platform_score),
        "avg_game_score": avg_game_score,
        "top_player": {
            "username": top_player.username if top_player else "None",
            "total_score": top_player.total_score if top_player else 0,
            "avatar_color": top_player.avatar_color if top_player else "#6366f1"
        } if top_player else None,
        "category_distribution": cat_counts
    })


@app.route('/api/admin/players-summary', methods=['GET'])
@admin_required
def admin_players_summary():
    """
    Returns cumulative statistics for all registered players/customers:
    total games played, cumulative total score, average score, best score, and last game.
    Admins are excluded from player score summaries.
    """
    users = User.query.filter(User.role != 'admin').order_by(User.total_score.desc()).all()
    summary = []

    for u in users:
        # Score aggregates for this user
        user_scores = Score.query.filter_by(user_id=u.id).order_by(Score.created_at.desc()).all()
        games_played = len(user_scores)
        cumulative_score = sum(s.score_value for s in user_scores)
        avg_score = round(cumulative_score / games_played, 1) if games_played > 0 else 0
        best_score = max((s.score_value for s in user_scores), default=0)

        last_game = user_scores[0] if user_scores else None
        last_game_dict = last_game.to_dict() if last_game else None

        summary.append({
            "user_id": u.id,
            "username": u.username,
            "role": u.role or "customer",
            "is_admin": u.is_admin,
            "avatar_color": u.avatar_color,
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M"),
            "games_played": games_played,
            "cumulative_score": cumulative_score if cumulative_score > 0 else u.total_score,
            "avg_score": avg_score,
            "best_score": best_score,
            "puzzles_solved": u.puzzles_solved,
            "last_game": {
                "date": last_game_dict["date"] if last_game_dict else "Never",
                "puzzle_title": last_game_dict["puzzle_title"] if last_game_dict else "None",
                "score": last_game_dict["score_value"] if last_game_dict else 0
            } if last_game else None
        })

    return jsonify({
        "players": summary,
        "total_count": len(summary)
    })


@app.route('/api/admin/all-games', methods=['GET'])
@admin_required
def admin_all_games():
    """
    Returns individual game records for all players with detailed game scores,
    with flexible filtering by player, category, difficulty, or search keyword.
    """
    user_id = request.args.get('user_id', type=int)
    category = request.args.get('category', '').strip().lower()
    difficulty = request.args.get('difficulty', '').strip().lower()
    search = request.args.get('search', '').strip().lower()
    sort_by = request.args.get('sort', 'date_desc').strip().lower()
    limit = request.args.get('limit', 500, type=int)
    offset = request.args.get('offset', 0, type=int)

    query = Score.query.join(User, Score.user_id == User.id)

    if user_id:
        query = query.filter(Score.user_id == user_id)

    if category and category != 'all':
        query = query.outerjoin(Puzzle, Score.puzzle_id == Puzzle.id).filter(
            or_(
                Puzzle.category == category,
                Score.puzzle_id.like(f"%{category}%")
            )
        )

    if difficulty and difficulty != 'all':
        query = query.outerjoin(Puzzle, Score.puzzle_id == Puzzle.id).filter(
            Puzzle.difficulty == difficulty
        )

    if search:
        query = query.outerjoin(Puzzle, Score.puzzle_id == Puzzle.id).filter(
            or_(
                User.username.ilike(f"%{search}%"),
                Puzzle.title.ilike(f"%{search}%"),
                Score.puzzle_id.ilike(f"%{search}%")
            )
        )

    # Sorting
    if sort_by == 'score_desc':
        query = query.order_by(Score.score_value.desc(), Score.created_at.desc())
    elif sort_by == 'score_asc':
        query = query.order_by(Score.score_value.asc(), Score.created_at.desc())
    elif sort_by == 'time_asc':
        query = query.order_by(Score.time_seconds.asc())
    elif sort_by == 'moves_asc':
        query = query.order_by(Score.moves_count.asc())
    elif sort_by == 'date_asc':
        query = query.order_by(Score.created_at.asc())
    else: # date_desc
        query = query.order_by(Score.created_at.desc())

    total_filtered = query.count()
    scores = query.limit(limit).offset(offset).all()

    games_data = [s.to_dict() for s in scores]
    cumulative_score = sum(g["score_value"] for g in games_data)
    avg_score = round(cumulative_score / len(games_data), 1) if games_data else 0

    return jsonify({
        "games": games_data,
        "total_count": total_filtered,
        "cumulative_score_in_view": cumulative_score,
        "avg_score_in_view": avg_score
    })


@app.route('/api/admin/player/<int:target_user_id>/games', methods=['GET'])
@admin_required
def admin_player_games(target_user_id):
    """
    Returns specific player's profile and full chronological game history.
    """
    user = User.query.get(target_user_id)
    if not user:
        return jsonify({"error": "Player not found."}), 404

    scores = Score.query.filter_by(user_id=target_user_id).order_by(Score.created_at.desc()).all()
    games_list = [s.to_dict() for s in scores]

    cumulative_score = sum(s["score_value"] for s in games_list)
    avg_score = round(cumulative_score / len(games_list), 1) if games_list else 0
    best_score = max((s["score_value"] for s in games_list), default=0)

    # Category breakdown for this specific player
    cat_breakdown = {}
    for g in games_list:
        cat = g.get("puzzle_category") or "other"
        if cat not in cat_breakdown:
            cat_breakdown[cat] = {"count": 0, "total_score": 0, "best_score": 0}
        cat_breakdown[cat]["count"] += 1
        cat_breakdown[cat]["total_score"] += g["score_value"]
        if g["score_value"] > cat_breakdown[cat]["best_score"]:
            cat_breakdown[cat]["best_score"] = g["score_value"]

    for cat, data in cat_breakdown.items():
        data["avg_score"] = round(data["total_score"] / data["count"], 1)

    return jsonify({
        "player": user.to_dict(),
        "cumulative_stats": {
            "games_played": len(games_list),
            "cumulative_score": cumulative_score,
            "avg_score": avg_score,
            "best_score": best_score,
            "puzzles_solved": user.puzzles_solved
        },
        "category_breakdown": cat_breakdown,
        "games": games_list
    })


@app.route('/api/admin/games-stats', methods=['GET'])
@admin_required
def admin_games_stats():
    """
    Returns aggregate performance metrics across puzzle types/categories.
    """
    categories = ['sudoku', 'nonogram', 'lights_out', 'mastermind', 'sliding']
    stats = []

    for cat in categories:
        # Find scores for puzzles of this category
        cat_scores = Score.query.join(Puzzle, Score.puzzle_id == Puzzle.id)\
                                .filter(Puzzle.category == cat).all()

        count = len(cat_scores)
        total_pts = sum(s.score_value for s in cat_scores)
        avg_score = round(total_pts / count, 1) if count > 0 else 0
        best_score = max((s.score_value for s in cat_scores), default=0)
        avg_time = round(sum(s.time_seconds for s in cat_scores) / count, 1) if count > 0 else 0

        # Unique players count
        unique_players = len(set(s.user_id for s in cat_scores))

        # Best performer
        best_score_obj = max(cat_scores, key=lambda s: s.score_value) if cat_scores else None

        stats.append({
            "category": cat,
            "display_name": cat.replace("_", " ").title(),
            "games_played": count,
            "total_score": total_pts,
            "avg_score": avg_score,
            "best_score": best_score,
            "avg_time_seconds": avg_time,
            "unique_players": unique_players,
            "top_scorer": best_score_obj.user.username if (best_score_obj and best_score_obj.user) else "-"
        })

    return jsonify({"categories_stats": stats})


# -------------------------------------------------------------------
# OOAD ARCHITECTURE DIAGRAMS API
# -------------------------------------------------------------------
@app.route('/api/ooad/summary', methods=['GET'])
def ooad_summary():
    """
    Exposes structural OOAD meta info for classroom presentation & inspection.
    """
    return jsonify({
        "architecture_name": "LogicGrid Master OOAD Architecture",
        "design_patterns": [
            {
                "pattern": "Factory Pattern",
                "class": "PuzzleFactory",
                "description": "Instantiates polymorphic logic puzzle objects (SudokuPuzzle, NonogramPuzzle, LightsOutPuzzle, MastermindPuzzle, SlidingPuzzle) based on string type identifiers."
            },
            {
                "pattern": "Template Method Pattern",
                "class": "BasePuzzle (Abstract)",
                "description": "Defines core puzzle lifecycle skeleton (validate_solution, get_hint, get_initial_board) while deferring concrete rules to puzzle subclasses."
            },
            {
                "pattern": "Strategy Pattern",
                "class": "ScoringStrategy",
                "description": "Encapsulates modular scoring algorithms (TimeBasedScoring, MoveBasedScoring, HybridScoring) allowing dynamic strategy swaps."
            },
            {
                "pattern": "Singleton Pattern",
                "class": "DatabaseManager",
                "description": "Ensures single controlled access point for database creation, table initialization, and seed population."
            },
            {
                "pattern": "Repository / DAO Pattern",
                "class": "SQLAlchemy Models",
                "description": "Decouples domain logic from database queries via User, Puzzle, GameSession, and Score entities."
            }
        ],
        "class_diagram_nodes": [
            "BasePuzzle (Abstract)",
            "SudokuPuzzle", "NonogramPuzzle", "LightsOutPuzzle", "MastermindPuzzle", "SlidingPuzzle",
            "PuzzleFactory", "ScoringStrategy", "HybridScoring",
            "User", "Puzzle", "GameSession", "Score", "DatabaseManager"
        ]
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
