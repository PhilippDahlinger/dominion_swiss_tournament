import logging
import random

import networkx as nx
import numpy as np
import pandas as pd

from dominion_swiss_tournament.player import Player



def build_player_graph(players: dict[int, Player], pairings) -> nx.Graph:
    G = nx.Graph()
    G.add_nodes_from(players.keys())
    for player in players.values():
        for player2 in players.values():
            # add all valid edges between players
            if player.player_id == player2.player_id:
                continue
            # if they have played together before, continue
            if player2.player_id in player.past_opponents(pairings):
                continue
            # check if color difference is acceptable: 2 difference is acceptable, according to paper < 2 * 2 is needed
            if abs(player.color_difference(pairings) + player2.color_difference(pairings)) >= 4:
                continue
            # add edge with weight
            weight = compute_edge_weight(player, player2, pairings)
            G.add_edge(player.player_id, player2.player_id, weight=weight)

    # the weights are negative, so we need to shift them to be positive
    # find the minimum weight in the graph
    min_weight = min((data['weight'] for u, v, data in G.edges(data=True)), default=0)
    # shift all weights to be positive
    for u, v, data in G.edges(data=True):
        data['weight'] -= min_weight - 1
    # now the weights are positive, however, we want to assure a perfect maximum weighting.
    # Add the sum of all weights to every weight to assure that the maximum of edges are always selected
    total_weight = sum(data['weight'] for u, v, data in G.edges(data=True))
    for u, v, data in G.edges(data=True):
        data['weight'] += total_weight

    return G


def compute_pairings(G: nx.Graph, players, all_pairings) -> pd.DataFrame:
    # use the maximum weight matching algorithm to find the best pairings
    matching = nx.max_weight_matching(G)
    # convert the matching to a list of tuples
    matching = [(u, v) for u, v in matching]
    assert 2 * len(matching) == len(players), "Impossible to generate pairings with given players and previous pairings."
    # created pandas dataframe
    pairings = pd.DataFrame(matching, columns=["player1", "player2"])
    # the first player should be the one with the smaller color_difference (-> less played with white)
    pairings["color_difference_1"] = pd.Series([players[u].color_difference(all_pairings) for u, _ in matching])
    pairings["color_difference_2"] = pd.Series([players[v].color_difference(all_pairings) for _, v in matching])
    # mask where player1 has bigger color_difference than player2
    mask = pairings["color_difference_1"] > pairings["color_difference_2"]
    # swap values where condition holds
    pairings.loc[mask, ["player1", "player2"]] = pairings.loc[mask, ["player2", "player1"]].values
    # delete color_diff cols
    pairings.drop(["color_difference_1", "color_difference_2"], axis=1, inplace=True)
    pairings["score1"] = np.nan
    pairings["score2"] = np.nan
    pairings["table"] = np.nan
    pairings["round"] = np.nan
    return pairings


def compute_edge_weight(player1: Player, player2: Player, pairings) -> float:
    score_weight = - abs(player1.score(pairings) - player2.score(pairings))
    color_weight = - abs(player1.color_difference(pairings) - player2.color_difference(pairings))
    # TODO: implement all options ( monrad, burstein, durch, random, random2), for now just use random
    pi_weight = random.random()
    # lexicographic order of the different weights aspects
    return score_weight * 10000 + color_weight * 100 + pi_weight


def assign_tables(pairings: pd.DataFrame, players, all_pairings, tables: list[int]) -> pd.DataFrame:
    # assign tables to pairings randomly
    G = nx.Graph()
    G.add_nodes_from(tables)
    pairs = list(zip(pairings["player1"].astype(int), pairings["player2"].astype(int)))
    G.add_nodes_from(pairs)
    for pair in pairs:
        # add an edge between the pair and all tables on which they have not played yet
        tables_1 = players[pair[0]].past_tables(all_pairings)
        tables_2 = players[pair[1]].past_tables(all_pairings)
        free_opponents = set(tables) - set(tables_1) - set(tables_2)
        for table in free_opponents:
            G.add_edge(pair, table, weight=1)
    matching = nx.max_weight_matching(G)
    matching = [(u, v) for u, v in matching]
    # ensure that the matching is perfect

    # ensure that the tuple is (pair, table)
    for i in range(len(matching)):
        if isinstance(matching[i][1], tuple):
            matching[i] = (matching[i][1], matching[i][0])
    assigned_paris = []
    assigned_tables = []
    for pair, table in matching:
        pairings.loc[(pairings["player1"] == pair[0]) & (pairings["player2"] == pair[1]), "table"] = table
        assigned_paris.append(pair)  # keep track which pair already got a table
        assigned_tables.append(table)  # keep track which table was assigned
    missing_pairs = set(pairs) - set(assigned_paris)
    free_tables = list(set(tables) - set(assigned_tables))
    if len(missing_pairs) > 0:
        logging.warning("Not all pairings could be assigned to a new table. Assign randomly for problematic pairings.")
        for pair in missing_pairs:
            # select random free table
            random_table = random.choice(free_tables)
            free_tables.remove(random_table)
            pairings.loc[(pairings["player1"] == pair[0]) & (pairings["player2"] == pair[1]), "table"] = random_table


    return pairings


def compute_bye_player(players: dict[int, Player], pairings) -> Player:
    # get all player_ids which did not receive a bye yet
    valid_player_ids = [player_id for player_id in players.keys() if not players[player_id].received_bye(pairings)]
    # sort them by score
    valid_player_ids.sort(key=lambda x: players[x].score(pairings))
    # get all players with the lowest score, pick a random one
    min_score = players[valid_player_ids[0]].score(pairings)
    valid_player_ids = [player_id for player_id in valid_player_ids if players[player_id].score(pairings) == min_score]
    return random.choice(valid_player_ids)
