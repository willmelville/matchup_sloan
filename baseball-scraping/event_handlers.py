import difflib
import logging
import re
import string
from game_state import Base, Half, FieldPosition, GameState


def process_name(name):
    parts = name.split()
    if len(parts) >= 3 and all(len(part) == 2 and part.endswith('.') for part in parts[:-1]):
        name = ''.join(parts[:-1]) + ' ' + parts[-1]

    name = name.strip().rstrip(string.punctuation)

    # Replace "joshua" with "josh"
    name = name.replace("joshua", "josh").replace("Joshua", "josh")
    # Replace "luis garcia" with "luis garcia jr."
    name = name.replace("luis garcia", "luis garcia jr.").replace("Luis Garcia", "Luis Garcia Jr.")

    return remove_middle_initials(name.lower())


def get_closest_player_id(player_name, player_map):
    logging.info(f"Attempting to get player ID for: {player_name}")

    player_name_processed = process_name(player_name)

    # Build a mapping from processed names to player IDs
    reversed_player_map = {process_name(name): player_id for player_id, name in player_map.items()}

    names_list = list(reversed_player_map.keys())

    # Use difflib to find the closest match
    matches = difflib.get_close_matches(player_name_processed, names_list, n=1, cutoff=0.6)
    if matches:
        closest_name = matches[0]
        player_id = reversed_player_map[closest_name]
        logging.info(f"Found closest match for '{player_name}': '{closest_name}' (ID: {player_id})")
        return player_id
    else:
        logging.info(f"Warning: No close match found for player name '{player_name}'")
        return None


def handle_stolen_base(description, game_state, player_map):
    if ':' in description:
        description = description.split(':', 1)[1].strip()
    player_name = description.split(" steals")[0].strip()

    player_id = get_closest_player_id(player_name, player_map)

    if not player_id:
        logging.info(f"Error: Player '{player_name}' not found in player map.")
        return

    current_base = None
    for base, occupant in game_state.bases_occupied.items():
        if occupant == player_id:
            current_base = base
            break

    if not current_base:
        logging.info(f"Error: Player '{player_name}' (ID: {player_id}) not found on any base.")
        return

    if "2nd base" in description:
        new_base = Base.SECOND
    elif "3rd base" in description:
        new_base = Base.THIRD
    elif "home" in description:
        new_base = None  # Stealing home means scoring
    else:
        logging.info(f"Error: Unrecognized stolen base destination in description: '{description}'")
        return

    if new_base:
        game_state.bases_occupied[current_base] = -1
        game_state.bases_occupied[new_base] = player_id
        logging.info(f"Player '{player_name}' (ID: {player_id}) successfully stole {new_base.name.lower()}.")
    else:
        game_state.bases_occupied[current_base] = -1
        logging.info(f"Player '{player_name}' (ID: {player_id}) successfully stole home. Score updated.")


def handle_wild_pitch(description, game_state, player_map):
    abbreviations = ['Jr.', 'Sr.', 'II', 'III', 'IV', 'V']
    for abbr in abbreviations:
        description = description.replace(abbr, abbr.replace('.', '<dot>'))

    sentences = description.split('. ')
    sentences = [s.replace('<dot>', '.') for s in sentences]

    pitcher_info = sentences[0]
    base_runner_info = sentences[1:]

    for runner_info in base_runner_info:
        runner_info = runner_info.strip().rstrip('.')

        if not runner_info:
            continue

        if "scores" in runner_info:
            runner_name = runner_info.replace(" scores", "").strip()

            player_id = get_closest_player_id(runner_name, player_map)
            if not player_id:
                logging.info(f"Error: Player '{runner_name}' not found in player map.")
                continue

            current_base = next(
                (base for base, occupant in game_state.bases_occupied.items() if occupant == player_id),
                None
            )

            if not current_base:
                logging.info(f"Error: Player '{runner_name}' (ID: {player_id}) not found on any base.")
                continue

            game_state.bases_occupied[current_base] = -1
            logging.info(f"Player '{runner_name}' (ID: {player_id}) scored.")

        elif " to " in runner_info:
            runner_name, base_movement = runner_info.rsplit(" to ", 1)
            runner_name = runner_name.strip()

            player_id = get_closest_player_id(runner_name, player_map)
            if not player_id:
                logging.info(f"Error: Player '{runner_name}' not found in player map.")
                continue

            current_base = next(
                (base for base, occupant in game_state.bases_occupied.items() if occupant == player_id),
                None
            )

            if not current_base:
                logging.info(f"Error: Player '{runner_name}' (ID: {player_id}) not found on any base.")
                continue

            if "2nd" in base_movement or "second" in base_movement:
                new_base = Base.SECOND
            elif "3rd" in base_movement or "third" in base_movement:
                new_base = Base.THIRD
            else:
                logging.info(f"Error: Unrecognized base movement for '{runner_name}': '{base_movement}'")
                continue

            game_state.bases_occupied[current_base] = -1
            game_state.bases_occupied[new_base] = player_id
            logging.info(f"Player '{runner_name}' (ID: {player_id}) moved to {new_base.name.lower()}.")


