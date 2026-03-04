"""
TechBot Games Collection
A collection of fun, simple games
Lightweight and entertaining
"""

import tkinter as tk
from tkinter import messagebox
import random
import time

# ============== THEME ==============
BG_DARK = "#0a0a0f"
BG_PANEL = "#1a1a2e"
BG_GAME = "#16213e"
FG_TEXT = "#d0d8e0"
ACCENT_GREEN = "#00ff9f"
ACCENT_CYAN = "#00d4ff"
ACCENT_RED = "#ff2255"
ACCENT_YELLOW = "#ffcc00"
ACCENT_PURPLE = "#c084fc"
BORDER = "#3e3e42"


class GameLauncher:
    """Main game launcher window"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("TechBot Games - Arcade")
        self.root.geometry("900x700")
        self.root.configure(bg=BG_DARK)
        self.root.resizable(False, False)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the launcher UI"""
        # Header
        header = tk.Frame(self.root, bg=BG_PANEL, height=80)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        title = tk.Label(header, text="🎮 TECHBOT GAMES ARCADE 🎮", 
                        bg=BG_PANEL, fg=ACCENT_GREEN,
                        font=("Consolas", 24, "bold"))
        title.pack(pady=20)
        
        # Game grid
        games_frame = tk.Frame(self.root, bg=BG_DARK)
        games_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)
        
        games = [
            ("🐍 SNAKE", "Classic snake game", self.launch_snake, ACCENT_GREEN),
            ("🏓 PONG", "Two-player paddle game", self.launch_pong, ACCENT_CYAN),
            ("⭕ TIC TAC TOE", "Classic strategy game", self.launch_tictactoe, ACCENT_YELLOW),
            ("🧠 MEMORY MATCH", "Card matching game", self.launch_memory, ACCENT_PURPLE),
            ("🎯 REACTION TIME", "Test your reflexes", self.launch_reaction, ACCENT_RED),
            ("🔢 NUMBER GUESSER", "Guess the number", self.launch_number_guess, "#ff9500"),
        ]
        
        row, col = 0, 0
        for name, desc, command, color in games:
            game_btn = tk.Frame(games_frame, bg=BG_PANEL, relief=tk.RAISED, bd=2)
            game_btn.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")
            
            btn = tk.Button(game_btn, text=name, bg=BG_PANEL, fg=color,
                           font=("Consolas", 16, "bold"), bd=0, pady=20,
                           activebackground=BG_GAME, activeforeground=color,
                           command=command, cursor="hand2")
            btn.pack(fill=tk.BOTH, expand=True)
            
            desc_lbl = tk.Label(game_btn, text=desc, bg=BG_PANEL, fg=FG_TEXT,
                               font=("Consolas", 9))
            desc_lbl.pack(pady=(0, 10))
            
            col += 1
            if col > 1:
                col = 0
                row += 1
        
        # Configure grid weights
        for i in range(3):
            games_frame.rowconfigure(i, weight=1)
        for i in range(2):
            games_frame.columnconfigure(i, weight=1)
        
        # Footer
        footer = tk.Frame(self.root, bg=BG_PANEL, height=40)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        footer.pack_propagate(False)
        
        footer_text = tk.Label(footer, text="Created by TechBot AI • Have Fun!", 
                              bg=BG_PANEL, fg=FG_TEXT, font=("Consolas", 9))
        footer_text.pack(pady=10)
    
    def launch_snake(self):
        SnakeGame(tk.Toplevel(self.root))
    
    def launch_pong(self):
        PongGame(tk.Toplevel(self.root))
    
    def launch_tictactoe(self):
        TicTacToeGame(tk.Toplevel(self.root))
    
    def launch_memory(self):
        MemoryGame(tk.Toplevel(self.root))
    
    def launch_reaction(self):
        ReactionGame(tk.Toplevel(self.root))
    
    def launch_number_guess(self):
        NumberGuessGame(tk.Toplevel(self.root))


