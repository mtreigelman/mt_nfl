# %%
import requests
import pandas as pd
from sleeper_wrapper import League
import nfl_data_py as nfl
from functools import lru_cache

@lru_cache(maxsize=None)
def sleeper_week_projection(sleeper_pid: str, season: int, week: int) -> float:
    url = f"https://api.sleeper.com/projections/nfl/player/{sleeper_pid}?season={season}&season_type=regular&grouping=week"
    data = requests.get(url, timeout=15).json()
    # find this week's projection; Sleeper projection objects commonly include pts_ppr/pts_half_ppr/pts_std
    for row in data or []:
        if str(row.get("week")) == str(week):
            return row.get("pts_ppr") or row.get("pts_half_ppr") or row.get("pts_std") or 0.0
    return 0.0


def get_weekly_stats_df(season: int, week: int) -> pd.DataFrame:
    # pull nflfastR weekly player stats
    cols = [
        "season","week","player_id","player_name","recent_team","position",
        "rushing_yards","rushing_tds","receiving_receptions","receiving_yards","receiving_tds",
        "passing_yards","passing_tds","interceptions"
    ]
    df = nfl.import_weekly_data([season])[cols]
    df = df[(df["week"] == int(week)) & (df["season"] == int(season))].copy()
    # player_id here is GSIS id; keep types consistent
    return df

league_id = str(1120567286148091904)
league = League(league_id)

nfl_state = requests.get("https://api.sleeper.app/v1/state/nfl").json()
# season = nfl_state["season"]
season = 2024
week = nfl_state["week"]
user2owner = {
    "mtreigelman":"Reigelman",
    "Tophinator":"Christoph",
    "TheRodfather10":"Tony", 
    "Mdduff":"Duffy", 
    "danderson28":"Daniel",
    "WillDiesel":"Will", 
    "RhodesRhodes":"Rhodes",
    "gretemeyer":"Geoff",
    "steviemorgan":"Stevie",
    "msassman33":"Sassman",
    "bobm18":"Bobby",
    "jide49":"Jide",
}
# week=str(input("what week of the season are you looking for?"))
week=2
print(f"Looking at {season} Week {week}")
# %%
matchups = league.get_matchups(week)
users = league.get_users()
rosters = league.get_rosters()
board = league.get_scoreboards(rosters, matchups, users, score_type="pts_ppr", week=week, season=season)
matchups = pd.DataFrame(matchups)
users = pd.DataFrame(users)
# users["owner"] = [user2owner[u] for u in users.display_name.unique()]
users["owner"] = users["display_name"].map(user2owner)
rosters = pd.DataFrame(rosters)
rosters = rosters.rename(columns={"owner_id":"user_id"})
rosters = rosters.merge(users[["user_id","owner","display_name"]], on=["user_id"])
matchups = matchups.merge(rosters[["roster_id", "user_id","owner","display_name"]], on=["roster_id"])

# expand your players_df fields to include id mappings
players_df = pd.DataFrame(requests.get("https://api.sleeper.app/v1/players/nfl").json()).T
players_df = players_df[
    ["player_id","full_name","position","first_name","last_name","gsis_id","espn_id","yahoo_id"]
].copy()

# build a Sleeper->GSIS map (some may be null; handle gracefully)
sleeper_to_gsis = players_df.set_index("player_id")["gsis_id"].to_dict()

# %%
players_url = f"http://api.sleeper.app/v1/players/nfl"
parsed_json = requests.get(players_url).json()
players_df = pd.DataFrame(parsed_json).T
players_df = players_df[["player_id", "first_name", "last_name", "fantasy_positions", "full_name", "position"]]

# %%
# week 1 - highest point scorer of the week
if week == "1":
    max_idx = matchups.points.idxmax()
    winner_string = f"The high point scorer this week was: {matchups.owner[max_idx]} with {matchups.points[max_idx]} points"
    print(winner_string)

# week 2 - most offensive touchdowns
elif week == "2":
    stats_w = get_weekly_stats_df(int(season), int(week))
    # build a quick look-up: gsis_id -> total offensive TDs (rush + rec + pass)
    stats_w["off_td"] = stats_w["rushing_tds"].fillna(0) + stats_w["receiving_tds"].fillna(0) + stats_w["passing_tds"].fillna(0)
    td_map = stats_w.set_index("player_id")["off_td"].to_dict()

    rows = []
    for _, m in matchups.iterrows():
        total = 0
        for pid in m.starters:
            gsis = sleeper_to_gsis.get(pid)
            total += td_map.get(gsis, 0)
        rows.append((m.owner, int(total)))
    out = pd.DataFrame(rows, columns=["owner","off_td"]).sort_values("off_td", ascending=False)
    top = out.off_td.max()
    winners = out.query("off_td == @top")
    print(f"Most offensive TDs: {', '.join(winners.owner)} with {top} TDs")

