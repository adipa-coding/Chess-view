"""
Premium Chess PGN Viewer
========================
A fully overhauled, Lichess-inspired chess PGN viewer built with CustomTkinter.

Architecture highlights:
  - Single unified tkinter.Canvas for the board (no Label grid)
  - Cubic ease-out animation engine (f(t) = 1 - (1-t)^3)
  - Dynamic move duration (120ms – 200ms based on distance)
  - Simultaneous castling animations (king + rook together)
  - Debounced navigation (interrupt + graceful skip)
  - Multi-pack piece asset system with auto-download
  - Lichess-accurate board themes with last-move highlights
  - Square-click interaction with highlight ring
  - LANCZOS-filtered piece rescaling on resize
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import chess
import chess.pgn
import os
import io
import time
import math
import threading
import urllib.request
import re
from PIL import Image, ImageTk, ImageDraw, ImageFilter

# ──────────────────────────────────────────────
#  PIECE PACK DEFINITIONS
#  Each pack maps a piece symbol → filename.
#  All packs are fetched from public GitHub repos.
# ──────────────────────────────────────────────
PIECE_PACKS = {
    "Alpha": {
        "base_url": "https://raw.githubusercontent.com/oakmac/chessboardjs/master/website/img/chesspieces/alpha/",
        "files": {
            "P": "wP.png", "N": "wN.png", "B": "wB.png",
            "R": "wR.png", "Q": "wQ.png", "K": "wK.png",
            "p": "bP.png", "n": "bN.png", "b": "bB.png",
            "r": "bR.png", "q": "bQ.png", "k": "bK.png",
        },
        "folder": "pieces_alpha",
    },
    "Merida": {
        "base_url": "https://raw.githubusercontent.com/oakmac/chessboardjs/master/website/img/chesspieces/merida/",
        "files": {
            "P": "wP.png", "N": "wN.png", "B": "wB.png",
            "R": "wR.png", "Q": "wQ.png", "K": "wK.png",
            "p": "bP.png", "n": "bN.png", "b": "bB.png",
            "r": "bR.png", "q": "bQ.png", "k": "bK.png",
        },
        "folder": "pieces_merida",
    },
    "Leipzig": {
        "base_url": "https://raw.githubusercontent.com/oakmac/chessboardjs/master/website/img/chesspieces/leipzig/",
        "files": {
            "P": "wP.png", "N": "wN.png", "B": "wB.png",
            "R": "wR.png", "Q": "wQ.png", "K": "wK.png",
            "p": "bP.png", "n": "bN.png", "b": "bB.png",
            "r": "bR.png", "q": "bQ.png", "k": "bK.png",
        },
        "folder": "pieces_leipzig",
    },
    "Wikipedia": {
        "base_url": "https://raw.githubusercontent.com/oakmac/chessboardjs/master/website/img/chesspieces/wikipedia/",
        "files": {
            "P": "wP.png", "N": "wN.png", "B": "wB.png",
            "R": "wR.png", "Q": "wQ.png", "K": "wK.png",
            "p": "bP.png", "n": "bN.png", "b": "bB.png",
            "r": "bR.png", "q": "bQ.png", "k": "bK.png",
        },
        "folder": "pieces_wikipedia",
    },
}

# ──────────────────────────────────────────────
#  BOARD THEMES
#  last_move colours use (R,G,B,A) tuples for
#  direct PIL compositing.
# ──────────────────────────────────────────────
THEMES = {
    "Lichess Wood": {
        "light":     "#f0d9b5",
        "dark":      "#b58863",
        "last_move": (155, 199,   0, 105),   # golden-green overlay
        "selected":  (20,  85,  30, 128),    # deep green ring
        "coords":    "#b58863",              # coordinate label color
    },
    "Ocean Blue": {
        "light":     "#dee3e6",
        "dark":      "#8ca2ad",
        "last_move": (115, 203, 235, 128),
        "selected":  ( 30,  80, 190, 128),
        "coords":    "#8ca2ad",
    },
    "Tournament Green": {
        "light":     "#ffffdd",
        "dark":      "#86a666",
        "last_move": (247, 247, 121, 160),
        "selected":  ( 20, 140,  20, 128),
        "coords":    "#86a666",
    },
    "Dark Marble": {
        "light":     "#787878",
        "dark":      "#4b4b4b",
        "last_move": (200, 200,  80, 120),
        "selected":  (180,  60,  60, 128),
        "coords":    "#888888",
    },
    "Rose Gold": {
        "light":     "#f2d0c4",
        "dark":      "#c0806a",
        "last_move": (220, 120,  60, 110),
        "selected":  (180,  40, 100, 128),
        "coords":    "#c0806a",
    },
    "Midnight": {
        "light":     "#3d4a6b",
        "dark":      "#1e2640",
        "last_move": ( 80, 180, 240, 110),
        "selected":  (100, 220, 255, 128),
        "coords":    "#5a6a90",
    },
}

# ──────────────────────────────────────────────
#  ANIMATION CONSTANTS
# ──────────────────────────────────────────────
ANIM_MIN_MS   = 120    # milliseconds for 1-square move
ANIM_MAX_MS   = 200    # milliseconds for longest diagonal
ANIM_TICK_MS  = 8      # ~120 fps inner loop tick
COORD_FONT    = ("Segoe UI", 10, "bold")  # coordinate labels on canvas

# ──────────────────────────────────────────────
#  HELPER: hex colour → (R,G,B) tuple
# ──────────────────────────────────────────────
def hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


# ═══════════════════════════════════════════════════════════════════
#  CHESS BOARD CANVAS WIDGET
#  All board drawing and animation live here.
# ═══════════════════════════════════════════════════════════════════
class ChessBoardCanvas(tk.Canvas):
    """
    A single Canvas that renders the entire chess board:
      - Coloured squares drawn as filled rectangles
      - Rank/file coordinate labels drawn as canvas text items
      - Piece images rendered as canvas image items
      - Highlight overlays (last-move, selected-square) composited via PIL

    Animation is driven by self.after() scheduling with cubic ease-out
    interpolation.  Multiple simultaneous animations (castling) are
    supported by keeping a list of active animation descriptors.
    """

    def __init__(self, master, size: int, theme_name: str, **kwargs):
        super().__init__(
            master,
            width=size,
            height=size,
            bg="#1a1a2e",          # dark surround
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        # ── State ────────────────────────────────────────
        self.board_size   = size          # total canvas pixels
        self.sq_size      = size // 8     # pixels per square (will update on resize)
        self.theme_name   = theme_name
        self.theme        = THEMES[theme_name]
        self.flipped      = False         # board orientation

        # Chess board state (injected from parent app)
        self.chess_board: chess.Board | None = None

        # PIL images per piece symbol (resized to sq_size)
        self.piece_pil: dict[str, Image.Image] = {}   # original PIL images (pack resolution)
        self.piece_tk:  dict[str, ImageTk.PhotoImage] = {}  # tk-ready at current sq_size

        # Canvas item IDs for pieces: square_index → canvas item id
        self.piece_items: dict[int, int] = {}

        # Canvas item IDs for highlight overlays
        self._last_move_items: list[int] = []   # rectangles / overlays
        self._selected_item: int | None  = None  # selected-square ring

        # ── Animation state ─────────────────────────────
        # Each entry: {"item": canvas_id, "sx": float, "sy": float,
        #              "ex": float, "ey": float, "t": float,
        #              "duration_ms": float, "start_ms": float,
        #              "on_done": callable | None}
        self._animations: list[dict] = []
        self._anim_job: str | None   = None

        # ── Interaction ──────────────────────────────────
        self._selected_square: int | None = None   # chess.Square index
        self._last_move:  tuple | None    = None   # (from_sq, to_sq)

        # Click binding
        self.bind("<Button-1>", self._on_click)
        # Resize binding
        self.bind("<Configure>", self._on_resize)

    # ─────────────────────────────────────────
    #  COORDINATE → PIXEL HELPERS
    # ─────────────────────────────────────────
    def _sq_to_xy(self, sq: int) -> tuple[float, float]:
        """Return the top-left (x, y) pixel of the given chess square."""
        file = chess.square_file(sq)
        rank = chess.square_rank(sq)
        if self.flipped:
            col = 7 - file
            row = rank
        else:
            col = file
            row = 7 - rank
        return col * self.sq_size, row * self.sq_size

    def _xy_to_sq(self, px: float, py: float) -> int | None:
        """Return chess.Square index for pixel (px, py), or None if outside."""
        col = int(px // self.sq_size)
        row = int(py // self.sq_size)
        if not (0 <= col < 8 and 0 <= row < 8):
            return None
        if self.flipped:
            file = 7 - col
            rank = row
        else:
            file = col
            rank = 7 - row
        return chess.square(file, rank)

    def _sq_center(self, sq: int) -> tuple[float, float]:
        x, y = self._sq_to_xy(sq)
        half = self.sq_size / 2
        return x + half, y + half

    # ─────────────────────────────────────────
    #  FULL BOARD REDRAW
    # ─────────────────────────────────────────
    def full_redraw(self):
        """
        Wipe and repaint the entire canvas:
          1. Board squares
          2. Coordinate labels
          3. Highlight overlays (last-move)
          4. All pieces at rest positions
        """
        self.delete("all")
        self.piece_items.clear()
        self._last_move_items.clear()
        self._selected_item = None

        self._draw_squares()
        self._draw_coords()
        self._draw_last_move_highlights()
        self._draw_pieces()
        self._draw_selected_highlight()

    def _draw_squares(self):
        """Draw 64 coloured rectangles for the board."""
        light = self.theme["light"]
        dark  = self.theme["dark"]
        s = self.sq_size
        for row in range(8):
            for col in range(8):
                is_light = (row + col) % 2 == 0
                color = light if is_light else dark
                self.create_rectangle(
                    col * s, row * s,
                    (col + 1) * s, (row + 1) * s,
                    fill=color, outline="", tags="square"
                )

    def _draw_coords(self):
        """
        Draw rank numbers (1-8) on left edge of each rank row and
        file letters (a-h) on bottom edge of each file column.
        These overlap the squares for a Lichess-style embedded look.
        """
        s    = self.sq_size
        cols = self.theme["coords"]
        files = "abcdefgh"

        for i in range(8):
            # --- Rank numbers on the left side of rank row ---
            if self.flipped:
                rank_num = str(i + 1)
            else:
                rank_num = str(8 - i)

            self.create_text(
                3, i * s + 4,
                text=rank_num, anchor="nw",
                font=COORD_FONT, fill=cols,
                tags="coord"
            )

            # --- File letters on the bottom of file column ---
            if self.flipped:
                file_letter = files[7 - i]
            else:
                file_letter = files[i]

            self.create_text(
                (i + 1) * s - 3, 8 * s - 3,
                text=file_letter, anchor="se",
                font=COORD_FONT, fill=cols,
                tags="coord"
            )

    def _draw_last_move_highlights(self):
        """
        Composite a semi-transparent colour over the from/to squares
        of the most recent move.  We draw this as a translucent overlay
        rectangle using PIL → ImageTk compositing trick.
        """
        if not self._last_move:
            return

        r, g, b, a = self.theme["last_move"]
        s = self.sq_size

        for sq in self._last_move:
            x, y = self._sq_to_xy(sq)
            # Create a small RGBA image and paste it as a canvas image
            overlay = Image.new("RGBA", (s, s), (r, g, b, a))
            tk_img = ImageTk.PhotoImage(overlay)
            item = self.create_image(x, y, anchor="nw", image=tk_img, tags="highlight")
            # Keep a reference so Python GC doesn't delete the PhotoImage
            self._store_ref(item, tk_img)
            self._last_move_items.append(item)

    def _draw_selected_highlight(self):
        """Draw a subtle radial ring on the selected square if any."""
        if self._selected_square is None:
            return
        r, g, b, a = self.theme["selected"]
        s = self.sq_size
        x, y = self._sq_to_xy(self._selected_square)

        # Draw a filled overlay with ring appearance using PIL
        overlay = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw    = ImageDraw.Draw(overlay)
        # Outer filled rect at alpha/4 for background tint
        draw.rectangle([0, 0, s - 1, s - 1], fill=(r, g, b, a // 4))
        # Inner border ring
        border = max(3, s // 12)
        draw.rectangle([0, 0, s - 1, s - 1], outline=(r, g, b, a), width=border)

        tk_img = ImageTk.PhotoImage(overlay)
        item   = self.create_image(x, y, anchor="nw", image=tk_img, tags="selected_hl")
        self._store_ref(item, tk_img)
        self._selected_item = item

    def _draw_pieces(self):
        """
        Place all pieces from self.chess_board onto the canvas as image items.
        Each piece item is stored in self.piece_items[square] so animation
        can move them individually.
        """
        if not self.chess_board:
            return
        for sq in chess.SQUARES:
            piece = self.chess_board.piece_at(sq)
            if piece:
                tk_img = self.piece_tk.get(piece.symbol())
                if tk_img:
                    x, y  = self._sq_to_xy(sq)
                    item  = self.create_image(
                        x, y, anchor="nw", image=tk_img, tags="piece"
                    )
                    self.piece_items[sq] = item
                    self._store_ref(item, tk_img)

    # ─────────────────────────────────────────
    #  IMAGE REFERENCE MANAGEMENT
    #  Canvas image items need a live Python
    #  reference or the GC deletes the image.
    # ─────────────────────────────────────────
    def _store_ref(self, item_id: int, tk_img: ImageTk.PhotoImage):
        """Attach a reference to the canvas item so GC won't collect it."""
        if not hasattr(self, "_img_refs"):
            self._img_refs = {}
        self._img_refs[item_id] = tk_img

    def _clear_refs(self):
        if hasattr(self, "_img_refs"):
            self._img_refs.clear()

    # ─────────────────────────────────────────
    #  PIECE IMAGE LOADING / RESCALING
    # ─────────────────────────────────────────
    def load_pieces(self, pil_images: dict[str, Image.Image]):
        """
        Receive freshly loaded PIL images from the loader thread,
        scale them to the current square size, and cache as PhotoImages.
        """
        self.piece_pil = pil_images
        self._rescale_pieces()

    def _rescale_pieces(self):
        """
        Rescale all cached PIL images to the current sq_size using LANCZOS.
        Call this whenever the canvas is resized.
        """
        s = self.sq_size
        self.piece_tk.clear()
        for symbol, pil_img in self.piece_pil.items():
            scaled = pil_img.resize((s, s), Image.Resampling.LANCZOS)
            self.piece_tk[symbol] = ImageTk.PhotoImage(scaled)

    # ─────────────────────────────────────────
    #  RESIZE HANDLER
    # ─────────────────────────────────────────
    def _on_resize(self, event):
        """
        When the canvas widget is resized, recalculate sq_size,
        rescale piece images, and do a full redraw.
        """
        new_size = min(event.width, event.height)
        if new_size < 200:
            return
        self.sq_size = new_size // 8
        self.board_size = new_size
        # Cancel any ongoing animation first
        self._cancel_animations()
        if self.piece_pil:
            self._rescale_pieces()
        self.full_redraw()

    # ─────────────────────────────────────────
    #  THEME CHANGE
    # ─────────────────────────────────────────
    def set_theme(self, theme_name: str):
        self.theme_name = theme_name
        self.theme      = THEMES[theme_name]
        self.full_redraw()

    # ─────────────────────────────────────────
    #  CLICK INTERACTION
    # ─────────────────────────────────────────
    def _on_click(self, event):
        sq = self._xy_to_sq(event.x, event.y)
        if sq is None:
            return
        # Toggle selection
        if self._selected_square == sq:
            self._selected_square = None
        else:
            self._selected_square = sq

        # Redraw only the selection overlay for speed
        if self._selected_item is not None:
            self.delete(self._selected_item)
            self._selected_item = None
        self._draw_selected_highlight()

    # ─────────────────────────────────────────
    #  ANIMATION ENGINE
    # ─────────────────────────────────────────
    @staticmethod
    def _ease_out_cubic(t: float) -> float:
        """f(t) = 1 - (1-t)³  →  explosive start, micro-soft landing."""
        return 1.0 - (1.0 - t) ** 3

    def _cancel_animations(self):
        """Immediately cancel all running animations without finalising."""
        if self._anim_job:
            self.after_cancel(self._anim_job)
            self._anim_job = None
        self._animations.clear()

    def _finish_animations_instantly(self):
        """
        Snap all in-flight animated pieces to their final destination.
        Used for debounced skip: finish current move immediately,
        then allow the next one to start cleanly.
        """
        for anim in self._animations:
            self.coords(anim["item"], anim["ex"], anim["ey"])
            if anim.get("on_done"):
                anim["on_done"]()
        self._animations.clear()
        if self._anim_job:
            self.after_cancel(self._anim_job)
            self._anim_job = None

    def animate_pieces(
        self,
        moves_data: list[dict],
        on_complete: callable,
    ):
        """
        Animate one or more piece movements simultaneously.

        moves_data: list of dicts, each containing:
          {
            "item":       canvas image item id,
            "start_sq":   chess.Square (for coordinate lookup),
            "end_sq":     chess.Square,
            "on_done":    optional per-piece callback (None for most),
          }
        on_complete: called once ALL moves in this batch are done.
        """
        # If something is already animating, finish it instantly first
        if self._animations:
            self._finish_animations_instantly()

        now_ms = time.monotonic() * 1000
        batch_remaining = [len(moves_data)]  # mutable counter for closure

        def batch_done():
            batch_remaining[0] -= 1
            if batch_remaining[0] <= 0:
                on_complete()

        for md in moves_data:
            sx, sy = self._sq_to_xy(md["start_sq"])
            ex, ey = self._sq_to_xy(md["end_sq"])

            # Dynamic duration based on pixel distance
            dist_sq  = math.hypot(
                chess.square_file(md["end_sq"]) - chess.square_file(md["start_sq"]),
                chess.square_rank(md["end_sq"]) - chess.square_rank(md["start_sq"])
            )
            max_dist = math.hypot(7, 7)  # max board distance
            t_ratio  = dist_sq / max_dist
            dur_ms   = ANIM_MIN_MS + (ANIM_MAX_MS - ANIM_MIN_MS) * t_ratio

            self._animations.append({
                "item":       md["item"],
                "sx": sx, "sy": sy,
                "ex": ex, "ey": ey,
                "duration_ms": dur_ms,
                "start_ms":    now_ms,
                "on_done":     batch_done,
            })

        # Ensure piece items are raised above highlights
        for md in moves_data:
            self.tag_raise(md["item"])

        self._tick_animation()

    def _tick_animation(self):
        """
        Inner animation loop.  Runs at ANIM_TICK_MS intervals.
        For each active animation, computes eased position and
        moves the canvas item.  Removes finished animations.
        """
        now_ms   = time.monotonic() * 1000
        finished = []

        for anim in self._animations:
            elapsed = now_ms - anim["start_ms"]
            raw_t   = min(elapsed / anim["duration_ms"], 1.0)
            t       = self._ease_out_cubic(raw_t)

            cx = anim["sx"] + (anim["ex"] - anim["sx"]) * t
            cy = anim["sy"] + (anim["ey"] - anim["sy"]) * t
            self.coords(anim["item"], cx, cy)

            if raw_t >= 1.0:
                finished.append(anim)

        # Fire callbacks and clean up
        for anim in finished:
            self._animations.remove(anim)
            if anim["on_done"]:
                anim["on_done"]()

        if self._animations:
            # Schedule next tick
            self._anim_job = self.after(ANIM_TICK_MS, self._tick_animation)
        else:
            self._anim_job = None

    # ─────────────────────────────────────────
    #  PUBLIC: UPDATE PIECE AT SQUARE
    #  (called after board state changes)
    # ─────────────────────────────────────────
    def update_piece_at(self, sq: int):
        """
        Refresh the canvas image item for a single square.
        Removes existing item if any, places new one if a piece is there.
        """
        if sq in self.piece_items:
            self.delete(self.piece_items.pop(sq))

        if not self.chess_board:
            return
        piece = self.chess_board.piece_at(sq)
        if piece:
            tk_img = self.piece_tk.get(piece.symbol())
            if tk_img:
                x, y  = self._sq_to_xy(sq)
                item  = self.create_image(x, y, anchor="nw", image=tk_img, tags="piece")
                self.piece_items[sq] = item
                self._store_ref(item, tk_img)

    def set_last_move(self, from_sq: int | None, to_sq: int | None):
        """Update the last-move highlight squares and redraw overlays."""
        # Remove existing highlights
        for item in self._last_move_items:
            self.delete(item)
        self._last_move_items.clear()

        if from_sq is not None and to_sq is not None:
            self._last_move = (from_sq, to_sq)
        else:
            self._last_move = None

        self._draw_last_move_highlights()
        # Ensure pieces are above highlights
        self.tag_raise("piece")

    def flip_board(self):
        self.flipped = not self.flipped
        self.full_redraw()


