import tkinter as tk
from tkinter import ttk, messagebox
from midiutil import MIDIFile
import pygame
import threading
import tempfile
import os
import time
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Note to MIDI number mapping
def get_midi_note(note_str, octave):
    note_str_upper = note_str.upper()
    if note_str_upper == 'R':
        return None  # Rest note
    
    letter = note_str[0].upper()
    modifier = note_str[1:].lower()
    
    if letter not in 'ABCDEFG':
        raise ValueError(f"Invalid note letter: {letter}")
    
    if modifier and modifier not in ('#', 'b', '%'):
        raise ValueError(f"Invalid modifier: {modifier}")
    
    note_map = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
    base = note_map[letter]
    
    if modifier == '#':
        base += 1
    elif modifier in ('b', '%'):
        base -= 1
    
    base = base % 12
    return (octave + 1) * 12 + base

# Staff position for diatonic note
def get_staff_position(letter, octave):
    pos_map = {'C': 0, 'D': 1, 'E': 2, 'F': 3, 'G': 4, 'A': 5, 'B': 6}
    return pos_map[letter] + (octave - 4) * 7

# Get accidental symbol
def get_accidental(note_str):
    if len(note_str) > 1:
        mod = note_str[1].lower()
        if mod == '#':
            return '#'
        elif mod in ('b', '%'):
            return '♭'
    return ''

# Duration mapping
def get_duration(value):
    durations = {'1s': 4, '2': 2, '4s': 1, '8s': 0.5, '16s': 0.25, '32s': 0.125}
    return durations.get(value, 1)

class MidiWriterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Custom MIDI Writer")
        
        self.riffs = []
        self.editing_index = None
        self.preview_thread = None
        
        self.new_riff_button = tk.Button(root, text="New Riff", command=self.add_new_riff)
        self.new_riff_button.pack(pady=10)
        
        self.input_frame = tk.Frame(root)
        
        tk.Label(self.input_frame, text="Enter notes (e.g., A# B Bb R A+B+E):").pack(side=tk.LEFT)
        self.notes_entry = tk.Entry(self.input_frame, width=30)
        self.notes_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Label(self.input_frame, text="Duration:").pack(side=tk.LEFT)
        self.duration_combo = ttk.Combobox(self.input_frame, values=['1s', '2', '4s', '8s', '16s', '32s'], state="readonly")
        self.duration_combo.current(2)
        self.duration_combo.pack(side=tk.LEFT, padx=5)
        
        tk.Label(self.input_frame, text="Octave:").pack(side=tk.LEFT)
        self.octave_options = ['Low (2)', 'Mid-low (3)', 'Middle (4)', 'Mid-high (5)', 'High (6)', 'Very High (7)']
        self.octave_combo = ttk.Combobox(self.input_frame, values=self.octave_options, state="readonly")
        self.octave_combo.current(2)
        self.octave_combo.pack(side=tk.LEFT, padx=5)
        
        tk.Label(self.input_frame, text="Instrument:").pack(side=tk.LEFT)
        self.instrument_options = [
            'Acoustic Grand Piano (0)',
            'Bright Acoustic Piano (1)',
            'Electric Guitar (clean) (27)',
            'Violin (40)',
            'Synth Drum (118)'
        ]
        self.instrument_combo = ttk.Combobox(self.input_frame, values=self.instrument_options, state="readonly")
        self.instrument_combo.current(0)
        self.instrument_combo.pack(side=tk.LEFT, padx=5)
        
        self.add_button = tk.Button(self.input_frame, text="Add Riff", command=self.save_riff)
        self.add_button.pack(side=tk.LEFT, padx=5)
        
        self.song_list = tk.Listbox(root, height=10, width=70)
        self.song_list.pack(pady=10)
        
        self.manage_frame = tk.Frame(root)
        self.edit_button = tk.Button(self.manage_frame, text="Edit Selected", command=self.edit_riff)
        self.edit_button.pack(side=tk.LEFT, padx=5)
        self.delete_button = tk.Button(self.manage_frame, text="Delete Selected", command=self.delete_riff)
        self.delete_button.pack(side=tk.LEFT, padx=5)
        self.manage_frame.pack(pady=5)
        
        tk.Label(root, text="BPM:").pack()
        self.bpm_entry = tk.Entry(root, width=10)
        self.bpm_entry.insert(0, "120")
        self.bpm_entry.pack(pady=5)
        
        tk.Label(root, text="MIDI File Name (e.g., my_song.mid):").pack()
        self.file_name_entry = tk.Entry(root, width=30)
        self.file_name_entry.insert(0, "song.mid")
        self.file_name_entry.pack(pady=5)
        
        self.button_frame = tk.Frame(root)
        self.preview_button = tk.Button(self.button_frame, text="Preview MIDI", command=self.preview_riffs)
        self.preview_button.pack(side=tk.LEFT, padx=5)
        self.stop_button = tk.Button(self.button_frame, text="Stop Preview", command=self.stop_preview)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        self.sheet_preview_button = tk.Button(self.button_frame, text="Preview Sheet", command=self.preview_sheet)
        self.sheet_preview_button.pack(side=tk.LEFT, padx=5)
        self.export_button = tk.Button(self.button_frame, text="Export MIDI", command=self.export_midi)
        self.export_button.pack(side=tk.LEFT, padx=5)
        self.export_sheet_button = tk.Button(self.button_frame, text="Export Sheet PDF", command=self.export_sheet)
        self.export_sheet_button.pack(side=tk.LEFT, padx=5)
        self.button_frame.pack(pady=10)
    
    def add_new_riff(self):
        self.editing_index = None
        self.add_button.config(text="Add Riff", command=self.save_riff)
        self.notes_entry.delete(0, tk.END)
        self.duration_combo.current(2)
        self.octave_combo.current(2)
        self.instrument_combo.current(0)
        self.input_frame.pack(pady=10)
        self.new_riff_button.config(state=tk.DISABLED)
    
    def save_riff(self):
        self._save_or_update_riff(add_new=True)
    
    def update_riff(self):
        self._save_or_update_riff(add_new=False)
    
    def _save_or_update_riff(self, add_new):
        notes_str = self.notes_entry.get().strip()
        if not notes_str:
            messagebox.showerror("Error", "Enter some notes!")
            return
        
        duration = self.duration_combo.get()
        octave_str = self.octave_combo.get()
        octave = int(octave_str.split('(')[1][0])
        instrument_str = self.instrument_combo.get()
        instrument = int(instrument_str.split('(')[1][:-1])
        
        notes = notes_str.split()
        for note_group in notes:
            if note_group.upper() == 'R':
                continue
            sub_notes = note_group.split('+')
            for sub in sub_notes:
                letter = sub[0].upper()
                if letter not in 'ABCDEFG':
                    messagebox.showerror("Error", f"Invalid note letter: {letter} in {sub}")
                    return
                if len(sub) > 1:
                    mod = sub[1].lower()
                    if mod not in ('#', 'b', '%'):
                        messagebox.showerror("Error", f"Invalid modifier: {mod} in {sub}")
                        return
                if len(sub) > 2:
                    messagebox.showerror("Error", f"Note too long: {sub}")
                    return
        
        riff = {'notes': notes, 'duration': duration, 'octave': octave, 'instrument': instrument}
        
        riff_desc = f"Riff: {notes_str} - {duration} - Octave {octave} - Instrument {instrument}"
        
        if add_new or self.editing_index is None:
            self.riffs.append(riff)
            self.song_list.insert(tk.END, riff_desc)
        else:
            index = self.editing_index
            self.riffs[index] = riff
            self.song_list.delete(index)
            self.song_list.insert(index, riff_desc)
            self.add_button.config(text="Add Riff", command=self.save_riff)
            self.editing_index = None
        
        self.notes_entry.delete(0, tk.END)
        self.input_frame.pack_forget()
        self.new_riff_button.config(state=tk.NORMAL)
    
    def edit_riff(self):
        try:
            index = self.song_list.curselection()[0]
            riff = self.riffs[index]
            
            self.editing_index = index
            self.add_button.config(text="Update Riff", command=self.update_riff)
            
            self.notes_entry.delete(0, tk.END)
            self.notes_entry.insert(0, ' '.join(riff['notes']))
            self.duration_combo.set(riff['duration'])
            
            octave_opt = [opt for opt in self.octave_options if f"({riff['octave']})" in opt][0]
            self.octave_combo.set(octave_opt)
            
            instrument_opt = [opt for opt in self.instrument_options if f"({riff['instrument']})" in opt][0]
            self.instrument_combo.set(instrument_opt)
            
            self.input_frame.pack(pady=10)
            self.new_riff_button.config(state=tk.DISABLED)
        except IndexError:
            messagebox.showerror("Error", "Select a riff to edit!")
    
    def delete_riff(self):
        try:
            index = self.song_list.curselection()[0]
            del self.riffs[index]
            self.song_list.delete(index)
        except IndexError:
            messagebox.showerror("Error", "Select a riff to delete!")
    
    def preview_riffs(self):
        if not self.riffs:
            messagebox.showerror("Error", "No riffs to preview!")
            return
        
        if self.preview_thread and self.preview_thread.is_alive():
            messagebox.showinfo("Info", "Preview already playing!")
            return
        
        self.preview_thread = threading.Thread(target=self._play_preview)
        self.preview_thread.start()
    
    def _play_preview(self):
        try:
            tempo = int(self.bpm_entry.get())
            
            with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as temp_file:
                midi = MIDIFile(1)
                track = 0
                channel = 0
                time_pos = 0
                volume = 100
                
                midi.addTempo(track, time_pos, tempo)
                
                current_instrument = None
                for riff in self.riffs:
                    if riff['instrument'] != current_instrument:
                        midi.addProgramChange(track, channel, time_pos, riff['instrument'])
                        current_instrument = riff['instrument']
                    
                    dur = get_duration(riff['duration'])
                    for note_group in riff['notes']:
                        if note_group.upper() == 'R':
                            time_pos += dur
                            continue
                        sub_notes = note_group.split('+')
                        pitches = [get_midi_note(sub, riff['octave']) for sub in sub_notes]
                        for pitch in pitches:
                            midi.addNote(track, channel, pitch, time_pos, dur, volume)
                        time_pos += dur
                
                midi.writeFile(temp_file)
                temp_file_path = temp_file.name
            
            total_beats = sum(get_duration(r['duration']) * len(r['notes']) for r in self.riffs)
            total_seconds = total_beats * (60 / tempo) + 2
            
            pygame.init()
            pygame.mixer.init()
            pygame.mixer.music.load(temp_file_path)
            pygame.mixer.music.play()
            
            time.sleep(total_seconds)
            
            pygame.mixer.music.stop()
            pygame.quit()
            
            os.remove(temp_file_path)
            
            messagebox.showinfo("Success", "Preview finished!")
        except Exception as e:
            messagebox.showerror("Error", f"Preview failed: {str(e)}")
        finally:
            self.preview_thread = None
    
    def stop_preview(self):
        if pygame.get_init():
            pygame.mixer.music.stop()
    
    def export_midi(self):
        if not self.riffs:
            messagebox.showerror("Error", "No riffs added!")
            return
        
        file_name = self.file_name_entry.get().strip()
        if not file_name.endswith('.mid'):
            file_name += '.mid'
        if not file_name:
            file_name = 'song.mid'
        
        try:
            tempo = int(self.bpm_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid BPM!")
            return
        
        midi = MIDIFile(1)
        track = 0
        channel = 0
        time_pos = 0
        volume = 100
        
        midi.addTempo(track, time_pos, tempo)
        
        current_instrument = None
        for riff in self.riffs:
            if riff['instrument'] != current_instrument:
                midi.addProgramChange(track, channel, time_pos, riff['instrument'])
                current_instrument = riff['instrument']
            
            dur = get_duration(riff['duration'])
            for note_group in riff['notes']:
                if note_group.upper() == 'R':
                    time_pos += dur
                    continue
                sub_notes = note_group.split('+')
                pitches = [get_midi_note(sub, riff['octave']) for sub in sub_notes]
                for pitch in pitches:
                    midi.addNote(track, channel, pitch, time_pos, dur, volume)
                time_pos += dur
        
        try:
            with open(file_name, "wb") as output_file:
                midi.writeFile(output_file)
            messagebox.showinfo("Success", f"MIDI file '{file_name}' created successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save MIDI: {str(e)}")
    
    def preview_sheet(self):
        if not self.riffs:
            messagebox.showerror("Error", "No riffs to preview!")
            return
        
        fig, ax = self._generate_sheet_figure()
        
        sheet_win = tk.Toplevel(self.root)
        sheet_win.title("Sheet Music Preview")
        
        canvas = FigureCanvasTkAgg(fig, master=sheet_win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def export_sheet(self):
        if not self.riffs:
            messagebox.showerror("Error", "No riffs added!")
            return
        
        file_name = self.file_name_entry.get().strip()
        if file_name.endswith('.mid'):
            file_name = file_name[:-4]
        pdf_name = file_name + '.pdf'
        
        fig, ax = self._generate_sheet_figure()
        try:
            fig.savefig(pdf_name)
            messagebox.showinfo("Success", f"Sheet music PDF '{pdf_name}' created successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save PDF: {str(e)}")
        finally:
            plt.close(fig)
    
    def _generate_sheet_figure(self):
        fig, ax = plt.subplots(figsize=(12, 4))
        
        # Draw staff lines
        staff_ys = [2, 4, 6, 8, 10]
        for sy in staff_ys:
            ax.axhline(sy, color='black', linewidth=1)
        
        # Treble clef
        ax.text(0, 7, '𝄞', fontsize=40, va='center')
        
        # Time signature 4/4
        ax.text(1.5, 9, '4', fontsize=20, va='center')
        ax.text(1.5, 5, '4', fontsize=20, va='center')
        
        x_pos = 3.0
        beat_pos = 0.0
        scale_x = 2.0  # x units per beat
        bar_beat = 4.0  # assuming 4/4
        
        for riff in self.riffs:
            dur = get_duration(riff['duration'])
            for note_group in riff['notes']:
                if note_group.upper() == 'R':
                    # Draw rest (approximate quarter rest symbol)
                    ax.text(x_pos, 6, '𝄽', fontsize=20, ha='center', va='center')
                    beat_pos += dur
                    x_pos += dur * scale_x
                    continue
                
                sub_notes = note_group.split('+')
                ys = []
                accidentals = []
                for sub in sub_notes:
                    letter = sub[0].upper()
                    acc = get_accidental(sub)
                    y = get_staff_position(letter, riff['octave'])
                    ys.append(y)
                    accidentals.append(acc)
                
                # Draw accidentals
                acc_x = x_pos - 0.5
                for i, acc in enumerate(accidentals):
                    if acc:
                        ax.text(acc_x, ys[i], acc, fontsize=15, ha='center', va='center')
                
                # Determine note head style (simple: filled for <=1 beat, open for >1)
                fill = dur <= 1
                edgecolor = 'black' if fill else 'black'
                facecolor = 'black' if fill else 'white'
                
                # Draw note heads
                for y in ys:
                    ax.add_patch(Ellipse((x_pos, y), width=0.8, height=0.6, facecolor=facecolor, edgecolor=edgecolor))
                
                # Draw stem if not whole note
                if dur < 4:
                    if len(ys) > 1:
                        # Chord stem
                        stem_y_min = min(ys)
                        stem_y_max = max(ys)
                        ax.vlines(x_pos + 0.4, stem_y_min, stem_y_max + 3, color='black', linewidth=2)
                    elif len(ys) == 1:
                        # Single note stem
                        ax.vlines(x_pos + 0.4, ys[0], ys[0] + 3, color='black', linewidth=2)
                
                # Ledger lines
                for y in ys:
                    if y < 2:
                        for ly in range(int(y // 2 * 2) + 2 if y % 2 else int(y // 2 * 2), 2, 2):
                            ax.axhline(ly, x_pos - 0.6, x_pos + 0.6, color='black', linewidth=1)
                    if y > 10:
                        for ly in range(12, int(y // 2 * 2) + (2 if y % 2 else 0), 2):
                            ax.axhline(ly, x_pos - 0.6, x_pos + 0.6, color='black', linewidth=1)
                
                beat_pos += dur
                x_pos += dur * scale_x
                
                # Draw bar line if beat_pos is multiple of bar_beat
                if beat_pos % bar_beat == 0:
                    ax.axvline(x_pos - 0.5, 1, 11, color='black', linewidth=0.5)
                    x_pos += 1  # extra space after bar
        
        ax.set_ylim(0, 12)
        ax.set_xlim(0, x_pos + 2)
        ax.axis('off')
        
        return fig, ax

# Run the app
if __name__ == "__main__":
    root = tk.Tk()
    app = MidiWriterApp(root)
    root.mainloop()