class SnakeGame:
    """Classic Snake Game"""
    
    def __init__(self, window):
        self.window = window
        self.window.title("Snake Game")
        self.window.geometry("600x650")
        self.window.configure(bg=BG_DARK)
        self.window.resizable(False, False)
        
        self.cell_size = 20
        self.grid_width = 30
        self.grid_height = 30
        self.speed = 100
        
        self.snake = [(15, 15), (15, 14), (15, 13)]
        self.direction = "Right"
        self.food = self.spawn_food()
        self.score = 0
        self.game_over = False
        
        self.setup_ui()
        self.window.bind("<KeyPress>", self.change_direction)
        self.game_loop()
    
    def setup_ui(self):
        # Score
        self.score_label = tk.Label(self.window, text=f"Score: {self.score}",
                                    bg=BG_DARK, fg=ACCENT_GREEN,
                                    font=("Consolas", 16, "bold"))
        self.score_label.pack(pady=10)
        
        # Canvas
        self.canvas = tk.Canvas(self.window, 
                               width=self.grid_width * self.cell_size,
                               height=self.grid_height * self.cell_size,
                               bg="#000000", highlightthickness=0)
        self.canvas.pack()
        
        # Instructions
        info = tk.Label(self.window, text="Use Arrow Keys to Move",
                       bg=BG_DARK, fg=FG_TEXT, font=("Consolas", 10))
        info.pack(pady=5)
    
    def spawn_food(self):
        while True:
            food = (random.randint(0, self.grid_width - 1),
                   random.randint(0, self.grid_height - 1))
            if food not in self.snake:
                return food
    
    def change_direction(self, event):
        key = event.keysym
        opposite = {"Left": "Right", "Right": "Left", "Up": "Down", "Down": "Up"}
        
        if key in ["Left", "Right", "Up", "Down"]:
            if opposite.get(key) != self.direction:
                self.direction = key
    
    def game_loop(self):
        if self.game_over:
            return
        
        # Move snake
        head_x, head_y = self.snake[0]
        
        if self.direction == "Left":
            new_head = (head_x - 1, head_y)
        elif self.direction == "Right":
            new_head = (head_x + 1, head_y)
        elif self.direction == "Up":
            new_head = (head_x, head_y - 1)
        else:  # Down
            new_head = (head_x, head_y + 1)
        
        # Check collisions
        if (new_head[0] < 0 or new_head[0] >= self.grid_width or
            new_head[1] < 0 or new_head[1] >= self.grid_height or
            new_head in self.snake):
            self.end_game()
            return
        
        self.snake.insert(0, new_head)
        
        # Check food
        if new_head == self.food:
            self.score += 10
            self.score_label.config(text=f"Score: {self.score}")
            self.food = self.spawn_food()
            # Increase speed slightly
            self.speed = max(50, self.speed - 2)
        else:
            self.snake.pop()
        
        self.draw()
        self.window.after(self.speed, self.game_loop)
    
    def draw(self):
        self.canvas.delete("all")
        
        # Draw snake
        for i, (x, y) in enumerate(self.snake):
            color = ACCENT_GREEN if i == 0 else "#00cc7f"
            self.canvas.create_rectangle(
                x * self.cell_size, y * self.cell_size,
                (x + 1) * self.cell_size, (y + 1) * self.cell_size,
                fill=color, outline="#00ff9f"
            )
        
        # Draw food
        fx, fy = self.food
        self.canvas.create_oval(
            fx * self.cell_size + 2, fy * self.cell_size + 2,
            (fx + 1) * self.cell_size - 2, (fy + 1) * self.cell_size - 2,
            fill=ACCENT_RED, outline=ACCENT_YELLOW, width=2
        )
    
    def end_game(self):
        self.game_over = True
        self.canvas.create_text(
            self.grid_width * self.cell_size // 2,
            self.grid_height * self.cell_size // 2,
            text=f"GAME OVER!\nScore: {self.score}",
            fill=ACCENT_RED, font=("Consolas", 24, "bold")
        )


