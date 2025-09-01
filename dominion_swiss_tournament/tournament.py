import json
import logging
import pickle

import numpy as np
import pandas as pd
from math import comb

from dominion_swiss_tournament.graph_utils import build_player_graph, compute_pairings, assign_tables, \
    compute_bye_player
from dominion_swiss_tournament.player import Player


def create_from_data(path: str) -> "Tournament":
    assert path.endswith(".pkl")
    with open(path, "rb") as f:
        data = pickle.load(f)
        tournament = Tournament(num_tables=len(data["tables"]), save_path=path)
        tournament.pairings = data["pairings"]
        tournament.players = data["players"]
        tournament.tables = data["tables"]
        tournament.current_round = data["current_round"]
        tournament.recompute_leaderboard()
    return tournament


class Tournament:
    def __init__(self, num_tables, save_path: str):
        self.players = {}
        self.current_round = 0
        self.tables = [i + 1 for i in range(num_tables)]
        self.pairings = pd.DataFrame(columns=["round", "table", "player1", "player2", "score1", "score2"])
        self.leaderboard = None
        self.recompute_leaderboard()
        self.save_path = save_path

    def export(self):
        to_save = {
            "pairings": self.pairings,
            "players": self.players,
            "tables": self.tables,
            "current_round": self.current_round
        }
        assert self.save_path.endswith(".pkl"), "Path must end with .pkl"
        with open(self.save_path, "wb") as f:
            pickle.dump(to_save, f)
        logging.info(f"Saved current tournament data to {self.save_path}")

    def add_players(self, players: list[str]):
        # check that there are enough tables
        if len(self.tables) < (len(players) + len(self.players)) // 2:
            raise ValueError(
                f"Not enough tables for this amount of players: {len(self.tables)} tables for {(len(players) + len(self.players))} players")
        for player in players:
            # generate a unique player ID
            player_id = len(self.players) + 1
            player_obj = Player(player_id, player)
            self.players[player_id] = player_obj
        logging.info(f"Added {len(players)} players to the tournament.")

    def generate_new_round(self) -> pd.DataFrame:
        if len(self.players) % 2 == 1:
            # one player has to receive a bye
            bye_player_id = compute_bye_player(self.players, self.pairings)
            current_round_players = {key: value for key, value in self.players.items() if key != bye_player_id}
            # use -1 for a NaN player to keep the col as full integers, same for tables
            new_row = {"player1": bye_player_id, "player2": -1, "score1": 1, "score2": 0,
                       "round": self.current_round + 1,
                       "table": -1}
            logging.info(f"Player {self.players[bye_player_id]} received a bye.")
        else:
            current_round_players = self.players
            new_row = None
        G = build_player_graph(current_round_players, self.pairings)
        pairings = compute_pairings(G, current_round_players, self.pairings)
        pairings = assign_tables(pairings, self.players, self.pairings, self.tables)
        # if bye player, add a pairing line that this player plays against a NaN player
        if new_row is not None:
            pairings = pd.concat([pairings, pd.DataFrame([new_row])], ignore_index=True)
        # add round number and table to pairings
        pairings["round"] = self.current_round + 1
        self.pairings = pd.concat([self.pairings, pairings], ignore_index=True)
        # update round
        self.current_round += 1
        logging.info(f"Created new round with {len(pairings)} pairings.")
        # save current state
        self.export()
        return pairings  # return new pairings

    def delete_last_round(self) -> bool:
        if self.current_round == 1:
            logging.error("Cannot delete round 1.")
            return False
        # remove all pairings from the last round
        self.pairings = self.pairings[self.pairings["round"] < self.current_round]
        self.current_round -= 1
        self.recompute_leaderboard()
        return True

    def upload_result(self, table, score1, score2):
        # boolean mask for the match
        mask = (self.pairings["table"] == table) & (self.pairings["round"] == self.current_round)

        if not mask.any():
            logging.error(f"No pairings found for table {table} in round {self.current_round}.")
            return

        # Ensure exactly one match is found
        idx = self.pairings.index[mask]
        if len(idx) != 1:
            logging.error(f"Expected exactly one pairing for table {table}, found {len(idx)}.")
            return

        # Update directly in the original DataFrame
        self.pairings.loc[idx, "score1"] = score1
        self.pairings.loc[idx, "score2"] = score2

        logging.info(f"Results uploaded for table {table} in round {self.current_round}.")

    def all_pairings_submitted(self):
        current_pairings = self.pairings[self.pairings["round"] == self.current_round]
        return not (current_pairings["score1"].isnull().any() or current_pairings["score2"].isnull().any())

    def close_round(self) -> bool:
        # check if all pairings have scores
        if not self.all_pairings_submitted():
            logging.error("Not all pairings have scores. Cannot close round.")
            return False
        self.recompute_leaderboard()
        logging.info(f"Round {self.current_round} closed.")
        return True

    def recompute_leaderboard(self):
        def add_direct_encounter_score(leaderboard: pd.DataFrame, pairings: pd.DataFrame) -> pd.DataFrame:
            """
            Adds 'direct_encounter_score' to the leaderboard.

            For each tie group (same score, buchholz_score_cut1, buchholz_score):
              - Check if the players in that group all played each other exactly once.
                (i.e., number of games among group members == nC2)
              - If yes: compute each player's sum of points from only those intra-group games.
              - If not: set 0 for everyone in that group.
            """
            # Ensure we don't mutate the original
            lb = leaderboard.copy()
            lb["direct_encounter_score"] = 0.0

            # Helper to compute per-group direct-encounter scores
            def compute_group(df_group: pd.DataFrame) -> pd.Series:
                player_ids = set(df_group["player_id"].tolist())
                n = len(player_ids)
                if n < 2:
                    return pd.Series(0.0, index=df_group.index)

                # Games strictly within the group
                intra = pairings[
                    (pairings["player1"].isin(player_ids)) & (pairings["player2"].isin(player_ids)) & (
                        ~pairings["score1"].isnull())
                    ].copy()

                expected_games = comb(n, 2)
                if len(intra) != expected_games:
                    return pd.Series(0.0, index=df_group.index)

                # Long scores
                a = intra.rename(columns={"player1": "player_id", "score1": "score"})[["player_id", "score"]]
                b = intra.rename(columns={"player2": "player_id", "score2": "score"})[["player_id", "score"]]
                long_scores = pd.concat([a, b], ignore_index=True)

                sums = long_scores.groupby("player_id")["score"].sum()

                return df_group["player_id"].map(sums).fillna(0.0)

            if sum(~pairings["score1"].isnull()) == 0:
                # no matches played yet, return empty leaderboard
                return lb
            # Apply per tie-group
            group_cols = ["score", "buchholz_score_cut1", "buchholz_score"]
            lb["direct_encounter_score"] = (
                lb.groupby(group_cols, group_keys=False)
                .apply(compute_group, include_groups=False)
            )

            return lb

        def add_number_of_wins(leaderboard: pd.DataFrame, pairings: pd.DataFrame) -> pd.DataFrame:
            """
            Adds 'number_of_wins' to the leaderboard:
              - A win is defined as score == 1.
            """
            # Long format of all results
            a = pairings.rename(columns={"player1": "player_id", "score1": "score"})[["player_id", "score"]]
            b = pairings.rename(columns={"player2": "player_id", "score2": "score"})[["player_id", "score"]]
            long_scores = pd.concat([a, b], ignore_index=True)

            # Count wins per player
            wins = (long_scores["score"] == 1).groupby(long_scores["player_id"]).sum()

            # Map into leaderboard
            leaderboard = leaderboard.copy()
            leaderboard["number_of_wins"] = leaderboard["player_id"].map(wins).fillna(0).astype(int)

            return leaderboard

        def add_number_of_wins_as_player2(leaderboard: pd.DataFrame, pairings: pd.DataFrame) -> pd.DataFrame:
            """
            Adds 'number_of_wins_as_player2' to the leaderboard:
              - A win is defined as score2 == 1 (only when the player was player2).
            """
            # Take only player2 side
            p2 = pairings.rename(columns={"player2": "player_id", "score2": "score"})[["player_id", "score"]]

            # Count wins as player2
            wins_p2 = (p2["score"] == 1).groupby(p2["player_id"]).sum()

            # Map into leaderboard
            leaderboard = leaderboard.copy()
            leaderboard["number_of_wins_as_player2"] = leaderboard["player_id"].map(wins_p2).fillna(0).astype(int)

            return leaderboard

        def add_number_of_games_as_player2(leaderboard: pd.DataFrame, pairings: pd.DataFrame) -> pd.DataFrame:
            """
            Adds 'number_of_games_as_player2' to the leaderboard:
              - Counts every game where the player was in the player2 column.
            """
            # Count appearances as player2
            games_p2 = pairings["player2"].value_counts()

            # Map into leaderboard
            leaderboard = leaderboard.copy()
            leaderboard["number_of_games_as_player2"] = leaderboard["player_id"].map(games_p2).fillna(0).astype(int)

            return leaderboard

        self.leaderboard = {"player_id": [], "player_name": [], "score": [], "buchholz_score_cut1": [],
                            "buchholz_score": []}
        for player_id, player in self.players.items():
            self.leaderboard["player_id"].append(player_id)
            self.leaderboard["player_name"].append(player.player_name)
            self.leaderboard["score"].append(player.score(self.pairings))
            self.leaderboard["buchholz_score"].append(player.buchholz_score(self.pairings, self.players, mode="normal"))
            self.leaderboard["buchholz_score_cut1"].append(
                player.buchholz_score(self.pairings, self.players, mode="cut1"))
        self.leaderboard = pd.DataFrame(self.leaderboard)
        # get direct encounters:
        self.leaderboard = add_direct_encounter_score(self.leaderboard, self.pairings)
        self.leaderboard = add_number_of_wins(self.leaderboard, self.pairings)
        self.leaderboard = add_number_of_wins_as_player2(self.leaderboard, self.pairings)
        self.leaderboard = add_number_of_games_as_player2(self.leaderboard, self.pairings)

        # sort descending of score
        self.leaderboard = (
            self.leaderboard
            .sort_values(
                by=["score", "buchholz_score_cut1", "buchholz_score", "direct_encounter_score", "number_of_wins",
                    "number_of_wins_as_player2", "number_of_games_as_player2"],
                ascending=[False] * 7,  # all descending
                inplace=False
            )
            .reset_index(drop=True)
        )  # add rank column starting with 1
        self.leaderboard["rank"] = self.leaderboard.index + 1
        logging.info("Recomputed leaderboard.")
        logging.debug(self.leaderboard.to_string())
