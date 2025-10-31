# --------------------------------------------------------------
#  GrokMIDI Pro – P2P Edit, Grokify, Drums, Undo/Redo
# --------------------------------------------------------------
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json, os, tempfile, threading, time, random, re
from midiutil import MIDIFile
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, Rectangle
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# -------------------  NOTE HELPERS  -------------------
NOTE_MAP = {'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}
ACC_MAP  = {'#':1, 'B':-1, 'b':-1}
DRUM_MAP = {'K':35, 'S':38, 'H':42}  # Kick, Snare, Hi-hat

def midi_from_str(note_str, c_scale):
    if note_str.upper() == 'R': return None
    if note_str[0].upper() in DRUM_MAP: return DRUM_MAP[note_str[0].upper()]
    letter = note_str[0].upper()
    mod = note_str[1:].lower()
    base = NOTE_MAP[letter]
    if mod and mod[0] in ACC_MAP: base += ACC_MAP[mod[0]]
    base = base % 12
    return c_scale + base

def staff_pos(letter, c_scale):
    if letter in DRUM_MAP: return 6  # middle line for drums
    octave = c_scale // 12
    return NOTE_MAP[letter.upper()] + (octave - 4) * 7

def accidental_sym(note_str):
    if len(note_str)>1 and note_str[1] in '#Bb':
        return '#' if note_str[1]=='#' else 'b'
    return ''

def get_duration(val):
    d = {'1s':4,'2':2,'4s':1,'8s':.5,'16s':.25,'32s':.125}
    return d.get(val,1)

def extract_program(combo_text):
    m = re.search(r'\((\d+)\)', combo_text)
    return int(m.group(1)) if m else 0

# -------------------  CHORD & GROKIFY  -------------------
CHORD_LIB = {
    "C":  ["C","E","G"],     "Cm": ["C","Eb","G"],
    "C7": ["C","E","G","Bb"], "Cm7":["C","Eb","G","Bb"],
    "D":  ["D","F#","A"],    "Dm": ["D","F","A"],
    "G":  ["G","B","D"],     "Gm": ["G","Bb","D"],
    "Am": ["A","C","E"],     "A7": ["A","C#","E","G"],
    "F":  ["F","A","C"],     "Fm": ["F","Ab","C"]
}

def grokify_riff():
    notes = []
    length = random.randint(4, 8)
    for _ in range(length):
        if random.random() < 0.15:
            notes.append('R')
        elif random.random() < 0.3:
            chord = random.choice(list(CHORD_LIB.values()))
            notes.append('+'.join(chord))
        else:
            letter = random.choice('CDEFGAB')
            if random.random() < 0.3:
                letter += random.choice(['#','b'])
            notes.append(letter)
    return ' '.join(notes)

# -------------------  P2P EDITOR  -------------------
class P2PStaffEditor(tk.Toplevel):
    def __init__(self, parent, card):
        super().__init__(parent)
        self.card = card
        self.title("P2P Edit")
        self.geometry("800x300")
        self.notes = card.riff['notes'].copy()
        self.fig, self.ax = plt.subplots(figsize=(10,3))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.mpl_connect('button_press_event', self.on_click)
        self.draw_staff()
        btn = tk.Button(self, text="Done", command=self.done)
        btn.pack(pady=5)

    def draw_staff(self):
        ax = self.ax; ax.clear()
        for y in range(2,11,2): ax.axhline(y, color='k', lw=1)
        ax.text(0.2,7,'G',fontsize=40,va='center')
        x = 1.0
        for ng in self.notes:
            if ng.upper()=='R':
                ax.text(x,6,'rest',fontsize=12,ha='center')
                x += 1.2; continue
            subs = ng.split('+')
            ys = []
            for s in subs:
                let = s[0].upper()
                y = staff_pos(let, self.card.riff['c_scale'])
                ys.append(y)
                acc = accidental_sym(s)
                if acc: ax.text(x-0.3, y, acc, fontsize=12, ha='center')
            for y in ys:
                ax.add_patch(Ellipse((x,y),0.7,0.5,facecolor='k',edgecolor='k'))
            if len(subs)>1:
                ax.vlines(x+0.35, min(ys), max(ys)+2.5, color='k', lw=1.5)
            x += 1.2
        for gx in range(1,30): ax.axvline(gx, ymin=0.1, ymax=0.9, color='gray', lw=0.5, alpha=0.3)
        ax.set_xlim(0,30); ax.set_ylim(0,12); ax.axis('off')
        self.canvas.draw()

    def on_click(self, event):
        if not event.inaxes: return
        x = round(event.xdata)
        y = round(event.ydata)
        if y < 2 or y > 10: return
        rel = y - 6
        oct_offset = rel // 7
        step = rel % 7
        letters = 'CDEFGAB'
        letter = letters[step] if step>=0 else letters[step+7]
        note = letter
        if x < len(self.notes):
            self.notes[x] = note
        else:
            self.notes.append(note)
        self.draw_staff()

    def done(self):
        self.card.riff['notes'] = self.notes
        self.card.entry.delete(0,tk.END)
        self.card.entry.insert(0,' '.join(self.notes))
        self.card.draw_staff()
        self.card.app.update_full_sheet()
        self.destroy()

# -------------------  CARD CLASS  -------------------
class RiffCard(tk.Frame):
    def __init__(self, master, track, card_idx, app):
        super().__init__(master, relief=tk.RAISED, bd=2, bg="#f8f8f8")
        self.app = app
        self.track = track
        self.idx = card_idx
        self.riff = {'notes':[], 'duration':'4s', 'c_scale':60, 'strum':False}
        self.history = []
        self.redo_stack = []

        # Staff
        self.fig, self.ax = plt.subplots(figsize=(3.2,1.2))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Controls
        ctrl = tk.Frame(self); ctrl.pack(fill=tk.X, pady=2)
        self.entry = tk.Entry(ctrl, width=25); self.entry.pack(side=tk.LEFT, padx=2)
        self.entry.bind('<Return>', lambda e: self.save_riff())

        self.strum_var = tk.BooleanVar()
        tk.Checkbutton(ctrl, text="Strum", variable=self.strum_var).pack(side=tk.LEFT)

        tk.Button(ctrl, text="Chords", command=lambda: chord_popup(self.entry)).pack(side=tk.LEFT, padx=2)
        tk.Button(ctrl, text="P2P Edit", command=self.p2p_edit).pack(side=tk.LEFT, padx=2)
        tk.Button(ctrl, text="Grokify", command=self.grokify).pack(side=tk.LEFT, padx=2)
        tk.Button(ctrl, text="Save", command=self.save_riff).pack(side=tk.LEFT, padx=2)

        self.draw_staff(empty=True)

    def save_state(self):
        state = self.riff.copy()
        state['text'] = self.entry.get()
        state['strum'] = self.strum_var.get()
        self.history.append(state)
        self.redo_stack.clear()

    def undo(self):
        if len(self.history) > 1:
            self.redo_stack.append(self.history.pop())
            prev = self.history[-1]
            self.riff.update(prev)
            self.entry.delete(0,tk.END)
            self.entry.insert(0, prev['text'])
            self.strum_var.set(prev['strum'])
            self.draw_staff()
            self.app.update_full_sheet()

    def redo(self):
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.history.append(state)
            self.riff.update(state)
            self.entry.delete(0,tk.END)
            self.entry.insert(0, state['text'])
            self.strum_var.set(state['strum'])
            self.draw_staff()
            self.app.update_full_sheet()

    def p2p_edit(self):
        self.save_state()
        P2PStaffEditor(self, self)

    def grokify(self):
        self.save_state()
        riff = grokify_riff()
        self.entry.delete(0,tk.END)
        self.entry.insert(0, riff)
        self.save_riff()

    def draw_staff(self, empty=False):
        ax = self.ax; ax.clear()
        for y in range(2,11,2): ax.axhline(y, color='k', lw=1)
        ax.text(0.1,7,'G',fontsize=20,va='center')
        if empty:
            ax.text(1.5,6,"empty",ha='center',fontsize=10)
        else:
            x = 0.8
            dur = get_duration(self.riff['duration'])
            is_drum = self.app.tracks[self.track].inst_combo.get().startswith('Acoustic Bass Drum')
            for ng in self.riff['notes']:
                if ng.upper()=='R':
                    ax.text(x,6,'rest',fontsize=9,ha='center')
                    x += dur*0.6; continue
                subs = ng.split('+')
                if is_drum:
                    for s in subs:
                        sym = 'X' if s[0].upper()=='S' else 'o'
                        ax.text(x,6,sym,fontsize=14,ha='center',va='center')
                    x += dur*0.6; continue
                ys,accs = [],[]
                for s in subs:
                    let = s[0].upper()
                    y = staff_pos(let, self.riff['c_scale'])
                    ys.append(y); accs.append(accidental_sym(s))
                for i,acc in enumerate(accs):
                    if acc: ax.text(x-0.2, ys[i], acc, fontsize=9, ha='center')
                fill = dur<=1
                for y in ys:
                    ax.add_patch(Ellipse((x,y),0.35,0.25,
                                        facecolor='k' if fill else 'w',
                                        edgecolor='k'))
                if dur<4 and len(subs)>1:
                    ax.vlines(x+0.15, min(ys), max(ys)+1.5, color='k', lw=1)
                x += dur*0.6
        ax.set_xlim(0,3.5); ax.set_ylim(0,12); ax.axis('off')
        self.canvas.draw()

    def save_riff(self):
        self.save_state()
        txt = self.entry.get().strip()
        if not txt: return
        notes = txt.split()
        self.riff['notes'] = notes
        self.riff['duration'] = '4s'
        self.riff['strum'] = self.strum_var.get()
        self.app.song_data[self.track][self.idx] = self.riff.copy()
        self.draw_staff()
        self.app.update_full_sheet()

# -------------------  TRACK ROW  -------------------
class TrackRow(tk.Frame):
    def __init__(self, master, track_idx, app):
        super().__init__(master)
        self.app = app
        self.idx = track_idx

        inst_frame = tk.Frame(self, width=120); inst_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        tk.Label(inst_frame, text="Instrument:", anchor='w').pack(fill=tk.X)
        self.inst_combo = ttk.Combobox(inst_frame,
                    values=[
                        'Acoustic Grand Piano (0)',
                        'Electric Guitar (clean) (27)',
                        'Electric Bass (finger) (33)',
                        'Violin (40)',
                        'Acoustic Bass Drum (35)'
                    ],
                    state="readonly")
        self.inst_combo.current(track_idx % 5)
        self.inst_combo.pack(fill=tk.X, pady=2)
        self.inst_combo.bind('<<ComboboxSelected>>', lambda e: app.update_full_sheet())

        tk.Label(inst_frame, text="C-Scale:", anchor='w').pack(fill=tk.X)
        c_options = [f"C{i} ({12*i})" for i in range(1,9)]
        self.c_combo = ttk.Combobox(inst_frame, values=c_options, state="readonly", width=10)
        self.c_combo.current(3)
        self.c_combo.pack(fill=tk.X, pady=2)
        self.c_combo.bind('<<ComboboxSelected>>', self.update_c_scale)

        self.card_frame = tk.Frame(self); self.card_frame.pack(side=tk.LEFT, expand=True, fill=tk.X)
        for i in range(3):
            card = RiffCard(self.card_frame, track_idx, i, app)
            card.pack(side=tk.LEFT, padx=3, fill=tk.BOTH, expand=True)
            app.song_data[track_idx][i] = card.riff

    def update_c_scale(self, event=None):
        c_text = self.c_combo.get()
        c_midi = int(c_text.split('(')[1][:-1])
        for card in self.card_frame.winfo_children():
            if isinstance(card, RiffCard):
                card.riff['c_scale'] = c_midi
                card.draw_staff()

# -------------------  MAIN APP  -------------------
class CardWriterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GrokMIDI Pro")
        self.song_data = [[{'notes':[], 'duration':'4s', 'c_scale':60, 'strum':False} for _ in range(3)] for _ in range(4)]
        self.current_card = None

        # Menu
        menubar = tk.Menu(root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="New", command=self.new_song)
        filemenu.add_command(label="Open", command=self.open_song)
        filemenu.add_command(label="Save", command=self.save_song)
        filemenu.add_separator()
        filemenu.add_command(label="Undo", command=self.undo)
        filemenu.add_command(label="Redo", command=self.redo)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=root.quit)
        menubar.add_cascade(label="File", menu=filemenu)
        root.config(menu=menubar)

        self.track_frame = tk.Frame(root); self.track_frame.pack(pady=10, fill=tk.BOTH, expand=True)
        self.tracks = []
        for i in range(4):
            self.add_track(i)

        tk.Button(root, text="+ Add Instrument", command=self.add_new_track).pack(pady=5)

        ctrl = tk.Frame(root); ctrl.pack(pady=5)
        tk.Label(ctrl, text="Global BPM:").pack(side=tk.LEFT)
        self.global_bpm = tk.Entry(ctrl, width=6); self.global_bpm.insert(0,"120")
        self.global_bpm.pack(side=tk.LEFT, padx=5)

        acts = tk.Frame(root); acts.pack(pady=5)
        tk.Button(acts, text="Preview MIDI", command=self.preview_midi).pack(side=tk.LEFT, padx=3)
        tk.Button(acts, text="Stop", command=self.stop_midi).pack(side=tk.LEFT, padx=3)
        tk.Button(acts, text="Export MIDI", command=self.export_midi).pack(side=tk.LEFT, padx=3)
        tk.Button(acts, text="Export PDF", command=self.export_pdf).pack(side=tk.LEFT, padx=3)

        self.sheet_fig, self.sheet_ax = plt.subplots(figsize=(12,5))
        self.sheet_canvas = FigureCanvasTkAgg(self.sheet_fig, master=root)
        self.sheet_canvas.get_tk_widget().pack(pady=10, fill=tk.BOTH, expand=True)
        self.update_full_sheet()

    def add_track(self, idx):
        row = TrackRow(self.track_frame, idx, self)
        row.pack(fill=tk.X, pady=5)
        self.tracks.append(row)

    def add_new_track(self):
        idx = len(self.tracks)
        self.song_data.append([{'notes':[], 'duration':'4s', 'c_scale':60, 'strum':False} for _ in range(3)])
        self.add_track(idx)

    def undo(self):
        if self.current_card: self.current_card.undo()

    def redo(self):
        if self.current_card: self.current_card.redo()

    def update_full_sheet(self):
        ax = self.sheet_ax; ax.clear()
        for y in range(2,11,2): ax.axhline(y, color='k', lw=1)
        ax.text(0.2,7,'G',fontsize=40,va='center')
        ax.text(1.2,9,'4',fontsize=20,ha='center'); ax.text(1.2,5,'4',fontsize=20,ha='center')
        x = 2.0
        for track in self.tracks:
            prog = extract_program(track.inst_combo.get())
            c_scale = int(track.c_combo.get().split('(')[1][:-1])
            is_drum = prog == 35
            for card in track.card_frame.winfo_children():
                if not isinstance(card, RiffCard): continue
                riff = card.riff
                if not riff['notes']: continue
                dur = get_duration(riff['duration'])
                for ng in riff['notes']:
                    if ng.upper()=='R':
                        ax.text(x,6,'rest',fontsize=12,ha='center')
                        x += dur*0.8; continue
                    if is_drum:
                        for s in ng.split('+'):
                            sym = 'X' if s[0].upper()=='S' else 'o'
                            ax.text(x,6,sym,fontsize=14,ha='center',va='center')
                        x += dur*0.8; continue
                    subs = ng.split('+')
                    ys = [staff_pos(s[0].upper(), c_scale) for s in subs]
                    for i, s in enumerate(subs):
                        acc = accidental_sym(s)
                        if acc: ax.text(x-0.3, ys[i], acc, fontsize=12, ha='center')
                        ax.add_patch(Ellipse((x,ys[i]),0.7,0.5, facecolor='k', edgecolor='k'))
                    if dur<4 and len(subs)>1:
                        ax.vlines(x+0.35, min(ys), max(ys)+2.5, color='k', lw=1.5)
                    x += dur*0.8
            x += 1.5
        ax.set_xlim(0, max(x+2,15)); ax.set_ylim(0,12); ax.axis('off')
        self.sheet_canvas.draw()

    # ---------- MIDI ----------
    def preview_midi(self):
        threading.Thread(target=self._play_midi, daemon=True).start()

    def _play_midi(self):
        try:
            tf = tempfile.NamedTemporaryFile(suffix='.mid', delete=False)
            midi = MIDIFile(len(self.tracks))
            global_bpm = int(self.global_bpm.get() or 120)
            for t_idx, track in enumerate(self.tracks):
                prog = extract_program(track.inst_combo.get())
                midi.addTrackName(t_idx, 0, track.inst_combo.get().split(' (')[0])
                midi.addTempo(t_idx, 0, global_bpm)
                midi.addProgramChange(t_idx, 0, 0, prog)
                c_scale = int(track.c_combo.get().split('(')[1][:-1])
                time_pos = 0
                for card in track.card_frame.winfo_children():
                    if not isinstance(card, RiffCard): continue
                    riff = card.riff
                    if not riff['notes']: continue
                    dur = get_duration(riff['duration'])
                    strum = riff.get('strum', False)
                    delay = 0.03 if strum else 0
                    for ng in riff['notes']:
                        if ng.upper()=='R':
                            time_pos += dur; continue
                        subs = ng.split('+')
                        pitches = [midi_from_str(s, c_scale) for s in subs]
                        for j, p in enumerate(pitches):
                            if p is None: continue
                            offset = delay * j
                            midi.addNote(t_idx, 9 if prog==35 else 0, p, time_pos + offset, dur, 100)
                        time_pos += dur
            midi.writeFile(tf); tf.close()
            import pygame
            pygame.mixer.init()
            pygame.mixer.music.load(tf.name)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy(): time.sleep(0.1)
            os.unlink(tf.name)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def stop_midi(self):
        import pygame
        pygame.mixer.music.stop()

    def export_midi(self):
        path = filedialog.asksaveasfilename(defaultextension=".mid")
        if not path: return
        midi = MIDIFile(len(self.tracks))
        global_bpm = int(self.global_bpm.get() or 120)
        for t_idx, track in enumerate(self.tracks):
            prog = extract_program(track.inst_combo.get())
            midi.addTrackName(t_idx, 0, track.inst_combo.get().split(' (')[0])
            midi.addTempo(t_idx, 0, global_bpm)
            midi.addProgramChange(t_idx, 0, 0, prog)
            c_scale = int(track.c_combo.get().split('(')[1][:-1])
            time_pos = 0
            for card in track.card_frame.winfo_children():
                if not isinstance(card, RiffCard): continue
                riff = card.riff
                if not riff['notes']: continue
                dur = get_duration(riff['duration'])
                strum = riff.get('strum', False)
                delay = 0.03 if strum else 0
                for ng in riff['notes']:
                    if ng.upper()=='R':
                        time_pos += dur; continue
                    subs = ng.split('+')
                    pitches = [midi_from_str(s, c_scale) for s in subs]
                    for j, p in enumerate(pitches):
                        if p is None: continue
                        offset = delay * j
                        midi.addNote(t_idx, 9 if prog==35 else 0, p, time_pos + offset, dur, 100)
                    time_pos += dur
        with open(path, 'wb') as f: midi.writeFile(f)
        messagebox.showinfo("Saved", f"MIDI → {path}")

    def export_pdf(self):
        path = filedialog.asksaveasfilename(defaultextension=".pdf")
        if not path: return
        fig, ax = plt.subplots(figsize=(12,6))
        for y in range(2,11,2): ax.axhline(y, color='k', lw=1)
        ax.text(0.2,7,'G',fontsize=40,va='center')
        ax.text(1.2,9,'4',fontsize=20,ha='center'); ax.text(1.2,5,'4',fontsize=20,ha='center')
        x = 2.0
        for track in self.tracks:
            c_scale = int(track.c_combo.get().split('(')[1][:-1])
            prog = extract_program(track.inst_combo.get())
            is_drum = prog == 35
            for card in track.card_frame.winfo_children():
                if not isinstance(card, RiffCard): continue
                riff = card.riff
                if not riff['notes']: continue
                dur = get_duration(riff['duration'])
                for ng in riff['notes']:
                    if ng.upper()=='R':
                        ax.text(x,6,'rest',fontsize=12,ha='center')
                        x += dur*0.8; continue
                    if is_drum:
                        for s in ng.split('+'):
                            sym = 'X' if s[0].upper()=='S' else 'o'
                            ax.text(x,6,sym,fontsize=14,ha='center',va='center')
                        x += dur*0.8; continue
                    subs = ng.split('+')
                    ys = [staff_pos(s[0].upper(), c_scale) for s in subs]
                    for i, s in enumerate(subs):
                        acc = accidental_sym(s)
                        if acc: ax.text(x-0.3, ys[i], acc, fontsize=12, ha='center')
                        ax.add_patch(Ellipse((x,ys[i]),0.7,0.5, facecolor='k', edgecolor='k'))
                    if dur<4 and len(subs)>1:
                        ax.vlines(x+0.35, min(ys), max(ys)+2.5, color='k', lw=1.5)
                    x += dur*0.8
            x += 1.5
        ax.set_xlim(0, max(x+2,15)); ax.set_ylim(0,12); ax.axis('off')
        fig.savefig(path, bbox_inches='tight')
        plt.close(fig)
        messagebox.showinfo("Saved", f"PDF → {path}")

    def new_song(self):
        if messagebox.askyesno("New","Discard?"):
            self.song_data = [[{'notes':[], 'duration':'4s', 'c_scale':60, 'strum':False} for _ in range(3)] for _ in range(4)]
            for track in self.tracks:
                for card in track.card_frame.winfo_children():
                    if isinstance(card, RiffCard):
                        card.riff.update(self.song_data[track.idx][card.idx])
                        card.entry.delete(0,tk.END)
                        card.history.clear()
                        card.redo_stack.clear()
                        card.draw_staff(empty=True)
            self.update_full_sheet()

    def open_song(self):
        path = filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if not path: return
        with open(path) as f: data = json.load(f)
        self.song_data = data['tracks']
        self.global_bpm.delete(0,tk.END); self.global_bpm.insert(0,str(data.get('bpm',120)))
        for t, track in enumerate(self.tracks):
            prog = self.song_data[t][0].get('instrument', extract_program(track.inst_combo.get()))
            opts = track.inst_combo['values']
            match = next((o for o in opts if f"({prog})" in o), opts[0])
            track.inst_combo.set(match)
            c_val = next((c for c in track.c_combo['values'] if f"({self.song_data[t][0]['c_scale']})" in c), "C4 (60)")
            track.c_combo.set(c_val)
            for i, card in enumerate(track.card_frame.winfo_children()):
                if isinstance(card, RiffCard):
                    card.riff.update(self.song_data[t][i])
                    card.entry.delete(0,tk.END)
                    card.entry.insert(0,' '.join(self.song_data[t][i]['notes']))
                    card.strum_var.set(self.song_data[t][i].get('strum',False))
                    card.history.clear()
                    card.redo_stack.clear()
                    card.draw_staff()
        self.update_full_sheet()

    def save_song(self):
        path = filedialog.asksaveasfilename(defaultextension=".json")
        if not path: return
        payload = {'bpm': int(self.global_bpm.get() or 120), 'tracks': self.song_data}
        with open(path,'w') as f: json.dump(payload, f, indent=2)
        messagebox.showinfo("Saved", f"Song → {path}")

# ------------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = CardWriterApp(root)
    root.bind('<Control-z>', lambda e: app.undo())
    root.bind('<Control-y>', lambda e: app.redo())
    root.mainloop()