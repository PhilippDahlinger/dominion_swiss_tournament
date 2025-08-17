import pandas as pd


class Player:
    def __init__(self, player_id, player_name):
        self.player_id = player_id
        self.player_name = player_name
        self.pairings_history = pd.DataFrame(columns=["round", "table", "player1", "player2", "score1", "score2"])

    @property
    def score(self) -> float:
        """Total score accumulated across rounds."""
        if self.pairings_history.empty:
            return 0
        # Check if player was player1 or player2, and sum accordingly
        mask1 = self.pairings_history["player1"] == self.player_id
        mask2 = self.pairings_history["player2"] == self.player_id

        score_as_p1 = self.pairings_history.loc[mask1, "score1"].astype(float).sum()
        score_as_p2 = self.pairings_history.loc[mask2, "score2"].astype(float).sum()

        return float(score_as_p1 + score_as_p2)

    @property
    def past_opponents(self) -> list:
        """List of all opponents played so far."""
        if self.pairings_history.empty:
            return []
        opponents = []
        for _, row in self.pairings_history.iterrows():
            # filter out Nan opponents (resulting from byes)
            if row["player1"] == self.player_id and row["player2"] != -1:
                opponents.append(row["player2"])
            elif row["player2"] == self.player_id:
                opponents.append(row["player1"])
        return opponents

    @property
    def past_tables(self) -> list:
        """List of tables the player has played on."""
        if self.pairings_history.empty:
            return []
        table_list =  list(self.pairings_history.loc[
                        (self.pairings_history["player1"] == self.player_id) |
                        (self.pairings_history["player2"] == self.player_id),
                        "table"
                    ])
        # ignore -1 (table placeholder for a bye)
        table_list = [table_id for table_id in table_list if table_id != -1]
        return table_list

    @property
    def color_difference(self) -> int:
        """
        Difference between number of starts as player1 vs player2.
        For Dominion, treat 'player1' as starting player.
        Positive => more starts, Negative => more second-player games.
        """
        if self.pairings_history.empty:
            return 0
        starts_as_p1 = (self.pairings_history["player1"] == self.player_id).sum()
        starts_as_p2 = (self.pairings_history["player2"] == self.player_id).sum()
        return starts_as_p1 - starts_as_p2

    @property
    def received_bye(self) -> bool:
        # check if the player played against a NaN player
        return (self.pairings_history["player2"] == -1).any()

    def __repr__(self):
        return self.player_name