def handle_passed_ball(description, game_state, player_map):
    parts = description.split(". ")
    catcher_info = parts[0]
    base_runner_info = parts[1:]

    runner_movements = []
    for runner_info in base_runner_info:
        runner_info = runner_info.strip()
        if "scores" in runner_info:
            runner_name = runner_info.replace(" scores", "").strip()
            runner_movements.append((runner_name, "scores"))
        elif " to " in runner_info:
            runner_name, base_movement = runner_info.split(" to ")
            runner_name = runner_name.strip()
            runner_movements.append((runner_name, base_movement.strip()))

    runner_movements.sort(key=lambda x: (
        0 if x[1] == "scores" else
        1 if "3rd" in x[1] else
        2 if "2nd" in x[1] else 3
    ))

    for runner_name, movement in runner_movements:
        player_id = get_closest_player_id(runner_name, player_map)
        if not player_id:
            logging.info(f"Error: Player '{runner_name}' not found in player map.")
            continue

        current_base = None
        for base, occupant in game_state.bases_occupied.items():
            if occupant == player_id:
                current_base = base
                break

        if not current_base:
            logging.info(f"Error: Player '{runner_name}' (ID: {player_id}) not found on any base.")
            continue

        if movement == "scores":
            game_state.bases_occupied[current_base] = -1
            logging.info(f"Player '{runner_name}' (ID: {player_id}) scored.")
        else:
            if "3rd" in movement:
                new_base = Base.THIRD
            elif "2nd" in movement:
                new_base = Base.SECOND
            else:
                logging.info(f"Error: Unrecognized base movement for '{runner_name}': '{movement}'")
                continue

            game_state.bases_occupied[current_base] = -1
            game_state.bases_occupied[new_base] = player_id
            logging.info(f"Player '{runner_name}' (ID: {player_id}) moved to {new_base.name.lower()}.")


