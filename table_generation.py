import os
import random

NUM_TABLES = 8

available_games = {
    "base_old": 7,
    "base_new": 3,
    "intrigue": 2,
    "seaside": 2,
    "prosperity": 2,
}

sea_basic_table = {
    "base_new": 1,
    "base_old": 6,
    "seaside": 3,
}

intrigue_basic_table = {
    "base_new": 1,
    "base_old": 6,
    "intrigue": 3,
}

intrigue_less_new_table = {
    "base_new": 1,
    "base_old": 7,
    "intrigue": 2,
}

finals_table = {
    "base_new": 2,
    "base_old": 0,
    "intrigue": 1,
    "seaside": 3,
    "prosperity": 4,
}

tables = [
    sea_basic_table,
    sea_basic_table,
    intrigue_basic_table,
    intrigue_basic_table,
    sea_basic_table,
    sea_basic_table,
    intrigue_basic_table,
    intrigue_basic_table,
    sea_basic_table,
    intrigue_basic_table,
    # intrigue_basic_table,
    # finals_table,
]


# --- LOAD CARDS FROM FILES ---

def load_cards(base_path="cards_in_games"):
    """Reads all .txt files and returns {expansion_name: [cards]}."""
    cards = {}
    for filename in os.listdir(base_path):
        if filename.endswith(".txt"):
            key = filename.replace(".txt", "")
            with open(os.path.join(base_path, filename), "r", encoding="utf-8") as f:
                cards[key] = [line.strip() for line in f if line.strip()]
    return cards


# --- PREPARE COPIES OF EACH EXPANSION ---

def prepare_expansions(all_cards, available_games):
    """Replicates each expansion's deck according to the number of available copies."""
    expanded = {}
    for expansion, cards in all_cards.items():
        num_copies = available_games.get(expansion, 1)
        expanded[expansion] = cards * num_copies  # repeat full deck
        random.shuffle(expanded[expansion])
    return expanded


# --- DRAW CARDS ---

def draw_cards(available_cards, expansion, count):
    """Draws `count` cards from a specific expansion, ensuring no duplicates within one table."""
    pool = available_cards.get(expansion, [])
    if len(pool) < count:
        raise ValueError(f"Not enough cards left in '{expansion}' (needed {count}, got {len(pool)}).")

    # make sure we don't draw duplicates *within* one table
    drawn = []
    used_names = set()
    while len(drawn) < count and pool:
        card = random.choice(pool)
        if card not in used_names:
            drawn.append(card)
            used_names.add(card)
            pool.remove(card)
        else:
            # skip duplicate name
            pool.remove(card)

    if len(drawn) < count:
        raise ValueError(f"Couldn't find {count} unique cards for {expansion}.")

    available_cards[expansion] = pool
    return drawn


# --- GENERATE TABLES ---

def generate_tables(tables, available_cards):
    result = {}
    for i, table_config in enumerate(tables):
        table_cards = []
        for expansion, count in table_config.items():
            if count > 0:
                drawn = draw_cards(available_cards, expansion, count)
                table_cards.extend(drawn)
        result[i] = table_cards
    return result


if __name__ == "__main__":
    all_cards = load_cards()
    num_trials = 10
    while num_trials > 0:
        try:
            available_cards = prepare_expansions(all_cards, available_games)
            game_tables = generate_tables(tables, available_cards)
        except ValueError as e:
            print(f"Error: {e}. Retrying...")
            num_trials -= 1
            continue
        break


    # print results
    for tid, cards in game_tables.items():
        print(f"\n=== TABLE {tid+1} ===")
        for c in cards:
            print(c)

