from __future__ import annotations
import argparse
import copy
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from time import sleep
from typing import Tuple, TypeVar, Type, Iterable, ClassVar
import random
import requests

# maximum and minimum values for our heuristic scores (usually represents an end of game condition)
MAX_HEURISTIC_SCORE = 2000000000
MIN_HEURISTIC_SCORE = -2000000000

filename = ""


class UnitType(Enum):
    """Every unit type."""

    AI = 0
    Tech = 1
    Virus = 2
    Program = 3
    Firewall = 4


class Player(Enum):
    """The 2 players."""

    Attacker = 0
    Defender = 1

    def next(self) -> Player:
        """The next (other) player."""
        if self is Player.Attacker:
            return Player.Defender
        else:
            return Player.Attacker


class GameType(Enum):
    AttackerVsDefender = 0
    AttackerVsComp = 1
    CompVsDefender = 2
    CompVsComp = 3


##############################################################################################################


@dataclass(slots=True)
class Unit:
    player: Player = Player.Attacker
    type: UnitType = UnitType.Program
    health: int = 9
    # class variable: damage table for units (based on the unit type constants in order)
    damage_table: ClassVar[list[list[int]]] = [
        [3, 3, 3, 3, 1],  # AI
        [1, 1, 6, 1, 1],  # Tech
        [9, 6, 1, 6, 1],  # Virus
        [3, 3, 3, 3, 1],  # Program
        [1, 1, 1, 1, 1],  # Firewall
    ]
    # class variable: repair table for units (based on the unit type constants in order)
    repair_table: ClassVar[list[list[int]]] = [
        [0, 1, 1, 0, 0],  # AI
        [3, 0, 0, 3, 3],  # Tech
        [0, 0, 0, 0, 0],  # Virus
        [0, 0, 0, 0, 0],  # Program
        [0, 0, 0, 0, 0],  # Firewall
    ]

    def is_alive(self) -> bool:
        """Are we alive ?"""
        return self.health > 0

    def mod_health(self, health_delta: int):
        """Modify this unit's health by delta amount."""
        self.health += health_delta
        if self.health < 0:
            self.health = 0
        elif self.health > 9:
            self.health = 9

    def to_string(self) -> str:
        """Text representation of this unit."""
        p = self.player.name.lower()[0]
        t = self.type.name.upper()[0]
        return f"{p}{t}{self.health}"

    def __str__(self) -> str:
        """Text representation of this unit."""
        return self.to_string()

    def damage_amount(self, target: Unit) -> int:
        """How much can this unit damage another unit."""
        amount = self.damage_table[self.type.value][target.type.value]
        if target.health - amount < 0:
            return target.health
        return amount

    def repair_amount(self, target: Unit) -> tuple[int, str]:
        """How much can this unit repair another unit."""
        amount = self.repair_table[self.type.value][target.type.value]
        if target.health + amount > 9:
            return [9 - target.health, "full"]
        return [amount, ""]

    def belongs_to(self, player):
        """Check if this unit belongs to the specified player."""
        return self.player == player


##############################################################################################################


@dataclass(slots=True)
class Coord:
    """Representation of a game cell coordinate (row, col)."""

    row: int = 0
    col: int = 0

    def col_string(self) -> str:
        """Text representation of this Coord's column."""
        coord_char = "?"
        if self.col < 16:
            coord_char = "0123456789abcdef"[self.col]
        return str(coord_char)

    def row_string(self) -> str:
        """Text representation of this Coord's row."""
        coord_char = "?"
        if self.row < 26:
            coord_char = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[self.row]
        return str(coord_char)

    def to_string(self) -> str:
        """Text representation of this Coord."""
        return self.row_string() + self.col_string()

    def __str__(self) -> str:
        """Text representation of this Coord."""
        return self.to_string()

    def clone(self) -> Coord:
        """Clone a Coord."""
        return copy.copy(self)

    def iter_range(self, dist: int) -> Iterable[Coord]:
        """Iterates over Coords inside a rectangle centered on our Coord."""
        for row in range(self.row - dist, self.row + 1 + dist):
            for col in range(self.col - dist, self.col + 1 + dist):
                yield Coord(row, col)

    def iter_adjacent(self) -> Iterable[Coord]:
        """Iterates over adjacent Coords."""
        # Up
        if self.row - 1 >= 0:
            yield Coord(self.row - 1, self.col)
        # Left
        if self.col - 1 >= 0:
            yield Coord(self.row, self.col - 1)
        # Down
        if self.row + 1 < 5:  # Assuming BOARD_DIMENSION is the size of the board
            yield Coord(self.row + 1, self.col)
        # Right
        if self.col + 1 < 5:
            yield Coord(self.row, self.col + 1)

    @classmethod
    def from_string(cls, s: str) -> Coord | None:
        """Create a Coord from a string. ex: D2."""
        s = s.strip()
        for sep in " ,.:;-_":
            s = s.replace(sep, "")
        if len(s) == 2:
            coord = Coord()
            coord.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coord.col = "0123456789abcdef".find(s[1:2].lower())
            return coord
        else:
            return None