def attempt_base_update(description, game_state, player_map):
    logging.info(f"Processing description: '{description}'")

    # Step 1: Handle challenge descriptions
    if 'challenged' in description.lower():
        challenge_index = description.lower().find('challenged')
        description = description[challenge_index:]
        match = re.search(r'(overturned|upheld):\s*(.*)', description, re.IGNORECASE)
        if match:
            description = match.group(2).strip()
            logging.info(f"Adjusted description after challenge: '{description}'")
        else:
            logging.info("No 'overturned:' or 'upheld:' found after 'challenged'")
            return

    # Step 2: Normalize and split the description into sentences
    description = description.replace('.', '. ')
    sentences = [s.strip() for s in description.split('. ') if s.strip()]

    if not sentences:
        logging.info("No actionable sentences found in the description.")
        return

    # Expanded action keywords and sorted from longest to shortest
    action_keywords = [
        'grounds into a fielder\'s choice',
        'grounds into a double play',
        'grounds into a force out',
        'intentionally walks',
        'hits a grand slam',
        'hits a home run',
        'hit by pitch',
        'intentionally walk',
        'grounds out',
        'grounds into',
        'walks',
        'singles',
        'doubles',
        'triples',
        'homers',
        'reaches',
        'hits'
    ]
    action_keywords.sort(key=len, reverse=True)
    action_keywords_pattern = '|'.join(map(re.escape, action_keywords))

    main_action = sentences[0]

    # Special handling for intentional walks
    intentional_walk_match = re.match(
        r"^(.*?)\s+intentionally walks\s+(.*?)\.?$",
        main_action,
        re.IGNORECASE
    )

    if intentional_walk_match:
        # For intentional walks, the first group is the pitcher and second group is the batter
        batter_name = intentional_walk_match.group(2).strip()
        action = "intentionally walks"
    else:
        # Regular action handling (unchanged)
        action_regex = re.compile(
            rf"^(.*?)\s+({action_keywords_pattern})(?:\s+\(.*?\))?(?:\s+[^,]*)?(?:,|$)",
            re.IGNORECASE
        )
        action_match = action_regex.match(main_action)

        if action_match:
            batter_name = action_match.group(1).strip()
            action = action_match.group(2).lower()
        else:
            alt_action_regex = re.compile(
                rf"^(.*?)\s+({action_keywords_pattern})\s+(.*?)\.?$",
                re.IGNORECASE
            )
            alt_match = alt_action_regex.match(main_action)
            if alt_match:
                pitcher_name = alt_match.group(1).strip()
                action = alt_match.group(2).lower()
                batter_name = alt_match.group(3).strip()
            else:
                logging.info("No main action found in the description.")
                return

    batter_id = get_closest_player_id(batter_name, player_map)
    if not batter_id:
        logging.info(f"Error: Batter '{batter_name}' not found in player map.")
        return

    # Move existing runners ahead of batter
    move_existing_runners(action, game_state)

    # Update bases based on the action
    if action in ['walks', 'intentionally walks']:
        occupy_base(Base.FIRST, batter_id, game_state)
        logging.info(f"Batter '{batter_name}' (ID: {batter_id}) walked to first base.")
    elif action == 'hit by pitch':
        occupy_base(Base.FIRST, batter_id, game_state)
        logging.info(f"Batter '{batter_name}' (ID: {batter_id}) reached first base via hit by pitch.")
    elif action in ['singles', 'reaches']:
        occupy_base(Base.FIRST, batter_id, game_state)
        logging.info(f"Batter '{batter_name}' (ID: {batter_id}) reached first base.")
    elif action == 'doubles':
        occupy_base(Base.SECOND, batter_id, game_state)
        logging.info(f"Batter '{batter_name}' (ID: {batter_id}) reached second base.")
    elif action == 'triples':
        occupy_base(Base.THIRD, batter_id, game_state)
        logging.info(f"Batter '{batter_name}' (ID: {batter_id}) reached third base.")
    elif action in ['homers', 'hits a grand slam', 'hits a home run']:
        logging.info(f"Batter '{batter_name}' (ID: {batter_id}) hit a home run.")
        score_runner(batter_id, game_state)
    elif action in ['grounds into a force out', 'grounds into a double play', "grounds into a fielder's choice"]:
        # For force outs and double plays, the batter may or may not reach first base
        # Additional logic may be needed here based on runner movements
        occupy_base(Base.FIRST, batter_id, game_state)
        logging.info(f"Batter '{batter_name}' (ID: {batter_id}) reached first base on {action}.")
    else:
        logging.info(f"Unrecognized action '{action}' for batter '{batter_name}'.")

    # Step 4: Process any additional runner movements
    runner_movements = sentences[1:]

    # Updated movement_patterns to handle "advances to" and commas
    movement_patterns = [
        re.compile(r"^(.*?)\s+(?:to|advances to)\s+(1st|2nd|3rd|home)(?:,.*)?$", re.IGNORECASE),
        re.compile(r"^(.*?)\s+(scores|out at home|out at 1st|out at 2nd|out at 3rd)(?:,.*)?$", re.IGNORECASE),
    ]

    # Process runner movements with priority
    movement_priority = {
        'scores': 0,
        'home': 0,
        'out at home': 0,
        '3rd': 1,
        'out at 3rd': 1,
        '2nd': 2,
        'out at 2nd': 2,
        '1st': 3,
        'out at 1st': 3,
    }
    movements = []

    for movement in runner_movements:
        movement = movement.strip().rstrip('.')
        for pattern in movement_patterns:
            match = pattern.match(movement)
            if match:
                runner_name = match.group(1).strip()
                action = match.group(2).lower()
                priority = movement_priority.get(action, 99)
                movements.append((priority, runner_name, action))
                break
        else:
            logging.info(f"Unrecognized runner movement: '{movement}'")

    # Sort movements based on priority
    movements.sort()

    # Process movements
    for _, runner_name, action in movements:
        runner_id = get_closest_player_id(runner_name, player_map)
        if not runner_id:
            logging.info(f"Error: Runner '{runner_name}' not found in player map.")
            continue

        current_base = get_runner_current_base(runner_id, game_state)
        if current_base is None:
            logging.info(f"Error: Runner '{runner_name}' (ID: {runner_id}) not found on any base.")
            continue

        if action in ['scores', 'home']:
            game_state.bases_occupied[current_base] = -1
            logging.info(f"Runner '{runner_name}' (ID: {runner_id}) scored from {current_base.name.lower()}.")
        elif action.startswith('out at'):
            game_state.bases_occupied[current_base] = -1
            logging.info(f"Runner '{runner_name}' (ID: {runner_id}) was out at {action.split()[-1]}.")
        else:
            new_base = get_base_enum(action)
            if not new_base:
                logging.info(f"Error: Unrecognized base '{action}' for runner '{runner_name}'.")
                continue
            game_state.bases_occupied[current_base] = -1
            occupy_base(new_base, runner_id, game_state)
            logging.info(f"Runner '{runner_name}' (ID: {runner_id}) moved to {new_base.name.lower()}.")

