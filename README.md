# Pro PGN Viewer

A sleek, modern Python desktop application built with `customtkinter` for viewing chess PGNs and static FEN positions. It features a beautifully themed digital chessboard, smooth Lichess-style piece animations, and automatic game metadata extraction.

## Features
- **Dynamic Board Themes**: Switch instantly between Classic Wood, Ocean Blue, Lichess Green, and Dark Mode.
- **High-Resolution Graphics**: Automatically downloads and utilizes the crisp "Alpha" chess piece set.
- **Fluid Animations**: Pieces glide naturally across the board with ultra-smooth cubic-ease easing functions.
- **Game Metadata**: Automatically parses and displays Player Names, ELO Ratings, Event/Site information, and Final Outcome from PGN headers.
- **File Browsing & FEN Support**: Easily browse your computer for `.pgn` files or paste a static FEN string to instantly load a position.

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
