# -*- coding: utf-8 -*-
#%% Import libraries
import sys 
import requests
import pandas as pd
import argparse

# %%
class KeeperValueDecider:
    def __init__(
        self,
        league_id: str,
        draft_id: str,
        league_name: str,
        year: int,
        file_location: str, 
    ):
        self.league_id = str(league_id)
        self.draft_id = draft_id
        self.league_name = league_name
        self.year = year
        self.keep_cols = [
            "Player",
            "position",
            "team",
            "round",
            "draft_slot",
            "is_keeper",
            "picked_by",
            "player_id",
        ]
        if file_location:
            self.results_location = f"{file_location}/{self.league_name}_{self.year}_Keeper_Sheet.xlsx"
        else:
            self.results_location = f"{self.league_name}_{self.year}_Keeper_Sheet.xlsx"
        return 
    
    def get_draft_data(self) -> pd.DataFrame:
        draft_url = f"http://api.sleeper.app/v1/draft/{self.draft_id}/picks"
        parsed_json = requests.get(draft_url).json()

        pick_data = []
        for p in parsed_json:
            metadata = p["metadata"]
            alldata = p | metadata
            del alldata["metadata"]
            pick_data.append(alldata)

        draft = pd.DataFrame(pick_data)
        draft["Player"] = draft.first_name + " " + draft.last_name
        draft = draft[self.keep_cols]
        new_col_names = {
            col: " ".join([c.capitalize() for c in col.split("_")]) for col in self.keep_cols
        }
        draft = draft.rename(columns=new_col_names)
        return self.draft
    
    def get_user_data(self) -> pd.DataFrame:
        user_url = f"http://api.sleeper.app/v1/league/{self.league_id}/users"
        parsed_json = requests.get(user_url).json()

        user_data = []
        for p in parsed_json:
            metadata = p["metadata"]
            alldata = p | metadata
            del alldata["metadata"]
            user_data.append(alldata)

        owners = pd.DataFrame(user_data)
        self.owners = owners.rename(columns={"user_id": "picked_by"})
        return self.owners
    
    def get_rosters(self) -> pd.DataFrame:
        # bringing in rosters
        roster_url = f"http://api.sleeper.app/v1/league/{self.league_id}/rosters"
        parsed_json = requests.get(roster_url).json()

        org_rosters = pd.DataFrame(parsed_json)
        org_rosters = org_rosters.rename(columns={"user_id": "owner_id"})

        exploded = []
        for i, r in org_rosters.iterrows():
            user_id = r.owner_id

            for player in r.players:
                exploded.append([player, user_id])

        rosters = pd.DataFrame(exploded, columns=["Player Id", "Picked By"])
        rosters = rosters.merge(self.owners, on=["Picked By"], how="left")
        del rosters["Picked By"]
        self.rosters = rosters
        return self.rosters
    
    def get_undrafted_players(self) -> pd.DataFrame:
        # bringing in non-drafted players
        players_url = f"http://api.sleeper.app/v1/players/nfl"
        parsed_json = requests.get(players_url).json()

        raw_players = pd.DataFrame(parsed_json)
        player_data = []
        for pid in raw_players.columns:
            p = raw_players[pid]
            name = p.first_name + " " + p.last_name
            pos = p.position
            team = p.team_abbr
            player_data.append([pid, name, pos, team])

        self.players = pd.DataFrame(player_data, columns=["Player Id", "Player", "Position", "Team"])
        return self.players
    
    def run(self,):
        print(
            "Now running the script to create the keepers page for a Sleeper Fantasy Football League..."
        )
        draft_df = self.get_draft_data()
        users_df = self.get_user_data()
        rosters_df = self.get_rosters()
        players_df = self.get_undrafted_players()

        # merge draft results with owners
        draft_df = draft_df.merge(users_df, on=["Picked By"], how="left")
        del draft_df["Picked By"]
        draft_df = draft_df.rename(
            columns={
                "display_name": "User Name",
                "team_name": "Team Name",
                "Owner": "Picked By",
                "Is Keeper": "Keeper",
            }
        )
        draft_df = draft_df.merge(rosters_df, on=["Player Id"], how="left")
        draft_df["Keeper"] = draft_df["Keeper"] == True 
        roster_cols = [
            "Player Id",
            "Round",
            "Draft Slot",
            "Keeper",
        ]
        rosters_df = rosters_df.merge(draft_df[roster_cols], on=["Player Id"], how="left")
        rosters_df = rosters_df.merge(players_df, on=["Player Id"], how="left")
        rosters_df["Last Year's Keeper"] = rosters_df["Keeper"] == True 
        rosters_df = rosters_df.sort_values(["Owner", "Position"])[
            ["Owner", "Position", "Player", "Round", "Draft Slot", "Last Year's Keeper"]
        ]
        del draft_df["Player Id"]

        with pd.ExcelWriter(self.results_location, engine='xlsxwriter') as writer:
            draft_df.to_excel(writer, sheet_name=f"{self.year - 1} Draft", index=False)
            rosters_df.to_excel(writer, sheet_name=f"{self.year - 1} Final Rosters", index=False)

        return print(f"File Saved to: `{self.results_location}`")

# %%
# ---------------------------
# CLI
# ---------------------------

def main():
    p = argparse.ArgumentParser(description="Creating Sleeper Values Based off Draft Position")
    p.add_argument("--league_id", type=str, required=True, help="Sleeper league ID")
    p.add_argument("--draft_id", type=str, required=True, help="Draft ID to base keeper values off of")
    p.add_argument("--league_name", type=str, default=None, help="Used to name results file")
    p.add_argument("--year", type=int, default=None, help="Used to name results file; should be current/upcoming year")
    p.add_argument("--file_location", type=str, default=None, help="Directory location for final results file")
    args = p.parse_args()

    engine = KeeperValueDecider(league_id=args.league_id, draft_id=args.draft_id, league_name=args.league_name, year=args.year, file_location=args.file_location)
    try:
        msg = engine.run()
        print(msg)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
#%% End of script