import csv
import datetime
import sys
import tkinter as tk
from tkinter import font

# --- Configuration ---
# For testing, read from example.csv instead of the full schedule.
SCHEDULE_FILE = 'example.csv'

# If a row in the CSV doesn't include an explicit Date column,
# this date will be used. For Agile on the Beach this would be
# set to the appropriate conference day; for development you can
# leave it as "today" so tests line up with the current clock.
CONFERENCE_DATE = datetime.date.today()

# --- Colour palette (roughly matching the schedule screenshots) ---
PALETTE_BASE_BG = "#f6c049"   # yellow for breaks / general background
PALETTE_TALK_BG = "#f7931e"   # orange for talks / countdown
PALETTE_TEXT_DARK = "#5b3b00"  # dark brown text on yellow
PALETTE_TEXT_LIGHT = "#ffffff"  # white text on orange

# --- Constants for State Display ---
SECONDS_BEFORE_INTERMISSION_WARNING = 5 * 60  # 5 minutes in seconds

def load_schedule(filename: str, track_name: str | None = None):
    """Load schedule CSV and build a list of event dicts.

    Expected CSV columns (case-sensitive headers):

    - Track        (optional, used to filter per room)
    - Date         (optional, YYYY-MM-DD; falls back to CONFERENCE_DATE)
    - Start Time   (required, HH:MM 24h clock)
    - Duration     (required, minutes)
    - Speaker      (optional, for display)
    - Talk Title   (optional, for display)
    - Synopsis     (optional, for display)
    - Type         (optional, e.g. Talk/Workshop/Break)
    """
    schedule: list[dict] = []
    try:
        with open(filename, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Filter by track if requested and Track column present
                row_track = row.get('Track')
                if track_name and row_track and row_track.strip() != track_name:
                    continue

                # Parse date (per-row) or fall back to configured conference date
                date_str = (row.get('Date') or '').strip()
                if date_str:
                    try:
                        date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                    except ValueError:
                        # If format is unexpected, skip this row rather than crash
                        continue
                else:
                    date_obj = CONFERENCE_DATE

                # Parse start time
                time_str = (row.get('Start Time') or '').strip()
                if not time_str:
                    continue
                try:
                    start_time_obj = datetime.datetime.strptime(time_str, '%H:%M').time()
                except ValueError:
                    continue

                start_datetime = datetime.datetime.combine(date_obj, start_time_obj)

                # Duration and end time
                duration_str = (row.get('Duration') or '').strip()
                if not duration_str:
                    continue
                try:
                    duration_minutes = int(duration_str)
                except ValueError:
                    continue
                end_datetime = start_datetime + datetime.timedelta(minutes=duration_minutes)

                speaker = (row.get('Speaker') or '').strip()
                title = (row.get('Talk Title') or row.get('Title') or row.get('Speaker/Title') or '').strip()
                synopsis = (row.get('Synopsis') or '').strip()
                event_type = (row.get('Type') or 'Talk').strip()

                event = {
                    'track': row_track.strip() if row_track else None,
                    'date': date_obj,
                    'type': event_type,
                    'start': start_datetime,
                    'end': end_datetime,
                    'speaker': speaker,
                    'title': title,
                    'synopsis': synopsis,
                }
                schedule.append(event)

        # Sort by start time for predictable behaviour
        schedule.sort(key=lambda e: e['start'])
        return schedule
    except FileNotFoundError:
        print(f"ERROR: Schedule file '{filename}' not found. Please create it.")
        return []
    except Exception as e:
        print(f"ERROR: Failed to load schedule: {e}")
        return []


def compute_display_state(schedule: list[dict], now: datetime.datetime):
    """Compute what should be shown on screen at a given time.

    Returns a dict with keys:

    - mode: 'normal', 'pre_start', 'in_talk', 'none'
    - current: event dict for the talk currently in progress (if any)
    - next_event: next upcoming event for this room (if any)
    - following_event: event after next_event (if any)
    - seconds_to_start: seconds until next_event starts (if applicable)
    """
    current = None
    upcoming: list[dict] = []

    for e in schedule:
        if e['start'] <= now < e['end']:
            current = e
        if e['start'] >= now:
            upcoming.append(e)

    next_event = upcoming[0] if upcoming else None
    following_event = upcoming[1] if len(upcoming) > 1 else None

    # No more events at all
    if not current and not next_event:
        return {
            'mode': 'none',
            'current': None,
            'next_event': None,
            'following_event': None,
            'seconds_to_start': None,
        }

    # If a talk is currently in progress, show the in-talk slide
    if current:
        return {
            'mode': 'in_talk',
            'current': current,
            'next_event': next_event,
            'following_event': following_event,
            'seconds_to_start': None,
        }

    # Otherwise, we are between talks and have a next_event
    if next_event is None:
        # Defensive: this should not happen because it is covered by
        # the checks above, but keeps type checkers happy.
        return {
            'mode': 'none',
            'current': None,
            'next_event': None,
            'following_event': None,
            'seconds_to_start': None,
        }

    delta = next_event['start'] - now
    seconds_to_start = int(delta.total_seconds())

    # Only trigger the pre-start countdown for actual sessions
    # (talks/workshops), not for breaks or social events.
    event_type = (next_event.get('type') or '').strip().lower()
    if event_type not in ("break", "social") and seconds_to_start <= 5 * 60:
        mode = 'pre_start'
    else:
        mode = 'normal'

    return {
        'mode': mode,
        'current': None,
        'next_event': next_event,
        'following_event': following_event,
        'seconds_to_start': max(seconds_to_start, 0),
    }


def format_timedelta(td):
    total = int(td.total_seconds())
    if total < 0:
        total = 0
    hrs, rem = divmod(total, 3600)
    mins, secs = divmod(rem, 60)
    if hrs:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"

class SpeakerDisplayApp:
    def __init__(self, root, schedule_file: str = SCHEDULE_FILE, track_name: str | None = None):
        self.root = root
        self.root.title("Speaker Display")
        self.root.configure(bg=PALETTE_BASE_BG)

        self.track_name = track_name
        self.schedule = load_schedule(schedule_file, track_name=track_name)

        self.large_font = font.Font(family='Helvetica', size=48, weight='bold')
        self.mid_font = font.Font(family='Helvetica', size=28)
        self.small_font = font.Font(family='Helvetica', size=20)

        # UI Elements
        header_text = f"Track: {track_name}" if track_name else "Upcoming in this room"
        self.header_label = tk.Label(root, text=header_text, fg=PALETTE_TEXT_DARK, bg=PALETTE_BASE_BG, font=self.small_font)
        self.status_label = tk.Label(root, text='', fg=PALETTE_TEXT_DARK, bg=PALETTE_BASE_BG, font=self.mid_font)
        self.title_label = tk.Label(root, text='', fg=PALETTE_TEXT_DARK, bg=PALETTE_BASE_BG, font=self.large_font, wraplength=1400, justify='center')
        self.info_label = tk.Label(root, text='', fg=PALETTE_TEXT_DARK, bg=PALETTE_BASE_BG, font=self.mid_font, wraplength=1400, justify='center')
        self.extra_label = tk.Label(root, text='', fg=PALETTE_TEXT_DARK, bg=PALETTE_BASE_BG, font=self.small_font, wraplength=1400, justify='center')

        self.header_label.pack(pady=(10, 5))
        self.status_label.pack(pady=(5, 10))
        self.title_label.pack(pady=10)
        self.info_label.pack(pady=10)
        self.extra_label.pack(pady=(10, 20))

        # Start update loop
        self.update_interval_ms = 1000
        self.update()

    def _apply_theme(self, *, bg: str, title_fg: str, body_fg: str, extra_fg: str | None = None):
        """Apply a simple colour theme to all labels and the window."""
        if extra_fg is None:
            extra_fg = body_fg
        self.root.configure(bg=bg)
        self.header_label.config(bg=bg, fg=body_fg)
        self.status_label.config(bg=bg, fg=body_fg)
        self.title_label.config(bg=bg, fg=title_fg)
        self.info_label.config(bg=bg, fg=body_fg)
        self.extra_label.config(bg=bg, fg=extra_fg)

    def update(self):
        now = datetime.datetime.now().replace(microsecond=0)
        if not self.schedule:
            self.status_label.config(text='FAIL-SAFE: No schedule loaded')
            self.title_label.config(text='Waiting for schedule...')
            self.info_label.config(text=f"Ensure {SCHEDULE_FILE} is present and formatted correctly.")
            self.extra_label.config(text='')
            self.root.after(self.update_interval_ms, self.update)
            return

        state = compute_display_state(self.schedule, now)
        mode = state['mode']
        current = state['current']
        next_event = state['next_event']
        following = state['following_event']

        if mode == 'none':
            self._apply_theme(bg=PALETTE_BASE_BG, title_fg=PALETTE_TEXT_DARK, body_fg=PALETTE_TEXT_DARK)
            self.status_label.config(text='No more events in this room today')
            self.title_label.config(text='Thank you for attending')
            self.info_label.config(text='')
            self.extra_label.config(text='')

        elif mode == 'in_talk' and current:
            # Talk in progress – show that talk only, no countdown, until end time
            speaker = current['speaker'] or ''
            title = current['title'] or ''
            synopsis = current['synopsis'] or ''
            end_time_str = current['end'].strftime('%H:%M')

            self._apply_theme(bg=PALETTE_TALK_BG, title_fg=PALETTE_TEXT_LIGHT, body_fg=PALETTE_TEXT_LIGHT)
            self.status_label.config(text='Now on stage')
            main_text = f"{speaker}\n{title}" if speaker else title
            self.title_label.config(text=main_text)
            self.info_label.config(text=f"Scheduled to end at {end_time_str}")
            self.extra_label.config(text=synopsis)

        elif mode == 'pre_start' and next_event:
            # Within 5 minutes of next talk – focus only on next talk and countdown
            speaker = next_event['speaker'] or ''
            title = next_event['title'] or ''
            synopsis = next_event['synopsis'] or ''
            start_time_str = next_event['start'].strftime('%H:%M')

            secs = state['seconds_to_start'] or 0
            # Round up to whole minutes for the prominent warning (5,4,3,2,1)
            minutes_remaining = max((secs + 59) // 60, 0)

            self._apply_theme(bg=PALETTE_TALK_BG, title_fg=PALETTE_TEXT_LIGHT, body_fg=PALETTE_TEXT_LIGHT)

            countdown_str = format_timedelta(datetime.timedelta(seconds=secs))
            self.status_label.config(text=f"Starting soon – {minutes_remaining} minute warning")
            main_text = f"{speaker}\n{title}" if speaker else title
            self.title_label.config(text=main_text)
            self.info_label.config(text=f"Scheduled start: {start_time_str}  ·  T-minus {countdown_str}")
            self.extra_label.config(text=synopsis)

        elif mode == 'normal' and next_event:
            # Normal state – show next and following events
            speaker = next_event['speaker'] or ''
            title = next_event['title'] or ''
            start_time_str = next_event['start'].strftime('%H:%M')

            self._apply_theme(bg=PALETTE_BASE_BG, title_fg=PALETTE_TEXT_DARK, body_fg=PALETTE_TEXT_DARK)
            self.status_label.config(text='Upcoming in this room')
            main_text = f"{speaker}\n{title}" if speaker else title
            self.title_label.config(text=main_text)
            self.info_label.config(text=f"Starts at {start_time_str}")

            if following:
                f_speaker = following['speaker'] or ''
                f_title = following['title'] or ''
                f_start = following['start'].strftime('%H:%M')
                following_text = f"Following: {f_speaker} – {f_title} ({f_start})" if f_speaker else f"Following: {f_title} ({f_start})"
                self.extra_label.config(text=following_text)
            else:
                self.extra_label.config(text='')

        else:
            # Fallback – shouldn't normally hit
            self._apply_theme(bg=PALETTE_BASE_BG, title_fg=PALETTE_TEXT_DARK, body_fg=PALETTE_TEXT_DARK)
            self.status_label.config(text='Schedule state unknown')
            self.title_label.config(text='')
            self.info_label.config(text='')
            self.extra_label.config(text='')

        self.root.after(self.update_interval_ms, self.update)

if __name__ == "__main__":
    # Optional: pass track/room name on the command line so the
    # same script can be used for all five tracks, e.g.:
    #   python script.py "STUDIO A"
    cli_track_arg = sys.argv[1] if len(sys.argv) > 1 else None

    # For non-technical users, show a simple dialog asking which
    # room they are in. If a command-line argument is provided,
    # that takes precedence and skips the dialog.
    if cli_track_arg:
        chosen_track = cli_track_arg
        root = tk.Tk()
    else:
        # Use a temporary root for the selection dialog
        root = tk.Tk()
        root.title("Select room/track")

        # For testing with example.csv we expose the test tracks.
        # You can swap this list back to the real rooms when you
        # point SCHEDULE_FILE at schedule.csv again.
        tracks = [
            "TEST_PRE",      # next talk within 5 minutes (countdown)
            "TEST_NORMAL",   # upcoming + following, no countdown
            "TEST_INTALK",   # talk currently in progress
        ]

        selected = tk.StringVar(value=tracks[0])

        label = tk.Label(root, text="Which room are you in?", padx=20, pady=10)
        label.pack()

        option = tk.OptionMenu(root, selected, *tracks)
        option.pack(padx=20, pady=10)

        # Use a one-element list so the nested callback can modify
        # the chosen track without needing 'nonlocal'.
        chosen_track_box = [tracks[0]]

        def on_start():
            chosen_track_box[0] = selected.get()
            root.destroy()

        start_button = tk.Button(root, text="Start display", command=on_start, padx=20, pady=5)
        start_button.pack(pady=(0, 20))

        root.mainloop()

        # Re-create the main fullscreen window
        root = tk.Tk()
        chosen_track = chosen_track_box[0]

    app = SpeakerDisplayApp(root, schedule_file=SCHEDULE_FILE, track_name=chosen_track)
    # Toggle fullscreen here if desired for the conference machines.
    root.attributes('-fullscreen', False)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass