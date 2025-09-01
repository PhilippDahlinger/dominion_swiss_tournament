import tkinter as tk
from tkinter import ttk

class Tooltip:
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay  # milliseconds before showing
        self._id = None
        self._tipwindow = None

        self.widget.bind("<Enter>", self._schedule)
        self.widget.bind("<Leave>", self._unschedule)
        self.widget.bind("<ButtonPress>", self._unschedule)

    def _schedule(self, event=None):
        self._unschedule()
        self._id = self.widget.after(self.delay, self._show)

    def _unschedule(self, event=None):
        if self._id:
            self.widget.after_cancel(self._id)
            self._id = None
        self._hide()

    def _show(self):
        if self._tipwindow or not self.text:
            return

        x, y, cx, cy = self.widget.bbox("insert") or (0, 0, 0, 0)
        x = x + self.widget.winfo_rootx() + 25
        y = y + cy + self.widget.winfo_rooty() + 25

        self._tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            tw,
            text=self.text,
            background="lightyellow",
            foreground="black",
            relief="solid",
            borderwidth=1,
            padx=5,
            pady=2
        )
        label.pack()

    def _hide(self):
        tw = self._tipwindow
        if tw:
            tw.destroy()
            self._tipwindow = None