# %%
import requests
import pandas as pd
from sleeper_wrapper import League

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
    # fetch weekly player stats (Sleeper)
    # example URL pattern (documented by API clients around Sleeper’s stats endpoint)
    stats = requests.get(
        f"https://api.sleeper.com/stats/nfl/regular/{season}/{week}"
    ).json()

    # normalize into {player_id: stats_dict}
    stats_by_pid = {row["player_id"]: row for row in stats if "player_id" in row}

    rows = []
    for _, m in matchups.iterrows():
        td_sum = 0
        for pid in m.starters:
            s = stats_by_pid.get(pid, {})
            td_sum += s.get("rushing_td", 0) + s.get("receiving_td", 0) + s.get("passing_td", 0)
        rows.append((m.owner, td_sum))
    out = pd.DataFrame(rows, columns=["owner","off_td"]).sort_values("off_td", ascending=False)
    top = out.off_td.max()
    winners = out.query("off_td == @top")
    winner_string = f"Most offensive TDs: {', '.join(winners.owner)} with {top} TDs"
    print(winner_string)

# week 3 - most WR receptions
elif week == "3":
    # weekly stats as above
    stats = requests.get(
        f"https://api.sleeper.com/stats/nfl/regular/{season}/{week}"
    ).json()
    stats_by_pid = {row["player_id"]: row for row in stats if "player_id" in row}

    # which starters are WRs?
    wr_ids = set(players_df.query("position == 'WR'")["player_id"])
    rows = []
    for _, m in matchups.iterrows():
        recs = 0
        for pid in m.starters:
            if pid in wr_ids:
                recs += stats_by_pid.get(pid, {}).get("receptions", 0)
        rows.append((m.owner, recs))
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
    stats = requests.get(
        f"https://api.sleeper.com/stats/nfl/regular/{season}/{week}"
    ).json()
    stats_by_pid = {row["player_id"]: row for row in stats if "player_id" in row}

    rb_ids = set(players_df.query("position == 'RB'")["player_id"])
    rows = []
    for _, m in matchups.iterrows():
        rush_yd = 0
        for pid in m.starters:
            if pid in rb_ids:
                rush_yd += stats_by_pid.get(pid, {}).get("rushing_yd", 0)
        rows.append((m.owner, rush_yd))
    out = pd.DataFrame(rows, columns=["owner","rb_rush_yd"]).sort_values("rb_rush_yd", ascending=False)
    top = out.rb_rush_yd.max()
    winners = out.query("rb_rush_yd == @top")
    print(f"Most RB rushing yards: {', '.join(winners.owner)} with {int(top)} yards")

# week 8 - closet to projected points
elif week == "8":
    # can be done via sleeper weekly report
    # get projections for all players for this season, grouped by week
    # (documented player projections endpoint with ?grouping=week)
    # NOTE: we only need this week, so we’ll cache per player_id
    def proj_for(pid):
        url = f"https://api.sleeper.com/projections/nfl/player/{pid}?season={season}&season_type=regular&grouping=week"
        try:
            arr = requests.get(url).json()
            # find this week’s projection (handle arr being list or dict-like)
            for r in arr:
                if str(r.get("week")) == str(week):
                    return r.get("pts_ppr") or r.get("pts_half_ppr") or r.get("pts_std")
        except Exception:
            return None
        return None

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
    stats = requests.get(
        f"https://api.sleeper.com/stats/nfl/regular/{season}/{week}"
    ).json()
    stats_by_pid = {row["player_id"]: row for row in stats if "player_id" in row}
    qb_ids = set(players_df.query("position == 'QB'")["player_id"])
    rows = []
    for _, m in matchups.iterrows():
        pass_yd = 0
        for pid in m.starters:
            if pid in qb_ids:
                pass_yd += stats_by_pid.get(pid, {}).get("passing_yd", 0)
        rows.append((m.owner, pass_yd))
    out = pd.DataFrame(rows, columns=["owner","qb_pass_yd"]).sort_values("qb_pass_yd", ascending=False)
    top = out.qb_pass_yd.max()
    winners = out.query("qb_pass_yd == @top")
    print(f"Most QB passing yards: {', '.join(winners.owner)} with {int(top)} yards")




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
