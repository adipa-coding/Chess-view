import customtkinter as ctk
import chess
import chess.pgn
import os
import urllib.request
import io
import time
from PIL import Image

# Piece URL mapping (Alpha style)
PIECE_URLS = {
    'P': 'wP.png', 'N': 'wN.png', 'B': 'wB.png', 'R': 'wR.png', 'Q': 'wQ.png', 'K': 'wK.png',
    'p': 'bP.png', 'n': 'bN.png', 'b': 'bB.png', 'r': 'bR.png', 'q': 'bQ.png', 'k': 'bK.png'
}
BASE_URL = "https://raw.githubusercontent.com/oakmac/chessboardjs/master/website/img/chesspieces/alpha/"

# Themes (slightly refined for aesthetics)
THEMES = {
    "Classic Wood": {"light": "#EEDEA4", "dark": "#C89554"},
    "Ocean Blue": {"light": "#D1E4F6", "dark": "#4B7399"},
    "Lichess Green": {"light": "#F0D9B5", "dark": "#B58863"},
    "Dark Mode": {"light": "#787878", "dark": "#4B4B4B"}
}

class PGNViewerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Pro PGN Viewer")
        self.geometry("950x750")
        
        self.moves = []
        self.current_move_index = 0
        self.board = chess.Board()

        # Animation states
        self.is_animating = False
        self.anim_label = None
        self.anim_job = None
        self.pending_move = None
        self.pending_undo = False

        # Transparent image for clearing squares
        self.empty_image = ctk.CTkImage(Image.new("RGBA", (1, 1), (0, 0, 0, 0)), size=(65, 65))

        # Download pieces
        self.piece_images = {}
        self.download_pieces()

        # UI Setup
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=1)

        # Board Container (Left)
        self.board_container = ctk.CTkFrame(self, fg_color="transparent")
        self.board_container.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")

        # Make the grid 9x9 to fit the coordinates (ranks 0..7, rank labels 8, files 1..8, file labels 0)
        for i in range(1, 9):
            self.board_container.grid_rowconfigure(i-1, weight=1, uniform="square")
            self.board_container.grid_columnconfigure(i, weight=1, uniform="square")
            
        self.board_container.grid_rowconfigure(8, weight=0, minsize=30)
        self.board_container.grid_columnconfigure(0, weight=0, minsize=30)

        self.squares = {}
        self.current_theme = "Classic Wood"
        self.draw_board()

        # Controls Frame (Right)
        self.controls_frame = ctk.CTkFrame(self)
        self.controls_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.controls_frame.grid_columnconfigure(0, weight=1)

        # --- Game Info Panel ---
        self.game_info_frame = ctk.CTkFrame(self.controls_frame)
        self.game_info_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.game_info_frame.grid_columnconfigure(0, weight=1)
        
        self.matchup_label = ctk.CTkLabel(self.game_info_frame, text="White vs Black", font=("Arial", 16, "bold"))
        self.matchup_label.grid(row=0, column=0, pady=(10, 2), padx=10)
        
        self.site_label = ctk.CTkLabel(self.game_info_frame, text="Event / Site", font=("Arial", 12))
        self.site_label.grid(row=1, column=0, pady=2, padx=10)
        
        self.result_label = ctk.CTkLabel(self.game_info_frame, text="Result", font=("Arial", 14, "bold"))
        self.result_label.grid(row=2, column=0, pady=(2, 10), padx=10)


        # --- Settings & Loading ---
        self.settings_frame = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        self.settings_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        self.settings_frame.grid_columnconfigure((0,1), weight=1)

        self.theme_label = ctk.CTkLabel(self.settings_frame, text="Board Theme:", font=("Arial", 12, "bold"))
        self.theme_label.grid(row=0, column=0, padx=5, sticky="w")
        
        self.theme_dropdown = ctk.CTkOptionMenu(self.settings_frame, values=list(THEMES.keys()), command=self.change_theme)
        self.theme_dropdown.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        # PGN Input
        self.pgn_label = ctk.CTkLabel(self.controls_frame, text="Paste PGN or FEN Here:", font=("Arial", 12, "bold"))
        self.pgn_label.grid(row=2, column=0, padx=10, sticky="w")
        
        self.pgn_textbox = ctk.CTkTextbox(self.controls_frame, height=200)
        self.pgn_textbox.grid(row=3, column=0, padx=10, pady=5, sticky="ew")

        # Load Buttons
        self.load_buttons_frame = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        self.load_buttons_frame.grid(row=4, column=0, padx=10, pady=5, sticky="ew")
        self.load_buttons_frame.grid_columnconfigure((0, 1), weight=1)

        self.load_btn = ctk.CTkButton(self.load_buttons_frame, text="Load Text", command=self.load_pgn_from_text)
        self.load_btn.grid(row=0, column=0, padx=5, sticky="ew")

        self.browse_btn = ctk.CTkButton(self.load_buttons_frame, text="Browse File...", command=self.browse_file)
        self.browse_btn.grid(row=0, column=1, padx=5, sticky="ew")


        # --- Move Controls ---
        self.move_controls = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        self.move_controls.grid(row=5, column=0, padx=10, pady=20, sticky="ew")
        self.move_controls.grid_columnconfigure((0, 1), weight=1)

        self.prev_btn = ctk.CTkButton(self.move_controls, text="< Previous", command=self.prev_move, font=("Arial", 14))
        self.prev_btn.grid(row=0, column=0, padx=5, pady=5)

        self.next_btn = ctk.CTkButton(self.move_controls, text="Next >", command=self.next_move, font=("Arial", 14))
        self.next_btn.grid(row=0, column=1, padx=5, pady=5)
        
        self.info_label = ctk.CTkLabel(self.controls_frame, text="Move 0 / 0", font=("Arial", 16))
        self.info_label.grid(row=6, column=0, pady=(0, 10))

        self.update_board_ui()
        self.update_buttons()

    def download_pieces(self):
        os.makedirs("pieces_alpha", exist_ok=True)
        for symbol, filename in PIECE_URLS.items():
            filepath = os.path.join("pieces_alpha", filename)
            if not os.path.exists(filepath):
                try:
                    print(f"Downloading {filename}...")
                    urllib.request.urlretrieve(BASE_URL + filename, filepath)
                except Exception as e:
                    print(f"Failed to download {filename}: {e}")
            
            if os.path.exists(filepath):
                # Using 65x65 size for alpha pieces for crisp resolution
                img = Image.open(filepath)
                self.piece_images[symbol] = ctk.CTkImage(light_image=img, dark_image=img, size=(65, 65))

    def change_theme(self, choice):
        self.current_theme = choice
        self.recolor_board()

    def draw_board(self):
        # Draw Rank Labels (1-8)
        for row in range(8):
            rank_label = ctk.CTkLabel(self.board_container, text=str(8 - row), font=("Arial", 16, "bold"))
            rank_label.grid(row=row, column=0, sticky="e", padx=(0, 10))

        # Draw File Labels (A-H)
        files = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        for col in range(8):
            file_label = ctk.CTkLabel(self.board_container, text=files[col], font=("Arial", 16, "bold"))
            file_label.grid(row=8, column=col + 1, sticky="n", pady=(10, 0))

        # Draw Squares
        for row in range(8):
            for col in range(8):
                is_light = (row + col) % 2 == 0
                bg_color = THEMES[self.current_theme]["light"] if is_light else THEMES[self.current_theme]["dark"]

                rank = 7 - row
                file = col
                square_index = chess.square(file, rank)

                label = ctk.CTkLabel(
                    self.board_container, 
                    text="", 
                    fg_color=bg_color,
                    corner_radius=0
                )
                label.grid(row=row, column=col + 1, sticky="nsew") # col + 1 to offset rank labels
                self.squares[square_index] = label

    def recolor_board(self):
        for row in range(8):
            for col in range(8):
                is_light = (row + col) % 2 == 0
                bg_color = THEMES[self.current_theme]["light"] if is_light else THEMES[self.current_theme]["dark"]

                rank = 7 - row
                file = col
                square_index = chess.square(file, rank)
                self.squares[square_index].configure(fg_color=bg_color)

    def browse_file(self):
        filename = ctk.filedialog.askopenfilename(
            filetypes=[("PGN Files", "*.pgn"), ("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.pgn_textbox.delete("1.0", "end")
                    self.pgn_textbox.insert("1.0", content)
                    self.load_pgn_from_text(content)
            except Exception as e:
                self.info_label.configure(text=f"Error reading file: {e}")

    def load_pgn_from_text(self, text=None):
        self.finish_animation() # cancel any ongoing animation

        if not text:
            text = self.pgn_textbox.get("1.0", "end-1c").strip()
        if not text:
            self.info_label.configure(text="Please paste PGN/FEN text.")
            return

        # Check if FEN
        if len(text.split('/')) >= 7 and '{' not in text and '[' not in text:
            try:
                self.board.set_fen(text)
                self.moves = []
                self.current_move_index = 0
                self.matchup_label.configure(text="Static FEN Position")
                self.site_label.configure(text="Custom Board Setup")
                self.result_label.configure(text="")
                self.info_label.configure(text="FEN Loaded Successfully")
                self.update_board_ui()
                self.update_buttons()
                return
            except ValueError:
                pass # Not a valid FEN, fallback to PGN parsing

        # Parse as PGN
        try:
            game = chess.pgn.read_game(io.StringIO(text))
            if game:
                self.moves = list(game.mainline_moves())
                
                # Extract metadata
                white = game.headers.get("White", "Unknown Player")
                black = game.headers.get("Black", "Unknown Player")
                white_elo = game.headers.get("WhiteElo", "?")
                black_elo = game.headers.get("BlackElo", "?")
                site = game.headers.get("Site", "Unknown Site")
                event = game.headers.get("Event", "Unknown Event")
                result = game.headers.get("Result", "*")
                termination = game.headers.get("Termination", "")

                # Update UI elements
                self.matchup_label.configure(text=f"♔ {white} ({white_elo})  vs  ♚ {black} ({black_elo})")
                self.site_label.configure(text=f"📍 {event} - {site}")
                term_text = f" - {termination}" if termination else ""
                self.result_label.configure(text=f"🏆 Result: {result}{term_text}")
                
                self.board.reset()
                self.current_move_index = 0
                self.update_board_ui()
                self.update_buttons()
            else:
                self.info_label.configure(text="Failed to parse PGN.")
        except Exception as e:
            self.info_label.configure(text=f"Error parsing game: {e}")

    def update_board_ui(self):
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            label = self.squares[square]
            if piece:
                symbol = piece.symbol()
                img = self.piece_images.get(symbol)
                if img:
                    label.configure(image=img, text="")
                else:
                    label.configure(image=self.empty_image, text=symbol) # Fallback
            else:
                label.configure(image=self.empty_image, text="")

    # --- Animation Logic ---

    def finish_animation(self):
        if self.is_animating:
            self.is_animating = False
            if self.anim_job:
                self.after_cancel(self.anim_job)
                self.anim_job = None
            if self.anim_label:
                self.anim_label.destroy()
                self.anim_label = None
            self.finalize_move(self.pending_move, self.pending_undo)

    def finalize_move(self, move, is_undo):
        if is_undo:
            self.board.pop()
            self.current_move_index -= 1
        else:
            self.board.push(move)
            self.current_move_index += 1

        self.update_board_ui()
        self.update_buttons()

    def animate_move(self, move, is_undo=False):
        if is_undo:
            start_sq = move.to_square
            end_sq = move.from_square
            piece = self.board.piece_at(start_sq)
        else:
            start_sq = move.from_square
            end_sq = move.to_square
            piece = self.board.piece_at(start_sq)

        if not piece:
            # Fallback if somehow there's no piece
            self.finalize_move(move, is_undo)
            return

        start_lbl = self.squares[start_sq]
        end_lbl = self.squares[end_sq]
        
        self.update() # Ensure geometry is fresh
        start_x, start_y = start_lbl.winfo_x(), start_lbl.winfo_y()
        end_x, end_y = end_lbl.winfo_x(), end_lbl.winfo_y()

        # If window is minimized or not drawn properly, fallback
        if start_x == 0 and start_y == 0 and end_x == 0 and end_y == 0:
            self.finalize_move(move, is_undo)
            return

        self.is_animating = True
        self.pending_move = move
        self.pending_undo = is_undo

        img = self.piece_images.get(piece.symbol())
        start_lbl.configure(image=None) # Hide piece from start label

        w = start_lbl.winfo_width()
        h = start_lbl.winfo_height()

        self.anim_label = ctk.CTkLabel(self.board_container, text="", image=img, width=w, height=h)
        self.anim_label.place(x=start_x, y=start_y)
        self.anim_label.lift() # Ensure it's on top of everything

        duration = 0.15 # 150ms for Lichess-style snappy animation
        start_time = time.time()
        
        def anim_step():
            if not self.is_animating:
                return # Was cancelled
            
            now = time.time()
            t = (now - start_time) / duration
            if t > 1.0:
                t = 1.0
                
            # Ease out cubic function for ultra-smooth stopping
            eased_t = 1 - pow(1 - t, 3)
            
            curr_x = start_x + (end_x - start_x) * eased_t
            curr_y = start_y + (end_y - start_y) * eased_t
            
            self.anim_label.place(x=int(curr_x), y=int(curr_y))
            
            if t < 1.0:
                self.anim_job = self.after(10, anim_step)
            else:
                self.finish_animation()

        anim_step()

    # --- Move Controls ---

    def next_move(self):
        self.finish_animation()
        if self.current_move_index < len(self.moves):
            move = self.moves[self.current_move_index]
            self.animate_move(move, is_undo=False)

    def prev_move(self):
        self.finish_animation()
        if self.current_move_index > 0:
            move = self.moves[self.current_move_index - 1]
            self.animate_move(move, is_undo=True)

    def update_buttons(self):
        self.prev_btn.configure(state="normal" if self.current_move_index > 0 else "disabled")
        self.next_btn.configure(state="normal" if self.current_move_index < len(self.moves) else "disabled")
        self.info_label.configure(text=f"Move {self.current_move_index} / {len(self.moves)}")

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = PGNViewerApp()
    app.mainloop()