class PongGame:
    """Two-Player Pong Game"""
    
    def __init__(self, window):
        self.window = window
        self.window.title("Pong Game")
        self.window.geometry("800x600")
        self.window.configure(bg=BG_DARK)
        self.window.resizable(False, False)
        
        self.canvas = tk.Canvas(self.window, width=800, height=550, 
                               bg="#000000", highlightthickness=0)
        self.canvas.pack(pady=25)
        
        # Game state
        self.paddle1_y = 250
        self.paddle2_y = 250
        self.paddle_height = 100
        self.paddle_width = 15
        self.paddle_speed = 20
        
        self.ball_x = 400
        self.ball_y = 275
        self.ball_dx = 4
        self.ball_dy = 4
        self.ball_size = 15
        
        self.score1 = 0
        self.score2 = 0
        
        self.keys_pressed = set()
        
        # UI
        self.score_text = self.canvas.create_text(
            400, 30, text="Player 1: 0  |  Player 2: 0",
            fill=ACCENT_CYAN, font=("Consolas", 16, "bold")
        )
        
        self.paddle1 = self.canvas.create_rectangle(
            30, self.paddle1_y, 30 + self.paddle_width, 
            self.paddle1_y + self.paddle_height,
            fill=ACCENT_GREEN, outline=ACCENT_GREEN
        )
        
        self.paddle2 = self.canvas.create_rectangle(
            755, self.paddle2_y, 770,
            self.paddle2_y + self.paddle_height,
            fill=ACCENT_CYAN, outline=ACCENT_CYAN
        )
        
        self.ball = self.canvas.create_oval(
            self.ball_x, self.ball_y,
            self.ball_x + self.ball_size, self.ball_y + self.ball_size,
            fill=ACCENT_YELLOW, outline=ACCENT_YELLOW
        )
        
        # Center line
        for y in range(0, 550, 20):
            self.canvas.create_line(400, y, 400, y + 10, fill="#333333", width=2)
        
        # Instructions
        info = tk.Label(self.window, 
                       text="Player 1: W/S  |  Player 2: ↑/↓",
                       bg=BG_DARK, fg=FG_TEXT, font=("Consolas", 11))
        info.pack()
        
        self.window.bind("<KeyPress>", self.key_press)
        self.window.bind("<KeyRelease>", self.key_release)
        
        self.game_loop()
    
    def key_press(self, event):
        self.keys_pressed.add(event.keysym.lower())
    
    def key_release(self, event):
        self.keys_pressed.discard(event.keysym.lower())
    
    def game_loop(self):
        # Move paddles
        if 'w' in self.keys_pressed and self.paddle1_y > 0:
            self.paddle1_y -= self.paddle_speed
        if 's' in self.keys_pressed and self.paddle1_y < 450:
            self.paddle1_y += self.paddle_speed
        if 'up' in self.keys_pressed and self.paddle2_y > 0:
            self.paddle2_y -= self.paddle_speed
        if 'down' in self.keys_pressed and self.paddle2_y < 450:
            self.paddle2_y += self.paddle_speed
        
        # Move ball
        self.ball_x += self.ball_dx
        self.ball_y += self.ball_dy
        
        # Ball collision with top/bottom
        if self.ball_y <= 0 or self.ball_y >= 535:
            self.ball_dy = -self.ball_dy
        
        # Ball collision with paddles
        if (30 <= self.ball_x <= 45 and 
            self.paddle1_y <= self.ball_y <= self.paddle1_y + self.paddle_height):
            self.ball_dx = abs(self.ball_dx)
            self.ball_dy += random.choice([-1, 0, 1])
        
        if (755 <= self.ball_x <= 770 and
            self.paddle2_y <= self.ball_y <= self.paddle2_y + self.paddle_height):
            self.ball_dx = -abs(self.ball_dx)
            self.ball_dy += random.choice([-1, 0, 1])
        
        # Score points
        if self.ball_x < 0:
            self.score2 += 1
            self.reset_ball()
        elif self.ball_x > 785:
            self.score1 += 1
            self.reset_ball()
        
        # Update UI
        self.canvas.coords(self.paddle1, 30, self.paddle1_y,
                          45, self.paddle1_y + self.paddle_height)
        self.canvas.coords(self.paddle2, 755, self.paddle2_y,
                          770, self.paddle2_y + self.paddle_height)
        self.canvas.coords(self.ball, self.ball_x, self.ball_y,
                          self.ball_x + self.ball_size, 
                          self.ball_y + self.ball_size)
        self.canvas.itemconfig(self.score_text,
                              text=f"Player 1: {self.score1}  |  Player 2: {self.score2}")
        
        self.window.after(30, self.game_loop)
    
    def reset_ball(self):
        self.ball_x = 400
        self.ball_y = 275
        self.ball_dx = random.choice([-4, 4])
        self.ball_dy = random.choice([-4, -2, 2, 4])


