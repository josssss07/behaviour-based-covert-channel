#!/usr/bin/env python3
"""Small local demo: encode printable text as moves on an 8x8 board."""

import argparse
import unittest

BOARD_SIZE = 8
MAX_MESSAGE_BYTES = 15
Move = tuple[int, int]


def legal_moves(board: list[Move | None]) -> list[Move]:
    return [(i // 8, i % 8) for i, cell in enumerate(board) if cell is None]


def encode_message(message: str) -> list[Move]:
    try:
        data = message.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("message must be printable ASCII") from error
    if not data or any(byte < 32 or byte > 126 for byte in data):
        raise ValueError("message must be printable ASCII")
    if len(data) > MAX_MESSAGE_BYTES:
        raise ValueError("message must be 15 characters or fewer")

    board: list[Move | None] = [None] * 64
    moves = []
    for byte in data:
        for shift in (6, 4, 2, 0):
            symbol = (byte >> shift) & 3
            move = next(move for rank, move in enumerate(legal_moves(board)) if rank % 4 == symbol)
            board[move[0] * 8 + move[1]] = move
            moves.append(move)
    return moves


def decode_moves(moves: list[Move]) -> str:
    if not moves or len(moves) % 4:
        raise ValueError("moves must contain four moves per character")

    board: list[Move | None] = [None] * 64
    result = bytearray()
    value = 0
    for index, move in enumerate(moves):
        if (
            not isinstance(move, tuple)
            or len(move) != 2
            or any(type(part) is not int or not 0 <= part < 8 for part in move)
        ):
            raise ValueError(f"invalid move: {move}")
        choices = legal_moves(board)
        if move not in choices:
            raise ValueError(f"repeated move: {move}")
        value = (value << 2) | (choices.index(move) % 4)
        board[move[0] * 8 + move[1]] = move

        if index % 4 == 3:
            if not 32 <= value <= 126:
                raise ValueError("moves do not decode to printable ASCII")
            result.append(value)
            value = 0
    return result.decode("ascii")


def run(message: str) -> None:
    moves = encode_message(message)
    board: list[Move | None] = [None] * 64
    for number, move in enumerate(moves, 1):
        rank = legal_moves(board).index(move)
        board[move[0] * 8 + move[1]] = move
        print(f"Move {number}: row {move[0] + 1}, column {move[1] + 1}, symbol {rank % 4:02b}")

    print("\nBoard (X = selected):")
    for row in range(8):
        print(" ".join("X" if board[row * 8 + col] else "." for col in range(8)))
    print(f"\nSent:     {message}")
    print(f"Decoded:  {decode_moves(moves)}")


class Tests(unittest.TestCase):
    def test_round_trip(self):
        for text in ("A", "HELLO", "Local demo 123", "A" * MAX_MESSAGE_BYTES):
            self.assertEqual(decode_moves(encode_message(text)), text)

    def test_invalid_message(self):
        for text in ("", "line\nbreak", "café", "A" * 16):
            with self.assertRaises(ValueError):
                encode_message(text)

    def test_invalid_moves(self):
        with self.assertRaises(ValueError):
            decode_moves([(0, 0)] * 4)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message", default="HELLO")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
        )
        raise SystemExit(not result.wasSuccessful())
    try:
        run(args.message)
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