def move_existing_runners(action, game_state):
    # Define how many bases runners should advance based on the batter's action
    bases_to_advance = {
        'walks': 1,
        'intentionally walks': 1,
        'hit by pitch': 1,
        'singles': 1,
        'reaches': 1,
        'doubles': 2,
        'triples': 3,
        'homers': 4,
        'hits a grand slam': 4,
        'hits a home run': 4,
        'grounds into a force out': 1,
        'grounds into a double play': 1,
        "grounds into a fielder's choice": 1,
    }
    advance = bases_to_advance.get(action, 0)

    if advance == 0:
        return

    # Move runners starting from 3rd base to 1st base
    for base in [Base.THIRD, Base.SECOND, Base.FIRST]:
        runner_id = game_state.bases_occupied.get(base, -1)
        if runner_id != -1:
            new_base_index = base.value + advance
            if new_base_index >= 4:
                # Runner scores
                game_state.bases_occupied[base] = -1
                logging.info(f"Runner (ID: {runner_id}) scored from {base.name.lower()}.")
            else:
                new_base = Base(new_base_index)
                if game_state.bases_occupied.get(new_base, -1) == -1:
                    game_state.bases_occupied[base] = -1
                    game_state.bases_occupied[new_base] = runner_id
                    logging.info(
                        f"Runner (ID: {runner_id}) advanced from {base.name.lower()} to {new_base.name.lower()}.")
                else:
                    logging.info(
                        f"Error: Base {new_base.name.lower()} already occupied when moving runner (ID: {runner_id}).")


def occupy_base(base, player_id, game_state):
    if game_state.bases_occupied.get(base, -1) == -1:
        game_state.bases_occupied[base] = player_id
    else:
        logging.info(f"Error: Base {base.name.lower()} already occupied when trying to place player (ID: {player_id}).")


def score_runner(player_id, game_state):
    # Remove runner from bases if present
    for base in [Base.FIRST, Base.SECOND, Base.THIRD]:
        if game_state.bases_occupied.get(base, -1) == player_id:
            game_state.bases_occupied[base] = -1
            break
    logging.info(f"Player (ID: {player_id}) scored.")


def get_runner_current_base(runner_id, game_state):
    for base, occupant in game_state.bases_occupied.items():
        if occupant == runner_id:
            return base
    return None


def get_base_enum(base_str):
    base_str = base_str.lower()
    if base_str in ['1st', 'first']:
        return Base.FIRST
    elif base_str in ['2nd', 'second']:
        return Base.SECOND
    elif base_str in ['3rd', 'third']:
        return Base.THIRD
    else:
        return None

def handle_balk(description, game_state, player_map):
    if "on a balk" not in description:
        logging.info(f"Error: Not a valid balk event description.")
        return

    if "batting," in description:
        parts = description.split("batting, ")[1]
    else:
        logging.info(f"Error: Malformed balk description.")
        return

    base_runner_info = parts.split(" on a balk. ")

    for runner_info in base_runner_info:
        runner_info = runner_info.strip()

        if "advances to" in runner_info:
            runner_name, base_movement = runner_info.split(" advances to ")
            runner_name = runner_name.strip()

            player_id = get_closest_player_id(runner_name, player_map)
            if not player_id:
                logging.info(f"Error: Player '{runner_name}' not found in player map.")
                continue

            current_base = None
            for base, occupant in game_state.bases_occupied.items():
                if occupant == player_id:
                    current_base = base
                    break

            if not current_base:
                logging.info(f"Error: Player '{runner_name}' (ID: {player_id}) not found on any base.")
                continue

            if "2nd" in base_movement:
                new_base = Base.SECOND
            elif "3rd" in base_movement:
                new_base = Base.THIRD
            elif "scores" in base_movement:
                new_base = None
            else:
                logging.info(f"Error: Unrecognized base movement for '{runner_name}': '{base_movement}'")
                continue

            if new_base:
                game_state.bases_occupied[current_base] = -1
                game_state.bases_occupied[new_base] = player_id
                logging.info(f"Player '{runner_name}' (ID: {player_id}) moved to {new_base.name.lower()}.")
            else:
                game_state.bases_occupied[current_base] = -1
                logging.info(f"Player '{runner_name}' (ID: {player_id}) scored.")


def handle_offensive_sub(description, game_state, player_map):
    match = re.search(r'(?:runner|hitter)\s+(.+?)\s+replaces\s+(.+?)$', description, re.IGNORECASE)
    if not match:
        logging.info(f"Error: Could not parse player names from description: {description}")
        return

    new_player_name = process_name(match.group(1).strip())
    old_player_name = process_name(match.group(2).strip())

    new_player_id = get_closest_player_id(new_player_name, player_map)
    old_player_id = get_closest_player_id(old_player_name, player_map)

    if not new_player_id or not old_player_id:
        logging.info(
            f"Warning: Could not find one or both players in the player map: '{new_player_name}', '{old_player_name}'")
        return

    team = 'away' if game_state.half == Half.TOP else 'home'

    if team == 'away':
        if(game_state.away_pitcher == old_player_id):
            game_state.away_pitcher = None
            logging.info(f"found an offensive sub where the person being subbed out is the pitcher")
    else:
        if game_state.home_pitcher == old_player_id:
            game_state.home_pitcher = None
            logging.info(f"found an offensive sub where the person being subbed out is the pitcher")

    # We know the player is replaced in the batting order
    _replace_in_batting_order(game_state, team, old_player_id, new_player_id)
    # But we remain agnostic about who is going to fill the field position and wait til the next defensive switch
    _replace_position_player(game_state, team, old_player_id, None)


    if "Pinch-runner" in description:
        _replace_on_base(game_state, old_player_id, new_player_id)
        logging.info(
            f"Pinch-runner: {new_player_name} (ID: {new_player_id}) replaces {old_player_name} (ID: {old_player_id}) on the base paths.")
    else:
        logging.info(
            f"Pinch-hitter: {new_player_name} (ID: {new_player_id}) replaces {old_player_name} (ID: {old_player_id}) in the batting order.")


