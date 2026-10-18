# Local behavior-based channel demo

This repository is a basic locally hosted demonstration based on the 2009 paper Behavior-Based Covert Channel (Johnson, Lutz, and Yuan, 2009) in Cyberspace. The covert channel that is demonstrated in this repository is local only with a terminal demo and a web based demo. 

The demo uses only Python's standard library. Keep `index.html`, `web_demo.py`, and `demo.py` together in the same directory. The web server listens on the loopback interface (`127.0.0.1`) so it is available only on the local computer. It saves messages and move histories to `demo_messages.json` in the current directory.

## How to run it

```sh
# Terminal demo
python3 demo.py
python3 demo.py --message "HELLO"
python3 demo.py --message "Local demo 123"
python3 demo.py --self-test

# Live local website
python3 web_demo.py
```

Open <http://127.0.0.1:8765/> in a browser. Enter a printable ASCII message (up to 15 characters) and select **Start**. The page saves the message locally, then lets you advance the board one move at a time or use **Play all**. The simple, uncolored page shows the move rank, symbol, and decoded text. Stop the web server with Ctrl+C. The `index.html` file is served by the Python server because the game uses local API requests; opening it directly as a `file://` page will not run the game API.

To use a different port or choose exactly where the local JSON history is stored:

```sh
python3 web_demo.py --port 9000 --storage ./demo_messages.json
```

The saved JSON contains each message, its complete planned move sequence, the moves played so far, and its status. It is plain text and is not encrypted. Keep it local and remove it yourself if it contains data you no longer want. A started but unfinished game remains saved as `in progress`.

## How the demonstration works

The board has 8 rows and 8 columns. At each step, every unoccupied cell is a legal move. Legal cells are listed in row-major order (left to right, top to bottom), as in the move-labeling example in the paper.

1. The sender converts each printable ASCII byte into four two-bit symbols, from most significant pair to least significant pair.
2. For each symbol `s` in `0..3`, the sender selects the first currently empty cell whose legal-move rank modulo 4 equals `s`.
3. The receiver starts from the same empty board, applies the observed moves, and recovers each symbol from that move's rank modulo 4.
4. Four recovered symbols form one byte. The demo validates that the result is printable ASCII.

For example, the symbols of `A` (`01000001`) are `01`, `00`, `00`, and `01`. The receiver need not know the message in advance, but this simple demo assumes it knows where the sequence starts and that its length is a multiple of four moves.

There are four labels, so this scheme carries two bits per move. The program also reports the theoretical choice capacity `log2(N)` at each turn, where `N` is the number of currently legal moves. A message is limited to 15 printable ASCII bytes: four moves per byte on an 8x8 board, while keeping enough legal choices for every symbol.

## Relationship to the paper

The paper, *Behavior-Based Covert Channel in Cyberspace* (Johnson, Lutz, and Yuan, 2009), describes application behavior as a finite-state machine and presents an online board game, Magneton, whose move choices can carry information. These demos illustrate the central state/move-labeling/encoding/decoding idea in a much smaller model. They are not reproductions of the paper's implementation: they do not implement Magneton's attraction/repulsion rules, its handshake, a multiplayer game, or a remote network protocol.

## Scope and limitations

- This is an educational simulation, not a secure communication tool or a realistic game.
- The website is a local visualization. Its HTTP requests stay on the same computer; the input message is already visible in the page and is also saved in the local JSON history.
- The move selection policy is intentionally deterministic and always picks the first matching cell. That can produce conspicuous spatial patterns; no claim of stealth or undetectability is made.
- The demo does not hide the output from its operator: it shows the labels and recovered message to make the mechanism observable.
- The board has no win condition or game strategy. Its state exists only to make move availability and deterministic decoding concrete.
- Inputs must be non-empty, printable ASCII, and no longer than 15 bytes.

