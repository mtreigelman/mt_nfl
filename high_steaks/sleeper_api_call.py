# -*- coding: utf-8 -*-
#%% Import libraries
import requests
import pandas as pd

print(
    "Now running the script to create the keepers page for the High Steaks Fantasy Fooball League..."
)
#%% load in draft histories
draft_hist = pd.read_csv(
    "draft_histories.csv",
    dtype={
        "draft_year": "int",
        "draft_id": "string",
        "league_name": "string",
        "league_id": "string",
    },
)
league_name = "High Steaks"
draft_year = int(input("What year was the draft?\n"))
draft_id = draft_hist.query(
    "league_name == @league_name and draft_year == @draft_year"
).draft_id.values[0]
league_id = draft_hist.query(
    "league_name == @league_name and draft_year == @draft_year"
).league_id.values[0]

#%% get specified draft data
url = f"http://api.sleeper.app/v1/draft/{draft_id}/picks"
parsed_json = requests.get(url).json()

pick_data = []
for p in parsed_json:
    metadata = p["metadata"]
    alldata = p | metadata
    del alldata["metadata"]
    pick_data.append(alldata)

draft = pd.DataFrame(pick_data)
keep_cols = [
    "Player",
    "position",
    "team",
    "round",
    "draft_slot",
    "is_keeper",
    "picked_by",
    "player_id",
]
draft["Player"] = draft.first_name + " " + draft.last_name
draft = draft[keep_cols]
new_col_names = {
    col: " ".join([c.capitalize() for c in col.split("_")]) for col in keep_cols
}
draft = draft.rename(columns=new_col_names)

#%% bring in owner names
url = f"http://api.sleeper.app/v1/league/{league_id}/users"
parsed_json = requests.get(url).json()

user_data = []
for p in parsed_json:
    metadata = p["metadata"]
    alldata = p | metadata
    del alldata["metadata"]
    user_data.append(alldata)

owners = pd.DataFrame(user_data)
keep_cols = [
    "Picked By",
    "Owner",
]
owners = owners.rename(columns={"user_id": "Picked By"})

#%%
user_to_name = {
    "mtreigelman": "Mike",
    "chuckinbombz": "Chuck",
    "CWirf": "Chris",
    "JsPassek": "Justin",
    "49erz":"Justin",  # 2019
    "phunt": "Pat",
    "DemSillyNanniez": "Eric",
    "DemHoodHomiez":"Eric",  # 2021
    "LovableLosers":"Eric",  # 2020
    "damonate": "Damon",
    "SteveMT1000": "Stephen",
    "PrinceOfEgypt": "Jono",
    "ByeNoGame": "David",
    "RhodesRhodes": "Rhodes",
    "gregtheprophet": "Greg",
}
owners["Owner"] = [user_to_name[x] for x in owners.display_name]
owners = owners[keep_cols]

#%% bringing in rosters
url = f"http://api.sleeper.app/v1/league/{league_id}/rosters"
parsed_json = requests.get(url).json()

org_rosters = pd.DataFrame(parsed_json)
org_rosters = org_rosters.rename(columns={"user_id": "owner_id"})

#%%
exploded = []
for i, r in org_rosters.iterrows():
    user_id = r.owner_id

    for player in r.players:
        exploded.append([player, user_id])

rosters = pd.DataFrame(exploded, columns=["Player Id", "Picked By"])
rosters = rosters.merge(owners, on=["Picked By"], how="left")
del rosters["Picked By"]

#%% bringing in non-drafted players
url = f"http://api.sleeper.app/v1/players/nfl"
parsed_json = requests.get(url).json()

raw_players = pd.DataFrame(parsed_json)
player_data = []
for pid in raw_players.columns:
    p = raw_players[pid]
    name = p.first_name + " " + p.last_name
    pos = p.position
    team = p.team_abbr
    player_data.append([pid, name, pos, team])

players = pd.DataFrame(player_data, columns=["Player Id", "Player", "Position", "Team"])

#%% merge draft results with owners
draft = draft.merge(owners, on=["Picked By"], how="left")
del draft["Picked By"]
draft = draft.rename(
    columns={
        "display_name": "User Name",
        "team_name": "Team Name",
        "Owner": "Picked By",
        "Is Keeper": "Keeper",
    }
)
draft = draft.merge(rosters, on=["Player Id"], how="left")
roster_cols = [
    "Player Id",
    "Round",
    "Draft Slot",
]
rosters = rosters.merge(draft[roster_cols], on=["Player Id"], how="left")
rosters = rosters.merge(players, on=["Player Id"], how="left")
del draft["Player Id"]
del rosters["Player Id"]

#%% Saving Results
draft.to_csv(f"{draft_year}_high_steaks_draft_results.csv", index=False)
rosters = rosters.sort_values(["Owner", "Position"])[
    ["Owner", "Position", "Player", "Round", "Draft Slot"]
]
rosters.to_csv(f"{draft_year}_high_steaks_final_rosters.csv", index=False)

print("Two files saved.")
print(f"draft_results/{draft_year}_high_steaks_draft_results.csv")
print(f"draft_results/{draft_year}_high_steaks_final_rosters.csv")
#%% End of script