class TicTacToeGame:
    """Classic Tic Tac Toe"""
    
    def __init__(self, window):
        self.window = window
        self.window.title("Tic Tac Toe")
        self.window.geometry("500x600")
        self.window.configure(bg=BG_DARK)
        self.window.resizable(False, False)
        
        self.current_player = "X"
        self.board = [""] * 9
        self.game_over = False
        
        self.setup_ui()
    
    def setup_ui(self):
        # Header
        header = tk.Frame(self.window, bg=BG_DARK)
        header.pack(pady=20)
        
        self.status_label = tk.Label(header, text="Player X's Turn",
                                     bg=BG_DARK, fg=ACCENT_CYAN,
                                     font=("Consolas", 18, "bold"))
        self.status_label.pack()
        
        # Game board
        board_frame = tk.Frame(self.window, bg=BG_DARK)
        board_frame.pack(pady=20)
        
        self.buttons = []
        for i in range(9):
            btn = tk.Button(board_frame, text="", font=("Consolas", 32, "bold"),
                           width=4, height=2, bg=BG_PANEL, fg=ACCENT_GREEN,
                           activebackground=BG_GAME,
                           command=lambda idx=i: self.make_move(idx))
            btn.grid(row=i // 3, column=i % 3, padx=5, pady=5)
            self.buttons.append(btn)
        
        # Reset button
        reset_btn = tk.Button(self.window, text="New Game", 
                             font=("Consolas", 12, "bold"),
                             bg=BG_PANEL, fg=ACCENT_YELLOW,
                             command=self.reset_game, padx=20, pady=10)
        reset_btn.pack(pady=20)
    
    def make_move(self, idx):
        if self.board[idx] == "" and not self.game_over:
            self.board[idx] = self.current_player
            color = ACCENT_CYAN if self.current_player == "X" else ACCENT_RED
            self.buttons[idx].config(text=self.current_player, fg=color)
            
            if self.check_winner():
                self.status_label.config(text=f"Player {self.current_player} Wins!",
                                        fg=ACCENT_GREEN)
                self.game_over = True
            elif "" not in self.board:
                self.status_label.config(text="It's a Draw!", fg=ACCENT_YELLOW)
                self.game_over = True
            else:
                self.current_player = "O" if self.current_player == "X" else "X"
                color = ACCENT_CYAN if self.current_player == "X" else ACCENT_RED
                self.status_label.config(text=f"Player {self.current_player}'s Turn",
                                        fg=color)
    
    def check_winner(self):
        wins = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],  # Rows
            [0, 3, 6], [1, 4, 7], [2, 5, 8],  # Columns
            [0, 4, 8], [2, 4, 6]              # Diagonals
        ]
        
        for combo in wins:
            if (self.board[combo[0]] == self.board[combo[1]] == 
                self.board[combo[2]] != ""):
                # Highlight winning combo
                for idx in combo:
                    self.buttons[idx].config(bg=ACCENT_GREEN, fg=BG_DARK)
                return True
        return False
    
    def reset_game(self):
        self.current_player = "X"
        self.board = [""] * 9
        self.game_over = False
        
        for btn in self.buttons:
            btn.config(text="", bg=BG_PANEL, fg=ACCENT_GREEN)
        
        self.status_label.config(text="Player X's Turn", fg=ACCENT_CYAN)


