# %%
import requests
import pandas as pd
from sleeper_wrapper import League

league_id = str(1120567286148091904)
league = League(league_id)

nfl_state = requests.get("https://api.sleeper.app/v1/state/nfl").json()
season = nfl_state["season"]
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
week=str(input("what week of the season are you looking for?"))
print(f"Looking at {season} Week {week}")
# %%
matchups = league.get_matchups(week)
users = league.get_users()
rosters = league.get_rosters()
board = league.get_scoreboards(rosters, matchups, users, score_type="pts_ppr", week=week, season=season)
matchups = pd.DataFrame(matchups)
users = pd.DataFrame(users)
users["owner"] = [user2owner[u] for u in users.display_name.unique()]
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
# elif week == "2":



# week 3 - most WR receptions
# elif week == "3":



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
# elif week == "5":
    # can be done via sleeper weekly report

# week 6 - biggest margin of victory
    # can be done via sleeper weekly report

# week 7 - most RB rushing yards
# elif week == "7":



# week 8 - closet to projected points
# elif week == "8":
    # can be done via sleeper weekly report

# week 9 - lowest score in a win
# elif week == "9":
    # can be done via sleeper weekly report

# week 10 - highest flex score
# elif week == "10":



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
    win_val = to_30_df.dist_to_21.iloc[0]
    winners = to_30_df.query("dist_to_21 == @win_val")
    if winners.shape[0] == 1:
        winner = to_30_df.iloc[0]
        winner_string = f"The player closest to 21 this week was {winner.full_name} with {winner.score} points; {winner.dist_to_21} away from 21.\n{winner.owner} wins the contest"
    elif winners.shape[0] > 1:
        winner_string = f"The winners are {', '.join(list(winners.owner))}; who had {', '.join(list(winners.full_name))} score {', '.join(list(winners.score))} respectively."
    print(winner_string)

# week 12 - most QB passing yards
# elif week == "12":



# week 13 - smallest margin of victory
# elif week == "13":
    # can be done via sleeper weekly report