##############################################################################################################


@dataclass(slots=True)
class CoordPair:
    """Representation of a game move or a rectangular area via 2 Coords."""

    src: Coord = field(default_factory=Coord)
    dst: Coord = field(default_factory=Coord)

    def to_string(self) -> str:
        """Text representation of a CoordPair."""
        return self.src.to_string() + " " + self.dst.to_string()

    def __str__(self) -> str:
        """Text representation of a CoordPair."""
        return self.to_string()

    def clone(self) -> CoordPair:
        """Clones a CoordPair."""
        return copy.copy(self)

    def iter_rectangle(self) -> Iterable[Coord]:
        """Iterates over cells of a rectangular area."""
        for row in range(self.src.row, self.dst.row + 1):
            for col in range(self.src.col, self.dst.col + 1):
                yield Coord(row, col)

    @classmethod
    def from_quad(cls, row0: int, col0: int, row1: int, col1: int) -> CoordPair:
        """Create a CoordPair from 4 integers."""
        return CoordPair(Coord(row0, col0), Coord(row1, col1))

    @classmethod
    def from_dim(cls, dim: int) -> CoordPair:
        """Create a CoordPair based on a dim-sized rectangle."""
        return CoordPair(Coord(0, 0), Coord(dim - 1, dim - 1))

    @classmethod
    def from_string(cls, s: str) -> CoordPair | None:
        """Create a CoordPair from a string. ex: A3 B2"""
        s = s.strip()
        for sep in " ,.:;-_":
            s = s.replace(sep, "")
        if len(s) == 4:
            coords = CoordPair()
            coords.src.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coords.src.col = "0123456789abcdef".find(s[1:2].lower())
            coords.dst.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[2:3].upper())
            coords.dst.col = "0123456789abcdef".find(s[3:4].lower())
            return coords
        else:
            return None


##############################################################################################################


@dataclass(slots=True)
class Options:
    """Representation of the game options."""

    dim: int = 5
    max_depth: int | None = 3
    min_depth: int | None = 2
    max_time: float | None = 5.0
    game_type: GameType = GameType.AttackerVsDefender
    alpha_beta: bool = True
    max_turns: int | None = 100
    randomize_moves: bool = True
    broker: str | None = None


##############################################################################################################


@dataclass(slots=True)
class Stats:
    """Representation of the global game statistics."""

    evaluations_per_depth: dict[int, int] = field(default_factory=dict)
    total_seconds: float = 0.0


##############################################################################################################