# week 3 - most WR receptions
elif week == "3":
    stats_w = get_weekly_stats_df(int(season), int(week))
    rec_map = stats_w.set_index("player_id")["receiving_receptions"].fillna(0).to_dict()

    # set of WRs by Sleeper (your roster eligibility)
    wr_ids = set(players_df.loc[players_df["position"]=="WR","player_id"])
    rows = []
    for _, m in matchups.iterrows():
        recs = 0
        for pid in m.starters:
            if pid in wr_ids:
                gsis = sleeper_to_gsis.get(pid)
                recs += rec_map.get(gsis, 0)
        rows.append((m.owner, int(recs)))
    out = pd.DataFrame(rows, columns=["owner","wr_receptions"]).sort_values("wr_receptions", ascending=False)
    top = out.wr_receptions.max()
    winners = out.query("wr_receptions == @top")
    print(f"Most WR receptions: {', '.join(winners.owner)} with {top} receptions")

# week 4 - closest to 21 points
elif week == "4":
    to_21_list = []
    for i,m in matchups.iterrows():
        scorers = m.players_points
        for s in m.starters:
            dist_from_21 = min(abs(21 - scorers[s]), abs(scorers[s] - 21))
            player_name = players_df.query("player_id == @s").full_name[0]
            to_21_list.append([player_name, m.owner, scorers[s], dist_from_21])
    to_21_df = pd.DataFrame(to_21_list, columns=["full_name", "owner", "score", "dist_to_21"])
    to_21_df = to_21_df.sort_values("dist_to_21", ascending=True)
    win_val = to_21_df.dist_to_21.iloc[0]
    winners = to_21_df.query("dist_to_21 == @win_val")
    if winners.shape[0] == 1:
        winner = to_21_df.iloc[0]
        winner_string = f"The player closest to 21 this week was {winner.full_name} with {winner.score} points; {winner.dist_to_21} away from 21.\n{winner.owner} wins the contest"
    elif winners.shape[0] > 1:
        winner_string = f"The winners are {', '.join(list(winners.owner))}; who had {', '.join(list(winners.full_name))} score {', '.join(list(winners.score))} respectively."
    print(winner_string)

# week 5 - most points in a loss
elif week == "5":
    # can be done via sleeper weekly report
    pairs = matchups.groupby("matchup_id")
    losers = []
    for mid, g in pairs:
        if g.shape[0] == 2:
            g2 = g.sort_values("points", ascending=False)
            loser = g2.iloc[1]
            losers.append((loser.owner, loser.points))
    out = pd.DataFrame(losers, columns=["owner","points"]).sort_values("points", ascending=False)
    top = out.points.max()
    winners = out.query("points == @top")
    print(f"Most points in a loss: {', '.join(winners.owner)} with {top} pts")

# week 6 - biggest margin of victory
elif week == "6":
    # can be done via sleeper weekly report
    pairs = matchups.groupby("matchup_id")
    margins = []
    for mid, g in pairs:
        if g.shape[0] == 2:
            pts = g.sort_values("points", ascending=False)["points"].tolist()
            margins.append((g.iloc[g["points"].idxmax()].owner, pts[0]-pts[1]))
    out = pd.DataFrame(margins, columns=["winner","margin"]).sort_values("margin", ascending=False)
    top = out.margin.max()
    winners = out.query("margin == @top")
    print(f"Biggest margin of victory: {', '.join(winners.winner)} by {top:.2f}")

# week 7 - most RB rushing yards
elif week == "7":
    stats_w = get_weekly_stats_df(int(season), int(week))
    rush_map = stats_w.set_index("player_id")["rushing_yards"].fillna(0).to_dict()

    rb_ids = set(players_df.loc[players_df["position"]=="RB","player_id"])
    rows = []
    for _, m in matchups.iterrows():
        yards = 0
        for pid in m.starters:
            if pid in rb_ids:
                gsis = sleeper_to_gsis.get(pid)
                yards += rush_map.get(gsis, 0)
        rows.append((m.owner, int(yards)))
    out = pd.DataFrame(rows, columns=["owner","rb_rush_yd"]).sort_values("rb_rush_yd", ascending=False)
    top = out.rb_rush_yd.max()
    winners = out.query("rb_rush_yd == @top")
    print(f"Most RB rushing yards: {', '.join(winners.owner)} with {top} yards")

