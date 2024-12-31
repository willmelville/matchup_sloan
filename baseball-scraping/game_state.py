from enum import Enum, auto


class Base(Enum):
    FIRST = auto()
    SECOND = auto()
    THIRD = auto()


class Half(Enum):
    TOP = "Top"
    BOTTOM = "Bot"


class FieldPosition(Enum):
    DESIGNATED_HITTER = "DH"
    CATCHER = "C"
    FIRST_BASE = "1B"
    SECOND_BASE = "2B"
    THIRD_BASE = "3B"
    SHORTSTOP = "SS"
    LEFT_FIELD = "LF"
    CENTER_FIELD = "CF"
    RIGHT_FIELD = "RF"



class GameState:
    __slots__ = ('home_abbr', 'away_abbr', 'inning', 'half', 'score_home', 'score_away', 'outs',
                 'bases_occupied', 'home_lineup', 'away_lineup',
                 'home_pitcher', 'home_sub_ins', 'away_pitcher', 'away_sub_ins',
                 'home_position_players', 'away_position_players', 'at_bat', 'home_has_dh', 'away_has_dh', 'prev_half')

    def __init__(self, home_abbr=None, away_abbr=None, inning=1, half=Half.TOP, score_home=0, score_away=0, outs=0,
                 bases_occupied=None, home_lineup=None, away_lineup=None,
                 home_pitcher=None, home_sub_ins=None, away_pitcher=None, away_sub_ins=None,
                 home_position_players=None, away_position_players=None, at_bat=1, home_has_dh=True, away_has_dh=True):
        self.home_abbr = home_abbr
        self.away_abbr = away_abbr
        self.inning = inning
        self.half = half
        self.score_home = score_home
        self.score_away = score_away
        self.outs = outs
        self.bases_occupied = bases_occupied or {
            Base.FIRST: -1,
            Base.SECOND: -1,
            Base.THIRD: -1
        }
        self.home_lineup = home_lineup or [-1] * 9  # Initialize with -1 for empty slots
        self.away_lineup = away_lineup or [-1] * 9
        self.home_pitcher = home_pitcher
        self.away_pitcher = away_pitcher
        self.home_sub_ins = home_sub_ins
        self.away_sub_ins = away_sub_ins
        self.home_position_players = home_position_players or {pos: None for pos in FieldPosition}
        self.away_position_players = away_position_players or {pos: None for pos in FieldPosition}
        self.at_bat = at_bat
        self.home_has_dh = home_has_dh
        self.away_has_dh = away_has_dh

    def update(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def set_position_player(self, team, position, player):
        if team == 'home':
            self.home_position_players[position] = player
        elif team == 'away':
            self.away_position_players[position] = player
        else:
            raise ValueError("Team must be 'home' or 'away'")

    def get_position_player(self, team, position):
        if team == 'home':
            return self.home_position_players[position]
        elif team == 'away':
            return self.away_position_players[position]
        else:
            raise ValueError("Team must be 'home' or 'away'")

    def create_decision_point(self, event, is_decision, player_map) -> dict:
        decision_point = {
            "Event_Type": event['type'],
            "Is_Decision": is_decision,
            "Inning": self.inning,
            "Half": self.half.value,
            "At_Bat": self.at_bat,
            "Score_Deficit": self.score_home - self.score_away,
            "Outs": self.outs,
            "Third_Base": self._get_player_representation(self.bases_occupied[Base.THIRD], player_map),
            "Second_Base": self._get_player_representation(self.bases_occupied[Base.SECOND], player_map),
            "First_Base": self._get_player_representation(self.bases_occupied[Base.FIRST], player_map),
            "Home_Pitcher": self._get_player_representation(self.home_pitcher, player_map),
            "Away_Pitcher": self._get_player_representation(self.away_pitcher, player_map),
        }

        # Add individual lineup positions with player ID and name
        for i in range(9):
            decision_point[f"Home_Lineup_{i + 1}"] = self._get_player_representation(self.home_lineup[i], player_map)
            decision_point[f"Away_Lineup_{i + 1}"] = self._get_player_representation(self.away_lineup[i], player_map)

        # Add position players with player ID and name
        for pos, player_id in self.home_position_players.items():
            decision_point[f"Home_{pos.value}"] = player_id
        for pos, player_id in self.away_position_players.items():
            decision_point[f"Away_{pos.value}"] = player_id


        return decision_point

    def _get_player_representation(self, player_id, player_map):
        """Helper method to concatenate the player ID and name for easier debugging."""
        if player_id is None or player_id == -1:
            return None
        # player_name = player_map.get(player_id, "Unknown")
        return f"{player_id}"

    def empty_bases(self):
        self.bases_occupied = {
            Base.FIRST: -1,
            Base.SECOND: -1,
            Base.THIRD: -1
        }