def handle_defensive_switch(description, game_state, player_map):
    # Determine the format of the description and extract relevant details
    if "remains in the game as" in description:
        # Format: "player_name remains in the game as the new_position"
        player_name_part = description.split("remains in the game as")[0].strip()
        to_position_name = description.split("remains in the game as the ")[1].strip().lower()
        from_position = None  # No specified from_position in this case
    else:
        # Format: "switch from old_position to new_position for player_name"
        from_position_name = description.split("switch from ")[1].split(" to ")[0].strip().lower()
        to_position_name = description.split(" to ")[1].split(" for ")[0].strip().lower()
        player_name_part = description.split("for")[1].strip()
        from_position = _map_position_name_to_enum(from_position_name)

    # Clean the player's name and get the player ID
    player_name = process_name(player_name_part)
    player_id = get_closest_player_id(player_name, player_map)

    if not player_id:
        logging.info(f"Warning: Player '{player_name}' not found in the player map.")
        return

    # Determine the team based on the game state
    team = 'home' if game_state.half == Half.TOP else 'away'

    # Map the to_position name to the corresponding FieldPosition enum
    to_position = _map_position_name_to_enum(to_position_name)
    logging.info(f"to_position: to_position")
    if to_position is None:
        logging.info(f"Warning: Could not map '{to_position_name}' to a valid field position.")
        return

    # We should move the player to the to position
    game_state.set_position_player(team, to_position, player_id)
    # Update the defensive positions in the game state using set_position_player method
    if from_position:
        current_player_in_from_position = game_state.get_position_player(team, from_position)
        if current_player_in_from_position == player_id:
            # Clear the from position if the player is indeed occupying it
            game_state.set_position_player(team, from_position, None)


def handle_defensive_sub(description, game_state, player_map):
    new_player_name, old_player_name, target_position = _extract_from_defensive_sub_desc(description)
    new_player_id = get_closest_player_id(new_player_name, player_map)
    old_player_id = get_closest_player_id(old_player_name, player_map)
    target_position = _map_position_name_to_enum(target_position)

    team = 'home' if game_state.half == Half.TOP else 'away'

    if new_player_id:
        if target_position:
            # Update the position in the game state
            game_state.set_position_player(team, target_position, new_player_id)
            logging.info(f"Placed {new_player_name} (ID: {new_player_id}) at {target_position} for team {team}.")
        else:
            logging.info(f"Warning: Unable to determine the target position for '{new_player_name}'.")

        # Update the batting order by replacing the old player with the new player
        if old_player_id:
            _replace_in_batting_order(game_state, team, old_player_id, new_player_id)
        else:
            logging.info(f"Warning: Unable to find old player '{old_player_name}' in player map.")
    else:
        logging.info(f"Warning: Unable to find new player '{new_player_name}' in player map.")


def handle_pitching_sub(description, game_state, player_map):
    if "enters the batting order" in description:
        parts = description.split()
        new_player_name = process_name(' '.join(parts[1:3]))
        batting_position = next(int(part.rstrip('thstndrd,')) for part in parts if part.rstrip('thstndrd,').isdigit())

        # Find the old player name
        leave_index = parts.index("leaves")
        old_player_name = process_name(' '.join(parts[leave_index - 2:leave_index]))

        new_player_id = get_closest_player_id(new_player_name, player_map)
        old_player_id = get_closest_player_id(old_player_name, player_map)

        if not new_player_id or not old_player_id:
            logging.info(f"Warning: Player '{new_player_name}' or '{old_player_name}' not found in the player map.")
            return

        team = 'home' if game_state.half == Half.TOP else 'away'
        _replace_in_batting_order(game_state, team, old_player_id, new_player_id, batting_position)
        return

    match = re.match(
        r"Pitching Change:\s*(.+?)\s+replaces\s+(.+?)(?:,\s*batting\s+(\d+)(?:th|st|nd|rd))?(?:,\s*replacing.*)?\.?$",
        description)
    if not match:
        return

    new_pitcher_name = process_name(match.group(1))
    old_pitcher_name = process_name(match.group(2))
    batting_position = int(match.group(3)) if match.group(3) else None

    new_pitcher_id = get_closest_player_id(new_pitcher_name, player_map)
    old_pitcher_id = get_closest_player_id(old_pitcher_name, player_map)

    if not new_pitcher_id or not old_pitcher_id:
        return

    team = 'home' if game_state.half == Half.TOP else 'away'
    _replace_position_player(game_state, team, old_pitcher_id, new_pitcher_id)

    # If a batting position is specified, update the batting order
    if batting_position:
        _replace_in_batting_order(game_state, team, old_pitcher_id, new_pitcher_id, batting_position)