@dataclass(slots=True)
class Game:
    """Representation of the game state."""

    board: list[list[Unit | None]] = field(default_factory=list)
    next_player: Player = Player.Attacker
    turns_played: int = 1
    options: Options = field(default_factory=Options)
    stats: Stats = field(default_factory=Stats)
    _attacker_has_ai: bool = True
    _defender_has_ai: bool = True

    """Check if player's AI unit is self-destructed """
    _attacker_ai_self_destructed: bool = False
    _defender_ai_self_destructed: bool = False

    def __post_init__(self):
        """Automatically called after class init to set up the default board state."""
        dim = self.options.dim
        self.board = [[None for _ in range(dim)] for _ in range(dim)]
        md = dim - 1
        self.set(Coord(0, 0), Unit(player=Player.Defender, type=UnitType.AI))
        self.set(Coord(1, 0), Unit(player=Player.Defender, type=UnitType.Tech))
        self.set(Coord(0, 1), Unit(player=Player.Defender, type=UnitType.Tech))
        self.set(Coord(2, 0), Unit(player=Player.Defender, type=UnitType.Firewall))
        self.set(Coord(0, 2), Unit(player=Player.Defender, type=UnitType.Firewall))
        self.set(Coord(1, 1), Unit(player=Player.Defender, type=UnitType.Program))
        self.set(Coord(md, md), Unit(player=Player.Attacker, type=UnitType.AI))
        self.set(Coord(md - 1, md), Unit(player=Player.Attacker, type=UnitType.Virus))
        self.set(Coord(md, md - 1), Unit(player=Player.Attacker, type=UnitType.Virus))
        self.set(Coord(md - 2, md), Unit(player=Player.Attacker, type=UnitType.Program))
        self.set(Coord(md, md - 2), Unit(player=Player.Attacker, type=UnitType.Program))
        self.set(
            Coord(md - 1, md - 1), Unit(player=Player.Attacker, type=UnitType.Firewall)
        )

    def clone(self) -> Game:
        """Make a new copy of a game for minimax recursion.

        Shallow copy of everything except the board (options and stats are shared).
        """
        new = copy.copy(self)
        new.board = copy.deepcopy(self.board)
        return new

    def is_empty(self, coord: Coord) -> bool:
        """Check if contents of a board cell of the game at Coord is empty (must be valid coord)."""
        return self.board[coord.row][coord.col] is None

    def get(self, coord: Coord) -> Unit | None:
        """Get contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            return self.board[coord.row][coord.col]
        else:
            return None

    def set(self, coord: Coord, unit: Unit | None):
        """Set contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            self.board[coord.row][coord.col] = unit

    def remove_dead(self, coord: Coord):
        """Remove unit at Coord if dead."""
        unit = self.get(coord)
        if unit is not None and not unit.is_alive():
            self.set(coord, None)
            if unit.type == UnitType.AI:
                if unit.player == Player.Attacker:
                    self._attacker_has_ai = False
                else:
                    self._defender_has_ai = False

    def is_valid_move(self, coords: CoordPair) -> tuple[bool, str]:
        """Validate a move expressed as a CoordPair."""
        # check if coordinate is within the board
        if not self.is_valid_coord(coords.src) or not self.is_valid_coord(coords.dst):
            return (False, "Coordinate not within board! Try again.\n")
        # Check whether source space is empty or belongs to current player
        unit = self.get(coords.src)
        if unit is None or unit.player != self.next_player:
            return (False, f"Choose a {self.next_player.name} unit! Try again. \n")
        return (True, "")

    def is_movement_valid(self, coords: CoordPair) -> Tuple[bool, str]:
        """Validate if the movement action is valid"""
        unit = self.get(coords.src)
        # check if the unit is an AI, firewall or a program.
        if (
            unit.type == UnitType.AI
            or unit.type == UnitType.Firewall
            or unit.type == UnitType.Program
        ):
            if unit.player == Player.Attacker:
                # check if attacking unit is only moving up or left
                if not (
                    coords.dst == Coord(coords.src.row - 1, coords.src.col)
                    or coords.dst == Coord(coords.src.row, coords.src.col - 1)
                ):
                    return (
                        False,
                        f"{unit} can only move up or left by one! Try again.\n",
                    )

            else:
                # check if defending unit is only moving down or right
                if not (
                    coords.dst == Coord(coords.src.row + 1, coords.src.col)
                    or coords.dst == Coord(coords.src.row, coords.src.col + 1)
                ):
                    return (
                        False,
                        f"{unit} can only move down or right by one! Try again.\n",
                    )

            # check if unit is engaged in battle
            for adj_coord in coords.src.iter_adjacent():
                adj_unit = self.get(adj_coord)
                if adj_unit is not None and adj_unit.player != self.next_player:
                    return (
                        False,
                        f"{unit} is engaged in battle with {adj_unit}! Try again.\n",
                    )
        else:
            # Check if the virus or the tech is moving left, up, right or down by one
            if not (
                coords.dst == Coord(coords.src.row + 1, coords.src.col)
                or coords.dst == Coord(coords.src.row, coords.src.col + 1)
                or coords.dst == Coord(coords.src.row - 1, coords.src.col)
                or coords.dst == Coord(coords.src.row, coords.src.col - 1)
            ):
                return (
                    False,
                    f"{unit} can only move left, up, right or down by one! Try again.\n",
                )
        # Check destination space
        unit = self.get(coords.dst)
        if unit is not None:
            return (False, "Destination space occupied! Try again.\n")
        return (True, "Movement performed successfully")

    def perform_move(self, coords: CoordPair) -> Tuple[bool, str]:
        """Validate and perform a move expressed as a CoordPair."""

        src_unit = self.get(coords.src)
        dst_unit = self.get(coords.dst)

        # If T = S, the action is self-destruction
        if coords.src == coords.dst:
            # Prevent AI from self-destructing
            if self.options.game_type in [
                GameType.AttackerVsComp,
                GameType.CompVsDefender,
                GameType.CompVsComp,
            ]:
                return (False, "AI cannot self-destruct")
            return self.self_destruct(coords.src)

        # If the target T is an empty cell, the action is movement
        elif dst_unit is None:
            if self.is_valid_move(coords):
                (success, result) = self.is_movement_valid(coords)
                if success:
                    self.set(coords.dst, src_unit)
                    self.set(coords.src, None)
                    return (True, result)
                else:
                    return (False, result)
            else:
                return (False, "Invalid move")

        # If the target T is an adversarial unit, the action is an attack
        elif dst_unit.player != src_unit.player:
            return self.attack(coords.src, coords.dst)

        # If the target T is a friendly unit, the action is a repair
        elif dst_unit.player == src_unit.player:
            return self.repair(coords.src, coords.dst)

        # Default case (shouldn't be reached)
        return (False, "Unknown action")

    def next_turn(self):
        if self.next_player == Player.Attacker:
            self.next_player = Player.Defender
        else:
            self.next_player = Player.Attacker
        self.turns_played += 1

    def to_string(self) -> str:
        """Pretty text representation of the game."""
        output = ""
        output += "------------------------------------\n"
        output += f"Turn: {self.next_player.name}\n"
        output += f"Turns played: {self.turns_played}\n"
        output += "\n   "
        output += self.board_to_string()

        # record to file
        global filename
        actionInfo = "\n------------------------\n"
        actionInfo += f"Turn #{self.turns_played}\n"
        actionInfo += f"{self.next_player.name}\n"
        with open(filename, "a") as file:
            file.write(actionInfo)

        return output

    def board_to_string(self) -> str:
        """Initial Configuration of board (Text format)"""
        dim = self.options.dim
        coord = Coord()
        board = ""
        for col in range(dim):
            coord.col = col
            label = coord.col_string()
            board += f"{label:^3} "
        board += "\n"
        for row in range(dim):
            coord.row = row
            label = coord.row_string()
            board += f"{label}: "
            for col in range(dim):
                coord.col = col
                unit = self.get(coord)
                if unit is None:
                    board += " .  "
                else:
                    board += f"{str(unit):^3} "
            board += "\n"
        return board

    def __str__(self) -> str:
        """Default string representation of a game."""
        return self.to_string()

    def is_valid_coord(self, coord: Coord) -> bool:
        """Check if a Coord is valid within out board dimensions."""
        dim = self.options.dim
        if coord.row < 0 or coord.row >= dim or coord.col < 0 or coord.col >= dim:
            return False
        return True

    def read_move(self) -> CoordPair:
        """Read a move from keyboard and return as a CoordPair."""
        while True:
            s = input(f"Player {self.next_player.name}, enter your move: ")
            coords = CoordPair.from_string(s)
            if coords is not None:
                return coords
            else:
                print("Not a coordinate (e.g. c4 b4)! Try again.\n")

    def human_turn(self):
        """Allows the human player to make a move in the game."""

        global filename  # Use the global variable 'filename' for recording actions

        while True:
            try:
                # Get the coordinates of the players action
                mv = self.read_move()
                # Check the validity of the move
                (success, error_msg) = self.is_valid_move(mv)
                if success:
                    src_unit = self.get(mv.src)
                    dst_unit = self.get(mv.dst)

                    # Handle the 'Move' action
                    if dst_unit is None:
                        (success, result) = self.is_movement_valid(mv)
                        if success:
                            self.set(mv.dst, self.get(mv.src))
                            self.set(mv.src, None)
                            print("Move performed successfully")
                            self.next_turn()

                            # Record the move action to the file
                            actionInfo = f"Move from {chr(65 + mv.src.row)}{mv.src.col} to {chr(65 + mv.dst.row)}{mv.dst.col}\n"
                            actionInfo += f"\t{self.board_to_string()}"
                            with open(filename, "a") as file:
                                file.write(actionInfo)

                            break
                        else:
                            print(result)

                    # Handle the 'Attack' action
                    elif dst_unit.player != src_unit.player:
                        (success, result) = self.attack(mv.src, mv.dst)
                        if success:
                            print(result)
                            self.next_turn()

                            # Record the attack action to the file
                            actionInfo = f"Attack from {chr(65 + mv.src.row)}{mv.src.col} to {chr(65 + mv.dst.row)}{mv.dst.col}\n"
                            actionInfo += f"\t{self.board_to_string()}"
                            with open(filename, "a") as file:
                                file.write(actionInfo)
                            break
                        else:
                            print(result)

                    # Handle the 'Repair' action
                    elif src_unit.player == dst_unit.player and mv.src != mv.dst:
                        (success, result) = self.repair(mv.src, mv.dst)
                        if success:
                            print(result)
                            self.next_turn()

                            # Record the repair action to the file
                            actionInfo = f"Repair from {chr(65 + mv.src.row)}{mv.src.col} to {chr(65 + mv.dst.row)}{mv.dst.col}\n"
                            actionInfo += f"\t{self.board_to_string()}"
                            with open(filename, "a") as file:
                                file.write(actionInfo)
                            break
                        else:
                            print(result)

                    # Handle the 'Self-destruct' action
                    elif mv.src == mv.dst:
                        if self.board_belongs_to_current_player(mv.src):
                            (success, result) = self.self_destruct(mv.src)
                            if success:
                                print(result)
                                self.next_turn()

                                # Record the attack action to the file
                                actionInfo = f"{chr(65 + mv.src.row)}{mv.src.col} self-destructed. \n"
                                actionInfo += f"\t{self.board_to_string()}"
                                with open(filename, "a") as file:
                                    file.write(actionInfo)
                                break
                            else:
                                print(
                                    "The self-destruct action is not valid! Try again.\n"
                                )
                        else:
                            print("You can't self-destruct an opponent's unit!\n")
                else:
                    print(error_msg)
            except ValueError:
                # Handle invalid input types (e.g., non-numeric input)
                print("Invalid input! Please enter a valid number.\n")

    def computer_turn(self) -> CoordPair | None:
        """
        Executes the computer's turn in the game.

        The computer uses the suggest_move method to determine its move.
        If the move is valid, it is performed, and the game proceeds to the next turn.
        If the move is invalid (illegal), the computer loses the game.

        Returns:
        - The CoordPair representing the move made by the computer, or None if no move was made.
        """

        # Get the suggested move for the computer
        mv = self.suggest_move()

        # If a move is suggested
        if mv is not None:
            # Try to perform the move
            (success, result) = self.perform_move(mv)

            # If the move is successful
            if success:
                print(f"Computer {self.next_player.name}: ", end="")
                print(result)
                # Proceed to the next turn
                self.next_turn()
            else:
                # Handle the case where the AI generates an illegal action
                print("AI generated an illegal action!")
                # Determine the winner based on the current player (the computer)
                if self.next_player == Player.Attacker:
                    print("Defender wins!")
                    self.is_finished()
                else:
                    print("Attacker wins!")
                    self.is_finished()
                return None
        return mv

    def has_winner(self) -> Player | None:
        """Check if the game is over and returns winner."""

        # Check if both players have 0 units on the board
        if self.check_zero_units():
            return Player.Defender

        # Check if the maximum number of turns has been played
        if (
            self.options.max_turns is not None
            and self.turns_played > self.options.max_turns
        ):
            return Player.Defender

        # Check if the attacker has no AI units left
        elif not self._attacker_has_ai:
            return Player.Defender

        # Check if the defender has no AI units left
        elif not self._defender_has_ai:
            return Player.Attacker

        # Check if no action is available to the current player
        elif not any(self.move_candidates()):
            return (
                Player.Defender
                if self.next_player == Player.Attacker
                else Player.Attacker
            )

        # Check if either player's AI unit has self-destructed
        elif self._attacker_ai_self_destructed:
            return Player.Defender
        elif self._defender_ai_self_destructed:
            return Player.Attacker

        # If none of the above conditions are met, the game is still ongoing
        else:
            return None

    def is_finished(self) -> bool:
        """Check if the game is over."""
        return self.has_winner() is not None

    def player_units(self, player: Player) -> Iterable[Tuple[Coord, Unit]]:
        """Iterates over all units belonging to a player."""
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None and unit.player == player:
                yield (coord, unit)

    def check_zero_units(self) -> bool:
        """Check if both players have zero units on the board."""
        # Iterate through the game board and count units for each player
        attacker_units = 0
        defender_units = 0

        for row in self.board:
            for unit in row:
                if unit is not None:
                    if unit.belongs_to(Player.Attacker):
                        attacker_units += 1
                    elif unit.belongs_to(Player.Defender):
                        defender_units += 1

        # Check if both players have 0 units on the board
        return attacker_units == 0 and defender_units == 0

    def move_candidates(self) -> Iterable[CoordPair]:
        """
        Generate all possible move candidates for the next player.

        This method considers all types of moves:
        1. Regular movement to an empty cell.
        2. Attack on an adversarial unit.
        3. Repair on a friendly unit.
        4. Self-destruction.

        Yields:
        - CoordPair representing the source and destination coordinates of a valid move.
        """

        # Initialize a CoordPair to store the current move being considered
        move = CoordPair()

        # Iterate over all units of the next player
        for src, _ in self.player_units(self.next_player):
            move.src = src

            # Check all adjacent cells as potential destinations
            for dst in src.iter_adjacent():
                move.dst = dst

                # If moving to the destination is valid, yield the move
                if self.is_valid_move(move):
                    if self.is_movement_valid(move):
                        yield move.clone()

                # Check if a repair move is possible
                unit_at_dst = self.get(dst)
                if (
                    unit_at_dst is not None
                    and unit_at_dst.player == self.next_player
                    and src != dst
                ):
                    yield move.clone()

            # Consider the self-destruction move where source and destination are the same
            move.dst = src
            yield move.clone()

    # def random_move(self) -> Tuple[int, CoordPair | None, float]:
    #     """Returns a random move."""
    #     move_candidates = list(self.move_candidates())
    #     random.shuffle(move_candidates)
    #     if len(move_candidates) > 0:
    #         return 0, move_candidates[0], 1
    #     else:
    #         return 0, None, 0

    def suggest_move(self) -> CoordPair | None:
        """
        Suggest the best move for the current player using the Minimax algorithm with or without Alpha-Beta pruning.

        Returns:
        - The best move as a CoordPair or None if no valid move is found.
        """

        # Record the start time to calculate the time taken by the algorithm
        start_time = datetime.now()

        # Check if alpha-beta pruning should be used
        if self.options.alpha_beta:
            # Use the Minimax algorithm with Alpha-Beta pruning to get the best move and its heuristic score
            (score, move) = self.minimax_alpha_beta(
                self.options.max_depth, float("-inf"), float("inf"), True
            )
        else:
            # Use just the Minimax algorithm to get the best move and its heuristic score
            # Note: You'll need to implement the minimax method without alpha-beta pruning
            (score, move) = self.minimax_alpha_beta(
                self.options.max_depth, float("-inf"), float("inf"), False
            )

        # Calculate the time taken by the algorithm
        elapsed_seconds = (datetime.now() - start_time).total_seconds()

        # Update the total time taken by all calls to this method
        self.stats.total_seconds += elapsed_seconds

        # Print the heuristic score of the best move and the time taken by the algorithm
        print(f"Heuristic score: {score}")
        print(f"Elapsed time: {elapsed_seconds:0.1f}s")

        # Return the best move
        return move

    def evaluate_board(self):
        # Calculate the weighted sum of Player 1's units
        score_p1 = (
            3 * self.count_units(UnitType.Virus, Player.Attacker)
            + 3 * self.count_units(UnitType.Tech, Player.Attacker)
            + 3 * self.count_units(UnitType.Firewall, Player.Attacker)
            + 3 * self.count_units(UnitType.Program, Player.Attacker)
            + 9999 * self.count_units(UnitType.AI, Player.Attacker)
        )
        # Calculate the weighted sum of Player 2's units
        score_p2 = (
            3 * self.count_units(UnitType.Virus, Player.Defender)
            + 3 * self.count_units(UnitType.Tech, Player.Defender)
            + 3 * self.count_units(UnitType.Firewall, Player.Defender)
            + 3 * self.count_units(UnitType.Program, Player.Defender)
            + 9999 * self.count_units(UnitType.AI, Player.Defender)
        )
        if self.next_player == Player.Attacker:
            return score_p1 - score_p2
        else:
            return score_p2 - score_p1

    def count_units(self, unit_type: UnitType, player: Player) -> int:
        """Count the number of units of a specific type and player on the board."""
        count = 0
        for row in self.board:
            for unit in row:
                if (
                    unit is not None
                    and unit.type == unit_type
                    and unit.player == player
                ):
                    count += 1
        return count

    def minimax_alpha_beta(self, depth, alpha, beta, is_maximizing):
        """
        Use the Minimax algorithm with Alpha-Beta pruning to determine the best move.

        Parameters:
        - depth: The depth of the search tree.
        - alpha: The best value that the maximizer currently can guarantee at that level or above.
        - beta: The best value that the minimizer currently can guarantee at that level or above.
        - is_maximizing: True if the current move is by the maximizing player, otherwise False.

        Returns:
        - The heuristic value of the board after the best move.
        - The best move as a CoordPair.
        """

        # Base case: if the search has reached maximum depth or the game is finished
        if depth == 0 or self.is_finished():
            return self.evaluate_board(), None

        best_move = None

        # Maximizing player's turn
        if is_maximizing:
            max_eval = float("-inf")
            for move in self.move_candidates():
                # Simulate the game after making the move
                simulated_game = self.clone()
                # Try to perform the move and skip if it's not valid
                success, _ = simulated_game.perform_move(move)
                if not success:
                    continue
                # Recursively evaluate the board after the move
                eval_value, _ = self.minimax_alpha_beta(depth - 1, alpha, beta, False)
                # Update the best move if the current move has a better evaluation
                if eval_value > max_eval:
                    max_eval = eval_value
                    best_move = move
                # Update alpha and prune the search tree if necessary
                alpha = max(alpha, eval_value)
                if beta <= alpha:
                    break
            return max_eval, best_move

        # Minimizing player's turn
        else:
            min_eval = float("inf")
            for move in self.move_candidates():
                # Simulate the game after making the move
                simulated_game = self.clone()
                # Try to perform the move and skip if it's not valid
                success, _ = simulated_game.perform_move(move)
                if not success:
                    continue
                # Recursively evaluate the board after the move
                eval_value, _ = self.minimax_alpha_beta(depth - 1, alpha, beta, True)
                # Update the best move if the current move has a better evaluation
                if eval_value < min_eval:
                    min_eval = eval_value
                    best_move = move
                # Update beta and prune the search tree if necessary
                beta = min(beta, eval_value)
                if beta <= alpha:
                    break
            return min_eval, best_move

    def post_move_to_broker(self, move: CoordPair):
        """Send a move to the game broker."""
        if self.options.broker is None:
            return
        data = {
            "from": {"row": move.src.row, "col": move.src.col},
            "to": {"row": move.dst.row, "col": move.dst.col},
            "turn": self.turns_played,
        }
        try:
            r = requests.post(self.options.broker, json=data)
            if (
                r.status_code == 200
                and r.json()["success"]
                and r.json()["data"] == data
            ):
                # print(f"Sent move to broker: {move}")
                pass
            else:
                print(
                    f"Broker error: status code: {r.status_code}, response: {r.json()}"
                )
        except Exception as error:
            print(f"Broker error: {error}")

    def get_move_from_broker(self) -> CoordPair | None:
        """Get a move from the game broker."""
        if self.options.broker is None:
            return None
        headers = {"Accept": "application/json"}
        try:
            r = requests.get(self.options.broker, headers=headers)
            if r.status_code == 200 and r.json()["success"]:
                data = r.json()["data"]
                if data is not None:
                    if data["turn"] == self.turns_played + 1:
                        move = CoordPair(
                            Coord(data["from"]["row"], data["from"]["col"]),
                            Coord(data["to"]["row"], data["to"]["col"]),
                        )
                        print(f"Got move from broker: {move}")
                        return move
                    else:
                        # print("Got broker data for wrong turn.")
                        # print(f"Wanted {self.turns_played+1}, got {data['turn']}")
                        pass
                else:
                    # print("Got no data from broker")
                    pass
            else:
                print(
                    f"Broker error: status code: {r.status_code}, response: {r.json()}"
                )
        except Exception as error:
            print(f"Broker error: {error}")
        return None

    # attack actions
    def attack(self, attacker_coord: Coord, target_coord: Coord) -> Tuple[bool, str]:
        # Retrieve the units at the attacker and target coordinates
        attacker_unit = self.get(attacker_coord)
        target_unit = self.get(target_coord)

        # Rule 1: Check if either the attacker or target unit is None, indicating an invalid attack attempt
        if attacker_unit is None or target_unit is None:
            return False, "Invalid attack attempt! Try again.\n"

        # Rule 2：Check if the attacker and target units belong to different players (are adversarial)
        if not attacker_unit.player.next() == target_unit.player:
            return False, "Units are not adversarial! Try again.\n"

        # Rule 3: Check if the attacker and target units are adjacent on the board
        if not self.is_adjacent(attacker_coord, target_coord):
            return False, "Units are not adjacent! Try again.\n"

        # Calculate and apply damage to the target unit based on the attacker unit's damage amount
        damage = attacker_unit.damage_amount(target_unit)
        target_unit.mod_health(-damage)
        self.remove_dead(target_coord)

        # Bidirectional combat: Calculate and apply damage back to the attacker unit
        damage_back = target_unit.damage_amount(attacker_unit)
        attacker_unit.mod_health(-damage_back)
        self.remove_dead(attacker_coord)

        # Return success message with details of the attack
        return (
            True,
            f"{attacker_unit.player.name}'s {attacker_unit.type.name} attacked {target_unit.player.name}'s {target_unit.type.name}",
        )

    # repair actions
    def repair(self, repairer_coord: Coord, target_coord: Coord) -> Tuple[bool, str]:
        # Retrieve the units at the repairer and target coordinates
        repairer_unit = self.get(repairer_coord)
        target_unit = self.get(target_coord)

        # Rule 1: Check if units are adjacent
        if not self.is_adjacent(repairer_coord, target_coord):
            return False, "Invalid repair action: units are not adjacent\n"

        # Rule 2: Check if units are friendly
        if (
            repairer_unit is None
            or target_unit is None
            or not repairer_unit.player == target_unit.player
        ):
            return False, "Invalid repair action: units are not friendly\n"

        # Rule 3a: Check if the repair leads to a change in health
        (repair_amount, result) = repairer_unit.repair_amount(target_unit)
        if repair_amount == 0 and result == "full":
            return (
                False,
                f"Invalid repair action: {target_unit} is already full HP\n",
            )
        elif repair_amount == 0:
            return (
                False,
                f"Invalid repair action: {repairer_unit} cannot repair {target_unit}\n",
            )

        # Rule 3b: Check if target unit's health is already at 9
        if target_unit.health == 9:
            return (
                False,
                "Invalid repair action: Target unit's health is already at maximum\n",
            )

        # Apply the repair amount to the target unit's health
        target_unit.mod_health(repair_amount)

        # Return success message with details of the repair action
        return (
            True,
            f"{repairer_unit.player.name}'s {repairer_unit.type.name} repaired {target_unit.player.name}'s {target_unit.type.name}",
        )

    # Check if the coordinates are adjacent
    def is_adjacent(self, coord1: Coord, coord2: Coord) -> bool:
        # Calculate the difference in rows and columns between the two coordinates
        # Check if the sum of the row and column differences is 1, indicating that the coordinates are adjacent
        return abs(coord1.row - coord2.row) + abs(coord1.col - coord2.col) == 1

    def is_ai_self_destruct(self, player: Player):
        """Check if player's AI is self-destructed."""
        if player == Player.Attacker:
            self._attacker_ai_self_destructed = (
                True  # Set the flag for the attacker's AI unit.
            )
        elif player == Player.Defender:
            self._defender_ai_self_destructed = (
                True  # Set the flag for the defender's AI unit.
            )

    def self_destruct(self, coord: Coord) -> Tuple[bool, str]:
        """Perform self-destruct action for the unit at the given coordinates."""
        unit = self.get(coord)

        # Check if the unit belongs to an AI player and trigger ai_self_destruct accordingly
        if unit.type == UnitType.AI:
            self.is_ai_self_destruct(unit.player)

        if unit is None or not unit.is_alive():
            # No unit to self-destruct
            return False, "Invalid self-destruct attempt"

        # Inflict 2 points of damage to all 8 surrounding units
        for adjacent_coord in coord.iter_range(1):
            if self.is_valid_coord(adjacent_coord):
                self.mod_health(adjacent_coord, -2)

        # Remove the self-destructed unit from the board
        self.set(coord, None)

        return True, f"{unit.player.name}'s {unit.type.name} self-destructed at {coord}"

    def board_belongs_to_current_player(self, coord: Coord) -> bool:
        """Check if the unit at the given coordinates belongs to the current player."""
        # Retrieve the unit at the specified coordinates
        unit = self.get(
            coord
        )  # Assuming you have a method called 'get' to retrieve a unit based on coordinates

        # If there's no unit at the coordinates, or the unit does not belong to the current player, return False
        return unit is not None and unit.belongs_to(self.next_player)

    def mod_health(self, coord: Coord, health_delta: int):
        target = self.get(coord)
        if target is not None:
            target.mod_health(health_delta)
            self.remove_dead(coord)


