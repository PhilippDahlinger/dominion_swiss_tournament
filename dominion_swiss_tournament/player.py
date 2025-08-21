import pandas as pd


class Player:
    def __init__(self, player_id, player_name):
        self.player_id = player_id
        self.player_name = player_name

    def score(self, all_pairings) -> float:
        """Total score accumulated across rounds."""
        # Check if player was player1 or player2, and sum accordingly
        mask1 = all_pairings["player1"] == self.player_id
        mask2 = all_pairings["player2"] == self.player_id

        score_as_p1 = all_pairings.loc[mask1, "score1"].astype(float).sum()
        score_as_p2 = all_pairings.loc[mask2, "score2"].astype(float).sum()

        return float(score_as_p1 + score_as_p2)

    def buchholz_score(self, all_pairings, all_players, median=True):
        """
        Computes the sum of socres of all opponents played Used as a tiebreaker
        :param all_pairings:
        :param all_players:
        :param median If true, discard the best and the worst opponent from the computation
        :return:
        """
        opponents = self.past_opponents(all_pairings)
        if not opponents:
            return 0.0
        opponents_score = []
        for opp in opponents:
            opp_score = all_players[opp].score(all_pairings)
            if all_players[opp].received_bye(all_pairings):
                # if opponent received a bye, their score for buchholz is 0.5 lower (bye counts 0.5 for buchholz, but 1.0 for score)
                opp_score -= 0.5
            opponents_score.append(opp_score)

        if median and len(opponents_score) > 2:
            # discard the best and the worst opponent
            opponents_score = sorted(opponents_score)
            opponents_score = opponents_score[1:-1]  # remove first and last element

        return sum(opponents_score)

    def past_opponents(self, all_pairings) -> list:
        """List of all opponents played so far."""
        opponents = []
        for _, row in all_pairings.iterrows():
            # ignore rows which have NaN as a score
            if pd.isna(row["score1"]) or pd.isna(row["score2"]):
                continue
            # filter out Nan opponents (resulting from byes)
            if row["player1"] == self.player_id and row["player2"] != -1:
                opponents.append(row["player2"])
            elif row["player2"] == self.player_id:
                opponents.append(row["player1"])
        return opponents

    def past_tables(self, all_pairings) -> list:
        """List of tables the player has played on."""
        table_list =  list(all_pairings.loc[
                        (all_pairings["player1"] == self.player_id) |
                        (all_pairings["player2"] == self.player_id),
                        "table"
                    ])
        # ignore -1 (table placeholder for a bye)
        table_list = [table_id for table_id in table_list if table_id != -1]
        return table_list

    def color_difference(self, all_pairings) -> int:
        """
        Difference between number of starts as player1 vs player2.
        For Dominion, treat 'player1' as starting player.
        Positive => more starts, Negative => more second-player games.
        """
        starts_as_p1 = (all_pairings["player1"] == self.player_id).sum()
        starts_as_p2 = (all_pairings["player2"] == self.player_id).sum()
        return starts_as_p1 - starts_as_p2

    def received_bye(self, all_pairings) -> bool:
        filtered_pairings = all_pairings[all_pairings["player1"] == self.player_id]
        # check if the player played against a NaN player
        return (filtered_pairings["player2"] == -1).any()

    def __repr__(self):
        return self.player_name

