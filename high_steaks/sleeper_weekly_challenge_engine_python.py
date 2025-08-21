#!/usr/bin/env python3
"""
Sleeper Weekly Challenge Engine

Dependencies:
  pip install sleeper-wrapper nfl-data-py pandas requests

Usage (examples):
  python challenge_engine.py --league_id 1120567286148091904 --week 4
  python challenge_engine.py --league_id 1120567286148091904 --week 8 --projections sleeper
  python challenge_engine.py --league_id 1120567286148091904 --week 8 --projections rolling --rolling_n 3

Notes:
- Uses nfl_data_py (nflfastR) for weekly box-score style stats.
- Uses Sleeper for league/matchups/players and optional per-player projections.
- Tie handling: prints all tied winners.
- Scoring assumptions: PPR for projection-related summaries; actual points are Sleeper's `players_points` in your league.
"""

from __future__ import annotations
import argparse
import sys
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

try:
    from sleeper_wrapper import League
except Exception as e:
    print("Please install sleeper-wrapper: pip install sleeper-wrapper", file=sys.stderr)
    raise

try:
    import nfl_data_py as nfl
except Exception as e:
    print("Please install nfl-data-py: pip install nfl-data-py", file=sys.stderr)
    raise

# ---------------------------
# Config: owner display mapping (optional)
# ---------------------------
DEFAULT_USER_TO_OWNER = {
    "mtreigelman": "Reigelman",
    "Tophinator": "Christoph",
    "TheRodfather10": "Tony",
    "Mdduff": "Duffy",
    "danderson28": "Daniel",
    "WillDiesel": "Will",
    "RhodesRhodes": "Rhodes",
    "gretemeyer": "Geoff",
    "steviemorgan": "Stevie",
    "msassman33": "Sassman",
    "bobm18": "Bobby",
    "jide49": "Jide",
}

FLEX_ELIGIBLE = {"RB", "WR", "TE"}

# ---------------------------
# Providers
# ---------------------------

def _ppr_points_from_weekly_row(df_row: pd.Series) -> float:
    """Approximate PPR fantasy points from nflfastR weekly stats row."""
    py = float(df_row.get("passing_yards", 0) or 0)
    ptd = float(df_row.get("passing_tds", 0) or 0)
    ints = float(df_row.get("interceptions", 0) or 0)
    ry = float(df_row.get("rushing_yards", 0) or 0)
    rtd = float(df_row.get("rushing_tds", 0) or 0)
    recy = float(df_row.get("receiving_yards", 0) or 0)
    rectd = float(df_row.get("receiving_tds", 0) or 0)
    recs = float(df_row.get("receiving_receptions", 0) or 0)
    # Basic PPR
    pts = (py / 25.0) + (ptd * 4.0) - (ints * 2.0) \
          + (ry / 10.0) + (rtd * 6.0) \
          + (recy / 10.0) + (rectd * 6.0) + (recs * 1.0)
    return float(pts)

class WeeklyStatsProvider:
    """Abstracts weekly player stats (box-score style) keyed by GSIS player_id."""
    def weekly_stats(self, season: int, week: int) -> pd.DataFrame:
        raise NotImplementedError

class NflDataPyStatsProvider(WeeklyStatsProvider):
    def weekly_stats(self, season: int, week: int) -> pd.DataFrame:
        cols = [
            "season", "week", "player_id", "player_name", "recent_team", "position",
            "rushing_yards", "rushing_tds",
            "receiving_receptions", "receiving_yards", "receiving_tds",
            "passing_yards", "passing_tds", "interceptions",
        ]
        df = nfl.import_weekly_data([season])[cols]
        df = df[(df["season"] == int(season)) & (df["week"] == int(week))].copy()
        return df

class ProjectionsProvider:
    def projection_points(self, sleeper_player_id: str, season: int, week: int) -> float:
        raise NotImplementedError

