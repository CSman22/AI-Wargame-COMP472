# AI-Wargame-COMP472
AI Wargame1 is a 2-player game played by an attacker (a) and a defender (d) on a 5 × 5 board. 

## Game Rule Overview
- Each player has 6 units on the board.
- Each unit has a health level, represented by an integer between [0...9].
- When a unit's health reaches 0 or below, it is destroyed and removed from the board.
- If the health of an AI reaches 0, the player loses the game.

## Board Unit Type
  - **AI (A)**: Each player has only 1 AI unit. The goal is to destroy the opponent's AI.
  - **Viruses (V)**: Very offensive units that can destroy the AI in 1 attack.
  - **Techs (T)**: Very defensive units, equal in combat against Viruses.
  - **Programs (P)**: Generic soldiers.
  - **Firewalls (F)**: Strong at absorbing attacks, weak at damaging other units.
    
## Initial Configuration

- Attacker: 1×AI, 2×Viruses, 2×Programs, 1×Firewall.
- Defender: 1×AI, 2×Techs, 2×Firewalls, 1×Program.

|   | 0  | 1   | 2   | 3   | 4   |
|---|-----|-----|-----|-----|-----|
| A | dA9 | dT9 | dF9 |  .  |  .  |
| B | dT9 | dP9 |  .  |  .  |  .  |
| C | dF9 |  .  |  .  |  .  | aP9 |
| D |  .  |  .  |  .  | aF9 | aV9 |
| E |  .  |  .  | aP9 | aV9 | aA9 |
