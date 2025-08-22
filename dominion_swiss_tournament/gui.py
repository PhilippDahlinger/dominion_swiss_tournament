# gui.py
import functools
import logging
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
import pandas as pd
import sv_ttk

# Adjust these imports to match your project structure
from dominion_swiss_tournament.player import Player
from dominion_swiss_tournament.tournament import Tournament

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")


RESULT_OPTIONS = ["N/A", "1-0", "0.5-0.5", "0-1"]
RESULT_TO_SCORES = {"1-0": (1.0, 0.0), "0.5-0.5": (0.5, 0.5), "0-1": (0.0, 1.0), "N/A": (np.nan, np.nan)}


def _scores_to_result(score1, score2):
    """Map numeric scores to a display string; fall back if non-standard."""
    if pd.isna(score1) or pd.isna(score2):
        return "N/A"
    tup = (float(score1), float(score2))
    if tup == (1.0, 0.0):
        return "1-0"
    if tup == (0.5, 0.5):
        return "0.5-0.5"
    if tup == (0.0, 1.0):
        return "0-1"
    return f"{score1}-{score2}"


class ScrollableFrame(ttk.Frame):
    """A vertically scrollable frame (for the pairings table)."""
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")


class TournamentApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Dominion Swiss Tournament")
        self.geometry("1000x650")

        # sv_ttk theme (dark)
        sv_ttk.set_theme("dark")

        # state
        self.tournament: Tournament | None = None
        self.result_widgets = []                 # per pairing row widgets (metadata)
        self.view_round: int | None = None       # Pairings view round

        # notebook with 3 tabs (views)
        self.nb = ttk.Notebook(self)
        self.setup_tab = ttk.Frame(self.nb)
        self.pairings_tab = ttk.Frame(self.nb)
        self.leaderboard_tab = ttk.Frame(self.nb)

        self.nb.add(self.setup_tab, text="Setup")
        self.nb.add(self.pairings_tab, text="Pairings & Results")
        self.nb.add(self.leaderboard_tab, text="Leaderboard")
        self.nb.pack(fill="both", expand=True)

        # when switching to Leaderboard, just refresh from tournament.leaderboard
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # build tabs
        self._build_setup_tab()
        self._build_pairings_tab()
        self._build_leaderboard_tab()

    # ---------- Setup tab ----------
    def _build_setup_tab(self):
        wrapper = ttk.Frame(self.setup_tab, padding=16)
        wrapper.pack(fill="both", expand=True)

        header = ttk.Label(wrapper, text="Setup Tournament", font=("TkDefaultFont", 16, "bold"))
        header.pack(anchor="w", pady=(0, 12))

        form = ttk.Frame(wrapper)
        form.pack(fill="x", pady=8)

        # Number of tables
        ttk.Label(form, text="Number of tables:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.tables_var = tk.IntVar(value=8)
        self.tables_spin = ttk.Spinbox(form, from_=1, to=200, textvariable=self.tables_var, width=8)
        self.tables_spin.grid(row=0, column=1, sticky="w")

        # Players input
        ttk.Label(wrapper, text="Players (one per line):").pack(anchor="w", pady=(12, 4))
        self.players_text = tk.Text(wrapper, height=16)
        self.players_text.pack(fill="both", expand=True)

        # Start button
        start_btn = ttk.Button(wrapper, text="Start Tournament", command=self._start_tournament)
        start_btn.pack(anchor="e", pady=12)

    def _start_tournament(self):
        players_raw = self.players_text.get("1.0", "end").strip()
        if not players_raw:
            messagebox.showerror("Validation", "Please enter at least two players.")
            return

        players = [p.strip() for p in players_raw.splitlines() if p.strip()]
        if len(players) < 2:
            messagebox.showerror("Validation", "Please enter at least two players.")
            return

        num_tables = self.tables_var.get()
        if num_tables < 1:
            messagebox.showerror("Validation", "Number of tables must be at least 1.")
            return

        # create Tournament and first round
        self.tournament = Tournament(num_tables=num_tables)
        try:
            self.tournament.add_players(players)
        except ValueError:
            messagebox.showerror("Setup Error", "Not enough tables for the number of players.")
            self.tournament = None
            return

        # Generate round 1
        _ = self.tournament.generate_new_round()

        # Initialize view round to the current round
        self.view_round = self.tournament.current_round
        self._populate_pairings_view()
        self._populate_leaderboard_view()

        # switch to pairings tab
        self.nb.select(self.pairings_tab)

    # ---------- Pairings tab ----------
    def _build_pairings_tab(self):
        outer = ttk.Frame(self.pairings_tab, padding=12)
        outer.pack(fill="both", expand=True)

        # Round header with arrows
        header_bar = ttk.Frame(outer)
        header_bar.pack(fill="x", pady=(0, 8))

        self.prev_btn = ttk.Button(header_bar, text="◀", width=3, command=self._goto_prev_round)
        self.prev_btn.pack(side="left")

        self.round_label = ttk.Label(header_bar, text="Round -", font=("TkDefaultFont", 14, "bold"))
        self.round_label.pack(side="left", padx=8)

        self.next_btn = ttk.Button(header_bar, text="▶", width=3, command=self._goto_next_round)
        self.next_btn.pack(side="left")

        ttk.Separator(outer, orient="horizontal").pack(fill="x", pady=6)

        # Scrollable area containing ONE grid for both header and rows (ensures perfect alignment)
        self.scroll = ScrollableFrame(outer)
        self.scroll.pack(fill="both", expand=True)

        self.table_grid = ttk.Frame(self.scroll.inner)
        self.table_grid.pack(fill="x", expand=True)

        # Shared grid column configuration
        # (weights and minsize mirror both header "columns" and row cells)
        for col_idx, (w, minw) in enumerate([(1, 80), (3, 220), (3, 220), (2, 140)]):
            self.table_grid.grid_columnconfigure(col_idx, weight=w, uniform="paircols", minsize=minw)

        # Actions
        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=8)
        self.submit_btn = ttk.Button(actions, text="Generate next round", command=self._generate_next_round, state="disabled")
        self.submit_btn.pack(side="right")

    def _clear_pairings_rows(self):
        # Destroy everything in table_grid (header + rows) and rebuild header
        for child in self.table_grid.winfo_children():
            child.destroy()
        self.result_widgets.clear()

    def _build_pairings_header(self):
        # Header row (in the same grid container as the rows)
        headers = [("Table", 0), ("Player 1", 1), ("Player 2", 2), ("Result", 3)]
        for text, col in headers:
            ttk.Label(
                self.table_grid,
                text=text,
                font=("TkDefaultFont", 10, "bold")  # 👈 bold font
            ).grid(
                row=0, column=col,
                sticky="w",
                padx=(6 if col else 0, 6),
                pady=(0, 4)
            )

    def _populate_pairings_view(self):
        self._clear_pairings_rows()
        if self.tournament is None:
            return

        if self.view_round is None:
            self.view_round = self.tournament.current_round

        self.round_label.config(text=f"Round {self.view_round}")
        self.prev_btn.configure(state=("normal" if self.view_round > 1 else "disabled"))
        self.next_btn.configure(state=("normal" if self.view_round < self.tournament.current_round else "disabled"))
        self.submit_btn.configure(state="disabled")

        self._build_pairings_header()

        df = self.tournament.pairings[self.tournament.pairings["round"] == self.view_round].copy()
        if df.empty:
            return

        df['__bye__'] = (df['table'] == -1).astype(int)
        df = df.sort_values(['__bye__', 'table']).drop(columns='__bye__')

        viewing_current = (self.view_round == self.tournament.current_round)

        for r, (_, row) in enumerate(df.iterrows(), start=1):
            table = int(row["table"])
            p1 = int(row["player1"])
            p2 = int(row["player2"])
            s1, s2 = row.get("score1", np.nan), row.get("score2", np.nan)

            def name_for(pid):
                if pid == -1:
                    return "BYE"
                return self.tournament.players.get(pid, Player(pid, f"#{pid}")).player_name

            ttk.Label(self.table_grid, text=("—" if table == -1 else str(table))).grid(row=r, column=0, sticky="w",
                                                                                       padx=(0, 6))
            ttk.Label(self.table_grid, text=name_for(p1)).grid(row=r, column=1, sticky="w", padx=6)
            ttk.Label(self.table_grid, text=name_for(p2)).grid(row=r, column=2, sticky="w", padx=6)

            initial = _scores_to_result(s1, s2)
            cb_var = tk.StringVar(value=initial if initial in RESULT_OPTIONS else "N/A")
            cb = ttk.Combobox(
                self.table_grid,
                values=RESULT_OPTIONS,
                textvariable=cb_var,
                state="readonly",
                width=10
            )
            cb.grid(row=r, column=3, sticky="w", padx=6)

            disable = (table == -1 or p2 == -1 or not viewing_current)
            if disable:
                cb.configure(state="disabled")

            # Bind callback — use functools.partial to pass row context
            cb.bind("<<ComboboxSelected>>",
                    functools.partial(self._on_result_changed, row_index=r, table=table, p1=p1, p2=p2))

            self.result_widgets.append({
                "round": self.view_round,
                "table": table,
                "player1": p1,
                "player2": p2,
                "combobox": cb,
                "var": cb_var,
            })

    def _on_result_changed(self, event, row_index, table, p1, p2):
        """Callback when a combobox result is changed. Upsert the tournament data."""
        cb = event.widget
        new_value = cb.get()
        # upload this value to the tournament database
        score1, score2 = RESULT_TO_SCORES[new_value]  # validate the result
        self.tournament.upload_result(table, score1, score2)
        if self.tournament.all_pairings_submitted():
            # enable the submit button
            self.submit_btn.configure(state="normal")
        else:
            # disable the submit button
            self.submit_btn.configure(state="disabled")


    def _goto_prev_round(self):
        if not self.tournament or self.view_round is None:
            return
        if self.view_round > 1:
            self.view_round -= 1
            self._populate_pairings_view()

    def _goto_next_round(self):
        if not self.tournament or self.view_round is None:
            return
        if self.view_round < self.tournament.current_round:
            self.view_round += 1
            self._populate_pairings_view()

    def _generate_next_round(self):
        if self.tournament is None:
            return
        if self.view_round != self.tournament.current_round:
            messagebox.showinfo("Results", "You can only submit results on the current round.")
            return
        # Close current round
        if self.tournament.close_round():
            # Generate next round (if possible)
            try:
                self.tournament.generate_new_round()
            except Exception as e:
                logging.error(e)
                messagebox.showinfo("Tournament", "Next round could not be generated (maybe tournament is over).")
                self._populate_leaderboard_view()
                return

            # Update pairings & leaderboard views
            self.view_round = self.tournament.current_round
            self._populate_pairings_view()
            self._populate_leaderboard_view()
            self.nb.select(self.pairings_tab)
        else:
            messagebox.showinfo("Results", "Cannot close round: not all results are uploaded.")

    # ---------- Leaderboard tab ----------
    def _build_leaderboard_tab(self):
        outer = ttk.Frame(self.leaderboard_tab, padding=12)
        outer.pack(fill="both", expand=True)

        header = ttk.Label(outer, text="Leaderboard (current)", font=("TkDefaultFont", 14, "bold"))
        header.pack(anchor="w", pady=(0, 8))

        cols = {"rank": "Rank", "player_name": "Player", "score": "Score"}
        self.leader_tv = ttk.Treeview(outer, columns=list(cols.keys()), show="headings", height=20)
        for c, display_name in cols.items():
            self.leader_tv.heading(c, text=display_name)
            self.leader_tv.column(c, width=150 if c != "player_name" else 300, anchor="center")
        self.leader_tv.pack(fill="both", expand=True)

        btns = ttk.Frame(outer)
        btns.pack(fill="x", pady=8)
        refresh_btn = ttk.Button(btns, text="Refresh", command=self._populate_leaderboard_view)
        refresh_btn.pack(side="right")

    def _populate_leaderboard_view(self):
        # Clear
        for row in self.leader_tv.get_children():
            self.leader_tv.delete(row)

        if not self.tournament or self.tournament.leaderboard is None:
            return

        # Use the leaderboard as provided by Tournament (no recomputation here)
        self.tournament.recompute_leaderboard()
        lb = self.tournament.leaderboard

        # Expect columns: player_id, player_name, score, buchholz_score, rank
        for _, r in lb.iterrows():
            self.leader_tv.insert("", "end", values=(int(r["rank"]), r["player_name"], float(r["score"])))

    # ---------- Tab switch handling ----------
    def _on_tab_changed(self, event):
        """When switching tabs, if it's the Leaderboard, refresh from Tournament (no recompute)."""
        if not self.tournament:
            return
        tab = event.widget.select()
        tab_widget = self.nametowidget(tab)
        if tab_widget is self.leaderboard_tab:
            self._populate_leaderboard_view()


if __name__ == "__main__":
    app = TournamentApp()
    app.mainloop()