class SleeperProjectionsProvider(ProjectionsProvider):
    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    @lru_cache(maxsize=None)
    def projection_points(self, sleeper_player_id: str, season: int, week: int) -> float:
        url = f"https://api.sleeper.com/projections/nfl/player/{sleeper_player_id}?season={season}&season_type=regular&grouping=week"
        try:
            data = requests.get(url, timeout=self.timeout).json()
            for row in data or []:
                if str(row.get("week")) == str(week):
                    return float(row.get("pts_ppr") or row.get("pts_half_ppr") or row.get("pts_std") or 0.0)
        except Exception:
            return 0.0
        return 0.0

class RollingAverageProjectionsProvider(ProjectionsProvider):
    def __init__(self, stats_provider: WeeklyStatsProvider, sleeper_to_gsis: Dict[str, str], n: int = 3):
        self.stats_provider = stats_provider
        self.sleeper_to_gsis = sleeper_to_gsis
        self.n = n

    def projection_points(self, sleeper_player_id: str, season: int, week: int) -> float:
        gsis = self.sleeper_to_gsis.get(sleeper_player_id)
        if not gsis:
            return 0.0
        # Pull this season's weekly rows for the player, weeks prior to current
        cols = [
            "season", "week", "player_id", "position",
            "rushing_yards", "rushing_tds",
            "receiving_yards", "receiving_receptions", "receiving_tds",
            "passing_yards", "passing_tds", "interceptions",
        ]
        df = nfl.import_weekly_data([season])[cols]
        df = df[(df["player_id"] == gsis) & (df["week"] < int(week))]
        if df.empty:
            return 0.0
        pts = df.apply(_ppr_points_from_weekly_row, axis=1)
        return float(pts.tail(self.n).mean())

# ---------------------------
# Core Engine
# ---------------------------

@dataclass
class LoadedContext:
    season: int
    week: int
    league_id: str
    users_df: pd.DataFrame
    rosters_df: pd.DataFrame
    matchups_df: pd.DataFrame
    players_df: pd.DataFrame  # Sleeper players payload subset (player_id, full_name, position, gsis_id)
    sleeper_to_gsis: Dict[str, Optional[str]]


