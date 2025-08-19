import logging

import numpy as np
import pandas as pd

from dominion_swiss_tournament.graph_utils import build_player_graph, compute_pairings, assign_tables, \
    compute_bye_player
from dominion_swiss_tournament.player import Player


class Tournament:
    def __init__(self, num_tables):
        self.players = {}
        self.current_round = 0
        self.tables = [i + 1 for i in range(num_tables)]
        self.pairings = pd.DataFrame(columns=["round", "table", "player1", "player2", "score1", "score2"])
        self.leaderboard = None
        self.recompute_leaderboard()

    def add_players(self, players: list[str]):
        for player in players:
            # generate a unique player ID
            player_id = len(self.players) + 1
            player_obj = Player(player_id, player)
            self.players[player_id] = player_obj
        logging.info(f"Added {len(players)} players to the tournament.")

    def generate_new_round(self) -> pd.DataFrame:
        self.current_round += 1
        if len(self.players) % 2 == 1:
            # one player has to receive a bye
            bye_player_id = compute_bye_player(self.players, self.pairings)
            current_round_players = {key: value for key, value in self.players.items() if key != bye_player_id}
            # use -1 for a NaN player to keep the col as full integers, same for tables
            new_row = {"player1": bye_player_id, "player2": -1, "score1": 1, "score2": 0, "round": self.current_round,
                       "table": -1}
            logging.info(f"Player {self.players[bye_player_id]} received a bye.")
        else:
            current_round_players = self.players
            new_row = None
        G = build_player_graph(current_round_players, self.pairings)
        pairings = compute_pairings(G, current_round_players, self.pairings)
        pairings = assign_tables(pairings, self.tables)
        # if bye player, add a pairing line that this player plays against a NaN player
        if new_row is not None:
            pairings = pd.concat([pairings, pd.DataFrame([new_row])], ignore_index=True)
        # add round number and table to pairings
        pairings["round"] = self.current_round
        self.pairings = pd.concat([self.pairings, pairings], ignore_index=True)
        logging.info(f"Created new round with {len(pairings)} pairings.")
        return pairings  # return new pairings

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


    def close_round(self):
        # check if all pairings have scores
        current_pairings = self.pairings[self.pairings["round"] == self.current_round]
        if current_pairings["score1"].isnull().any() or current_pairings["score2"].isnull().any():
            logging.error("Not all pairings have scores. Cannot close round.")
            return
        # update player local pairings history
        for player_id in self.players:
            player = self.players[player_id]
            player_pairings = current_pairings[
                (current_pairings["player1"] == player_id) | (current_pairings["player2"] == player_id)]
            if not player_pairings.empty:
                player.pairings_history = pd.concat([player.pairings_history, player_pairings], ignore_index=True)
        self.recompute_leaderboard()
        # increment the round number
        logging.info(f"Round {self.current_round} closed.")

    def recompute_leaderboard(self):
        self.leaderboard = {"player_id": [], "player_name": [], "score": []}
        for player_id, player in self.players.items():
            self.leaderboard["player_id"].append(player_id)
            self.leaderboard["player_name"].append(player.player_name)
            self.leaderboard["score"].append(player.score(self.pairings))
        self.leaderboard = pd.DataFrame(self.leaderboard)
        # sort descending of score
        self.leaderboard = self.leaderboard.sort_values("score", ascending=False, inplace=False).reset_index(drop=True)
        # add rank column starting with 1
        self.leaderboard["rank"] = self.leaderboard.index + 1
        logging.info("Recomputed leaderboard.")
