# Pro PGN Viewer

A sleek, modern Python desktop application built with `customtkinter` for viewing chess PGNs and static FEN positions. It features a beautifully themed digital chessboard, smooth Lichess-style piece animations, and automatic game metadata extraction.

## Features
- **Unified Canvas Architecture**: The entire board, coordinates, highlights, and pieces are rendered on a single high-performance `tkinter.Canvas`, eliminating performance hiccups, widget-spacing bugs, and image ghosting.
- **Buttery-Smooth Animations**: Pieces glide naturally with a dynamic cubic ease-out (`1 - (1-t)^3`) engine. Move durations scale dynamically between 120ms and 200ms depending on the distance traveled.
- **Advanced Navigation & Debouncing**: Features a debounced animation pipeline. If you click "Next" or "Previous" rapidly, current animations instantly snap to completion so you never get visual desyncs.
- **Simultaneous Castling Animations**: Both the King and Rook animate at the same time during castling!
- **Dynamic Resizing**: Features automatic on-the-fly piece rescaling using PIL `LANCZOS` filters whenever the window is resized, maintaining crystal-sharp visuals.
- **Multiple Piece Styles**: Switch instantly between **Alpha**, **Merida**, **Leipzig**, and **Wikipedia** piece packs, which download automatically in a background thread upon selection.
- **Lichess-Accurate Themes**: Choose between beautifully rendered board themes complete with semi-transparent last-move highlight overlays and square-selection outline rings.
- **File Browsing & FEN Support**: Easily browse your local files for `.pgn` files or paste a static FEN string to set up custom positions instantly.
- **PGN Comment Sanitization**: Cleans metadata and technical command strings (e.g. `[%eval]`, `[%clk]`, `[%c_effect]`, `[%arrow]`, `[%cal]`) from PGN comments, formatting evaluations and clock times beautifully in the move analysis panel.
- **NAG Notation Support**: Maps Numeric Annotation Glyphs (NAGs) like `!!`, `!?`, `?`, or `??` to their readable chess symbol suffixes for moves.
- **Engine Analysis (Coming Soon)**: A dedicated button to run real-time local Stockfish engine evaluations and best-move recommendations directly on the current board position.

## Requirements
- Python 3.x
- `customtkinter`
- `python-chess`
- `Pillow`

## Installation
1. Clone the repository.
2. Install the required dependencies:
   ```bash
   pip install customtkinter chess pillow
   ```
3. Run the application:
   ```bash
   python pgn_viewer.py
   ```

*Note: On first run, the application will automatically download the chess piece graphics to a local `pieces_alpha` directory.*
