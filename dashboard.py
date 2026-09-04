"""
Admin dashboard: visibility analytics, hazard logs/charts, and basic user
management -- all reading from the DB rather than live pipeline state,
since this is meant for reviewing history, not the live feed itself.
"""

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import db


class DashboardFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self._build_layout()
        self.refresh()

    def _build_layout(self):
        self.grid_columnconfigure((0, 1), weight=1)
        self.grid_rowconfigure(1, weight=1)

        refresh_btn = ctk.CTkButton(self, text="Refresh", command=self.refresh)
        refresh_btn.grid(row=0, column=0, sticky="w", padx=10, pady=10)

        # --- Charts row ---
        self.visibility_chart_frame = ctk.CTkFrame(self)
        self.visibility_chart_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        self.hazard_chart_frame = ctk.CTkFrame(self)
        self.hazard_chart_frame.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)

        # --- Recent hazards table ---
        self.hazard_log_frame = ctk.CTkScrollableFrame(self, label_text="Recent hazard events")
        self.hazard_log_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)

        # --- User management ---
        self.user_frame = ctk.CTkFrame(self)
        self.user_frame.grid(row=2, column=1, sticky="nsew", padx=10, pady=10)
        ctk.CTkLabel(self.user_frame, text="Users", font=("Arial", 14, "bold")).pack(
            anchor="w", padx=10, pady=(10, 5)
        )
        self.user_list_frame = ctk.CTkScrollableFrame(self.user_frame, height=140)
        self.user_list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        add_user_row = ctk.CTkFrame(self.user_frame, fg_color="transparent")
        add_user_row.pack(fill="x", padx=10, pady=(5, 10))
        self.new_username_entry = ctk.CTkEntry(add_user_row, placeholder_text="username")
        self.new_username_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(add_user_row, text="Add", width=60, command=self._add_user).pack(side="left")

        self.grid_rowconfigure(2, weight=1)

    def refresh(self):
        self._render_visibility_chart()
        self._render_hazard_chart()
        self._render_hazard_log()
        self._render_users()

    def _render_visibility_chart(self):
        for widget in self.visibility_chart_frame.winfo_children():
            widget.destroy()

        rows = db.fetch_visibility_trend(limit=50)
        fig = Figure(figsize=(4, 3), dpi=100)
        ax = fig.add_subplot(111)
        if rows:
            scores = [r[1] for r in rows]
            ax.plot(range(len(scores)), scores, color="#2fa572")
        ax.set_title("Visibility score (recent)")
        ax.set_ylim(0, 100)
        canvas = FigureCanvasTkAgg(fig, master=self.visibility_chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)

    def _render_hazard_chart(self):
        for widget in self.hazard_chart_frame.winfo_children():
            widget.destroy()

        rows = db.fetch_daily_hazard_counts(days=7)
        fig = Figure(figsize=(4, 3), dpi=100)
        ax = fig.add_subplot(111)
        if rows:
            labels = [str(r[0]) for r in rows]
            counts = [r[1] for r in rows]
            ax.bar(labels, counts, color="#3b8ed0")
            ax.tick_params(axis="x", rotation=45, labelsize=7)
        ax.set_title("Daily hazard count (7d)")
        canvas = FigureCanvasTkAgg(fig, master=self.hazard_chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)

    def _render_hazard_log(self):
        for widget in self.hazard_log_frame.winfo_children():
            widget.destroy()

        rows = db.fetch_recent_hazards(limit=25)
        if not rows:
            ctk.CTkLabel(self.hazard_log_frame, text="No hazard events logged yet.").pack(
                anchor="w", padx=5, pady=5
            )
            return

        for row in rows:
            text = (
                f"{row['detected_at'].strftime('%Y-%m-%d %H:%M:%S')}  |  "
                f"{row['class_name']}  |  conf {row['confidence']:.2f}  |  "
                f"visibility {row['visibility_score']}"
            )
            ctk.CTkLabel(self.hazard_log_frame, text=text, anchor="w").pack(
                fill="x", padx=5, pady=2
            )

    def _render_users(self):
        for widget in self.user_list_frame.winfo_children():
            widget.destroy()

        rows = db.fetch_users()
        if not rows:
            ctk.CTkLabel(self.user_list_frame, text="No users yet.").pack(anchor="w", padx=5, pady=5)
            return

        for row in rows:
            text = f"{row['username']}  ({row['role']})"
            ctk.CTkLabel(self.user_list_frame, text=text, anchor="w").pack(
                fill="x", padx=5, pady=2
            )

    def _add_user(self):
        username = self.new_username_entry.get().strip()
        if not username:
            return
        if db.add_user(username):
            self.new_username_entry.delete(0, "end")
            self._render_users()
