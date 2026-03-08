"""
ESPN undocumented API client for live game data.

Provides real-time game clock, score, and period info to determine
if a game is truly in its final minutes (4th quarter, 9th inning, etc).
"""

from dataclasses import dataclass
from typing import Optional

import httpx

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

# Map Kalshi series prefixes to ESPN sport/league paths
KALSHI_TO_ESPN = {
    "KXNBAGAME": "basketball/nba",
    "KXNHLGAME": "hockey/nhl",
    "KXNFLGAME": "football/nfl",
    "KXMLBGAME": "baseball/mlb",
    "KXNCAAMBGAME": "basketball/mens-college-basketball",
    "KXNCAAFBGAME": "football/college-football",
    "KXUFCFIGHT": "mma/ufc",
    "KXEPLGAME": "soccer/eng.1",
    "KXLALIGAGAME": "soccer/esp.1",
    "KXMLSGAME": "soccer/usa.1",
    "KXMLBSTGAME": "baseball/mlb",
}

# How many periods/quarters each sport has in regulation
SPORT_FINAL_PERIOD = {
    "basketball/nba": 4,
    "hockey/nhl": 3,
    "football/nfl": 4,
    "baseball/mlb": 9,
    "basketball/mens-college-basketball": 2,
    "football/college-football": 4,
    "mma/ufc": 5,  # 5 rounds max
    "soccer/eng.1": 2,
    "soccer/esp.1": 2,
    "soccer/usa.1": 2,
}


@dataclass
class GameState:
    """Live state of a game from ESPN."""

    espn_id: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    period: int
    display_clock: str
    clock_seconds: float
    state: str  # "pre", "in", "post"
    status_name: str  # e.g. "STATUS_IN_PROGRESS", "STATUS_FINAL"
    sport_path: str

    @property
    def final_period(self) -> int:
        return SPORT_FINAL_PERIOD.get(self.sport_path, 4)

    @property
    def is_live(self) -> bool:
        return self.state == "in"

    @property
    def is_final_period(self) -> bool:
        return self.period >= self.final_period

    @property
    def is_in_final_minutes(self) -> bool:
        """True if game is live, in the final period, with <=5 min on the clock."""
        if not self.is_live:
            return False
        if not self.is_final_period:
            return False
        # Baseball has no clock — being in the final period is enough
        if "baseball" in self.sport_path:
            return True
        from db import get_config_int

        final_secs = get_config_int(f"final_seconds:{self.sport_path}")
        # Soccer clock counts UP — require >= threshold
        if "soccer" in self.sport_path:
            return self.clock_seconds >= (final_secs or 4800)
        return self.clock_seconds <= (final_secs or 300)

    @property
    def score_diff(self) -> int:
        return abs(self.home_score - self.away_score)

    @property
    def leading_team(self) -> str:
        if self.home_score > self.away_score:
            return self.home_team
        elif self.away_score > self.home_score:
            return self.away_team
        return "tied"


async def get_scoreboard(sport_path: str) -> list[GameState]:
    """Fetch live scoreboard for a sport from ESPN."""
    url = f"{ESPN_BASE}/{sport_path}/scoreboard"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    games = []
    for event in data.get("events", []):
        competitions = event.get("competitions", [])
        if not competitions:
            continue
        comp = competitions[0]
        status = comp.get("status", {})
        status_type = status.get("type", {})

        competitors = comp.get("competitors", [])
        home = away = None
        for c in competitors:
            if c.get("homeAway") == "home":
                home = c
            else:
                away = c

        if not home or not away:
            continue

        clock_str = status.get("displayClock", "0:00")
        # Parse clock to seconds
        clock_seconds = 0.0
        try:
            parts = clock_str.split(":")
            if len(parts) == 2:
                clock_seconds = int(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 1:
                clock_seconds = float(parts[0])
        except (ValueError, IndexError):
            clock_seconds = 0.0

        games.append(
            GameState(
                espn_id=event.get("id", ""),
                home_team=home.get("team", {}).get("abbreviation", ""),
                away_team=away.get("team", {}).get("abbreviation", ""),
                home_score=int(home.get("score", "0")),
                away_score=int(away.get("score", "0")),
                period=status.get("period", 0),
                display_clock=clock_str,
                clock_seconds=clock_seconds,
                state=status_type.get("state", ""),
                status_name=status_type.get("name", ""),
                sport_path=sport_path,
            )
        )

    return games


async def get_live_final_minutes_games() -> dict[str, list[GameState]]:
    """Get all games across all sports that are in their final minutes."""
    result = {}
    for kalshi_series, sport_path in KALSHI_TO_ESPN.items():
        games = await get_scoreboard(sport_path)
        final_min = [g for g in games if g.is_in_final_minutes]
        if final_min:
            result[kalshi_series] = final_min
    return result


async def get_categorized_games() -> tuple[dict[str, list[GameState]], dict[str, list[GameState]]]:
    """Fetch live games once, return (final_minutes, final_period) dicts.

    final_minutes: games matching the configured end-of-game timing.
    final_period: all live games in their final period (broader net for what-ifs).
    """
    final_minutes: dict[str, list[GameState]] = {}
    final_period: dict[str, list[GameState]] = {}
    for kalshi_series, sport_path in KALSHI_TO_ESPN.items():
        games = await get_scoreboard(sport_path)
        fm = [g for g in games if g.is_in_final_minutes]
        fp = [g for g in games if g.is_live and g.is_final_period]
        if fm:
            final_minutes[kalshi_series] = fm
        if fp:
            final_period[kalshi_series] = fp
    return final_minutes, final_period


def game_meets_timing(game: GameState, countdown_secs: int, countup_secs: int) -> bool:
    """Check if a game meets a specific timing threshold."""
    if not game.is_live or not game.is_final_period:
        return False
    if "baseball" in game.sport_path:
        return True
    if "soccer" in game.sport_path:
        return game.clock_seconds >= countup_secs
    return game.clock_seconds <= countdown_secs


# ESPN abbreviations that differ from Kalshi ticker abbreviations.
# Only entries where ESPN and Kalshi use DIFFERENT codes.
# Map ESPN abbreviation → list of Kalshi equivalents to check.
ESPN_TO_KALSHI_ABBR: dict[str, list[str]] = {
    # NBA
    "GS": ["GSW"],
    "UTAH": ["UTA"],
    "SA": ["SAS"],
    # MLS
    "DC": ["DCU"],
    "LA": ["LAG", "LA"],  # ESPN "LA" = LA Galaxy; Kalshi uses "LAG"
    # NFL
    "JAX": ["JAC"],
}


def _espn_to_kalshi_codes(espn_abbr: str) -> list[str]:
    """Return Kalshi codes that an ESPN abbreviation could map to."""
    codes = ESPN_TO_KALSHI_ABBR.get(espn_abbr.upper(), [])
    # Always include the original ESPN abbreviation itself
    if espn_abbr.upper() not in [c.upper() for c in codes]:
        codes = [espn_abbr.upper()] + codes
    return codes


def match_kalshi_to_espn(
    kalshi_ticker: str,
    kalshi_title: str,
    espn_games: list[GameState],
) -> Optional[GameState]:
    """
    Try to match a Kalshi market to an ESPN game by team abbreviations.
    Kalshi tickers contain team abbreviations (e.g., KXNBAGAME-26MAR07NYKLAC-LAC).
    """
    ticker_upper = kalshi_ticker.upper()
    title_upper = kalshi_title.upper()

    for game in espn_games:
        home_codes = _espn_to_kalshi_codes(game.home_team)
        away_codes = _espn_to_kalshi_codes(game.away_team)

        home_match = any(c in ticker_upper or c in title_upper for c in home_codes)
        away_match = any(c in ticker_upper or c in title_upper for c in away_codes)

        # Require BOTH teams to match — single-team matches cause false positives
        # against future games (e.g., tomorrow's MIL game matching today's MIL game)
        if home_match and away_match:
            return game

    return None