def _map_position_name_to_enum(position_name):
    # Clean the position name by removing any periods and extra whitespace
    cleaned_position_name = position_name.replace('.', '').strip().lower()

    # Map cleaned position names to the FieldPosition enum
    position_mapping = {
        "catcher": FieldPosition.CATCHER,
        "first baseman": FieldPosition.FIRST_BASE,
        "first base": FieldPosition.FIRST_BASE,
        "second baseman": FieldPosition.SECOND_BASE,
        "second base": FieldPosition.SECOND_BASE,
        "third baseman": FieldPosition.THIRD_BASE,
        "third base": FieldPosition.THIRD_BASE,
        "shortstop": FieldPosition.SHORTSTOP,
        "left fielder": FieldPosition.LEFT_FIELD,
        "left field": FieldPosition.LEFT_FIELD,
        "center fielder": FieldPosition.CENTER_FIELD,
        "center field": FieldPosition.CENTER_FIELD,
        "right fielder": FieldPosition.RIGHT_FIELD,
        "right field": FieldPosition.RIGHT_FIELD,
        "pitcher": None,  # Pitcher is handled separately in the logic
        "designated hitter": FieldPosition.DESIGNATED_HITTER
    }
    return position_mapping.get(cleaned_position_name)


def handle_pickoff_error_1b(description, game_state, player_map):
    logging.info(f"Handling Pickoff Error at 1B")
    scored_players = []

    if "scores" in description:
        for player_name in player_map.values():
            if process_name(player_name) in description.lower():
                player_id = get_closest_player_id(player_name, player_map)
                if not player_id:
                    logging.info(f"Warning: Player '{player_name}' not found in player map.")
                    continue
                for base, occupant in game_state.bases_occupied.items():
                    if occupant == player_id:
                        game_state.bases_occupied[base] = -1
                        scored_players.append(player_id)
                        logging.info(f"Player '{player_name}' (ID: {player_id}) scored.")
                        break

    runner_on_first = game_state.bases_occupied.get(Base.FIRST, -1)
    runner_on_second = game_state.bases_occupied.get(Base.SECOND, -1)

    if runner_on_first != -1 and runner_on_first not in scored_players:
        game_state.bases_occupied[Base.FIRST] = -1
        game_state.bases_occupied[Base.SECOND] = runner_on_first
        logging.info(f"Runner on 1st (Player ID: {runner_on_first}) advanced to 2nd.")

    if runner_on_second != -1 and runner_on_second not in scored_players:
        game_state.bases_occupied[Base.SECOND] = -1
        game_state.bases_occupied[Base.THIRD] = runner_on_second
        logging.info(f"Runner on 2nd (Player ID: {runner_on_second}) advanced to 3rd.")


def handle_pickoff_error_2b(description, game_state, player_map):
    logging.info(f"Handling Pickoff Error at 2B")
    scored_players = []

    if "scores" in description:
        for player_name in player_map.values():
            if process_name(player_name) in description.lower():
                player_id = get_closest_player_id(player_name, player_map)
                if not player_id:
                    logging.info(f"Warning: Player '{player_name}' not found in player map.")
                    continue
                for base, occupant in game_state.bases_occupied.items():
                    if occupant == player_id:
                        game_state.bases_occupied[base] = -1
                        scored_players.append(player_id)
                        logging.info(f"Player '{player_name}' (ID: {player_id}) scored.")
                        break

    runner_on_second = game_state.bases_occupied.get(Base.SECOND, -1)
    runner_on_first = game_state.bases_occupied.get(Base.FIRST, -1)

    if runner_on_second != -1 and runner_on_second not in scored_players:
        game_state.bases_occupied[Base.SECOND] = -1
        game_state.bases_occupied[Base.THIRD] = runner_on_second
        logging.info(f"Runner on 2nd (Player ID: {runner_on_second}) advanced to 3rd.")

    if runner_on_first != -1 and runner_on_first not in scored_players:
        game_state.bases_occupied[Base.FIRST] = -1
        game_state.bases_occupied[Base.SECOND] = runner_on_first
        logging.info(f"Runner on 1st (Player ID: {runner_on_first}) advanced to 2nd.")


def handle_pickoff_error_3b(description, game_state, player_map):
    logging.info(f"Handling Pickoff Error at 3B")
    scored_players = []

    if "scores" in description:
        for player_name in player_map.values():
            if process_name(player_name) in description.lower():
                player_id = get_closest_player_id(player_name, player_map)
                if not player_id:
                    logging.info(f"Warning: Player '{player_name}' not found in player map.")
                    continue
                for base, occupant in game_state.bases_occupied.items():
                    if occupant == player_id:
                        game_state.bases_occupied[base] = -1
                        scored_players.append(player_id)
                        logging.info(f"Player '{player_name}' (ID: {player_id}) scored.")
                        break

    # No further base advancements as the pickoff error occurred at 3B
    # and any runners on bases would have been handled above


