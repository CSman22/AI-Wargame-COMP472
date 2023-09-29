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
        if target.health + amount > 9:
            return 9 - target.health
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
        yield Coord(self.row - 1, self.col)
        yield Coord(self.row, self.col - 1)
        yield Coord(self.row + 1, self.col)
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
    max_depth: int | None = 4
    min_depth: int | None = 2
    max_time: float | None = 5.0
    game_type: GameType = GameType.AttackerVsDefender
    alpha_beta: bool = False
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
    turns_played: int = 0
    options: Options = field(default_factory=Options)
    stats: Stats = field(default_factory=Stats)
    _attacker_has_ai: bool = True
    _defender_has_ai: bool = True

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

    def mod_health(self, coord: Coord, health_delta: int):
        """Modify health of unit at Coord (positive or negative delta)."""
        target = self.get(coord)
        if target is not None:
            target.mod_health(health_delta)
            self.remove_dead(coord)

    def next_turn(self):
        """Transitions game to the next turn."""
        self.next_player = self.next_player.next()
        self.turns_played += 1

    def to_string(self) -> str:
        """Pretty text representation of the game."""
        output = ""
        output += f"Next player: {self.next_player.name}\n"
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
            if (
                coords is not None
                and self.is_valid_coord(coords.src)
                and self.is_valid_coord(coords.dst)
            ):
                return coords
            else:
                print("Invalid coordinates! Try again.")

    def human_turn(self):
        """Human player plays a move (or get via broker)."""
        while True:
            # Display a menu of actions
            print(f"Player {self.next_player.name}, choose an action:")
            print("1. Move")
            print("2. Attack")
            print("3. Repair")
            print("4. Self-destruct")

            try:
                action_choice = int(input("Enter the number of your chosen action: "))

                if action_choice == 1:
                    mv = self.read_move()
                    (success, result) = self.perform_move(mv)
                    if success:
                        print(result)
                        self.next_turn()

                        # Record the move action to the file
                        actionInfo = f"Move from {chr(65 + mv.src.row)}{mv.src.col} to {chr(65 + mv.dst.row)}{mv.dst.col}\n"
                        actionInfo += f"\t{self.board_to_string()}"
                        with open(filename, "a") as file:
                            file.write(actionInfo)

                        break
                    else:
                        print("The move is not valid! Try again.")

                elif action_choice == 2:
                    attacker = Coord.from_string(
                        input("Enter the attacker's coordinates: ")
                    )
                    target = Coord.from_string(
                        input("Enter the target's coordinates: ")
                    )
                    (success, result) = self.attack(attacker, target)
                    if success:
                        print(result)
                        self.next_turn()
                        break
                    else:
                        print("The attack is not valid! Try again.")

                elif action_choice == 3:
                    repairer = Coord.from_string(
                        input("Enter the repairer's coordinates: ")
                    )
                    target = Coord.from_string(
                        input("Enter the target's coordinates: ")
                    )
                    (success, result) = self.repair(repairer, target)
                    if success:
                        print(result)
                        self.next_turn()

                        # Record the repair action to the file
                        actionInfo = f"Repair from {chr(65 + repairer.row)}{repairer.row} to {chr(65 + target.row)}{target.col}\n"
                        actionInfo += f"\t{self.board_to_string()}"
                        with open(filename, "a") as file:
                            file.write(actionInfo)

                        break
                    else:
                        print("The repair action is not valid! Try again.")

                elif action_choice == 4:
                    unit = Coord.from_string(
                        input("Enter the unit's coordinates to self-destruct: ")
                    )
                    (success, result) = self.self_destruct(unit)
                    if success:
                        print(result)
                        self.next_turn()
                        break
                    else:
                        print("The self-destruct action is not valid! Try again.")

                else:
                    print("Invalid choice! Please choose a number between 1 and 4.")

            except ValueError:
                print("Invalid input! Please enter a valid number.")

    def computer_turn(self) -> CoordPair | None:
        """Computer plays a move."""
        mv = self.suggest_move()
        if mv is not None:
            (success, result) = self.perform_move(mv)
            if success:
                print(f"Computer {self.next_player.name}: ", end="")
                print(result)
                self.next_turn()
        return mv

    def player_units(self, player: Player) -> Iterable[Tuple[Coord, Unit]]:
        """Iterates over all units belonging to a player."""
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None and unit.player == player:
                yield (coord, unit)

    def is_finished(self) -> bool:
        """Check if the game is over."""
        return self.has_winner() is not None

    def has_winner(self) -> Player | None:
        """Check if the game is over and returns winner"""
        if (
            self.options.max_turns is not None
            and self.turns_played > self.options.max_turns
        ):
            return Player.Defender
        elif not self._attacker_has_ai:
            return Player.Defender
        elif not self._defender_has_ai:
            return Player.Attacker
        elif not any(
            self.move_candidates()
        ):  # Check if no action is available to the current player
            return (
                Player.Defender
                if self.next_player == Player.Attacker
                else Player.Attacker
            )
        else:
            return None

    def move_candidates(self) -> Iterable[CoordPair]:
        """Generate valid move candidates for the next player."""
        move = CoordPair()
        for src, _ in self.player_units(self.next_player):
            move.src = src
            for dst in src.iter_adjacent():
                move.dst = dst
                if self.is_valid_move(move):
                    yield move.clone()
            move.dst = src
            yield move.clone()

    def random_move(self) -> Tuple[int, CoordPair | None, float]:
        """Returns a random move."""
        move_candidates = list(self.move_candidates())
        random.shuffle(move_candidates)
        if len(move_candidates) > 0:
            return 0, move_candidates[0], 1
        else:
            return 0, None, 0

    def suggest_move(self) -> CoordPair | None:
        """Suggest the next move using minimax alpha beta. TODO: REPLACE RANDOM_MOVE WITH PROPER GAME LOGIC!!!"""
        start_time = datetime.now()
        (score, move, avg_depth) = self.random_move()
        elapsed_seconds = (datetime.now() - start_time).total_seconds()
        self.stats.total_seconds += elapsed_seconds
        print(f"Heuristic score: {score}")
        print(f"Average recursive depth: {avg_depth:0.1f}")
        print(f"Evals per depth: ", end="")
        for k in sorted(self.stats.evaluations_per_depth.keys()):
            print(f"{k}:{self.stats.evaluations_per_depth[k]} ", end="")
        print()
        total_evals = sum(self.stats.evaluations_per_depth.values())
        if self.stats.total_seconds > 0:
            print(
                f"Eval perf.: {total_evals / self.stats.total_seconds / 1000:0.1f}k/s"
            )
        print(f"Elapsed time: {elapsed_seconds:0.1f}s")
        return move

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


##############################################################################################################


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
        default="manual",
        help="game type: auto|attacker|defender|manual",
    )
    parser.add_argument("--broker", type=str, help="play via a game broker")
    args = parser.parse_args()

    # parse the game type
    if args.game_type == "attacker":
        game_type = GameType.AttackerVsComp
    elif args.game_type == "defender":
        game_type = GameType.CompVsDefender
    elif args.game_type == "manual":
        game_type = GameType.AttackerVsDefender
    else:
        game_type = GameType.CompVsComp

    # set up game options
    options = Options(game_type=game_type)

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
        print()
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