# ═══════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════
class PGNViewerApp(ctk.CTk):
    """
    Main application window.  Orchestrates:
      - Piece downloading in a background thread
      - Board state management via python-chess
      - Animation sequencing (forward / backward with castling)
      - UI layout: canvas board + sidebar controls
    """

    WINDOW_W = 1080
    WINDOW_H = 780

    NAG_SYMBOLS: dict[int, str] = {
        1:  "!",        # Good move
        2:  "?",        # Mistake
        3:  "!!",       # Brilliant move
        4:  "??",       # Blunder
        5:  "!?",       # Interesting / speculative
        6:  "?!",       # Dubious / inaccuracy
        7:  "□",        # Forced move
        10: "=",        # Equal position
        13: "∞",        # Unclear position
        14: "⩲",        # Slight advantage White
        15: "⩱",        # Slight advantage Black
        16: "±",        # Clear advantage White
        17: "∓",        # Clear advantage Black
        18: "+−",       # Decisive advantage White
        19: "−+",       # Decisive advantage Black
        22: "⊘",        # Zugzwang White
        23: "⊘",        # Zugzwang Black
        32: "⟳",        # Development advantage
        36: "→",        # Initiative
        40: "↑",        # Attack
        44: "⌗",        # Compensation
        132: "⇆",       # Counterplay
        138: "⊕",       # Time pressure
        140: "△",       # With the idea
        142: "⌓",       # Better is
        145: "RR",      # Editorial comment
        146: "N",       # Novelty
    }

    _EFFECT_LABELS: dict[str, str] = {
        "Brilliant":    "!! Brilliant",
        "GreatFind":    "! Great Find",
        "BestMove":     "✓ Best Move",
        "Excellent":    "✓ Excellent",
        "Good":         "Good",
        "Book":         "📖 Book",
        "Inaccuracy":   "?! Inaccuracy",
        "Mistake":      "? Mistake",
        "Blunder":      "?? Blunder",
        "Miss":         "✗ Miss",
        "MissedWin":    "✗ Missed Win",
    }

    @staticmethod
    def _clean_comment(raw: str) -> tuple[str, str]:
        """
        Parse a raw PGN comment string (the text between { }) and return:
          (clean_text, annotation_label)

        What gets stripped / parsed:
          • [%clk H:MM:SS.s]          → extracted as clock string
          • [%timestamp N]            → discarded (server-internal)
          • [%c_effect sq;...;type;X;...]  → type label extracted
          • [%eval N.NN]              → extracted as eval string
          • [%arrow ...]              → discarded
          • [%cal ...]                → discarded (colored squares)
          • Any other [%xxx ...]      → discarded

        The bracket commands can span multiple lines (chess.com wraps them),
        so the regex uses DOTALL.

        Returns
        -------
        clean_text : str
            The human-readable comment prose, with surrounding whitespace
            and stray punctuation normalised.
        annotation_label : str
            A short summary string combining annotation type + clock if found,
            e.g.  "!! Brilliant  ·  ⏱ 2:06"   or  "" if nothing found.
        """
        if not raw:
            return "", ""

        # ── 1. Extract [%clk H:MM:SS.s] ─────────────────────────────────
        clk_match = re.search(r'\[%clk\s+([^\]]+)\]', raw, re.DOTALL)
        clock_str = ""
        if clk_match:
            clk_val = clk_match.group(1).strip()
            if '.' in clk_val:
                clk_val = clk_val.split('.')[0]
            parts = clk_val.split(':')
            if len(parts) == 3:
                try:
                    h = int(parts[0])
                    m = int(parts[1])
                    s = parts[2]
                    if h == 0:
                        clock_str = f"{m}:{s}"
                    else:
                        clock_str = f"{h}:{m:02d}:{s}"
                except ValueError:
                    clock_str = clk_val
            elif len(parts) == 2:
                try:
                    m = int(parts[0])
                    s = parts[1]
                    clock_str = f"{m}:{s}"
                except ValueError:
                    clock_str = clk_val
            else:
                clock_str = clk_val

        # ── 2. Extract [%c_effect sq;...;type;X;...] ────────────────────
        c_effect_match = re.search(r'\[%c_effect\s+[^\]]*?type;([^;\]]+)', raw, re.DOTALL)
        effect_label = ""
        if c_effect_match:
            effect_type = c_effect_match.group(1).strip()
            effect_label = PGNViewerApp._EFFECT_LABELS.get(effect_type, effect_type)

        # ── 3. Extract [%eval N.NN] ─────────────────────────────────────
        eval_match = re.search(r'\[%eval\s+([^\]]+)\]', raw, re.DOTALL)
        eval_str = ""
        if eval_match:
            eval_raw = eval_match.group(1).strip()
            if eval_raw.startswith('#'):
                eval_str = eval_raw
            else:
                try:
                    val = float(eval_raw)
                    if val > 0:
                        eval_str = f"+{eval_raw}" if not eval_raw.startswith('+') else eval_raw
                    else:
                        eval_str = eval_raw
                except ValueError:
                    eval_str = eval_raw

        # ── 4. Strip all [%xxx ...] metadata commands from the raw text ──
        clean_text = re.sub(r'\[%[a-zA-Z0-9_]+\s+.*?\]', '', raw, flags=re.DOTALL)

        # ── 5. Normalise spacing, linebreaks, and punctuation ───────────
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        clean_text = re.sub(r'\s+([.,?!;:])', r'\1', clean_text)
        clean_text = re.sub(r'^[,\s;]+', '', clean_text)
        clean_text = re.sub(r'[,\s;]+$', '', clean_text)

        # ── 6. Incorporate evaluation info into clean_text if present ────
        if eval_str:
            if clean_text:
                clean_text = f"[{eval_str}] {clean_text}"
            else:
                clean_text = f"[{eval_str}]"

        # ── 7. Build the final annotation label ─────────────────────────
        label_parts = []
        if effect_label:
            label_parts.append(effect_label)
        if clock_str:
            label_parts.append(f"⏱ {clock_str}")

        annotation_label = "  ·  ".join(label_parts)

        return clean_text, annotation_label

    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.title("♛  Premium PGN Viewer")
        self.geometry(f"{self.WINDOW_W}x{self.WINDOW_H}")
        self.minsize(800, 600)

        # ── Game state ───────────────────────
        self.chess_board        = chess.Board()
        self.moves: list[chess.Move] = []
        self.game: chess.pgn.Game | None = None
        self.current_node: chess.pgn.GameNode | None = None
        self.main_game_nodes: set = set()
        self.current_move_index = 0

        # ── Asset state ──────────────────────
        self.current_pack   = "Alpha"
        self.current_theme  = "Lichess Wood"
        self._piece_pil_cache: dict[str, dict[str, Image.Image]] = {}  # pack → {sym: PIL}

        # ── Animation gating ─────────────────
        # Pending move queued while animation is running
        self._pending_action: dict | None = None
        self._animating = False

        # ── Build UI ─────────────────────────
        self._build_layout()

        # Start downloading default piece pack asynchronously
        self._start_piece_download(self.current_pack)

    # ─────────────────────────────────────────
    #  UI LAYOUT
    # ─────────────────────────────────────────
    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=3)   # board side
        self.grid_columnconfigure(1, weight=1)   # sidebar

        # ── Left: Board frame ─────────────────
        board_frame = ctk.CTkFrame(self, fg_color="#0f0f1a", corner_radius=16)
        board_frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        board_frame.grid_rowconfigure(0, weight=1)
        board_frame.grid_columnconfigure(0, weight=1)

        # We size the canvas inside the frame and let it expand
        self.board_canvas = ChessBoardCanvas(
            board_frame,
            size=640,
            theme_name=self.current_theme,
        )
        self.board_canvas.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        self.board_canvas.chess_board = self.chess_board

        # ── Right: Sidebar ────────────────────
        sidebar = ctk.CTkScrollableFrame(self, fg_color="#12122a", corner_radius=16, width=290)
        sidebar.grid(row=0, column=1, padx=(0, 20), pady=20, sticky="nsew")
        sidebar.grid_columnconfigure(0, weight=1)

        self._build_sidebar(sidebar)

        # Initial static board render (no pieces yet)
        self.board_canvas.full_redraw()

    def _build_sidebar(self, parent):
        """Construct all sidebar panels."""
        row = 0

        # ── App title ─────────────────────────
        title = ctk.CTkLabel(
            parent, text="♛  PGN Viewer",
            font=("Georgia", 22, "bold"),
            text_color="#e8d5a3"
        )
        title.grid(row=row, column=0, pady=(18, 4)); row += 1

        subtitle = ctk.CTkLabel(
            parent, text="Premium Edition",
            font=("Georgia", 11, "italic"),
            text_color="#7a6a50"
        )
        subtitle.grid(row=row, column=0, pady=(0, 14)); row += 1

        sep1 = ctk.CTkFrame(parent, height=1, fg_color="#2a2a4a")
        sep1.grid(row=row, column=0, sticky="ew", padx=10, pady=6); row += 1

        # ── Game info ─────────────────────────
        self.matchup_label = ctk.CTkLabel(
            parent, text="White vs Black",
            font=("Georgia", 14, "bold"),
            text_color="#c8b88a", wraplength=260
        )
        self.matchup_label.grid(row=row, column=0, pady=(8, 2)); row += 1

        self.event_label = ctk.CTkLabel(
            parent, text="—", font=("Segoe UI", 11),
            text_color="#8a7a60", wraplength=260
        )
        self.event_label.grid(row=row, column=0, pady=2); row += 1

        self.result_label = ctk.CTkLabel(
            parent, text="", font=("Georgia", 13, "bold"),
            text_color="#d4a843"
        )
        self.result_label.grid(row=row, column=0, pady=(2, 10)); row += 1

        sep2 = ctk.CTkFrame(parent, height=1, fg_color="#2a2a4a")
        sep2.grid(row=row, column=0, sticky="ew", padx=10, pady=6); row += 1

        # ── Move Counter ──────────────────────
        self.move_label = ctk.CTkLabel(
            parent, text="Move  0 / 0",
            font=("Courier New", 18, "bold"),
            text_color="#e0d0b0"
        )
        self.move_label.grid(row=row, column=0, pady=(10, 6)); row += 1

        # ── Navigation buttons ────────────────
        nav_frame = ctk.CTkFrame(parent, fg_color="transparent")
        nav_frame.grid(row=row, column=0, padx=10, pady=6, sticky="ew"); row += 1
        nav_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        btn_style = {"font": ("Segoe UI", 13), "corner_radius": 8,
                     "height": 36, "fg_color": "#1e1e3a",
                     "hover_color": "#2a2a5a", "border_color": "#3a3a5a",
                     "border_width": 1}

        self.start_btn = ctk.CTkButton(nav_frame, text="⏮", command=self._goto_start, width=44, **btn_style)
        self.start_btn.grid(row=0, column=0, padx=3)

        self.prev_btn = ctk.CTkButton(nav_frame, text="◀", command=self._prev_move, width=54, **btn_style)
        self.prev_btn.grid(row=0, column=1, padx=3)

        self.next_btn = ctk.CTkButton(nav_frame, text="▶", command=self._next_move, width=54, **btn_style)
        self.next_btn.grid(row=0, column=2, padx=3)

        self.end_btn = ctk.CTkButton(nav_frame, text="⏭", command=self._goto_end, width=44, **btn_style)
        self.end_btn.grid(row=0, column=3, padx=3)

        # Action row (Flip & Analyze)
        action_frame = ctk.CTkFrame(parent, fg_color="transparent")
        action_frame.grid(row=row, column=0, padx=10, pady=(4, 10), sticky="ew"); row += 1
        action_frame.grid_columnconfigure((0, 1), weight=1)

        self.flip_btn = ctk.CTkButton(
            action_frame, text="⇅  Flip Board", command=self._flip_board,
            font=("Segoe UI", 12), corner_radius=8, height=32,
            fg_color="#1a2a1a", hover_color="#2a4a2a",
            border_color="#3a5a3a", border_width=1
        )
        self.flip_btn.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.analyze_btn = ctk.CTkButton(
            action_frame, text="🔬 Analyze", command=self._analyze_position,
            font=("Segoe UI", 12), corner_radius=8, height=32,
            fg_color="#3a1e50", hover_color="#5a2a70",
            border_color="#5a3a70", border_width=1
        )
        self.analyze_btn.grid(row=0, column=1, padx=(4, 0), sticky="ew")

        # ── Move Analysis / Comments Panel ──
        self.comment_frame = ctk.CTkFrame(parent, fg_color="#181830", corner_radius=10, border_color="#2a2a50", border_width=1)
        self.comment_frame.grid(row=row, column=0, padx=10, pady=10, sticky="ew"); row += 1
        
        self.comment_header = ctk.CTkLabel(
            self.comment_frame, text="📝 Move Analysis",
            font=("Segoe UI", 12, "bold"),
            text_color="#c8b88a"
        )
        self.comment_header.pack(anchor="w", padx=10, pady=(8, 2))
        
        self.comment_detail_label = ctk.CTkLabel(
            self.comment_frame, text="Load a PGN to see comments.",
            font=("Segoe UI", 11, "italic"),
            text_color="#8a8a9a",
            wraplength=250,
            justify="left"
        )
        self.comment_detail_label.pack(anchor="w", padx=10, pady=(2, 10))

        sep3 = ctk.CTkFrame(parent, height=1, fg_color="#2a2a4a")
        sep3.grid(row=row, column=0, sticky="ew", padx=10, pady=6); row += 1

        # ── Board Theme ───────────────────────
        ctk.CTkLabel(parent, text="Board Theme", font=("Segoe UI", 12, "bold"),
                     text_color="#a090c0").grid(row=row, column=0, padx=12, sticky="w"); row += 1

        self.theme_menu = ctk.CTkOptionMenu(
            parent, values=list(THEMES.keys()),
            command=self._change_theme,
            font=("Segoe UI", 12), dropdown_font=("Segoe UI", 12),
            corner_radius=8, height=32
        )
        self.theme_menu.set(self.current_theme)
        self.theme_menu.grid(row=row, column=0, padx=10, pady=(4, 10), sticky="ew"); row += 1

        # ── Piece Pack ────────────────────────
        ctk.CTkLabel(parent, text="Piece Style", font=("Segoe UI", 12, "bold"),
                     text_color="#a090c0").grid(row=row, column=0, padx=12, sticky="w"); row += 1

        self.pack_menu = ctk.CTkOptionMenu(
            parent, values=list(PIECE_PACKS.keys()),
            command=self._change_piece_pack,
            font=("Segoe UI", 12), dropdown_font=("Segoe UI", 12),
            corner_radius=8, height=32
        )
        self.pack_menu.set(self.current_pack)
        self.pack_menu.grid(row=row, column=0, padx=10, pady=(4, 10), sticky="ew"); row += 1

        self.pack_status = ctk.CTkLabel(
            parent, text="", font=("Segoe UI", 10),
            text_color="#608060"
        )
        self.pack_status.grid(row=row, column=0, pady=2); row += 1

        sep4 = ctk.CTkFrame(parent, height=1, fg_color="#2a2a4a")
        sep4.grid(row=row, column=0, sticky="ew", padx=10, pady=6); row += 1

        # ── PGN / FEN Input ───────────────────
        ctk.CTkLabel(parent, text="Paste PGN or FEN", font=("Segoe UI", 12, "bold"),
                     text_color="#a090c0").grid(row=row, column=0, padx=12, sticky="w"); row += 1

        self.pgn_text = ctk.CTkTextbox(
            parent, height=160,
            font=("Courier New", 11),
            corner_radius=8,
            border_color="#3a3a5a", border_width=1
        )
        self.pgn_text.grid(row=row, column=0, padx=10, pady=(4, 6), sticky="ew"); row += 1

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.grid(row=row, column=0, padx=10, pady=4, sticky="ew"); row += 1
        btn_row.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_row, text="Load Text", command=self._load_from_text,
            font=("Segoe UI", 12), corner_radius=8, height=32,
            fg_color="#1e3050", hover_color="#2a4070"
        ).grid(row=0, column=0, padx=3, sticky="ew")

        ctk.CTkButton(
            btn_row, text="Browse…", command=self._browse_file,
            font=("Segoe UI", 12), corner_radius=8, height=32,
            fg_color="#1e3050", hover_color="#2a4070"
        ).grid(row=0, column=1, padx=3, sticky="ew")

        self.status_label = ctk.CTkLabel(
            parent, text="No game loaded", font=("Segoe UI", 11),
            text_color="#607060", wraplength=260
        )
        self.status_label.grid(row=row, column=0, pady=(6, 16)); row += 1

    # ─────────────────────────────────────────
    #  PIECE DOWNLOADING
    # ─────────────────────────────────────────
    def _start_piece_download(self, pack_name: str):
        """
        Download a piece pack in a background thread to avoid blocking the UI.
        Once done, push the images into the canvas via self.after().
        """
        self.pack_status.configure(text=f"⬇  Downloading {pack_name}…")
        t = threading.Thread(
            target=self._download_pack_thread,
            args=(pack_name,),
            daemon=True
        )
        t.start()

    def _download_pack_thread(self, pack_name: str):
        """Background thread: download + load PIL images for a pack."""
        pack   = PIECE_PACKS[pack_name]
        folder = pack["folder"]
        os.makedirs(folder, exist_ok=True)

        images = {}
        for symbol, filename in pack["files"].items():
            filepath = os.path.join(folder, filename)
            if not os.path.exists(filepath):
                try:
                    url = pack["base_url"] + filename
                    urllib.request.urlretrieve(url, filepath)
                except Exception as e:
                    print(f"[Download] Failed {filename}: {e}")
                    continue
            try:
                img = Image.open(filepath).convert("RGBA")
                images[symbol] = img
            except Exception as e:
                print(f"[Load] Failed {filename}: {e}")

        # Schedule delivery back on the main thread
        self.after(0, lambda: self._on_pack_loaded(pack_name, images))

    def _on_pack_loaded(self, pack_name: str, images: dict):
        """Called on main thread once a pack's images are ready."""
        self._piece_pil_cache[pack_name] = images
        if pack_name == self.current_pack:
            self.board_canvas.load_pieces(images)
            self.board_canvas.full_redraw()
            self.pack_status.configure(text=f"✔  {pack_name} loaded")

    # ─────────────────────────────────────────
    #  THEME & PACK SWITCHING
    # ─────────────────────────────────────────
    def _change_theme(self, choice: str):
        self.current_theme = choice
        self.board_canvas.set_theme(choice)

    def _change_piece_pack(self, choice: str):
        self.current_pack = choice
        if choice in self._piece_pil_cache:
            # Already downloaded — just swap
            self.board_canvas.load_pieces(self._piece_pil_cache[choice])
            self.board_canvas.full_redraw()
            self.pack_status.configure(text=f"✔  {choice} loaded")
        else:
            self._start_piece_download(choice)

    # ─────────────────────────────────────────
    #  PGN / FEN LOADING
    # ─────────────────────────────────────────
    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Open PGN File",
            filetypes=[("PGN Files", "*.pgn"), ("All Files", "*.*")]
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                self.pgn_text.delete("1.0", "end")
                self.pgn_text.insert("1.0", content)
                self._load_from_text(content)
            except Exception as e:
                self.status_label.configure(text=f"Error: {e}")

    def _load_from_text(self, text: str | None = None):
        """Parse text from the textbox (or supplied string) as PGN or FEN."""
        # Cancel any in-flight animation
        self._cancel_current_animation()

        if text is None:
            text = self.pgn_text.get("1.0", "end-1c").strip()
        if not text:
            self.status_label.configure(text="Please paste PGN or FEN text.")
            return

        # ── Try FEN ──────────────────────────
        if len(text.split("/")) >= 7 and "{" not in text and "[" not in text:
            try:
                self.chess_board.set_fen(text.strip())
                self.moves = []
                self.game = None
                self.current_node = None
                self.main_game_nodes = set()
                self.current_move_index = 0
                self.matchup_label.configure(text="Static FEN Position")
                self.event_label.configure(text="Custom Board Setup")
                self.result_label.configure(text="")
                self.status_label.configure(text="FEN loaded ✔")
                self._refresh_board_full()
                self._update_ui()
                return
            except ValueError:
                pass  # fall through to PGN

        # ── Try PGN ──────────────────────────
        try:
            game = chess.pgn.read_game(io.StringIO(text))
            if not game:
                self.status_label.configure(text="Could not parse PGN.")
                return

            self.game = game
            self.current_node = game
            
            # Trace and store all nodes that belong to the Main Game Line (played line)
            self.main_game_nodes = set()
            node = game
            while node is not None:
                self.main_game_nodes.add(node)
                if node.is_end():
                    break
                node = node.variations[0]

            self._rebuild_active_path()
            self.chess_board.reset()

            # Metadata
            white = game.headers.get("White", "?")
            black = game.headers.get("Black", "?")
            w_elo = game.headers.get("WhiteElo", "")
            b_elo = game.headers.get("BlackElo", "")
            event = game.headers.get("Event", "")
            site  = game.headers.get("Site", "")
            result = game.headers.get("Result", "*")
            term   = game.headers.get("Termination", "")

            elo_w = f" ({w_elo})" if w_elo else ""
            elo_b = f" ({b_elo})" if b_elo else ""
            self.matchup_label.configure(text=f"♔ {white}{elo_w}  vs  ♚ {black}{elo_b}")
            ev_str = " · ".join(x for x in [event, site] if x)
            self.event_label.configure(text=ev_str or "—")
            
            # Beautiful dynamic game outcome parser
            def parse_outcome(res, trm, mvs):
                if res == "1-0":
                    winner_color = "White"
                elif res == "0-1":
                    winner_color = "Black"
                elif res == "1/2-1/2":
                    winner_color = "Draw"
                else:
                    return "⚔️ Game in Progress"

                reason = ""
                t_lower = trm.lower() if trm else ""
                
                # Check for standard termination keywords
                if "checkmate" in t_lower:
                    reason = "by checkmate"
                elif "resignation" in t_lower:
                    reason = "by resignation"
                elif "on time" in t_lower or "time" in t_lower:
                    reason = "on time"
                elif "stalemate" in t_lower:
                    reason = "by stalemate"
                elif "insufficient" in t_lower:
                    reason = "due to insufficient material"
                elif "agreement" in t_lower:
                    reason = "by agreement"
                elif "abandoned" in t_lower:
                    reason = "by abandonment"
                elif trm:
                    cleaned_trm = trm.replace("Game drawn by ", "").replace("won by ", "").replace("won on ", "")
                    reason = f"({cleaned_trm})"

                # Fallback: simulate final board state if no explicit termination detail is present
                if not reason and mvs:
                    try:
                        temp_board = chess.Board()
                        for m in mvs:
                            temp_board.push(m)
                        if temp_board.is_checkmate():
                            reason = "by checkmate"
                        elif temp_board.is_stalemate():
                            reason = "by stalemate"
                        elif temp_board.is_insufficient_material():
                            reason = "due to insufficient material"
                        elif temp_board.is_seventyfive_moves() or temp_board.is_fivefold_repetition():
                            reason = "by repetition"
                    except:
                        pass

                if winner_color == "Draw":
                    return f"🤝 Draw {reason}".strip() + " (½-½)"
                else:
                    return f"🏆 {winner_color} won {reason}".strip() + f" ({res})"

            res_str = parse_outcome(result, term, self.moves)
            self.result_label.configure(text=res_str)
            self.status_label.configure(text=f"Loaded {len(self.moves)} moves ✔")

            board_canvas = self.board_canvas
            board_canvas.set_last_move(None, None)
            board_canvas._selected_square = None
            self._refresh_board_full()
            self._update_ui()

        except Exception as e:
            self.status_label.configure(text=f"Parse error: {e}")

    # ─────────────────────────────────────────
    #  BOARD REFRESH HELPERS
    # ─────────────────────────────────────────
    def _rebuild_active_path(self):
        """
        Reconstruct self.moves list and determine self.current_move_index
        based on the active path from the root of self.game, passing through self.current_node,
        and continuing along the default variations (variations[0]) to the end.
        """
        if not self.game:
            self.moves = []
            self.current_move_index = 0
            return

        # 1. Walk backward from self.current_node to the root self.game to get the history
        history_nodes = []
        node = self.current_node
        while node is not None and node != self.game:
            history_nodes.append(node)
            node = node.parent
        history_nodes.reverse()

        # 2. Walk forward from self.current_node along the default mainline to the end
        forward_nodes = []
        node = self.current_node
        while not node.is_end():
            node = node.variations[0]
            forward_nodes.append(node)

        # Combine them to get the complete active path
        all_nodes = history_nodes + forward_nodes
        self.moves = [n.move for n in all_nodes]
        self.current_move_index = len(history_nodes)

    def _refresh_board_full(self):
        """
        Synchronise canvas visuals with self.chess_board state.
        Performs a clean full redraw (squares + highlights + pieces).
        """
        self.board_canvas.chess_board = self.chess_board
        self.board_canvas.full_redraw()

    def _update_ui(self):
        n  = len(self.moves)
        mi = self.current_move_index
        self.move_label.configure(text=f"Move  {mi} / {n}")
        self.prev_btn.configure(state="normal" if mi > 0 else "disabled")
        self.next_btn.configure(state="normal" if mi < n else "disabled")
        self.start_btn.configure(state="normal" if mi > 0 else "disabled")
        self.end_btn.configure(state="normal" if mi < n else "disabled")
        self._update_comment_panel()

    def _update_comment_panel(self):
        # Clear variation buttons first
        for widget in getattr(self, "_var_buttons", []):
            try:
                widget.destroy()
            except:
                pass
        self._var_buttons = []

        if not hasattr(self, "var_container"):
            # Create a clean subframe inside the comment frame
            self.var_container = ctk.CTkFrame(self.comment_frame, fg_color="transparent")
            self.var_container.pack(fill="x", padx=10, pady=(0, 10))

        if not self.game:
            if self.chess_board:
                turn = "White" if self.chess_board.turn == chess.WHITE else "Black"
                icon = "⚪" if turn == "White" else "⚫"
                self.comment_detail_label.configure(
                    text=f"⚙️ Static Position\n\n{icon} {turn} to move",
                    text_color="#e0d0b0"
                )
            else:
                self.comment_detail_label.configure(
                    text="Load a PGN game to see comments and move analysis.",
                    text_color="#8a8a9a"
                )
            return

        if self.current_node == self.game:
            self.comment_detail_label.configure(
                text="🎬 Game Start\n\n⚪ White to move",
                text_color="#e0d0b0"
            )
            choices = self.current_node.variations
            self._draw_variation_buttons(choices)
            return

        # Get parent board and current move info
        parent_node = self.current_node.parent
        curr_board = parent_node.board()
        move_num = curr_board.fullmove_number
        san = self.current_node.san()

        # Suffix the SAN with NAG symbols if any
        nags = self.current_node.nags
        nag_suffixes = "".join(self.NAG_SYMBOLS.get(nag, "") for nag in nags if nag in self.NAG_SYMBOLS)

        turn = "White" if curr_board.turn == chess.WHITE else "Black"
        comment = self.current_node.comment.strip()

        # Next player's turn to move
        next_turn = "Black" if turn == "White" else "White"
        next_icon = "⚫" if next_turn == "Black" else "⚪"

        outcome_text = f"♟️ Move {move_num}: {san}{nag_suffixes} ({turn})\n"
        outcome_text += f"{next_icon} Next: {next_turn} to move\n\n"

        clean_text, annotation_label = self._clean_comment(comment)

        if annotation_label:
            outcome_text += f"✨ {annotation_label}\n\n"

        if clean_text:
            outcome_text += f"💬 Comment:\n\"{clean_text}\""
            self.comment_detail_label.configure(text=outcome_text, text_color="#e8d5a3")
        else:
            outcome_text += "💬 Comment:\n(No comment on this move)"
            self.comment_detail_label.configure(text=outcome_text, text_color="#a0a0b0")

        # Draw variation buttons for choices branching from this node
        choices = self.current_node.variations
        self._draw_variation_buttons(choices)

    def _draw_variation_buttons(self, choices):
        if len(choices) > 1:
            lbl = ctk.CTkLabel(
                self.var_container, text="🔀 Alternatives:",
                font=("Segoe UI", 11, "bold"),
                text_color="#c8b88a"
            )
            lbl.pack(anchor="w", pady=(6, 2))
            self._var_buttons.append(lbl)
            
            for i, v in enumerate(choices):
                san = v.san()
                # Create a closure
                def make_handler(node_to_play):
                    return lambda: self._play_variation(node_to_play)
                
                is_played = v in getattr(self, "main_game_nodes", set())
                
                if is_played:
                    btn_color = "#1e3d25"      # forest green for played line
                    hover = "#285c34"
                    prefix = "★ Played Line: "
                else:
                    btn_color = "#2b2b4a"      # dark indigo for analysis sub-lines
                    hover = "#3b3b6a"
                    prefix = "↳ Sub-line: "
                
                btn = ctk.CTkButton(
                    self.var_container,
                    text=f"{prefix}{san}",
                    command=make_handler(v),
                    font=("Segoe UI", 11),
                    height=24,
                    fg_color=btn_color,
                    hover_color=hover,
                    corner_radius=6
                )
                btn.pack(fill="x", pady=2)
                self._var_buttons.append(btn)

    def _play_variation(self, node_to_play):
        self._execute_animated_move(node_to_play.move, is_undo=False)

    # ─────────────────────────────────────────
    #  NAVIGATION
    # ─────────────────────────────────────────
    def _goto_start(self):
        """Jump to the initial position (no animation)."""
        self._cancel_current_animation()
        self.chess_board.reset()
        if self.game:
            self.current_node = self.game
            self._rebuild_active_path()
        else:
            self.current_move_index = 0
        self.board_canvas.set_last_move(None, None)
        self._refresh_board_full()
        self._update_ui()

    def _goto_end(self):
        """Jump to the final position (no animation)."""
        self._cancel_current_animation()
        if self.game and self.current_node:
            while not self.current_node.is_end():
                self.current_node = self.current_node.variations[0]
            self._rebuild_active_path()
            self.chess_board = self.current_node.board()
        else:
            self.chess_board.reset()
            for move in self.moves:
                self.chess_board.push(move)
            self.current_move_index = len(self.moves)
            
        if self.moves:
            last = self.moves[-1]
            self.board_canvas.set_last_move(last.from_square, last.to_square)
        else:
            self.board_canvas.set_last_move(None, None)
        self._refresh_board_full()
        self._update_ui()

    def _next_move(self):
        """Advance one move forward with animation."""
        if self.current_move_index >= len(self.moves):
            return
        move = self.moves[self.current_move_index]
        self._execute_animated_move(move, is_undo=False)

    def _prev_move(self):
        """Step one move backward with animation."""
        if self.current_move_index <= 0:
            return
        move = self.moves[self.current_move_index - 1]
        self._execute_animated_move(move, is_undo=True)

    def _flip_board(self):
        self._cancel_current_animation()
        self.board_canvas.flip_board()

    def _analyze_position(self):
        messagebox.showinfo(
            "Analyze Position",
            "Stockfish Engine Analysis is currently under development!\n\n"
            "This coming-soon feature will allow you to run real-time local Stockfish analysis "
            "directly on the current board position, complete with evaluation scores and "
            "best-move recommendations."
        )

    # ─────────────────────────────────────────
    #  ANIMATION ORCHESTRATION
    # ─────────────────────────────────────────
    def _cancel_current_animation(self):
        """
        Debounce guard: if an animation is running, snap it to completion
        and apply the board state changes instantly.
        """
        if self._animating:
            self._animating = False
            self.board_canvas._finish_animations_instantly()
            # The on_complete callback will have been called by
            # _finish_animations_instantly above; we just reset
            self._pending_action = None

    def _execute_animated_move(self, move: chess.Move, is_undo: bool):
        """
        Main entry point for a move animation.
        Handles:
          - Debounce of rapid button presses
          - Castle detection (two simultaneous piece animations)
          - Forward / backward direction
        """
        # If something is already in flight, snap it first
        if self._animating:
            self._cancel_current_animation()

        self._animating = True

        board    = self.chess_board
        canvas   = self.board_canvas

        if is_undo:
            # For undo we want to move the piece from to_square back to from_square
            moving_sq  = move.to_square
            target_sq  = move.from_square
            piece      = board.piece_at(moving_sq)

            # Detect castling undo: the king is on g1/c1/g8/c8 for a castling move
            is_castle = (
                piece and piece.piece_type == chess.KING and
                abs(chess.square_file(move.from_square) -
                    chess.square_file(move.to_square)) == 2
            )
        else:
            moving_sq  = move.from_square
            target_sq  = move.to_square
            piece      = board.piece_at(moving_sq)

            is_castle = (
                piece and piece.piece_type == chess.KING and
                abs(chess.square_file(move.from_square) -
                    chess.square_file(move.to_square)) == 2
            )

        if not piece:
            # Fallback: no piece found, apply instantly
            self._apply_move(move, is_undo)
            self._animating = False
            self._update_ui()
            return

        # ── Build moves_data list ─────────────
        moves_data = []

        # Primary piece
        item = canvas.piece_items.get(moving_sq)
        if item is not None:
            moves_data.append({
                "item":     item,
                "start_sq": moving_sq,
                "end_sq":   target_sq,
            })
        
        # ── Castling companion (rook) ─────────
        if is_castle:
            rank = chess.square_rank(move.from_square)
            if not is_undo:
                # Determine rook positions for forward castle
                king_to_file = chess.square_file(move.to_square)
                if king_to_file == 6:  # kingside
                    rook_from = chess.square(7, rank)
                    rook_to   = chess.square(5, rank)
                else:                   # queenside
                    rook_from = chess.square(0, rank)
                    rook_to   = chess.square(3, rank)
            else:
                # Undo: rook is on f1/d1 or f8/d8, move it back
                king_orig_file = chess.square_file(move.from_square)
                king_dest_file = chess.square_file(move.to_square)
                if king_dest_file > king_orig_file:  # was kingside
                    rook_from = chess.square(5, rank)
                    rook_to   = chess.square(7, rank)
                else:                                  # was queenside
                    rook_from = chess.square(3, rank)
                    rook_to   = chess.square(0, rank)

            rook_item = canvas.piece_items.get(rook_from)
            if rook_item is not None:
                moves_data.append({
                    "item":     rook_item,
                    "start_sq": rook_from,
                    "end_sq":   rook_to,
                })

        if not moves_data:
            # Nothing to animate, apply instantly
            self._apply_move(move, is_undo)
            self._animating = False
            self._update_ui()
            return

        # ── Hide captured piece early (visual only) ──
        if not is_undo:
            captured = board.piece_at(target_sq)
            if captured:
                cap_item = canvas.piece_items.get(target_sq)
                if cap_item:
                    canvas.delete(cap_item)
                    del canvas.piece_items[target_sq]

        def on_animation_done():
            """Called after all pieces in this batch have reached their destinations."""
            self._apply_move(move, is_undo)
            self._animating = False
            self._update_ui()

        canvas.animate_pieces(moves_data, on_animation_done)

    def _apply_move(self, move: chess.Move, is_undo: bool):
        """
        Commit the board state change and refresh the canvas.
        This is called after the animation completes.
        """
        if is_undo:
            self.chess_board.pop()
            if self.current_node and self.current_node.parent:
                self.current_node = self.current_node.parent
            self._rebuild_active_path()
            
            if self.current_move_index > 0:
                prev = self.moves[self.current_move_index - 1]
                self.board_canvas.set_last_move(prev.from_square, prev.to_square)
            else:
                self.board_canvas.set_last_move(None, None)
        else:
            self.chess_board.push(move)
            if self.current_node:
                matching_child = None
                for v in self.current_node.variations:
                    if v.move == move:
                        matching_child = v
                        break
                if matching_child:
                    self.current_node = matching_child
            
            self._rebuild_active_path()
            self.board_canvas.set_last_move(move.from_square, move.to_square)

        # Full sync of canvas piece items to board state
        self.board_canvas.chess_board = self.chess_board
        self._resync_pieces()

    def _resync_pieces(self):
        """
        Efficiently sync canvas piece items with the current board state
        WITHOUT a full redraw (avoids flickering).
        We recalculate what *should* be on each square and update deltas.
        """
        canvas   = self.board_canvas
        board    = self.chess_board

        # Remove all existing piece items
        for item in list(canvas.piece_items.values()):
            canvas.delete(item)
        canvas.piece_items.clear()

        # Redraw pieces cleanly
        canvas._draw_pieces()
        # Ensure highlights stay under pieces
        canvas.tag_raise("piece")


# ═══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = PGNViewerApp()
    app.mainloop()