class MemoryGame:
    """Memory Card Matching Game"""
    
    def __init__(self, window):
        self.window = window
        self.window.title("Memory Match")
        self.window.geometry("600x700")
        self.window.configure(bg=BG_DARK)
        self.window.resizable(False, False)
        
        self.symbols = ["🎮", "🎯", "🎲", "🎪", "🎨", "🎭", "🎺", "🎸"] * 2
        random.shuffle(self.symbols)
        
        self.cards = []
        self.revealed = []
        self.matched = []
        self.moves = 0
        self.can_click = True
        
        self.setup_ui()
    
    def setup_ui(self):
        # Header
        self.moves_label = tk.Label(self.window, text=f"Moves: {self.moves}",
                                    bg=BG_DARK, fg=ACCENT_PURPLE,
                                    font=("Consolas", 16, "bold"))
        self.moves_label.pack(pady=20)
        
        # Game board
        board_frame = tk.Frame(self.window, bg=BG_DARK)
        board_frame.pack(pady=20)
        
        for i in range(16):
            btn = tk.Button(board_frame, text="?", font=("Consolas", 28),
                           width=4, height=2, bg=BG_PANEL, fg=FG_TEXT,
                           command=lambda idx=i: self.reveal_card(idx))
            btn.grid(row=i // 4, column=i % 4, padx=5, pady=5)
            self.cards.append(btn)
        
        # Reset button
        reset_btn = tk.Button(self.window, text="New Game",
                             font=("Consolas", 12, "bold"),
                             bg=BG_PANEL, fg=ACCENT_YELLOW,
                             command=self.reset_game, padx=20, pady=10)
        reset_btn.pack(pady=20)
    
    def reveal_card(self, idx):
        if not self.can_click or idx in self.matched or idx in self.revealed:
            return
        
        self.cards[idx].config(text=self.symbols[idx], fg=ACCENT_CYAN)
        self.revealed.append(idx)
        
        if len(self.revealed) == 2:
            self.moves += 1
            self.moves_label.config(text=f"Moves: {self.moves}")
            self.can_click = False
            self.window.after(800, self.check_match)
    
    def check_match(self):
        idx1, idx2 = self.revealed
        
        if self.symbols[idx1] == self.symbols[idx2]:
            # Match!
            self.matched.extend([idx1, idx2])
            self.cards[idx1].config(bg=ACCENT_GREEN, fg=BG_DARK)
            self.cards[idx2].config(bg=ACCENT_GREEN, fg=BG_DARK)
            
            if len(self.matched) == 16:
                self.moves_label.config(text=f"You Won in {self.moves} moves!")
        else:
            # No match
            self.cards[idx1].config(text="?", fg=FG_TEXT)
            self.cards[idx2].config(text="?", fg=FG_TEXT)
        
        self.revealed = []
        self.can_click = True
    
    def reset_game(self):
        self.symbols = ["🎮", "🎯", "🎲", "🎪", "🎨", "🎭", "🎺", "🎸"] * 2
        random.shuffle(self.symbols)
        self.revealed = []
        self.matched = []
        self.moves = 0
        self.can_click = True
        
        for btn in self.cards:
            btn.config(text="?", bg=BG_PANEL, fg=FG_TEXT)
        
        self.moves_label.config(text=f"Moves: {self.moves}")


class ReactionGame:
    """Reaction Time Test"""
    
    def __init__(self, window):
        self.window = window
        self.window.title("Reaction Time Test")
        self.window.geometry("600x500")
        self.window.configure(bg=BG_DARK)
        self.window.resizable(False, False)
        
        self.waiting = False
        self.start_time = 0
        self.best_time = None
        
        self.setup_ui()
    
    def setup_ui(self):
        # Title
        tk.Label(self.window, text="Reaction Time Test",
                bg=BG_DARK, fg=ACCENT_CYAN,
                font=("Consolas", 20, "bold")).pack(pady=30)
        
        # Game area
        self.game_frame = tk.Frame(self.window, bg=ACCENT_RED, 
                                   width=500, height=300)
        self.game_frame.pack(pady=20)
        self.game_frame.pack_propagate(False)
        
        self.status_label = tk.Label(self.game_frame, 
                                     text="Click to Start",
                                     bg=ACCENT_RED, fg="white",
                                     font=("Consolas", 24, "bold"))
        self.status_label.pack(expand=True)
        
        self.game_frame.bind("<Button-1>", self.handle_click)
        self.status_label.bind("<Button-1>", self.handle_click)
        
        # Best time
        self.best_label = tk.Label(self.window, text="Best: ---",
                                   bg=BG_DARK, fg=ACCENT_GREEN,
                                   font=("Consolas", 14))
        self.best_label.pack(pady=10)
        
        # Instructions
        tk.Label(self.window, 
                text="Wait for GREEN, then click as fast as you can!",
                bg=BG_DARK, fg=FG_TEXT,
                font=("Consolas", 10)).pack(pady=5)
    
    def handle_click(self, event):
        if self.waiting:
            # Too early!
            self.game_frame.config(bg=ACCENT_RED)
            self.status_label.config(bg=ACCENT_RED, 
                                    text="Too Early!\nClick to Retry")
            self.waiting = False
        elif self.start_time > 0:
            # Calculate reaction time
            reaction_time = int((time.time() - self.start_time) * 1000)
            self.game_frame.config(bg=ACCENT_CYAN)
            self.status_label.config(bg=ACCENT_CYAN,
                                    text=f"{reaction_time} ms\nClick to Retry",
                                    fg=BG_DARK)
            
            if self.best_time is None or reaction_time < self.best_time:
                self.best_time = reaction_time
                self.best_label.config(text=f"Best: {self.best_time} ms")
            
            self.start_time = 0
        else:
            # Start new round
            self.game_frame.config(bg=ACCENT_RED)
            self.status_label.config(bg=ACCENT_RED, text="Wait...", fg="white")
            self.waiting = True
            
            delay = random.randint(1000, 4000)
            self.window.after(delay, self.show_green)
    
    def show_green(self):
        if self.waiting:
            self.game_frame.config(bg=ACCENT_GREEN)
            self.status_label.config(bg=ACCENT_GREEN, text="CLICK!", fg=BG_DARK)
            self.start_time = time.time()
            self.waiting = False


class NumberGuessGame:
    """Number Guessing Game"""
    
    def __init__(self, window):
        self.window = window
        self.window.title("Number Guesser")
        self.window.geometry("500x600")
        self.window.configure(bg=BG_DARK)
        self.window.resizable(False, False)
        
        self.min_num = 1
        self.max_num = 100
        self.target = random.randint(self.min_num, self.max_num)
        self.attempts = 0
        self.game_over = False
        
        self.setup_ui()
    
    def setup_ui(self):
        # Title
        tk.Label(self.window, text="Number Guesser",
                bg=BG_DARK, fg="#ff9500",
                font=("Consolas", 22, "bold")).pack(pady=30)
        
        # Instructions
        tk.Label(self.window, text=f"Guess a number between {self.min_num} and {self.max_num}",
                bg=BG_DARK, fg=FG_TEXT,
                font=("Consolas", 12)).pack(pady=10)
        
        # Attempts
        self.attempts_label = tk.Label(self.window, text=f"Attempts: {self.attempts}",
                                       bg=BG_DARK, fg=ACCENT_CYAN,
                                       font=("Consolas", 14))
        self.attempts_label.pack(pady=10)
        
        # Input
        self.entry = tk.Entry(self.window, font=("Consolas", 16),
                             width=10, justify="center",
                             bg=BG_PANEL, fg=FG_TEXT,
                             insertbackground=FG_TEXT)
        self.entry.pack(pady=20)
        self.entry.focus()
        
        # Guess button
        guess_btn = tk.Button(self.window, text="Guess",
                             font=("Consolas", 14, "bold"),
                             bg=ACCENT_GREEN, fg=BG_DARK,
                             command=self.make_guess,
                             padx=40, pady=10)
        guess_btn.pack(pady=10)
        
        self.entry.bind("<Return>", lambda e: self.make_guess())
        
        # Feedback
        self.feedback_label = tk.Label(self.window, text="",
                                       bg=BG_DARK, fg=ACCENT_YELLOW,
                                       font=("Consolas", 16, "bold"))
        self.feedback_label.pack(pady=20)
        
        # History
        self.history_frame = tk.Frame(self.window, bg=BG_DARK)
        self.history_frame.pack(pady=10)
        
        tk.Label(self.history_frame, text="Your Guesses:",
                bg=BG_DARK, fg=FG_TEXT,
                font=("Consolas", 11)).pack()
        
        self.history_label = tk.Label(self.history_frame, text="",
                                      bg=BG_DARK, fg=FG_TEXT,
                                      font=("Consolas", 10))
        self.history_label.pack()
        
        # Reset button
        reset_btn = tk.Button(self.window, text="New Game",
                             font=("Consolas", 11),
                             bg=BG_PANEL, fg=ACCENT_YELLOW,
                             command=self.reset_game,
                             padx=20, pady=5)
        reset_btn.pack(pady=10)
        
        self.guesses = []
    
    def make_guess(self):
        if self.game_over:
            return
        
        try:
            guess = int(self.entry.get())
            self.entry.delete(0, tk.END)
            
            if guess < self.min_num or guess > self.max_num:
                self.feedback_label.config(text=f"Please enter {self.min_num}-{self.max_num}",
                                          fg=ACCENT_RED)
                return
            
            self.attempts += 1
            self.attempts_label.config(text=f"Attempts: {self.attempts}")
            self.guesses.append(guess)
            self.history_label.config(text=" • ".join(map(str, self.guesses[-10:])))
            
            if guess == self.target:
                self.feedback_label.config(
                    text=f"🎉 Correct! You got it in {self.attempts} tries!",
                    fg=ACCENT_GREEN
                )
                self.game_over = True
            elif guess < self.target:
                self.feedback_label.config(text="📈 Higher!", fg=ACCENT_YELLOW)
            else:
                self.feedback_label.config(text="📉 Lower!", fg=ACCENT_CYAN)
        
        except ValueError:
            self.feedback_label.config(text="Please enter a valid number",
                                      fg=ACCENT_RED)
    
    def reset_game(self):
        self.target = random.randint(self.min_num, self.max_num)
        self.attempts = 0
        self.game_over = False
        self.guesses = []
        
        self.attempts_label.config(text=f"Attempts: {self.attempts}")
        self.feedback_label.config(text="")
        self.history_label.config(text="")
        self.entry.delete(0, tk.END)
        self.entry.focus()


def main():
    root = tk.Tk()
    app = GameLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
