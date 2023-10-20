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

    def repair_amount(self, target: Unit) -> int:
        """How much can this unit repair another unit."""
        amount = self.repair_table[self.type.value][target.type.value]
        return amount

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
    alpha_beta: bool = False
    max_turns: int | None = 100
    randomize_moves: bool = True
    broker: str | None = None
    heuristic: int | None = 0


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

    # Add attributes for statistics tracking
    total_nodes: int = 0
    eval_by_depth = {}
    non_leaf_nodes: int = 0

    # reset statistics
    def reset_statistics(self):
        self.total_nodes = 0
        self.eval_by_depth.clear()
        self.non_leaf_nodes = 0

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
        src_unit = self.get(coords.src)
        # check if the src unit is an AI, firewall or a program.
        if (
            src_unit.type == UnitType.AI
            or src_unit.type == UnitType.Firewall
            or src_unit.type == UnitType.Program
        ):
            if src_unit.player == Player.Attacker:
                # check if attacking unit is only moving up or left
                if not (
                    coords.dst == Coord(coords.src.row - 1, coords.src.col)
                    or coords.dst == Coord(coords.src.row, coords.src.col - 1)
                ):
                    return (
                        False,
                        f"Invalid move attempt: {src_unit} can only move up or left by one!\n",
                    )

            else:
                # check if defending unit is only moving down or right
                if not (
                    coords.dst == Coord(coords.src.row + 1, coords.src.col)
                    or coords.dst == Coord(coords.src.row, coords.src.col + 1)
                ):
                    return (
                        False,
                        f"Invalid move attempt: {src_unit} can only move down or right by one!\n",
                    )

            # check if unit is engaged in battle
            for adj_coord in coords.src.iter_adjacent():
                adj_unit = self.get(adj_coord)
                if adj_unit is not None and adj_unit.player != self.next_player:
                    return (
                        False,
                        f"Invalid move attempt: {src_unit} is engaged in battle with {adj_unit}!\n",
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
                    f"Invalid move attempt: {src_unit} can only move left, up, right or down by one!\n",
                )
        # Check destination space
        dst_unit = self.get(coords.dst)
        if dst_unit is not None:
            return (False, "Invalid move attempt: Destination space occupied!\n")
        return (True, f"{src_unit} at {coords.src} moved to {coords.dst}")

    def perform_move(self, coords: CoordPair) -> Tuple[bool, str]:
        """Validate and perform a move expressed as a CoordPair."""

        src_unit = self.get(coords.src)
        dst_unit = self.get(coords.dst)

        # If T = S, the action is self-destruction
        if coords.src == coords.dst:
            return self.self_destruct(coords.src)

        # If the target T is an empty cell, the action is movement
        elif dst_unit is None:
            (success, result) = self.is_valid_move(coords)
            if success:
                (success, move_result) = self.is_movement_valid(coords)
                if success:
                    self.set(coords.dst, src_unit)
                    self.set(coords.src, None)
                    return (True, move_result)
                else:
                    return (False, move_result)
            else:
                return (False, result)

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
                            print(result)
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

        # If no move is suggested or the game is finished, handle the end of the game
        if mv is None or self.is_finished():
            self.handle_game_end()
            return None

        # Try to perform the move
        (success, result) = self.perform_move(mv)

        # If the move is successful, print and save statistics, then proceed to the next turn
        if success:
            print(f"Computer {self.next_player.name}: {result}")
            self.print_cumulative_info()
            self.write_statistics_to_file(result)
            self.next_turn()
        else:
            # Handle the case where the AI generates an illegal action
            self.handle_illegal_action()

        return mv

    def handle_game_end(self):
        """Handle the end of the game due to AI errors."""
        if self.next_player == Player.Attacker:
            print("Defender wins due to AI time penalty!")
        else:
            print("Attacker wins due to AI time penalty!")

    def handle_illegal_action(self):
        """Handle the case where the AI generates an illegal action."""
        print("AI generated an illegal action!")
        if self.next_player == Player.Attacker:
            print("Defender wins due to AI illegal action!")
        else:
            print("Attacker wins due to AI illegal action!")
        self.is_finished()

    def write_statistics_to_file(self, result):
        """Write the game statistics to a file."""
        with open(filename, "a") as file:
            stats = [
                f"\nComputer {self.next_player.name}: ",
                f"\n{result}\n\n",
                f"\t{self.board_to_string()}",
                f"\nCumulative evals: {self.format_number(self.total_nodes)}",
                "\nCumulative evals by depth: "
                + " ".join(
                    [
                        f"{depth}={self.format_number(count)}"
                        for depth, count in self.eval_by_depth.items()
                    ]
                ),
                "\nCumulative % evals by depth: "
                + " ".join(
                    [
                        f"{depth}={count/sum(self.eval_by_depth.values())*100:.1f}%"
                        for depth, count in self.eval_by_depth.items()
                    ]
                ),
                f"\nAverage branching factor: {self.get_average_branching_factor():.1f}",
            ]
            file.write("\n".join(stats))

    def print_cumulative_info(self):
        print(f"Cumulative evals: {self.total_nodes}")

        # Evaluations by depth
        eval_by_depth_str = " ".join(
            [
                f"{depth}={self.format_number(count)}"
                for depth, count in self.eval_by_depth.items()
            ]
        )
        print(f"Cumulative evals by depth: {eval_by_depth_str}")

        # Percentage evaluations by depth
        percentages_by_depth_str = " ".join(
            [
                f"{depth}={count/sum(self.eval_by_depth.values())*100:.1f}%"
                for depth, count in self.eval_by_depth.items()
            ]
        )
        print(f"Cumulative % evals by depth: {percentages_by_depth_str}")

        # Average branching factor (assuming it's calculated and stored in self.avg_branching_factor)
        print(f"Average branching factor: {self.get_average_branching_factor():.1f}")

    def format_number(self, num):
        if num < 1_000:
            return str(num)
        elif num < 1_000_000:
            return f"{num/1_000:.1f}k"
        else:
            return f"{num/1_000_000:.1f}M"

    def get_average_branching_factor(self):
        if self.non_leaf_nodes == 0:
            return 0
        return (self.total_nodes - 1) / self.non_leaf_nodes

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
        Suggesting certain units first

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

        # Iterate over all units to suggest in certain order
        for unit_type in [
            UnitType.Firewall,
            UnitType.Program,
            UnitType.Tech,
            UnitType.Virus,
            UnitType.AI,
        ]:
            for src, unit in self.player_units(self.next_player):
                if unit.type == unit_type:
                    move.src = src

                    # Check all adjacent cells as potential action
                    for dst in src.iter_adjacent():
                        move.dst = dst

                        (success, result) = self.is_valid_move(move)
                        if success:
                            yield move.clone()

                    # Consider the self-destruction move where source and destination are the same
                    move.dst = src
                    yield move.clone()

    def suggest_move(self) -> CoordPair | None:
        """
        Suggest the best move for the current player using the Minimax algorithm with or without Alpha-Beta pruning.

        Returns:
        - The best move as a CoordPair or None if no valid move is found.
        """

        # Helper function to calculate the adjusted remaining time
        def calculate_remaining_time(elapsed: float, max_time: float) -> float:
            remaining = max_time - elapsed
            # Adjust the remaining time to ensure the AI stops searching in time
            return remaining * 0.90

        start_time = datetime.now()
        # set boolean value for the current player is maximizing or minimizing
        is_maximizing = self.next_player == Player.Attacker

        # Calculate the remaining time for the AI to make a decision
        adjusted_remaining_time = calculate_remaining_time(0, self.options.max_time)

        # Use the Minimax algorithm to get the best move and its heuristic score
        score, move = self.minimax_alpha_beta(
            self.options.max_depth,
            float("-inf"),
            float("inf"),
            is_maximizing,
            self.options.alpha_beta,
            adjusted_remaining_time,
        )

        elapsed_seconds = (datetime.now() - start_time).total_seconds()

        # Check if the AI exceeded the maximum allowed time and disable the AI for the current player
        if elapsed_seconds > self.options.max_time:
            if is_maximizing:
                self._attacker_has_ai = False
            else:
                self._defender_has_ai = False

        # Update the total time taken by all calls to this method
        self.stats.total_seconds += elapsed_seconds

        # Print the heuristic score of the best move and the time taken by the algorithm
        print(f"Heuristic score: {score}")
        print(f"Time for this action: {elapsed_seconds:.2f} sec")

        return move

    def heuristic_zero(self, player: Player) -> int:
        """
        Evaluate the score of a player based on the number of units they have.

        Args:
        - player: The player whose score is to be evaluated.

        Returns:
        - int: The total score for the player based on the number of units.
        """

        # Dictionary mapping unit types to their respective score multipliers
        UNIT_SCORE_MULTIPLIERS = {
            UnitType.Virus: 3,
            UnitType.Tech: 3,
            UnitType.Firewall: 3,
            UnitType.Program: 3,
            UnitType.AI: 9999,
        }

        # Calculate the total score by multiplying the count of each unit type by its score multiplier
        score = sum(
            UNIT_SCORE_MULTIPLIERS[unit_type] * self.count_units(unit_type, player)
            for unit_type in UNIT_SCORE_MULTIPLIERS
        )

        return score

    def heuristic_one(self, player: Player) -> int:
        """
        Evaluate the total score for a player based on the total health of their units.

        Args:
        - player: The player whose score is to be evaluated.

        Returns:
        - int: The total score for the player.
        """

        # Define multipliers for each unit type in a dictionary
        UNIT_MULTIPLIERS = {
            UnitType.AI: 900,
            UnitType.Virus: 60,
            UnitType.Tech: 60,
            UnitType.Firewall: 30,
            UnitType.Program: 30,
        }

        score = 0

        # Iterate through each unit of the player
        for _, unit in self.player_units(player):
            # Add to the score based on unit's health multiplied by its type's multiplier
            score += UNIT_MULTIPLIERS[unit.type] * unit.health

        return score

    def heuristic_two(self, player: Player) -> int:
        """
        Evaluate the total score for a player based on the positioning and health of all their units.

        Args:
        - player: The player whose score is to be evaluated.

        Returns:
        - int: The total score for the player.
        """

        # Define scoring constants in a dictionary
        SCORE_CONSTANTS = {
            'AI_MULTIPLIER': 1000,
            'VIRUS_MULTIPLIER': 5,
            'TECH_MULTIPLIER': 5,
            'FIREWALL_MULTIPLIER': 5,
            'PROGRAM_MULTIPLIER': 5,
            'HEALING_POINTS': 20,
            'ATTACK_POINTS': 20,
            'BLOCKING_POINTS': 10,
        }

        score = 0

        # Iterate through each unit of the player
        for src_coord, unit in self.player_units(player):
            if unit.type == UnitType.AI:
                score += self.evaluate_ai_unit(unit, src_coord, SCORE_CONSTANTS)
            elif unit.type == UnitType.Virus:
                score += self.evaluate_virus_unit(unit, src_coord, SCORE_CONSTANTS)
            elif unit.type == UnitType.Tech:
                score += self.evaluate_tech_unit(unit, src_coord, SCORE_CONSTANTS)
            elif unit.type == UnitType.Firewall:
                score += self.evaluate_firewall_unit(unit, src_coord, SCORE_CONSTANTS)
            elif unit.type == UnitType.Program:
                score += self.evaluate_program_unit(unit, src_coord, SCORE_CONSTANTS)
        return score

    def evaluate_ai_unit(self, unit, src_coord, SCORE_CONSTANTS):
        """
        Evaluate the score of an AI unit based on its position and health.

        Args:
        - unit: The AI unit to evaluate.
        - src_coord: The coordinates of the AI unit on the board.
        - SCORE_CONSTANTS: The constants used to calculate the score.

        Returns:
        - int: The score for the AI unit.
        """

        score = SCORE_CONSTANTS["AI_MULTIPLIER"] * unit.health
        for dst_coord in src_coord.iter_adjacent():
            dst_unit = self.get(dst_coord)
            if not dst_unit:
                continue
            if self.can_heal(unit, dst_unit):
                score += round(SCORE_CONSTANTS["HEALING_POINTS"] * 0.25)
                break
            if self.can_attack(unit, dst_unit):
                score += SCORE_CONSTANTS["ATTACK_POINTS"]
                break
        return score

    def evaluate_virus_unit(self, unit, src_coord, SCORE_CONSTANTS):
        """
        Evaluate the score of a Virus unit based on its position and health.

        Args:
        - unit: The Virus unit to evaluate.
        - src_coord: The coordinates of the Virus unit on the board.
        - SCORE_CONSTANTS: The constants used to calculate the score.

        Returns:
        - int: The score for the Virus unit.
        """

        score = SCORE_CONSTANTS["VIRUS_MULTIPLIER"] * unit.health
        for dst_coord in src_coord.iter_adjacent():
            dst_unit = self.get(dst_coord)
            if not dst_unit:
                continue
            if self.can_attack(unit, dst_unit):
                if dst_unit.type == UnitType.AI:
                    score += (
                        SCORE_CONSTANTS["ATTACK_POINTS"]
                        * SCORE_CONSTANTS["AI_MULTIPLIER"]
                    )
                else:
                    score += SCORE_CONSTANTS["ATTACK_POINTS"] * 2
                break
        return score

    def evaluate_tech_unit(self, unit, src_coord, SCORE_CONSTANTS):
        """
        Evaluate the score of a Tech unit based on its position and health.

        Args:
        - unit: The Tech unit to evaluate.
        - src_coord: The coordinates of the Tech unit on the board.
        - SCORE_CONSTANTS: The constants used to calculate the score.

        Returns:
        - int: The score for the Tech unit.
        """
        HEALING_POINTS = 20

        score = SCORE_CONSTANTS["TECH_MULTIPLIER"] * unit.health
        for dst_coord in src_coord.iter_adjacent():
            dst_unit = self.get(dst_coord)
            if not dst_unit:
                continue
            if self.can_heal(unit, dst_unit):
                score += HEALING_POINTS
                break
            if self.can_attack(unit, dst_unit) and dst_unit.type == UnitType.Virus:
                score += SCORE_CONSTANTS["ATTACK_POINTS"] * 2
                break
        return score

    def evaluate_firewall_unit(self, unit, src_coord, SCORE_CONSTANTS):
        """
        Evaluate the score of a Firewall unit based on its position and health.

        Args:
        - unit: The Firewall unit to evaluate.
        - src_coord: The coordinates of the Firewall unit on the board.
        - SCORE_CONSTANTS: The constants used to calculate the score.

        Returns:
        - int: The score for the Firewall unit.
        """
        score = SCORE_CONSTANTS["FIREWALL_MULTIPLIER"] * unit.health
        for dst_coord in src_coord.iter_adjacent():
            dst_unit = self.get(dst_coord)
            if not dst_unit:
                continue
            if dst_unit.player != unit.player and dst_unit.type in [
                UnitType.AI,
                UnitType.Program,
            ]:
                score += SCORE_CONSTANTS["BLOCKING_POINTS"]
            elif self.can_attack(unit, dst_unit):
                score += round(SCORE_CONSTANTS["ATTACK_POINTS"] * 0.25)
                break
        return score

    def evaluate_program_unit(self, unit, src_coord, SCORE_CONSTANTS):
        """
        Evaluate the score of a Program unit based on its position and health.

        Args:
        - unit: The Program unit to evaluate.
        - src_coord: The coordinates of the Program unit on the board.
        - SCORE_CONSTANTS: The constants used to calculate the score.

        Returns:
        - int: The score for the Program unit.
        """
        score = SCORE_CONSTANTS["PROGRAM_MULTIPLIER"] * unit.health
        for dst_coord in src_coord.iter_adjacent():
            dst_unit = self.get(dst_coord)
            if not dst_unit:
                continue
            if self.can_attack(unit, dst_unit):
                score += SCORE_CONSTANTS["ATTACK_POINTS"]
                break
        return score

    def can_heal(self, src_unit, dst_unit):
        """
        Check if a unit can heal another unit.

        Args:
        - src_unit: The source unit attempting to heal.
        - dst_unit: The destination unit being healed.

        Returns:
        - bool: True if the source unit can heal the destination unit, False otherwise.
        """
        return (
            dst_unit.player == src_unit.player
            and dst_unit.type in [UnitType.Virus, UnitType.Tech]
            and dst_unit.health < 9
        )

    def can_attack(self, src_unit, dst_unit):
        """
        Check if a unit can attack another unit.

        Args:
        - src_unit: The source unit attempting to attack.
        - dst_unit: The destination unit being attacked.

        Returns:
        - bool: True if the source unit can attack the destination unit, False otherwise.
        """
        return dst_unit.player != src_unit.player

    def evaluate_board(self) -> int:
        """
        Evaluate the board based on the heuristic chosen by the user.

        Returns:
        - int: The difference in scores between the attacker and defender.
        """

        # Map heuristic choices to their respective functions
        HEURISTIC_FUNCTIONS = {
            0: self.heuristic_zero,
            1: self.heuristic_one,
            2: self.heuristic_two,
        }

        # Get the appropriate heuristic function based on user's choice
        heuristic_func = HEURISTIC_FUNCTIONS.get(self.options.heuristic, lambda _: 0)

        # Calculate scores for both players using the chosen heuristic
        score_attacker = heuristic_func(Player.Attacker)
        score_defender = heuristic_func(Player.Defender)

        # Return the difference in scores
        return score_attacker - score_defender

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

    def minimax_alpha_beta(
        self,
        depth: int,
        alpha: float,
        beta: float,
        is_maximizing: bool,
        alpha_beta: bool,
        remaining_time: float,
    ):
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
        self.total_nodes += 1
        start_time = datetime.now()
        best_move = None

        # Update evals_by_depth
        if depth not in self.eval_by_depth:
            self.eval_by_depth[depth] = 0
        self.eval_by_depth[depth] += 1

        # Base case: if the search has reached maximum depth or the game is finished
        if depth == 0 or self.is_finished() or remaining_time <= 0:
            return self.evaluate_board(), None
        """
            1.Generate all the possible children/combination from current node
            2.Simulate the game after making the move
            3.Try to perform the move and skip if it's not valid
            4.Appending the move and the simulated game as a child into the children list
        """
        children = [
            self.clone_and_move(move)
            for move in self.move_candidates()
            if self.clone_and_move(move)
        ]

        # Update non_leaf_nodes for branching factor calculation
        if children:
            self.non_leaf_nodes += 1

        # Maximizing player's turn
        if is_maximizing:
            max_eval = float("-inf")

            # Evaluate the children
            for child in children:
                move, simulated_game = child
                # Calculate the remaining time left
                elapsed_seconds = (datetime.now() - start_time).total_seconds()
                remaining_time = remaining_time - elapsed_seconds
                # Switch to the minimizing player for the next recursive call
                simulated_game.next_player = Player.Defender
                eval_value, _ = simulated_game.minimax_alpha_beta(
                    depth - 1, alpha, beta, False, alpha_beta, remaining_time
                )
                # Update the best move if the current move has a better evaluation
                if eval_value > max_eval:
                    max_eval = eval_value
                    best_move = move
                # Update alpha and prune the search tree if necessary
                if alpha_beta:
                    alpha = max(alpha, eval_value)
                    if beta <= alpha:
                        break
            return max_eval, best_move

        # Minimizing player's turn
        else:
            min_eval = float("inf")

            # Evaluate the children
            for child in children:
                move, simulated_game = child
                # Calculate the remaining time left
                elapsed_seconds = (datetime.now() - start_time).total_seconds()
                remaining_time = remaining_time - elapsed_seconds
                # Switch to the maximizing player for the next recursive call
                simulated_game.next_player = Player.Attacker
                eval_value, _ = simulated_game.minimax_alpha_beta(
                    depth - 1, alpha, beta, True, alpha_beta, remaining_time
                )
                # Update the best move if the current move has a better evaluation
                if eval_value < min_eval:
                    min_eval = eval_value
                    best_move = move
                # Update beta and prune the search tree if necessary
                if alpha_beta:
                    beta = min(beta, eval_value)
                    if beta <= alpha:
                        break
            return min_eval, best_move

    def clone_and_move(self, move):
        simulated_game = self.clone()
        success, _ = simulated_game.perform_move(move)
        if success:
            return move, simulated_game
        return None

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
            return False, "Invalid attack attempt!\n"

        # Rule 2：Check if the attacker and target units belong to different players (are adversarial)
        if not attacker_unit.player.next() == target_unit.player:
            return False, "Invalid attack attempt: units are not adversarial!\n"

        # Rule 3: Check if the attacker and target units are adjacent on the board
        if not self.is_adjacent(attacker_coord, target_coord):
            return False, "Invalid attack attempt: units are not adjacent!\n"

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
            return False, "Invalid repair action: units are not adjacent!\n"

        # Rule 2: Check if units are friendly
        if (
            repairer_unit is None
            or target_unit is None
            or not repairer_unit.player == target_unit.player
        ):
            return False, "Invalid repair action: units are not friendly!\n"

        # Rule 3a: Check if the repair leads to a change in health
        repair_amount = repairer_unit.repair_amount(target_unit)
        if repair_amount == 0:
            return (
                False,
                f"Invalid repair action: {repairer_unit} cannot repair {target_unit}!\n",
            )

        # Rule 3b: Check if target unit's health is already at 9
        if target_unit.health == 9:
            return (
                False,
                f"Invalid repair action: {target_unit}'s health is already at maximum!\n",
            )

        # Apply the repair amount to the target unit's health
        target_unit.mod_health(repair_amount)

        # Return success message with details of the repair action
        return (
            True,
            f"{repairer_unit.player.name}'s {repairer_unit.type.name} repaired {target_unit.player.name}'s {target_unit.type.name}.",
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
    print("------------------------------------")
    print("Welcome to the AI War Game!")
    print("Choose a game mode: ")
    print("1. Attacker VS Defender")
    print("2. Attacker VS Computer")
    print("3. Computer VS Defender")
    print("4. Computer VS Computer")
    choice = int(input("Enter your choice (1-4): "))
    while choice not in [1, 2, 3, 4]:
        print("Invalid choice. Please choose between 1 and 4.\n")
        choice = int(input("Enter your choice (1-4): "))
    print("------------------------------------")
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


def choose_alpha_beta() -> bool:
    while True:
        user_input = input("Use Alpha-Beta Pruning (Y/N)(Default: Y): ").upper()
        if user_input == "Y" or user_input.strip() == "":
            return True
        elif user_input == "N":
            return False
        else:
            print("Invalid input: Please enter 'Y' or 'N'!\n")


def choose_allowed_time() -> float:
    while True:
        user_input = input(
            "Enter maximum allowed seconds for the computer to return a move (Default: 5): "
        )
        if user_input.strip() == "":
            return 5
        try:
            user_input = float(user_input)
            if user_input > 0:
                return user_input
            else:
                print("Invalid input: Please choose a number above 0 seconds.\n")
        except ValueError:
            print("Invalid input: Please enter a valid time(seconds).\n")


def choose_max_turns() -> int:
    while True:
        user_input = input("Enter maximum number of turns (Default:100): ")
        if user_input.strip() == "":
            return 100
        try:
            user_input = int(user_input)
            if user_input > 0:
                return user_input
            else:
                print("Invalid input: Please choose a number above 0.\n")
        except ValueError:
            print("Invalid input: Please enter a valid number. \n")


def choose_max_depth() -> int:
    while True:
        user_input = input("Enter max depth (Default: 4): ")
        if user_input.strip() == "":
            return 4
        try:
            user_input = int(user_input)
            if user_input > 0:
                return user_input
            else:
                print("Invalid input: Please choose a number above 0.\n")
        except ValueError:
            print("Invalid input: Please enter a valid number. \n")


def choose_heuristic():
    while True:
        user_input = input("Enter heuristic e(0, 1 or 2)(Default: 0): ")
        if user_input.strip() == "":
            return 0
        try:
            user_input = int(user_input)
            if user_input >= 0 and user_input <= 2:
                return user_input
            else:
                print(
                    "Invalid input: Please choose a number between 0 and 2 inclusive.\n"
                )
        except ValueError:
            print("Invalid input: Please enter a valid number. \n")


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

    # Prompt the user for alpha-beta, allowed time, and max turns
    include_alpha_beta = False
    max_allowed_time = 0
    max_depth = 0
    max_turns = choose_max_turns()
    heuristic = 0
    # check if computer is playing
    if chosen_game_type != GameType.AttackerVsDefender:
        max_allowed_time = choose_allowed_time()
        max_depth = choose_max_depth()
        include_alpha_beta = choose_alpha_beta()
        heuristic = choose_heuristic()
    options.alpha_beta = include_alpha_beta
    options.max_time = max_allowed_time
    options.max_turns = max_turns
    options.max_depth = max_depth
    options.heuristic = heuristic

    # create a new game
    game = Game(options=options)

    # reset statistics for every game
    game.reset_statistics()

    # creating the output file
    b = game.options.alpha_beta
    t = game.options.max_time
    m = game.options.max_turns
    e = game.options.heuristic
    global filename
    filename = f"gameTrace-{b}-{t}-{m}.txt"

    game_parameters = ""
    game_parameters += f"1. The game parameters\n"
    game_parameters += f"a) Timeout (seconds): {t}\n"
    game_parameters += f"b) Max number of turns: {m}\n"
    game_parameters += f"c) Alpha-beta: {b}\n"
    game_parameters += f"d) Play Mode: Player 1 = H & Player 2 = H\n"
    game_parameters += f"e) Name of heuristic: h{e}\n"
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
