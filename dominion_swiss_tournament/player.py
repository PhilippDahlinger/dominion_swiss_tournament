import pandas as pd


class Player:
    def __init__(self, player_id, player_name):
        self.player_id = player_id
        self.player_name = player_name
        self.pairings_history = pd.DataFrame(columns=["round", "table", "player1", "player2", "score1", "score2"])

    def score(self, all_pairings) -> float:
        """Total score accumulated across rounds."""
        # Check if player was player1 or player2, and sum accordingly
        mask1 = all_pairings["player1"] == self.player_id
        mask2 = all_pairings["player2"] == self.player_id

        score_as_p1 = all_pairings.loc[mask1, "score1"].astype(float).sum()
        score_as_p2 = all_pairings.loc[mask2, "score2"].astype(float).sum()

        return float(score_as_p1 + score_as_p2)

    def past_opponents(self, all_pairings) -> list:
        """List of all opponents played so far."""
        opponents = []
        for _, row in all_pairings.iterrows():
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


def get_player_pairings(player_id: int, all_pairings: pd.DataFrame) -> pd.DataFrame:
    """
    Get all pairings for a specific player.
    :param player_id: ID of the player
    :param all_pairings: DataFrame containing all pairings
    :return: DataFrame with pairings for the player
    """
    mask = (all_pairings["player1"] == player_id) | (all_pairings["player2"] == player_id)
    return all_pairings[mask].reset_index(drop=True)
