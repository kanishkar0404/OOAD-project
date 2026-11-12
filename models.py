from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    """
    User Domain Entity Model.
    Tracks authentication, role (customer/admin), team membership, aggregate points, and solved puzzle counts.
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="customer") # 'customer' or 'admin'
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id', name='fk_user_team_id'), nullable=True)
    avatar_color = db.Column(db.String(20), default="#6366f1")
    total_score = db.Column(db.Integer, default=0)
    puzzles_solved = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    scores = db.relationship('Score', backref='user', lazy=True, cascade="all, delete-orphan")
    sessions = db.relationship('GameSession', backref='user', lazy=True, cascade="all, delete-orphan")

    @property
    def is_admin(self):
        return (self.role or '').strip().lower() == 'admin'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        role_val = "admin" if self.is_admin else "customer"
        return {
            "id": self.id,
            "username": self.username,
            "role": role_val,
            "is_admin": self.is_admin,
            "avatar_color": self.avatar_color,
            "team_id": self.team_id,
            "team_name": self.team.name if self.team else None,
            "team_badge_color": self.team.badge_color if self.team else None,
            "total_score": self.total_score,
            "puzzles_solved": self.puzzles_solved,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }


class Team(db.Model):
    """
    Team Domain Entity Model.
    Enables collective gameplay, team scores, rosters, and team rankings.
    """
    __tablename__ = 'teams'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)
    motto = db.Column(db.String(120), default="Logic Enthusiasts")
    badge_color = db.Column(db.String(20), default="#6366f1")
    leader_id = db.Column(db.Integer, db.ForeignKey('users.id', name='fk_team_leader_id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    members = db.relationship('User', backref='team', foreign_keys=[User.team_id], lazy=True)
    leader = db.relationship('User', foreign_keys=[leader_id], lazy=True)

    def calculate_stats(self):
        total_score = sum(m.total_score for m in self.members)
        puzzles_solved = sum(m.puzzles_solved for m in self.members)
        return total_score, puzzles_solved

    def to_dict(self):
        total_score, puzzles_solved = self.calculate_stats()
        return {
            "id": self.id,
            "name": self.name,
            "motto": self.motto,
            "badge_color": self.badge_color,
            "leader_id": self.leader_id,
            "leader_name": self.leader.username if self.leader else "Unknown",
            "member_count": len(self.members),
            "total_score": total_score,
            "puzzles_solved": puzzles_solved,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M")
        }


class Puzzle(db.Model):
    """
    Puzzle Data Entity Model.
    Stores initial board states, solution grids, categories, and difficulty levels.
    """
    __tablename__ = 'puzzles'

    id = db.Column(db.String(64), primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(30), nullable=False) # sudoku, nonogram, lights_out, mastermind, sliding
    difficulty = db.Column(db.String(20), nullable=False) # easy, medium, hard
    initial_state_json = db.Column(db.Text, nullable=False)
    solution_state_json = db.Column(db.Text, nullable=False)
    instructions = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    scores = db.relationship('Score', backref='puzzle', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "difficulty": self.difficulty,
            "initial_state": self.initial_state_json,
            "instructions": self.instructions
        }


class GameSession(db.Model):
    """
    Active Game Play Session Entity.
    Manages live game timer, move counts, and hint usage.
    """
    __tablename__ = 'game_sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    puzzle_id = db.Column(db.String(64), db.ForeignKey('puzzles.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    moves_count = db.Column(db.Integer, default=0)
    hints_used = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="ACTIVE") # ACTIVE, COMPLETED, ABANDONED

    def to_dict(self):
        return {
            "session_id": self.id,
            "user_id": self.user_id,
            "puzzle_id": self.puzzle_id,
            "start_time": self.start_time.isoformat(),
            "moves_count": self.moves_count,
            "hints_used": self.hints_used,
            "status": self.status
        }


class Score(db.Model):
    """
    Score Leaderboard Entity Model.
    Contains completed game metrics: calculated score, time taken, moves, and rank metadata.
    """
    __tablename__ = 'scores'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    puzzle_id = db.Column(db.String(64), db.ForeignKey('puzzles.id'), nullable=False)
    score_value = db.Column(db.Integer, nullable=False)
    time_seconds = db.Column(db.Float, nullable=False)
    moves_count = db.Column(db.Integer, nullable=False)
    hints_used = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        # Resolve puzzle title and category with smart fallbacks
        p_title = ""
        p_category = ""
        p_diff = "medium"
        if self.puzzle:
            p_title = self.puzzle.title
            p_category = self.puzzle.category
            p_diff = self.puzzle.difficulty
        elif self.puzzle_id:
            pid = str(self.puzzle_id)
            if pid.startswith("proc_"):
                parts = pid.split("_")
                cat = parts[1] if len(parts) > 1 else "Procedural"
                p_title = f"Procedural {cat.title()}"
                p_category = cat
            else:
                p_title = pid.replace("_", " ").title()
                p_category = pid.split("_")[0] if "_" in pid else "puzzle"

        mins = int(self.time_seconds // 60)
        secs = int(self.time_seconds % 60)
        time_formatted = f"{mins:02d}:{secs:02d}"

        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.user.username if self.user else "Anonymous",
            "role": (self.user.role if self.user and self.user.role else "customer"),
            "is_admin": (self.user.is_admin if self.user else False),
            "team_name": self.user.team.name if (self.user and self.user.team) else None,
            "avatar_color": self.user.avatar_color if self.user else "#6366f1",
            "puzzle_id": self.puzzle_id,
            "puzzle_title": p_title or "Logic Game",
            "puzzle_category": p_category or "puzzle",
            "difficulty": p_diff,
            "score_value": self.score_value,
            "time_seconds": round(self.time_seconds, 1),
            "time_formatted": time_formatted,
            "moves_count": self.moves_count,
            "hints_used": self.hints_used,
            "date": self.created_at.strftime("%Y-%m-%d %H:%M"),
            "created_at_iso": self.created_at.isoformat()
        }
