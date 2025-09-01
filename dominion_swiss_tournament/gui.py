# gui.py
import functools
import logging
import os
import webbrowser

from platformdirs import user_data_dir
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
import pandas as pd
import sv_ttk

# Adjust these imports to match your project structure
from dominion_swiss_tournament.player import Player
from dominion_swiss_tournament.tooltip import Tooltip
from dominion_swiss_tournament.tournament import Tournament, create_from_data

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

        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        # Do not pack scrollbar here; it will be packed/unpacked dynamically

    def _on_frame_configure(self, event):
        # Update scrollregion
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._update_scrollbar()

    def _on_canvas_configure(self, event):
        # Re-check whenever the canvas itself resizes
        self._update_scrollbar()

    def _update_scrollbar(self):
        # bbox returns (x1, y1, x2, y2)
        bbox = self.canvas.bbox("all")
        if not bbox:
            return
        content_height = bbox[3] - bbox[1]
        visible_height = self.canvas.winfo_height()

        if content_height > visible_height:
            if not self.vsb.winfo_ismapped():
                self.vsb.pack(side="right", fill="y")
        else:
            if self.vsb.winfo_ismapped():
                self.vsb.pack_forget()


class AutoHideScrollbar(ttk.Scrollbar):
    """A scrollbar that hides itself if not needed."""

    def set(self, lo, hi):
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.grid_remove()
        else:
            self.grid()
        super().set(lo, hi)

    def pack(self, **kw):
        raise tk.TclError("Cannot use pack with AutoHideScrollbar")

    def place(self, **kw):
        raise tk.TclError("Cannot use place with AutoHideScrollbar")


class TournamentApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Dominion Swiss Tournament")
        self.geometry("1000x650")

        # sv_ttk theme (dark)
        sv_ttk.set_theme("dark")

        # old save db
        self.base_dir = user_data_dir("DominionSwissTournament")
        logging.info("Using base directory: %s", self.base_dir)
        self.old_save_db_path = os.path.join(self.base_dir, "save_database.csv")
        if os.path.exists(self.old_save_db_path):
            self.old_save_db = pd.read_csv(self.old_save_db_path)
        else:
            self.old_save_db = pd.DataFrame(columns=["tournament_display_name", "tournament_save_path"])
        # state
        self.tournament: Tournament | None = None
        self.result_widgets = []  # per pairing row widgets (metadata)
        self.view_round: int | None = None  # Pairings view round

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

        tournament_name = self.tournament_name_var.get().strip()
        # create a path
        if not tournament_name:
            tournament_name = "Unnamed Tournament"
        # check if the name already exists in the old save db
        if (self.old_save_db["tournament_display_name"] == tournament_name).any():
            # ask for confirmation to overwrite
            overwrite = messagebox.askyesno(
                "Confirm Overwrite",
                f"A tournament named '{tournament_name}' already exists. Do you want to overwrite it?",
                icon="warning"
            )
            if not overwrite:
                return
        file_name = tournament_name.replace(" ", "_").lower()
        # ignore invalid filename characters
        file_name = "".join(c for c in file_name if c.isalnum() or c in ('_', '-')).rstrip()
        file_name = file_name + ".pkl"
        path = os.path.join(self.base_dir, "saved_tournaments", file_name)
        # create parent dir
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # create Tournament and first round
        self.tournament = Tournament(num_tables=num_tables, save_path=path)

        try:
            self.tournament.add_players(players)
        except ValueError:
            messagebox.showerror("Setup Error", "Not enough tables for the number of players.")
            self.tournament = None
            return

        if not (self.old_save_db["tournament_display_name"] == tournament_name).any():
            # add to database since the tournament was successfully created
            self.old_save_db.loc[len(self.old_save_db)] = [tournament_name, path]
            # save the updated database
            self.old_save_db.to_csv(self.old_save_db_path, index=False)
            logging.info("Updated save database at %s", self.old_save_db_path)

        # Generate round 1
        _ = self.tournament.generate_new_round()

        # Initialize view round to the current round
        self.view_round = self.tournament.current_round
        self._populate_pairings_view()
        self._populate_leaderboard_view()

        # switch to pairings tab
        self.nb.select(self.pairings_tab)

    def _build_setup_tab(self):
        wrapper = ttk.Frame(self.setup_tab, padding=16)
        wrapper.pack(fill="both", expand=True)

        # Header bar with title (left) and About link (right)
        header_bar = ttk.Frame(wrapper)
        header_bar.pack(fill="x", pady=(0, 12))

        header = ttk.Label(header_bar, text="Setup Tournament", font=("TkDefaultFont", 16, "bold"))
        header.pack(side="left")

        about_lbl = ttk.Label(
            header_bar,
            text="About",
            font=("TkDefaultFont", 10, "underline"),
            foreground="#57c8ff",
            cursor="hand2"
        )
        about_lbl.pack(side="right")
        about_lbl.bind("<Button-1>", lambda e: self._show_about_dialog())

        # Tournament settings in a labeled frame
        settings_frame = ttk.Labelframe(wrapper, text="Tournament Settings", padding=10)
        settings_frame.pack(fill="x", pady=8)

        ttk.Label(settings_frame, text="Tournament name:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.tournament_name_var = tk.StringVar()
        self.tournament_name_entry = ttk.Entry(settings_frame, textvariable=self.tournament_name_var, width=32)
        self.tournament_name_entry.grid(row=0, column=1, sticky="we", columnspan=2, pady=4)

        ttk.Label(settings_frame, text="Number of tables:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.tables_var = tk.IntVar(value=8)
        self.tables_spin = ttk.Spinbox(settings_frame, from_=1, to=200, textvariable=self.tables_var, width=8)
        self.tables_spin.grid(row=1, column=1, sticky="w", pady=4)

        settings_frame.columnconfigure(1, weight=1)

        # Players input in its own labeled frame
        players_frame = ttk.Labelframe(wrapper, text="Players", padding=10)
        players_frame.pack(fill="both", expand=True, pady=(12, 8))

        ttk.Label(players_frame, text="Enter one player name per line:").pack(anchor="w", pady=(0, 4))
        self.players_text = tk.Text(players_frame, height=4)
        self.players_text.pack(fill="both", expand=True)

        # Footer with left + right buttons
        footer = ttk.Frame(wrapper)
        footer.pack(fill="x", pady=12)

        # Left: Load Tournament
        load_btn = ttk.Button(footer, text="Load Existing Tournament", command=self._open_load_dialog)
        load_btn.pack(side="left")  # bottom-left

        start_btn = ttk.Button(footer, text="Create New Tournament", command=self._start_tournament)
        start_btn.pack(side="right")  # bottom-right

    import webbrowser
    import tkinter as tk
    from tkinter import ttk

    def _show_about_dialog(self):
        win = tk.Toplevel(self)
        win.title("About Dominion Swiss Tournament")
        win.resizable(False, False)
        win.transient(self)  # stay on top of parent

        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Dominion Swiss Tournament Manager",
                  font=("TkDefaultFont", 14, "bold")).pack(anchor="w")

        ttk.Label(frm, text="Version 1.0 (2025)\nCreated by Philipp Dahlinger",
                  font=("TkDefaultFont", 12)).pack(anchor="w", pady=(6, 12))

        ttk.Label(frm,
                  text=("This tool helps organize Dominion tournaments using the Swiss pairing system, "
                        "ensuring that no player is assigned to the same table more than once."),
                  font=("TkDefaultFont", 10),
                  wraplength=380,
                  justify="left").pack(anchor="w", pady=(0, 12))

        # GitHub link with tooltip
        github_url = "https://github.com/PhilippDahlinger/dominion_swiss_tournament"
        link = ttk.Label(
            frm,
            text="View on GitHub",
            font=("TkDefaultFont", 10, "underline"),
            foreground="#57c8ff",
            cursor="hand2"
        )
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda e: webbrowser.open(github_url))
        Tooltip(link, "github.com/PhilippDahlinger/dominion_swiss_tournament")

        # License note
        ttk.Label(frm,
                  text="Open Source – Licensed under the MIT License\nSee GitHub for full details.",
                  font=("TkDefaultFont", 9),
                  foreground="#888",
                  justify="left").pack(anchor="w", pady=(12, 0))

        ttk.Button(frm, text="OK", command=win.destroy).pack(pady=(12, 0))

        # Center on parent
        win.update_idletasks()
        px = self.winfo_rootx()
        py = self.winfo_rooty()
        pw = self.winfo_width()
        ph = self.winfo_height()
        ww = win.winfo_width()
        wh = win.winfo_height()
        x = px + (pw - ww) // 2
        y = py + (ph - wh) // 2
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")

        # Modal behavior
        win.wait_visibility()
        win.grab_set()
        win.focus_set()
        win.wait_window()

    def _open_load_dialog(self):
        # parent window
        parent = self.winfo_toplevel()

        dlg = tk.Toplevel(parent)
        dlg.title("Load Tournament")
        dlg.transient(parent)
        dlg.grab_set()  # modal
        dlg.resizable(False, False)

        # Content
        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Select a tournament:").pack(anchor="w", pady=(0, 8))

        # Listbox with scrollbar
        listframe = ttk.Frame(frm)
        listframe.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(listframe, orient="vertical")
        lb = tk.Listbox(listframe, height=10, activestyle="dotbox",
                        exportselection=False)  # keep selection when focus changes
        lb.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        lb.configure(yscrollcommand=scrollbar.set)
        scrollbar.configure(command=lb.yview)

        # Populate
        names = self._get_saved_tournament_names()
        for name in names:
            lb.insert("end", name)

        # Buttons
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(10, 0))

        def on_ok(event=None):
            sel = lb.curselection()
            if not sel:
                messagebox.showinfo("No selection", "Please select a tournament.")
                return
            name = lb.get(sel[0])
            try:
                self._on_tournament_selected(name)  # <-- your callback with the selected string
            finally:
                dlg.destroy()

        def on_cancel(event=None):
            dlg.destroy()

        ok_btn = ttk.Button(btns, text="OK", command=on_ok)
        cancel_btn = ttk.Button(btns, text="Cancel", command=on_cancel)
        cancel_btn.pack(side="right", padx=(8, 0))
        ok_btn.pack(side="right")

        # UX niceties
        lb.bind("<Double-1>", on_ok)  # double-click to confirm
        dlg.bind("<Return>", on_ok)  # Enter triggers OK
        dlg.bind("<Escape>", on_cancel)  # Esc cancels

        # Optional: preselect first item
        if names:
            lb.selection_set(0)
            lb.see(0)

        # Center over parent
        dlg.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (dlg.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (dlg.winfo_height() // 2)
        dlg.geometry(f"+{max(0, x)}+{max(0, y)}")

        dlg.wait_window()  # block until closed

    def _get_saved_tournament_names(self):
        """
        Replace this with your real storage (e.g., scan a directory, read a DB, etc.)
        Must return a list[str].
        """
        # check that the paths exist, otherwise filter them out
        self.old_save_db = self.old_save_db[self.old_save_db["tournament_save_path"].apply(os.path.exists)].reset_index(
            drop=True)
        return list(self.old_save_db["tournament_display_name"])

    def _on_tournament_selected(self, name: str):
        """
        This gets the SELECTED STRING from the dialog.
        Do your loading logic here.
        """
        print("Selected tournament:", name)
        # get the path
        load_path = self.old_save_db[self.old_save_db["tournament_display_name"] == name].reset_index(drop=True).loc[
            0, "tournament_save_path"]
        print("stop")
        self.tournament = create_from_data(load_path)
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

        # Scrollable area
        self.scroll = ScrollableFrame(outer)
        self.scroll.pack(fill="both", expand=True)

        self.table_grid = ttk.Frame(self.scroll.inner)
        self.table_grid.pack(fill="x", expand=True)

        # Shared grid column configuration
        for col_idx, (w, minw) in enumerate([(1, 80), (3, 220), (3, 220), (2, 140)]):
            self.table_grid.grid_columnconfigure(col_idx, weight=w, uniform="paircols", minsize=minw)

        # Actions
        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=8)

        self.delete_btn = ttk.Button(
            actions,
            text="Delete Current Round",
            command=self._delete_last_round,
            state="disabled"
        )
        self.delete_btn.pack(side="left")

        # Right button: Generate next round
        self.submit_btn = ttk.Button(actions, text="Generate next round",
                                     command=self._generate_next_round,
                                     style="Accent.TButton",
                                     state="disabled")
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
        self._update_delete_button_state()
        self._update_submit_button_state()

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
                    return "— (bye)"
                return self.tournament.players.get(pid, Player(pid, f"#{pid}")).player_name

            ttk.Label(self.table_grid, text=("—" if table == -1 else str(table))).grid(row=r, column=0, sticky="w",
                                                                                       padx=(0, 6))
            lbl_p1 = ttk.Label(self.table_grid, text=name_for(p1))
            lbl_p1.grid(row=r, column=1, sticky="w", padx=6)
            lbl_p2 = ttk.Label(self.table_grid, text=name_for(p2))
            lbl_p2.grid(row=r, column=2, sticky="w", padx=6)

            if p2 == -1:
                Tooltip(lbl_p2, "This player has a BYE: no opponent this round, automatic win.")
                Tooltip(lbl_p1, "This player has a BYE: no opponent this round, automatic win.")

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
        self._update_submit_button_state()

    def _update_submit_button_state(self):
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

    def _delete_last_round(self):
        if self.tournament is None:
            return

        # Confirmation dialog
        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete round {self.tournament.current_round}?",
            icon="warning"
        )
        if not confirm:
            return  # user canceled

        if self.tournament.delete_last_round():
            self.view_round = self.tournament.current_round
            self._populate_pairings_view()
        else:
            messagebox.showinfo("Delete Round", "Cannot delete first round.")

        self._update_delete_button_state()

    def _update_delete_button_state(self):
        if self.tournament.current_round > 1:
            self.delete_btn.config(state="normal")
        else:
            self.delete_btn.config(state="disabled")

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

    def _build_leaderboard_tab(self):
        outer = ttk.Frame(self.leaderboard_tab, padding=12)
        outer.pack(fill="both", expand=True)

        # Header bar: Leaderboard title (left), Show Tiebreaks (right)
        header_bar = ttk.Frame(outer)
        header_bar.pack(fill="x", pady=(0, 8))

        title_text = "Leaderboard"
        if self.tournament:
            title_text += f" – Round {self.tournament.current_round}"

        self.leader_header = ttk.Label(header_bar, text=title_text, font=("TkDefaultFont", 14, "bold"))
        self.leader_header.pack(side="left")

        self.show_tiebreaks_var = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(
            header_bar,
            text="Show Tiebreaks",
            variable=self.show_tiebreaks_var,
            command=self._toggle_tiebreaks
        )
        cb.pack(side="right")

        # Treeview with auto-hide vertical scrollbar
        tv_frame = ttk.Frame(outer)
        tv_frame.pack(fill="both", expand=True)

        vsb = AutoHideScrollbar(tv_frame, orient="vertical")
        vsb.grid(row=0, column=1, sticky="ns")

        self.base_cols = {"rank": "Rank", "player_name": "Player", "score": "Score"}
        self.tie_cols = {
            "buchholz_cut1": "Buchholz Cut 1",
            "buchholz": "Buchholz",
            "direct_encounter": "Direct Encounter",
            "num_wins": "Wins"
        }

        self.leader_tv = ttk.Treeview(
            tv_frame,
            columns=list(self.base_cols.keys()),
            show="headings",
            height=12,
            yscrollcommand=vsb.set
        )
        self._setup_leaderboard_columns()
        self.leader_tv.grid(row=0, column=0, sticky="nsew")

        vsb.config(command=self.leader_tv.yview)

        tv_frame.grid_rowconfigure(0, weight=1)
        tv_frame.grid_columnconfigure(0, weight=1)

        # Configure zebra striping
        self.leader_tv.tag_configure("oddrow", background="#2a2a2a")
        self.leader_tv.tag_configure("evenrow", background="#1e1e1e")

    def _setup_leaderboard_columns(self):
        """Configure Treeview columns depending on checkbox."""
        cols = self.base_cols.copy()
        if self.show_tiebreaks_var.get():
            cols.update(self.tie_cols)

        self.leader_tv.config(columns=list(cols.keys()))

        for c, display_name in cols.items():
            width = 150
            if c == "player_name":
                width = 300
                anchor = "w"  # left-align names
            else:
                anchor = "center"
            self.leader_tv.heading(c, text=display_name)
            self.leader_tv.column(c, width=width, anchor=anchor)

    def _toggle_tiebreaks(self):
        """Reconfigure columns and refresh view when checkbox changes."""
        self._setup_leaderboard_columns()
        self._populate_leaderboard_view()

    def _populate_leaderboard_view(self):
        # Clear
        for row in self.leader_tv.get_children():
            self.leader_tv.delete(row)

        if not self.tournament or self.tournament.leaderboard is None:
            return

        # Update header text with current round
        self.leader_header.config(text=f"Leaderboard – Round {self.tournament.current_round}")

        self.tournament.recompute_leaderboard()
        lb = self.tournament.leaderboard

        for idx, (_, r) in enumerate(lb.iterrows()):
            values = [int(r["rank"]), r["player_name"], float(r["score"])]
            if self.show_tiebreaks_var.get():
                values.extend([
                    float(r["buchholz_score_cut1"]),
                    float(r["buchholz_score"]),
                    float(r["direct_encounter_score"]),
                    int(r["number_of_wins"]),
                ])
            tag = "evenrow" if idx % 2 == 0 else "oddrow"
            self.leader_tv.insert("", "end", values=values, tags=(tag,))

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