##############################################################################################################
def choose_game_mode_interactive():
    print("\nChoose a game mode:")
    print("1. AttackerVsDefender")
    print("2. AttackerVsComp")
    print("3. CompVsDefender")
    print("4. CompVsComp")
    choice = int(input("Enter your choice (1-4): "))
    while choice not in [1, 2, 3, 4]:
        print("Invalid choice. Please choose between 1 and 4.")
        choice = int(input("Enter your choice (1-4): "))
    print("\n------------------------------------")
    match choice:
        case 1:
            print("Mode: Attacker vs Defender")
        case 2:
            print("Mode: Attacker vs Computer")
        case 3:
            print("Mode: Computer vs Defender")
        case _:
            print("Mode: Computer vs Computer")
    return GameType(choice - 1)


def main():
    # parse command line arguments
    parser = argparse.ArgumentParser(
        prog="ai_wargame", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--max_depth", type=int, help="maximum search depth")
    parser.add_argument("--max_time", type=float, help="maximum search time")
    parser.add_argument(
        "--game_type",
        type=str,
        default=None,
        help="game type: auto|attacker|defender|manual",
    )
    parser.add_argument("--broker", type=str, help="play via a game broker")
    args = parser.parse_args()

    # parse the game type
    if args.game_type is None:
        chosen_game_type = choose_game_mode_interactive()
    else:
        # parse the game type based on command line arguments
        if args.game_type == "attacker":
            chosen_game_type = GameType.AttackerVsComp
        elif args.game_type == "defender":
            chosen_game_type = GameType.CompVsDefender
        elif args.game_type == "manual":
            chosen_game_type = GameType.AttackerVsDefender
        else:
            chosen_game_type = GameType.CompVsComp

    # set up game options
    options = Options(game_type=chosen_game_type)

    # override class defaults via command line options
    if args.max_depth is not None:
        options.max_depth = args.max_depth
    if args.max_time is not None:
        options.max_time = args.max_time
    if args.broker is not None:
        options.broker = args.broker

    # create a new game
    game = Game(options=options)

    # creating the output file
    b = game.options.alpha_beta
    t = game.options.max_time
    m = game.options.max_turns
    global filename
    filename = f"gameTrace-{b}-{t}-{m}.txt"

    game_parameters = ""
    game_parameters += f"1. The game parameters\n"
    game_parameters += f"a) Timeout (seconds): {t}\n"
    game_parameters += f"b) Max number of turns: {m}\n"
    game_parameters += f"c) Alpha-beta: {b}\n"
    game_parameters += f"d) Play Mode: Player 1 = H & Player 2 = H\n"
    game_parameters += f"e) Name of heuristic: \n"
    init_conf = f"\n"
    init_conf += f"2. The initial configuration of the board:\n"
    init_conf += f"\t{game.board_to_string()} \n"
    action = f"3. Action \n3.1 Action info"
    # record information to file
    with open(filename, "w") as file:
        file.write(game_parameters + init_conf + action)

    # the main game loop
    while True:
        print(game)
        winner = game.has_winner()
        if winner is not None:
            print(f"{winner.name} wins!")
            # Record winner to file
            winnerInfo = f"\n4. Game Result\n"
            winnerInfo += f"{winner.name} wins in {game.turns_played} turns"
            with open(filename, "a") as file:
                file.write(winnerInfo)
            break
        if game.options.game_type == GameType.AttackerVsDefender:
            game.human_turn()
        elif (
            game.options.game_type == GameType.AttackerVsComp
            and game.next_player == Player.Attacker
        ):
            game.human_turn()
        elif (
            game.options.game_type == GameType.CompVsDefender
            and game.next_player == Player.Defender
        ):
            game.human_turn()
        else:
            player = game.next_player
            move = game.computer_turn()
            if move is not None:
                game.post_move_to_broker(move)
            else:
                print("Computer doesn't know what to do!!!")
                exit(1)


##############################################################################################################

if __name__ == "__main__":
    main()
