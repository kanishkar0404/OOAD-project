import json
from models import db, User, Puzzle, Score, GameSession
from puzzle_engine.puzzle_factory import PuzzleFactory

class DatabaseManager:
    """
    Singleton / Data Access Object Manager for SQLite database setup and seeding.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance

    @staticmethod
    def init_db(app):
        """
        Initializes app context and creates database tables if not existent.
        Also runs lightweight column migration and seeds default accounts and puzzles.
        """
        db.init_app(app)
        with app.app_context():
            db.create_all()
            DatabaseManager._check_and_migrate_columns()
            DatabaseManager.seed_initial_data()

    @staticmethod
    def _check_and_migrate_columns():
        """
        Ensures users table has role and team_id columns on SQLite safely.
        """
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                res = conn.execute(text("PRAGMA table_info(users)"))
                cols = [row[1] for row in res.fetchall()]
                if 'role' not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'customer'"))
                    conn.commit()
                if 'team_id' not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN team_id INTEGER"))
                    conn.commit()
        except Exception as e:
            print(f"[DB MIGRATION NOTICE] {e}")

    @staticmethod
    def seed_initial_data():
        """
        Pre-populates database with default logic puzzles, default admin/customer accounts,
        and leaderboard sample scores.
        """
        DatabaseManager.seed_puzzles()
        DatabaseManager.seed_roles_and_accounts()

    @staticmethod
    def seed_roles_and_accounts():
        """
        Ensures dedicated Admin ('admin' / 'admin123') and Customer ('customer' / 'customer123')
        accounts exist, and ensures existing users have role 'customer'.
        """
        # 1. Ensure Admin Account (Admin does not play games or accumulate scores)
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(
                username="admin",
                role="admin",
                avatar_color="#ef4444",
                total_score=0,
                puzzles_solved=0
            )
            admin.set_password("admin123")
            db.session.add(admin)
        else:
            admin.total_score = 0
            admin.puzzles_solved = 0
            admin.role = "admin"
            Score.query.filter_by(user_id=admin.id).delete()

        # 2. Ensure Customer Account
        customer = User.query.filter_by(username="customer").first()
        if not customer:
            customer = User(
                username="customer",
                role="customer",
                avatar_color="#10b981",
                total_score=3450,
                puzzles_solved=3
            )
            customer.set_password("customer123")
            db.session.add(customer)
            db.session.flush()

            # Seed sample completed games for this customer
            c_scores = [
                Score(user_id=customer.id, puzzle_id="sudoku_01", score_value=1250, time_seconds=92.5, moves_count=35, hints_used=1),
                Score(user_id=customer.id, puzzle_id="lights_01", score_value=1100, time_seconds=34.0, moves_count=9, hints_used=0),
                Score(user_id=customer.id, puzzle_id="nono_01", score_value=1100, time_seconds=48.2, moves_count=16, hints_used=0)
            ]
            db.session.add_all(c_scores)

        # 3. Normalize all non-admin users to 'customer'
        all_users = User.query.all()
        for u in all_users:
            if u.username != "admin" and (not u.role or u.role in ["user", "player", ""]):
                u.role = "customer"

        db.session.commit()

    @staticmethod
    def seed_puzzles():
        if Puzzle.query.first() is not None:
            return # Puzzles already seeded

        puzzles_seed = [
            # 1. SUDOKU PUZZLES
            {
                "id": "sudoku_01",
                "title": "Classic Sudoku Challenge 1",
                "category": "sudoku",
                "difficulty": "easy",
                "initial_state_json": json.dumps([
                    [5,3,0, 0,7,0, 0,0,0],
                    [6,0,0, 1,9,5, 0,0,0],
                    [0,9,8, 0,0,0, 0,6,0],

                    [8,0,0, 0,6,0, 0,0,3],
                    [4,0,0, 8,0,3, 0,0,1],
                    [7,0,0, 0,2,0, 0,0,6],

                    [0,6,0, 0,0,0, 2,8,0],
                    [0,0,0, 4,1,9, 0,0,5],
                    [0,0,0, 0,8,0, 0,7,9]
                ]),
                "solution_state_json": json.dumps([
                    [5,3,4, 6,7,8, 9,1,2],
                    [6,7,2, 1,9,5, 3,4,8],
                    [1,9,8, 3,4,2, 5,6,7],

                    [8,5,9, 7,6,1, 4,2,3],
                    [4,2,6, 8,5,3, 7,9,1],
                    [7,1,3, 9,2,4, 8,5,6],

                    [9,6,1, 5,3,7, 2,8,4],
                    [2,8,7, 4,1,9, 6,3,5],
                    [3,4,5, 2,8,6, 1,7,9]
                ]),
                "instructions": "Fill each 3x3 box, row, and column with digits 1-9."
            },
            {
                "id": "sudoku_02",
                "title": "Mindbender Sudoku 2",
                "category": "sudoku",
                "difficulty": "medium",
                "initial_state_json": json.dumps([
                    [0,0,0, 2,6,0, 7,0,1],
                    [6,8,0, 0,7,0, 0,9,0],
                    [1,9,0, 0,0,4, 5,0,0],

                    [8,2,0, 1,0,0, 0,4,0],
                    [0,0,4, 6,0,2, 9,0,0],
                    [0,5,0, 0,0,3, 0,2,8],

                    [0,0,9, 3,0,0, 0,7,4],
                    [0,4,0, 0,5,0, 0,3,6],
                    [7,0,3, 0,1,8, 0,0,0]
                ]),
                "solution_state_json": json.dumps([
                    [4,3,5, 2,6,9, 7,8,1],
                    [6,8,2, 5,7,1, 4,9,3],
                    [1,9,7, 8,3,4, 5,6,2],

                    [8,2,6, 1,9,5, 3,4,7],
                    [3,7,4, 6,8,2, 9,1,5],
                    [9,5,1, 7,4,3, 6,2,8],

                    [5,1,9, 3,2,6, 8,7,4],
                    [2,4,8, 9,5,7, 1,3,6],
                    [7,6,3, 4,1,8, 2,5,9]
                ]),
                "instructions": "Fill each cell with numbers 1 to 9."
            },

            # 2. NONOGRAM PUZZLES
            {
                "id": "nono_01",
                "title": "Pixel Heart Nonogram",
                "category": "nonogram",
                "difficulty": "easy",
                "initial_state_json": json.dumps([[0]*5 for _ in range(5)]),
                "solution_state_json": json.dumps([
                    [0,1,0,1,0],
                    [1,1,1,1,1],
                    [1,1,1,1,1],
                    [0,1,1,1,0],
                    [0,0,1,0,0]
                ]),
                "instructions": "Use row and column numbers to reveal the pixel heart image!"
            },
            {
                "id": "nono_02",
                "title": "Space Rocket Picross",
                "category": "nonogram",
                "difficulty": "medium",
                "initial_state_json": json.dumps([[0]*5 for _ in range(5)]),
                "solution_state_json": json.dumps([
                    [0,0,1,0,0],
                    [0,1,1,1,0],
                    [0,1,1,1,0],
                    [1,1,1,1,1],
                    [1,0,1,0,1]
                ]),
                "instructions": "Decode clues to build the space rocket grid."
            },

            # 3. LIGHTS OUT PUZZLES
            {
                "id": "lights_01",
                "title": "Lights Out 3x3 Warmup",
                "category": "lights_out",
                "difficulty": "easy",
                "initial_state_json": json.dumps([
                    [1,0,1],
                    [0,1,0],
                    [1,0,1]
                ]),
                "solution_state_json": json.dumps([
                    [0,0,0],
                    [0,0,0],
                    [0,0,0]
                ]),
                "instructions": "Toggle lights until every cell turns OFF."
            },
            {
                "id": "lights_02",
                "title": "Lights Out 4x4 Grid Matrix",
                "category": "lights_out",
                "difficulty": "medium",
                "initial_state_json": json.dumps([
                    [1,1,0,1],
                    [0,1,1,0],
                    [0,1,1,0],
                    [1,0,1,1]
                ]),
                "solution_state_json": json.dumps([
                    [0,0,0,0],
                    [0,0,0,0],
                    [0,0,0,0],
                    [0,0,0,0]
                ]),
                "instructions": "Turn off all 16 light cells."
            },

            # 4. MASTERMIND PUZZLES
            {
                "id": "master_01",
                "title": "Codebreaker Mission Alpha",
                "category": "mastermind",
                "difficulty": "easy",
                "initial_state_json": json.dumps([]),
                "solution_state_json": json.dumps(["Red", "Blue", "Green", "Yellow"]),
                "instructions": "Guess the 4-color sequence. Black peg = exact fit, White peg = right color."
            },
            {
                "id": "master_02",
                "title": "Cipher Break Hard",
                "category": "mastermind",
                "difficulty": "hard",
                "initial_state_json": json.dumps([]),
                "solution_state_json": json.dumps(["Purple", "Orange", "Red", "Blue"]),
                "instructions": "Cracking this cipher requires maximum logical deduction!"
            },

            # 5. SLIDING 15-PUZZLE
            {
                "id": "slide_01",
                "title": "8-Puzzle Starter (3x3)",
                "category": "sliding",
                "difficulty": "easy",
                "initial_state_json": json.dumps([
                    [1,2,3],
                    [4,0,6],
                    [7,5,8]
                ]),
                "solution_state_json": json.dumps([
                    [1,2,3],
                    [4,5,6],
                    [7,8,0]
                ]),
                "instructions": "Slide tile #5 down into empty space to arrange numbers 1 to 8!"
            },
            {
                "id": "slide_02",
                "title": "Classic 15-Puzzle (4x4)",
                "category": "sliding",
                "difficulty": "medium",
                "initial_state_json": json.dumps([
                    [1,2,3,4],
                    [5,6,7,8],
                    [9,10,0,12],
                    [13,14,11,15]
                ]),
                "solution_state_json": json.dumps([
                    [1,2,3,4],
                    [5,6,7,8],
                    [9,10,11,12],
                    [13,14,15,0]
                ]),
                "instructions": "Arrange numbers 1 through 15 in order!"
            }
        ]

        for p_data in puzzles_seed:
            puzzle = Puzzle(
                id=p_data["id"],
                title=p_data["title"],
                category=p_data["category"],
                difficulty=p_data["difficulty"],
                initial_state_json=p_data["initial_state_json"],
                solution_state_json=p_data["solution_state_json"],
                instructions=p_data["instructions"]
            )
            db.session.add(puzzle)

        # Seed Sample Users & Leaderboards for initial demo showcase
        u1 = User(username="LogicWizard", role="customer", avatar_color="#6366f1", total_score=4850, puzzles_solved=8)
        u1.set_password("pass123")
        u2 = User(username="PicrossQueen", role="customer", avatar_color="#ec4899", total_score=3920, puzzles_solved=6)
        u2.set_password("pass123")
        u3 = User(username="CyberMind", role="customer", avatar_color="#10b981", total_score=3100, puzzles_solved=5)
        u3.set_password("pass123")
        u4 = User(username="SudokuNinja", role="customer", avatar_color="#f59e0b", total_score=2450, puzzles_solved=4)
        u4.set_password("pass123")

        db.session.add_all([u1, u2, u3, u4])
        db.session.commit()

        # Seed scores
        scores_seed = [
            Score(user_id=u1.id, puzzle_id="sudoku_01", score_value=1450, time_seconds=84.2, moves_count=32, hints_used=0),
            Score(user_id=u1.id, puzzle_id="nono_01", score_value=1200, time_seconds=42.0, moves_count=14, hints_used=0),
            Score(user_id=u1.id, puzzle_id="lights_01", score_value=1100, time_seconds=30.5, moves_count=8, hints_used=0),
            Score(user_id=u2.id, puzzle_id="nono_01", score_value=1350, time_seconds=38.1, moves_count=12, hints_used=0),
            Score(user_id=u2.id, puzzle_id="master_01", score_value=1400, time_seconds=65.0, moves_count=4, hints_used=0),
            Score(user_id=u3.id, puzzle_id="slide_01", score_value=1250, time_seconds=22.8, moves_count=11, hints_used=0),
            Score(user_id=u4.id, puzzle_id="sudoku_01", score_value=1150, time_seconds=125.0, moves_count=40, hints_used=1),
        ]
        db.session.add_all(scores_seed)
        db.session.commit()
