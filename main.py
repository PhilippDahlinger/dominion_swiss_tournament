

if __name__ == "__main__":
    # create dummy tournament with 8 players
    from dominion_swiss_tournament.tournament import Tournament
    import logging
    logging.basicConfig(level=logging.ERROR)
    tournament = Tournament(num_tables=3)
    tournament.add_players(["A", "B", "C", "D", "E", "F", "G"])

    # upload random results for the first round
    import random
    for r in range(5):
        print("-----------------")
        new_pairings = tournament.generate_new_round()
        print(new_pairings)
        possible_scores = [(1, 0), (0.5, 0.5), (0, 1)]
        for _, row in tournament.pairings.iterrows():
            if row["player2"] == -1:
                continue
            score1, score2 = random.choice(possible_scores)
            tournament.upload_result(row["table"], score1, score2)
        tournament.close_round()
        print(tournament.leaderboard)