def handle_pickoff_caught_stealing(description, game_state, player_map):
    logging.info(f"Handling Pickoff Caught Stealing")

    # Check if "picked off" occurs exactly once
    if description.lower().count("picked off") != 1:
        logging.info(f"Error: 'Picked off' appears more than once in the description.")
        return

    # Extract the player's name who was picked off
    try:
        player_name_part = description.split("picked off")[0].split(",")[-1].strip()
        player_name = process_name(player_name_part)
    except IndexError:
        logging.info(f"Error: Could not find player's name in the description.")
        return

    # Resolve the player ID using the player map
    player_id = get_closest_player_id(player_name, player_map)
    if not player_id:
        logging.info(f"Warning: Player '{player_name}' not found in the player map.")
        return

    # Determine which base the player was attempting to steal based on the description
    if "stealing 2nd base" in description.lower():
        base_to_check = Base.FIRST
        target_base = "2B"
    elif "stealing 3rd base" in description.lower():
        base_to_check = Base.SECOND
        target_base = "3B"
    elif "stealing home" in description.lower():
        base_to_check = Base.THIRD
        target_base = "Home"
    else:
        logging.info(f"Error: Could not determine which base the player was attempting to steal.")
        return

    # Check if the player is on the expected base and update the game state
    runner_on_base = game_state.bases_occupied.get(base_to_check, -1)
    if runner_on_base == player_id:
        game_state.bases_occupied[base_to_check] = -1
        logging.info(f"Player '{player_name}' (ID: {player_id}) was picked off and caught stealing {target_base}.")
    else:
        logging.info(f"Warning: No player found on {base_to_check.name} to pick off (Expected Player ID: {player_id}).")


def handle_caught_stealing(description, game_state, player_map):
    logging.info(f"Handling Caught Stealing")
    # Check if "caught stealing" occurs exactly once
    if description.lower().count("caught stealing") != 1:
        logging.info(f"Warning: 'Caught stealing' appears more than once in the description.")
        return

    # Extract the player's name based on the format of the description
    try:
        if ":" in description:
            # Format: "Team challenged ..., call on the field was overturned: Player caught stealing ..."
            player_name_part = description.split(":")[1].split("caught stealing")[0].strip()
        else:
            # Format: "Player caught stealing ..."
            player_name_part = description.split("caught stealing")[0].strip()

        # Clean and process the player's name
        player_name = process_name(player_name_part)
    except IndexError:
        logging.info(f"Warning: Could not find player's name in the description.")
        return

    # Resolve the player ID using the player map
    player_id = get_closest_player_id(player_name, player_map)
    if not player_id:
        logging.info(f"Warning: Player '{player_name}' not found in the player map.")
        return

    # Determine which base the player was attempting to steal based on the description
    if "2nd base" in description.lower():
        base_to_check = Base.FIRST
        target_base = "2B"
    elif "3rd base" in description.lower():
        base_to_check = Base.SECOND
        target_base = "3B"
    elif "home" in description.lower():
        base_to_check = Base.THIRD
        target_base = "Home"
    else:
        logging.info(f"Warning: Could not determine which base the player was attempting to steal.")
        return

    # Check if the player is on the expected base and update the game state
    runner_on_base = game_state.bases_occupied.get(base_to_check, -1)
    if runner_on_base == player_id:
        game_state.bases_occupied[base_to_check] = -1
        logging.info(f"Player '{player_name}' (ID: {player_id}) was caught stealing {target_base}.")
    else:
        logging.info(f"Warning: No player found on {base_to_check.name} to be caught stealing (Expected Player ID: {player_id}).")
        # TODO: there are rare cases when statcast is wrong so we don't have anyone on base to steal
        # we can see what the description implies, and create a decision point that we return from this function
        # and then in our process loop if an event handler returns something that means we should overwrite the previous
        # decision point with our corrected one

def _replace_on_base(game_state, old_player_id, new_player_id):
    for base, occupant in game_state.bases_occupied.items():
        if occupant == old_player_id:
            game_state.bases_occupied[base] = new_player_id
            logging.info(f"Player {new_player_id} replaces {old_player_id} on {base.name}.")
            return
    logging.info(f"Warning: Could not find {old_player_id} on any base to replace.")