class ChallengeEngine:
    def __init__(
        self,
        league_id: str,
        owner_map: Optional[Dict[str, str]] = None,
        stats_provider: Optional[WeeklyStatsProvider] = None,
        projections_provider: Optional[ProjectionsProvider] = None,
        score_type: str = "pts_ppr",
        timeout: int = 20,
    ):
        self.league_id = str(league_id)
        self.owner_map = owner_map or DEFAULT_USER_TO_OWNER
        self.stats_provider = stats_provider or NflDataPyStatsProvider()
        self.projections_provider = projections_provider  # can be set later
        self.score_type = score_type
        self.timeout = timeout

    # ----------- loading helpers -----------
    @staticmethod
    def _get_state():
        state = requests.get("https://api.sleeper.app/v1/state/nfl", timeout=15).json()
        return int(state["season"]), int(state["week"]) if state.get("week") is not None else 1

    @staticmethod
    def _load_players_df() -> pd.DataFrame:
        url = "https://api.sleeper.app/v1/players/nfl"
        players = requests.get(url, timeout=30).json()
        pdf = pd.DataFrame(players).T
        keep = ["player_id", "full_name", "position", "first_name", "last_name", "gsis_id", "espn_id", "yahoo_id"]
        # some players may lack some columns; fill missing
        for c in keep:
            if c not in pdf.columns:
                pdf[c] = None
        pdf = pdf[keep].copy()
        return pdf

    def load_context(self, week: Optional[int] = None, season: Optional[int] = None) -> LoadedContext:
        if season is None or week is None:
            cur_season, cur_week = self._get_state()
            season = season or cur_season
            week = week or cur_week
        season = int(season)
        week = int(week)

        league = League(self.league_id)
        matchups = league.get_matchups(str(week))
        users = league.get_users()
        rosters = league.get_rosters()

        matchups_df = pd.DataFrame(matchups)
        users_df = pd.DataFrame(users)
        # Map display_name -> friendly owner (fallback to display_name if not mapped)
        users_df["owner"] = users_df["display_name"].map(self.owner_map).fillna(users_df["display_name"])

        rosters_df = pd.DataFrame(rosters).rename(columns={"owner_id": "user_id"})
        rosters_df = rosters_df.merge(users_df[["user_id", "owner", "display_name"]], on=["user_id"], how="left")

        matchups_df = matchups_df.merge(
            rosters_df[["roster_id", "user_id", "owner", "display_name"]], on=["roster_id"], how="left"
        )

        players_df = self._load_players_df()
        sleeper_to_gsis = players_df.set_index("player_id")["gsis_id"].to_dict()

        return LoadedContext(
            season=season,
            week=week,
            league_id=self.league_id,
            users_df=users_df,
            rosters_df=rosters_df,
            matchups_df=matchups_df,
            players_df=players_df,
            sleeper_to_gsis=sleeper_to_gsis,
        )

    # ----------- utilities -----------
    @staticmethod
    def _tie_string(winners: List[str]) -> str:
        return ", ".join(sorted(set(map(str, winners))))

    def _player_name(self, players_df: pd.DataFrame, sleeper_pid: str) -> str:
        try:
            row = players_df.loc[players_df["player_id"] == sleeper_pid]
            if not row.empty:
                return str(row.iloc[0]["full_name"]) or sleeper_pid
        except Exception:
            pass
        return sleeper_pid

    # ----------- challenges -----------
    def wk1_highest_team_score(self, ctx: LoadedContext) -> str:
        m = ctx.matchups_df
        idx = m["points"].idxmax()
        row = m.loc[idx]
        return f"High point scorer: {row['owner']} with {row['points']:.2f} pts"

    def wk2_most_offensive_tds(self, ctx: LoadedContext) -> str:
        stats = self.stats_provider.weekly_stats(ctx.season, ctx.week)
        stats["off_td"] = stats["rushing_tds"].fillna(0) + stats["receiving_tds"].fillna(0) + stats["passing_tds"].fillna(0)
        td_map = stats.set_index("player_id")["off_td"].to_dict()
        rows: List[Tuple[str, float]] = []
        for _, m in ctx.matchups_df.iterrows():
            total = 0.0
            for pid in m.starters:
                gsis = ctx.sleeper_to_gsis.get(pid)
                total += float(td_map.get(gsis, 0.0) or 0.0)
            rows.append((m.owner, total))
        out = pd.DataFrame(rows, columns=["owner", "off_td"]).sort_values("off_td", ascending=False)
        top = out.off_td.max()
        winners = out.loc[out["off_td"] == top, "owner"].tolist()
        return f"Most offensive TDs: {self._tie_string(winners)} with {int(top)} TDs"

    def wk3_most_wr_receptions(self, ctx: LoadedContext) -> str:
        stats = self.stats_provider.weekly_stats(ctx.season, ctx.week)
        rec_map = stats.set_index("player_id")["receiving_receptions"].fillna(0).to_dict()
        wr_ids = set(ctx.players_df.loc[ctx.players_df["position"] == "WR", "player_id"])
        rows: List[Tuple[str, float]] = []
        for _, m in ctx.matchups_df.iterrows():
            recs = 0.0
            for pid in m.starters:
                if pid in wr_ids:
                    gsis = ctx.sleeper_to_gsis.get(pid)
                    recs += float(rec_map.get(gsis, 0.0) or 0.0)
            rows.append((m.owner, recs))
        out = pd.DataFrame(rows, columns=["owner", "wr_receptions"]).sort_values("wr_receptions", ascending=False)
        top = out.wr_receptions.max()
        winners = out.loc[out["wr_receptions"] == top, "owner"].tolist()
        return f"Most WR receptions: {self._tie_string(winners)} with {int(top)} receptions"

    def wk4_closest_to_21_single(self, ctx: LoadedContext) -> str:
        records: List[Tuple[str, str, float, float]] = []  # player_name, owner, score, dist
        for _, m in ctx.matchups_df.iterrows():
            scorers: Dict[str, float] = m.players_points or {}
            for pid in m.starters:
                pts = float(scorers.get(pid, 0.0) or 0.0)
                dist = abs(21.0 - pts)
                name = self._player_name(ctx.players_df, pid)
                records.append((name, m.owner, pts, dist))
        df = pd.DataFrame(records, columns=["full_name", "owner", "score", "dist_to_21"]).sort_values("dist_to_21")
        best = df.iloc[0]
        ties = df.loc[df["dist_to_21"] == best["dist_to_21"]]
        if len(ties) == 1:
            return (
                f"Closest to 21: {best['full_name']} ({best['owner']}) with {best['score']:.2f} pts; "
                f"Δ={best['dist_to_21']:.2f}"
            )
        else:
            names = ", ".join(ties["full_name"])  # players
            owners = ", ".join(ties["owner"].unique())
            return f"Closest to 21 (tie): {names}; owners: {owners}"

    def wk5_most_points_in_loss(self, ctx: LoadedContext) -> str:
        losers: List[Tuple[str, float]] = []
        for mid, g in ctx.matchups_df.groupby("matchup_id"):
            if g.shape[0] == 2:
                g2 = g.sort_values("points", ascending=False)
                loser = g2.iloc[1]
                losers.append((loser.owner, float(loser.points)))
        out = pd.DataFrame(losers, columns=["owner", "points"]).sort_values("points", ascending=False)
        top = out.points.max()
        winners = out.loc[out["points"] == top, "owner"].tolist()
        return f"Most points in a loss: {self._tie_string(winners)} with {top:.2f} pts"

    def wk6_biggest_margin(self, ctx: LoadedContext) -> str:
        margins: List[Tuple[str, float]] = []  # winner, margin
        for mid, g in ctx.matchups_df.groupby("matchup_id"):
            if g.shape[0] == 2:
                g2 = g.sort_values("points", ascending=False)
                margin = float(g2.iloc[0].points) - float(g2.iloc[1].points)
                margins.append((g2.iloc[0].owner, margin))
        out = pd.DataFrame(margins, columns=["winner", "margin"]).sort_values("margin", ascending=False)
        top = out.margin.max()
        winners = out.loc[out["margin"] == top, "winner"].tolist()
        return f"Biggest margin of victory: {self._tie_string(winners)} by {top:.2f}"

    def wk7_most_rb_rush_yds(self, ctx: LoadedContext) -> str:
        stats = self.stats_provider.weekly_stats(ctx.season, ctx.week)
        rush_map = stats.set_index("player_id")["rushing_yards"].fillna(0).to_dict()
        rb_ids = set(ctx.players_df.loc[ctx.players_df["position"] == "RB", "player_id"])
        rows: List[Tuple[str, float]] = []
        for _, m in ctx.matchups_df.iterrows():
            yards = 0.0
            for pid in m.starters:
                if pid in rb_ids:
                    gsis = ctx.sleeper_to_gsis.get(pid)
                    yards += float(rush_map.get(gsis, 0.0) or 0.0)
            rows.append((m.owner, yards))
        out = pd.DataFrame(rows, columns=["owner", "rb_rush_yd"]).sort_values("rb_rush_yd", ascending=False)
        top = out.rb_rush_yd.max()
        winners = out.loc[out["rb_rush_yd"] == top, "owner"].tolist()
        return f"Most RB rushing yards: {self._tie_string(winners)} with {int(top)} yards"

    def wk8_closest_to_projection(self, ctx: LoadedContext) -> str:
        if self.projections_provider is None:
            raise RuntimeError("No projections provider configured. Use --projections sleeper or rolling.")
        rows: List[Tuple[str, float, float, float]] = []  # owner, proj_sum, act_sum, abs_diff
        for _, m in ctx.matchups_df.iterrows():
            proj_sum = 0.0
            act_sum = 0.0
            scorers: Dict[str, float] = m.players_points or {}
            for pid in m.starters:
                proj_sum += float(self.projections_provider.projection_points(pid, ctx.season, ctx.week) or 0.0)
                act_sum += float(scorers.get(pid, 0.0) or 0.0)
            rows.append((m.owner, proj_sum, act_sum, abs(act_sum - proj_sum)))
        out = pd.DataFrame(rows, columns=["owner", "proj_pts", "actual_pts", "abs_diff"]).sort_values("abs_diff")
        best = out.iloc[0]
        ties = out.loc[out["abs_diff"] == best["abs_diff"], "owner"].tolist()
        return (
            f"Closest to projection: {self._tie_string(ties)} (proj {best['proj_pts']:.2f}, "
            f"actual {best['actual_pts']:.2f}, |Δ|={best['abs_diff']:.2f})"
        )

    def wk9_lowest_winning_score(self, ctx: LoadedContext) -> str:
        winners: List[Tuple[str, float]] = []
        for mid, g in ctx.matchups_df.groupby("matchup_id"):
            if g.shape[0] == 2:
                w = g.loc[g["points"].idxmax()]
                winners.append((w.owner, float(w.points)))
        out = pd.DataFrame(winners, columns=["owner", "points"]).sort_values("points")
        low = out.iloc[0]
        ties = out.loc[out["points"] == low["points"], "owner"].tolist()
        return f"Lowest score in a win: {self._tie_string(ties)} with {low['points']:.2f}"

    def wk10_highest_flex(self, ctx: LoadedContext) -> str:
        flex_ids = set(ctx.players_df.loc[ctx.players_df["position"].isin(FLEX_ELIGIBLE), "player_id"])
        rows: List[Tuple[str, str, float]] = []  # owner, player, points
        for _, m in ctx.matchups_df.iterrows():
            best_pts = -1.0
            best_name = None
            scorers: Dict[str, float] = m.players_points or {}
            for pid in m.starters:
                if pid in flex_ids:
                    pts = float(scorers.get(pid, 0.0) or 0.0)
                    if pts > best_pts:
                        best_pts = pts
                        best_name = self._player_name(ctx.players_df, pid)
            rows.append((m.owner, best_name or "N/A", best_pts))
        out = pd.DataFrame(rows, columns=["owner", "player", "points"]).sort_values("points", ascending=False)
        top = out.iloc[0]["points"]
        ties = out.loc[out["points"] == top]
        return (
            f"Highest FLEX score: {self._tie_string(ties['owner'].tolist())} ("
            f"{', '.join(ties['player'].tolist())}) with {top:.2f}"
        )

    def wk11_closest_to_30_single(self, ctx: LoadedContext) -> str:
        records: List[Tuple[str, str, float, float]] = []  # player_name, owner, score, dist
        for _, m in ctx.matchups_df.iterrows():
            scorers: Dict[str, float] = m.players_points or {}
            for pid in m.starters:
                pts = float(scorers.get(pid, 0.0) or 0.0)
                dist = abs(30.0 - pts)
                name = self._player_name(ctx.players_df, pid)
                records.append((name, m.owner, pts, dist))
        df = pd.DataFrame(records, columns=["full_name", "owner", "score", "dist_to_30"]).sort_values("dist_to_30")
        best = df.iloc[0]
        ties = df.loc[df["dist_to_30"] == best["dist_to_30"]]
        if len(ties) == 1:
            return (
                f"Closest to 30: {best['full_name']} ({best['owner']}) with {best['score']:.2f} pts; "
                f"Δ={best['dist_to_30']:.2f}"
            )
        else:
            names = ", ".join(ties["full_name"])  # players
            owners = ", ".join(ties["owner"].unique())
            return f"Closest to 30 (tie): {names}; owners: {owners}"

    def wk12_most_qb_pass_yds(self, ctx: LoadedContext) -> str:
        stats = self.stats_provider.weekly_stats(ctx.season, ctx.week)
        pass_map = stats.set_index("player_id")["passing_yards"].fillna(0).to_dict()
        qb_ids = set(ctx.players_df.loc[ctx.players_df["position"] == "QB", "player_id"])
        rows: List[Tuple[str, float]] = []
        for _, m in ctx.matchups_df.iterrows():
            yards = 0.0
            for pid in m.starters:
                if pid in qb_ids:
                    gsis = ctx.sleeper_to_gsis.get(pid)
                    yards += float(pass_map.get(gsis, 0.0) or 0.0)
            rows.append((m.owner, yards))
        out = pd.DataFrame(rows, columns=["owner", "qb_pass_yd"]).sort_values("qb_pass_yd", ascending=False)
        top = out.qb_pass_yd.max()
        winners = out.loc[out["qb_pass_yd"] == top, "owner"].tolist()
        return f"Most QB passing yards: {self._tie_string(winners)} with {int(top)} yards"

    def wk13_smallest_margin(self, ctx: LoadedContext) -> str:
        margins: List[Tuple[str, str, float]] = []  # winner, loser, margin
        for mid, g in ctx.matchups_df.groupby("matchup_id"):
            if g.shape[0] == 2:
                g2 = g.sort_values("points", ascending=False)
                margin = float(g2.iloc[0].points) - float(g2.iloc[1].points)
                margins.append((g2.iloc[0].owner, g2.iloc[1].owner, margin))
        out = pd.DataFrame(margins, columns=["winner", "loser", "margin"]).sort_values("margin")
        best = out.iloc[0]
        ties = out.loc[out["margin"] == best["margin"]]
        if len(ties) == 1:
            return f"Smallest margin: {best['winner']} over {best['loser']} by {best['margin']:.2f}"
        else:
            winners = ", ".join(ties["winner"].tolist())
            losers = ", ".join(ties["loser"].tolist())
            return f"Smallest margin (tie): {winners} over {losers} by {best['margin']:.2f}"

    # ----------- runner -----------
    def run(self, week: int, season: Optional[int] = None, projections: Optional[str] = None, rolling_n: int = 3) -> str:
        ctx = self.load_context(week=week, season=season)

        # Configure projections provider if requested
        if projections:
            if projections == "sleeper":
                self.projections_provider = SleeperProjectionsProvider()
            elif projections == "rolling":
                self.projections_provider = RollingAverageProjectionsProvider(self.stats_provider, ctx.sleeper_to_gsis, n=rolling_n)
            else:
                raise ValueError("Unsupported projections provider. Use 'sleeper' or 'rolling'.")

        week_strategies = {
            1: self.wk1_highest_team_score,
            2: self.wk2_most_offensive_tds,
            3: self.wk3_most_wr_receptions,
            4: self.wk4_closest_to_21_single,
            5: self.wk5_most_points_in_loss,
            6: self.wk6_biggest_margin,
            7: self.wk7_most_rb_rush_yds,
            8: self.wk8_closest_to_projection,
            9: self.wk9_lowest_winning_score,
            10: self.wk10_highest_flex,
            11: self.wk11_closest_to_30_single,
            12: self.wk12_most_qb_pass_yds,
            13: self.wk13_smallest_margin,
        }

        fn = week_strategies.get(int(week))
        if not fn:
            raise ValueError(f"No challenge defined for week {week}")
        return fn(ctx)


# ---------------------------
# CLI
# ---------------------------

def main():
    p = argparse.ArgumentParser(description="Sleeper Weekly Challenge Engine")
    p.add_argument("--league_id", required=True, help="Sleeper league ID")
    p.add_argument("--week", type=int, required=True, help="NFL regular season week number (1-18)")
    p.add_argument("--season", type=int, default=None, help="Season (defaults to current from Sleeper state)")
    p.add_argument("--projections", choices=["sleeper", "rolling"], default=None, help="Projection provider for week 8 or other projection-based challenges")
    p.add_argument("--rolling_n", type=int, default=3, help="N for rolling-average projections when --projections rolling")
    args = p.parse_args()

    engine = ChallengeEngine(league_id=args.league_id)
    try:
        msg = engine.run(week=args.week, season=args.season, projections=args.projections, rolling_n=args.rolling_n)
        print(msg)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