# week 8 - closet to projected points
elif week == "8":
    # can be done via sleeper weekly report
    rows = []
    for _, m in matchups.iterrows():
        proj_sum = 0.0
        act_sum  = 0.0
        for pid in m.starters:
            proj_sum += sleeper_week_projection(pid, int(season), int(week))
            act_sum  += m.players_points.get(pid, 0.0)
        rows.append((m.owner, proj_sum, act_sum, abs(act_sum - proj_sum)))
    out = pd.DataFrame(rows, columns=["owner","proj_pts","actual_pts","abs_diff"]).sort_values("abs_diff")
    best = out.iloc[0]
    print(f"Closest to projection: {best.owner} (proj {best.proj_pts:.2f}, actual {best.actual_pts:.2f}, |Δ|={best.abs_diff:.2f})")

    rows = []
    for _, m in matchups.iterrows():
        proj_sum, actual_sum = 0.0, 0.0
        for pid in m.starters:
            p = proj_for(pid) or 0.0
            proj_sum += p
            actual_sum += m.players_points.get(pid, 0.0)
        diff = abs(actual_sum - proj_sum)
        rows.append((m.owner, proj_sum, actual_sum, diff))
    out = pd.DataFrame(rows, columns=["owner","proj_pts","actual_pts","abs_diff"]).sort_values("abs_diff")
    best = out.iloc[0]
    print(f"Closest to projection: {best.owner} (proj {best.proj_pts:.2f}, actual {best.actual_pts:.2f}, |Δ|={best.abs_diff:.2f})")

# week 9 - lowest score in a win
elif week == "9":
    # can be done via sleeper weekly report
    pairs = matchups.groupby("matchup_id")
    winners = []
    for mid, g in pairs:
        if g.shape[0] == 2:
            w = g.loc[g.points.idxmax()]
            winners.append((w.owner, w.points))
    out = pd.DataFrame(winners, columns=["owner","points"]).sort_values("points")
    low = out.iloc[0]
    print(f"Lowest score in a win: {low.owner} with {low.points:.2f}")


# week 10 - highest flex score
elif week == "10":
    flex_positions = {"RB","WR","TE"}
    flex_ids = set(players_df[players_df["position"].isin(flex_positions)]["player_id"])
    rows = []
    for _, m in matchups.iterrows():
        best = 0.0
        best_name = None
        for pid in m.starters:
            if pid in flex_ids:
                pts = m.players_points.get(pid, 0.0)
                if pts > best:
                    best, best_name = pts, players_df.loc[players_df.player_id==pid,"full_name"].values[0]
        rows.append((m.owner, best_name, best))
    out = pd.DataFrame(rows, columns=["owner","player","points"]).sort_values("points", ascending=False)
    top = out.points.max()
    winners = out.query("points == @top")
    print(f"Highest FLEX score: {', '.join(winners.owner)} ({', '.join(winners.player)}) with {top:.2f}")



# week 11 - closest to 30 points
elif week == "11":
    to_30_list = []
    for i,m in matchups.iterrows():
        scorers = m.players_points
        for s in m.starters:
            dist_from_30 = abs(30 - scorers[s])
            player_name = players_df.query("player_id == @s").full_name[0]
            to_30_list.append([player_name, m.owner, scorers[s], dist_from_30])
    to_30_df = pd.DataFrame(to_30_list, columns=["full_name", "owner", "score", "dist_to_30"])
    to_30_df = to_30_df.sort_values("dist_to_30", ascending=True)
    win_val = to_30_df.dist_to_30.iloc[0]
    winners = to_30_df.query("dist_to_30 == @win_val")
    if winners.shape[0] == 1:
        winner = to_30_df.iloc[0]
        winner_string = f"The player closest to 30 this week was {winner.full_name} with {winner.score} points; {winner.dist_to_30} away from 21.\n{winner.owner} wins the contest"
    elif winners.shape[0] > 1:
        winner_string = f"The winners are {', '.join(list(winners.owner))}; who had {', '.join(list(winners.full_name))} score {', '.join(list(winners.score))} respectively."
    print(winner_string)

# week 12 - most QB passing yards
elif week == "12":
    stats_w = get_weekly_stats_df(int(season), int(week))
    pass_map = stats_w.set_index("player_id")["passing_yards"].fillna(0).to_dict()

    qb_ids = set(players_df.loc[players_df["position"]=="QB","player_id"])
    rows = []
    for _, m in matchups.iterrows():
        yards = 0
        for pid in m.starters:
            if pid in qb_ids:
                gsis = sleeper_to_gsis.get(pid)
                yards += pass_map.get(gsis, 0)
        rows.append((m.owner, int(yards)))
    out = pd.DataFrame(rows, columns=["owner","qb_pass_yd"]).sort_values("qb_pass_yd", ascending=False)
    top = out.qb_pass_yd.max()
    winners = out.query("qb_pass_yd == @top")
    print(f"Most QB passing yards: {', '.join(winners.owner)} with {top} yards")




# week 13 - smallest margin of victory
elif week == "13":
    # can be done via sleeper weekly report
    pairs = matchups.groupby("matchup_id")
    margins = []
    for mid, g in pairs:
        if g.shape[0] == 2:
            g2 = g.sort_values("points", ascending=False)
            margin = g2.iloc[0].points - g2.iloc[1].points
            margins.append((g2.iloc[0].owner, g2.iloc[1].owner, margin))
    out = pd.DataFrame(margins, columns=["winner","loser","margin"]).sort_values("margin")
    best = out.iloc[0]
    print(f"Smallest margin: {best.winner} over {best.loser} by {best.margin:.2f}")

    


# %%