def _replace_position_player(game_state, team, old_player_id, new_player_id):
    logging.info(f"entered replace position player/pitcher function: ")
    logging.info(f" team: team")
    logging.info(f" old_player_id: old_player_id")
    logging.info(f" new_player_id: new_player_id")

    # Determine which team's position players and flags we are working with
    if team == 'home':
        position_players = game_state.home_position_players
        current_pitcher = game_state.home_pitcher
    elif team == 'away':
        position_players = game_state.away_position_players
        current_pitcher = game_state.away_pitcher
    else:
        raise ValueError("Team must be 'home' or 'away'")

    logging.info(f"current_pitcher: {current_pitcher}")


    # Replace a position player in the field
    for position, player_id in position_players.items():
        if player_id == old_player_id:
            logging.info(f"Replacing {old_player_id} at {position} with {new_player_id} for {team}")
            game_state.set_position_player(team, position, new_player_id)
            return

    # If the old player is the pitcher, replace the pitcher
    if old_player_id == current_pitcher or current_pitcher is None:
        logging.info(f"Replacing pitcher for {team}: {old_player_id} with {new_player_id}")
        if team == 'home':
            game_state.home_pitcher = new_player_id
        else:
            game_state.away_pitcher = new_player_id


def _replace_in_batting_order(game_state, team, old_player_id, new_player_id, batting_position=None):
    lineup = game_state.home_lineup if team == 'home' else game_state.away_lineup

    if batting_position is not None:
        # If a batting position is specified, insert the new player at that position
        lineup[batting_position - 1] = new_player_id
        logging.info(f"Inserted {new_player_id} into the {team} batting order at position {batting_position}.")
    else:
        # Find the old player in the batting lineup and replace them with the new player
        for idx, player_id in enumerate(lineup):
            if player_id == old_player_id:
                lineup[idx] = new_player_id
                logging.info(f"Replaced {old_player_id} with {new_player_id} in the {team} batting order at position {idx + 1}.")
                return

        logging.info(f"Warning: Could not find {old_player_id} in the {team} batting order to replace with {new_player_id}.")


def _extract_from_defensive_sub_desc(description):
    # Remove 'Defensive Substitution:' from the start
    description = description.replace('Defensive Substitution:', '').strip()

    # Split the description into parts
    parts = description.split(',')

    # Extract new player name (always comes first)
    new_player_name = parts[0].strip().split(' replaces ')[0].strip()

    # Find the old player name
    old_player_pattern = r'replaces\s+(.*?)(?:,|\s*$)'
    old_player_match = re.search(old_player_pattern, description)
    old_player_name = old_player_match.group(1) if old_player_match else None

    # Extract the position the new player is playing
    position_pattern = r'playing\s+(.*?)(?:,|\s*$)'
    position_match = re.search(position_pattern, description)
    target_position = position_match.group(1) if position_match else None

    # Clean up player names
    if old_player_name:
        # Remove position if it's included with the old player's name
        old_player_name = re.sub(
            r'\b(first baseman|second baseman|shortstop|third baseman|left fielder|right fielder|catcher|center fielder|pitcher)\s+',
            '', old_player_name)
        old_player_name = old_player_name.strip()

    # Remove any middle initials from player names
    old_player_name = remove_middle_initials(old_player_name)
    new_player_name = remove_middle_initials(new_player_name)

    return new_player_name, old_player_name, target_position


def remove_middle_initials(name):
    # Pattern to match names with one or more middle initials (case insensitive)
    pattern = r'^(\w+)\s+(?:[A-Za-z]\.?\s+)+(\w+)$'

    match = re.match(pattern, name)
    if match:
        # If the pattern matches, return the name without middle initials
        return f"{match.group(1)} {match.group(2)}"
    else:
        # If the pattern doesn't match, return the original name
        return name


# Dictionary mapping event types to their handler functions
event_handlers = {
    "Stolen Base 2B": handle_stolen_base,
    "Stolen Base 3B": handle_stolen_base,
    "Stolen Base Home": handle_stolen_base,
    "Wild Pitch": handle_wild_pitch,
    "Passed Ball": handle_passed_ball,
    "Balk": handle_balk,
    "Pickoff Error 1B": handle_pickoff_error_1b,
    "Pickoff Error 2B": handle_pickoff_error_2b,
    "Pickoff Error 3B": handle_pickoff_error_3b,
    "Pitching Substitution": handle_pitching_sub,
    "Defensive Sub": handle_defensive_sub,
    "Defensive Switch": handle_defensive_switch,
    "Offensive Substitution": handle_offensive_sub,
    "Pickoff Caught Stealing 2B": handle_pickoff_caught_stealing,
    "Pickoff Caught Stealing 3B": handle_pickoff_caught_stealing,
    "Pickoff Caught Stealing Home": handle_pickoff_caught_stealing,
    "Caught Stealing 2B": handle_caught_stealing,
    "Caught Stealing 3B": handle_caught_stealing,
    "Caught Stealing Home": handle_caught_stealing,
    "AttemptBaseUpdate": attempt_base_update
}

if __name__ == "__main__":
    game_state = GameState()
    handle_pitching_sub('Pitching Change: Michael Fulmer replaces Mark Leiter Jr.', game_state, {})

