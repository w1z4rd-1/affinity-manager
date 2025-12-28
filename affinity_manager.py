"""
Affinity Manager
Manages CPU core affinity for processes to optimize performance.

Created by wizard1
"""
import sys
import os
import json
import ctypes
import psutil
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

# ============================================================================
# CONFIGURATION
# ============================================================================

# Default process patterns - can be extended by user
DEFAULT_CUSTOM_PROGRAMS = {
    'Minecraft': ['javaw', 'java', 'lunar', 'badlion', 'feather'],
    'Discord': ['discord'],
    'OBS': ['obs64', 'obs32', 'obs-browser']
}

SKIP_ALWAYS = {
    'system', 'system idle process', 'idle', 'registry', 'memcompression', 'memory compression',
    'smss.exe', 'csrss.exe', 'wininit.exe', 'services.exe', 'lsass.exe', 'winlogon.exe',
    'dwm.exe', 'fontdrvhost.exe', 'sihost.exe', 'startmenuexperiencehost.exe',
    'shellexperiencehost.exe', 'searchui.exe', 'searchapp.exe', 'runtimebroker.exe',
    'ctfmon.exe', 'audiodg.exe', 'mc-fw-host.exe'
}

# Colors - Dark theme palette
BG_MAIN = "#1e1e1e"           # Main background
BG_FRAME = "#252526"          # Frame background
BG_TRACK = "#2d2d30"          # Track background
P_CORE_BASE = "#0e4429"       # P-core unselected (dark green)
P_CORE_SELECTED = "#26a641"   # P-core selected (green)
E_CORE_BASE = "#0969da"       # E-core unselected (blue)
E_CORE_SELECTED = "#54aeff"   # E-core selected (light blue)
TEXT_DIM = "#8b949e"          # Dimmed text
TEXT_BRIGHT = "#e6edf3"       # Bright text
BORDER_SELECTED = "#ffa657"   # Orange border for selection
BTN_BG = "#238636"            # Button background
BTN_FG = "#ffffff"            # Button foreground

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def get_cpu_info():
    """Get CPU core information with P/E core detection."""
    logical = psutil.cpu_count(logical=True)
    physical = psutil.cpu_count(logical=False)
    threads_per_core = max(1, logical // physical) if physical else 1
    
    if logical > physical:
        ht_threads = logical - physical
        if physical >= 10:
            p_cores = ht_threads
            e_cores = physical - p_cores
            p_count = p_cores * 2
            e_count = e_cores
        else:
            p_cores = physical
            e_cores = 0
            p_count = logical
            e_count = 0
    else:
        p_cores = physical
        e_cores = 0
        p_count = logical
        e_count = 0
    
    core_types = []
    for i in range(logical):
        if i < p_count:
            core_types.append('P')
        else:
            core_types.append('E')
    
    return {
        'logical': logical,
        'physical': physical,
        'p_cores': p_cores,
        'e_cores': e_cores,
        'p_count': p_count,
        'e_count': e_count,
        'core_types': core_types,
        'threads_per_core': threads_per_core
    }

def find_processes(patterns):
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_affinity', 'num_threads']):
        try:
            name = proc.info['name'].lower()
            if any(p.lower() in name for p in patterns):
                procs.append({
                    'pid': proc.pid,
                    'name': proc.info['name'],
                    'threads': proc.info['num_threads'],
                    'cores': set(proc.cpu_affinity()),
                    'proc': proc
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return procs

def find_other_processes(known_pids):
    """Find user-owned processes not in known sets and not critical OS services."""
    procs = []
    try:
        current_user = psutil.Process(os.getpid()).username()
    except Exception:
        current_user = None

    for proc in psutil.process_iter(['pid', 'name', 'cpu_affinity', 'num_threads', 'username']):
        try:
            pid = proc.info['pid']
            name = (proc.info['name'] or '').lower()

            if pid in known_pids:
                continue

            if not name or name in SKIP_ALWAYS:
                continue

            if current_user and proc.info.get('username') and proc.info['username'].lower() != current_user.lower():
                continue

            procs.append({
                'pid': pid,
                'name': proc.info['name'],
                'threads': proc.info['num_threads'],
                'cores': set(proc.cpu_affinity()),
                'proc': proc
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return procs

def set_affinity_with_debug(procs, cores, app_name):
    """Set affinity with detailed error reporting."""
    results = []
    for p in procs:
        try:
            p['proc'].cpu_affinity(cores)
            results.append({
                'pid': p['pid'],
                'name': p['name'],
                'success': True,
                'error': None
            })
        except psutil.NoSuchProcess:
            results.append({
                'pid': p['pid'],
                'name': p['name'],
                'success': False,
                'error': "Process no longer exists"
            })
        except psutil.AccessDenied:
            results.append({
                'pid': p['pid'],
                'name': p['name'],
                'success': False,
                'error': "Access denied - may need higher privileges or process is protected"
            })
        except OSError as e:
            results.append({
                'pid': p['pid'],
                'name': p['name'],
                'success': False,
                'error': f"OS Error: {e}"
            })
        except Exception as e:
            results.append({
                'pid': p['pid'],
                'name': p['name'],
                'success': False,
                'error': f"{type(e).__name__}: {e}"
            })
    return results

def load_custom_programs():
    """Load custom program definitions from config file."""
    config_path = os.path.join(os.path.dirname(sys.argv[0]), 'affinity_config.json')
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return dict(DEFAULT_CUSTOM_PROGRAMS)

def save_custom_programs(programs):
    """Save custom program definitions to config file."""
    config_path = os.path.join(os.path.dirname(sys.argv[0]), 'affinity_config.json')
    try:
        with open(config_path, 'w') as f:
            json.dump(programs, f, indent=2)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save config: {e}")

# ============================================================================
# CORE SELECTOR WIDGET
# ============================================================================

class CoreSelector(tk.Canvas):
    """Visual core selector with P/E core colors and range selection."""
    
    def __init__(self, parent, cpu_info, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.cpu_info = cpu_info
        self.total_cores = cpu_info['logical']
        self.core_types = cpu_info['core_types']
        self.threads_per_core = cpu_info['threads_per_core']
        self.physical_cores = cpu_info['physical']
        
        # Selection range (start, end) - both inclusive
        self.start = 0
        self.end = self.total_cores - 1
        
        # Drag state
        self.drag_anchor = None
        
        # Dimensions
        self.core_width = 32
        self.core_height = 36
        self.core_spacing = 4
        self.padding_x = 12
        self.padding_y = 10
        self.corner_radius = 6
        
        # Configure size
        width = self.total_cores * (self.core_width + self.core_spacing) - self.core_spacing + self.padding_x * 2 + 90
        height = self.core_height + self.padding_y * 2
        self.configure(width=width, height=height, bg=BG_MAIN, highlightthickness=0)
        
        # Bind mouse events
        self.bind('<Button-1>', self.on_mouse_down)
        self.bind('<B1-Motion>', self.on_mouse_move)
        self.bind('<ButtonRelease-1>', self.on_mouse_up)
        
        self.draw()
    
    def create_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        """Draw a rounded rectangle."""
        points = [
            x1+r, y1,
            x2-r, y1,
            x2, y1,
            x2, y1+r,
            x2, y2-r,
            x2, y2,
            x2-r, y2,
            x1+r, y2,
            x1, y2,
            x1, y2-r,
            x1, y1+r,
            x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)
    
    def get_core_at_x(self, x):
        """Get core index from x coordinate."""
        core_x = x - self.padding_x
        if core_x < 0:
            return 0
        step = self.core_width + self.core_spacing
        idx = int(core_x / step)
        return max(0, min(idx, self.total_cores - 1))
    
    def on_mouse_down(self, event):
        """Start selection at clicked core."""
        core = self.get_core_at_x(event.x)
        self.drag_anchor = core
        self.start = core
        self.end = core
        self.draw()
    
    def on_mouse_move(self, event):
        """Expand selection as mouse moves."""
        if self.drag_anchor is None:
            return
        
        core = self.get_core_at_x(event.x)
        self.start = min(self.drag_anchor, core)
        self.end = max(self.drag_anchor, core)
        self.draw()
    
    def on_mouse_up(self, event):
        """End selection."""
        self.drag_anchor = None
    
    def draw(self):
        """Redraw the selector."""
        self.delete('all')
        
        # Draw track background
        track_x1 = self.padding_x - 4
        track_y1 = self.padding_y - 4
        track_x2 = self.padding_x + self.total_cores * (self.core_width + self.core_spacing) - self.core_spacing + 4
        track_y2 = self.padding_y + self.core_height + 4
        self.create_rounded_rect(track_x1, track_y1, track_x2, track_y2, 8, fill=BG_TRACK, outline='')
        
        # Draw each core
        for i in range(self.total_cores):
            x = self.padding_x + i * (self.core_width + self.core_spacing)
            y = self.padding_y
            
            is_p_core = self.core_types[i] == 'P'
            is_selected = self.start <= i <= self.end
            
            # Determine colors based on type and selection
            if is_selected:
                fill = P_CORE_SELECTED if is_p_core else E_CORE_SELECTED
                outline = BORDER_SELECTED
                outline_width = 2
                text_color = TEXT_BRIGHT
            else:
                fill = P_CORE_BASE if is_p_core else E_CORE_BASE
                outline = ''
                outline_width = 0
                text_color = TEXT_DIM
            
            # Draw core rounded rectangle
            self.create_rounded_rect(
                x, y,
                x + self.core_width, y + self.core_height,
                self.corner_radius,
                fill=fill, outline=outline, width=outline_width
            )
            
            # Draw core number
            self.create_text(
                x + self.core_width // 2,
                y + self.core_height // 2 - 6,
                text=str(i),
                font=('Consolas', 11, 'bold'),
                fill=text_color
            )
            
            # Draw P/E label
            label = "P" if is_p_core else "E"
            self.create_text(
                x + self.core_width // 2,
                y + self.core_height // 2 + 10,
                text=label,
                font=('Segoe UI', 8),
                fill=text_color if is_selected else '#4a5568'
            )
        
        # Draw selection info
        info_x = self.padding_x + self.total_cores * (self.core_width + self.core_spacing) + 10
        count = self.end - self.start + 1
        
        self.create_text(
            info_x, self.padding_y + self.core_height // 2 - 8,
            text=f"Cores {self.start}–{self.end}",
            anchor='w', font=('Segoe UI', 10, 'bold'), fill=TEXT_BRIGHT
        )
        self.create_text(
            info_x, self.padding_y + self.core_height // 2 + 10,
            text=f"({count} selected)",
            anchor='w', font=('Segoe UI', 9), fill=TEXT_DIM
        )
    
    def get_cores(self):
        """Get list of selected cores."""
        return list(range(self.start, self.end + 1))
    
    def set_range(self, start, end):
        """Set selection range."""
        self.start = max(0, min(start, self.total_cores - 1))
        self.end = max(0, min(end, self.total_cores - 1))
        if self.start > self.end:
            self.start, self.end = self.end, self.start
        self.draw()

# ============================================================================
# MAIN APPLICATION
# ============================================================================

class AffinityManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Affinity Manager")
        self.root.resizable(True, True)
        try:
            self.root.minsize(1100, 750)
            self.root.geometry("1200x820")
        except Exception:
            pass
        
        # Apply dark theme
        self.root.configure(bg=BG_MAIN)
        self.setup_dark_theme()
        
        self.cpu_info = get_cpu_info()
        self.custom_programs = load_custom_programs()
        self.custom_groups = {}  # name -> (patterns, procs, selector)
        
        self.refresh_processes()
        self.build_gui()
        self.load_current_affinities()
    
    def setup_dark_theme(self):
        """Configure ttk dark theme."""
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure('.', background=BG_FRAME, foreground=TEXT_BRIGHT, 
                       fieldbackground=BG_TRACK, borderwidth=0)
        style.configure('TFrame', background=BG_MAIN)
        style.configure('TLabel', background=BG_MAIN, foreground=TEXT_BRIGHT)
        style.configure('TLabelframe', background=BG_MAIN, foreground=TEXT_BRIGHT, 
                       borderwidth=1, relief='solid')
        style.configure('TLabelframe.Label', background=BG_MAIN, foreground=TEXT_BRIGHT)
        style.configure('TButton', background=BTN_BG, foreground=BTN_FG, 
                       borderwidth=1, focuscolor='none', padding=6)
        style.map('TButton', background=[('active', '#2ea043')])
    
    def refresh_processes(self):
        """Refresh all process lists including custom programs."""
        # Clear custom groups proc lists
        for name in self.custom_groups:
            patterns = self.custom_groups[name][0]
            procs = find_processes(patterns)
            selector = self.custom_groups[name][2]
            self.custom_groups[name] = (patterns, procs, selector)
        
        # Collect all known PIDs
        all_known = []
        for name, (patterns, procs, _) in self.custom_groups.items():
            all_known.extend(procs)
        
        known_pids = {p['pid'] for p in all_known}
        self.other_procs = find_other_processes(known_pids)
    
    def load_current_affinities(self):
        """Set selectors to show current affinity instead of recommended."""
        for name, (patterns, procs, selector) in self.custom_groups.items():
            if procs:
                # Use first process's affinity as representative
                cores = sorted(procs[0]['cores'])
                if cores:
                    selector.set_range(cores[0], cores[-1])
        
        # Set "Other" to all cores by default
        if hasattr(self, 'other_selector'):
            self.other_selector.set_range(0, self.cpu_info['logical'] - 1)
    
    def build_gui(self):
        # Create main scrollable frame
        main_canvas = tk.Canvas(self.root, bg=BG_MAIN, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=main_canvas.yview)
        main_frame = ttk.Frame(main_canvas)
        
        main_frame.bind("<Configure>", lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all")))
        
        main_canvas.create_window((0, 0), window=main_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=scrollbar.set)
        
        main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        main = ttk.Frame(main_frame, padding=15)
        main.grid(row=0, column=0, sticky="nsew")
        
        # Title
        title_label = ttk.Label(main, text="🎮 Affinity Manager", 
                 font=('Segoe UI', 14, 'bold'))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 2))
        author_label = ttk.Label(main, text="by wizard1", font=('Segoe UI', 9, 'italic'))
        author_label.grid(row=1, column=0, columnspan=2, pady=(0, 10))
        
        # CPU Info
        info_frame = ttk.LabelFrame(main, text="CPU Info", padding=10)
        info_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        cpu = self.cpu_info
        info_text = f"{cpu['physical']} physical cores, {cpu['logical']} logical cores"
        if cpu['e_cores'] > 0:
            info_text += f"  •  Hybrid: {cpu['p_cores']}P + {cpu['e_cores']}E"
        if cpu['threads_per_core'] > 1:
            info_text += f"  •  SMT/HT: {cpu['threads_per_core']} threads/core"
        ttk.Label(info_frame, text=info_text, font=('Segoe UI', 10)).grid(row=0, column=0, sticky='w')
        
        # Legend
        legend_frame = ttk.Frame(info_frame)
        legend_frame.grid(row=1, column=0, sticky='w', pady=(8, 0))
        
        p_canvas = tk.Canvas(legend_frame, width=24, height=16, highlightthickness=0, bg=BG_MAIN)
        p_canvas.grid(row=0, column=0, padx=(0, 5))
        p_canvas.create_rectangle(2, 2, 22, 14, fill=P_CORE_SELECTED, outline='')
        ttk.Label(legend_frame, text=f"P-core ({cpu['p_count']})", font=('Segoe UI', 9)).grid(row=0, column=1, padx=(0, 20))
        
        if cpu['e_count'] > 0:
            e_canvas = tk.Canvas(legend_frame, width=24, height=16, highlightthickness=0, bg=BG_MAIN)
            e_canvas.grid(row=0, column=2, padx=(0, 5))
            e_canvas.create_rectangle(2, 2, 22, 14, fill=E_CORE_SELECTED, outline='')
            ttk.Label(legend_frame, text=f"E-core ({cpu['e_count']})", font=('Segoe UI', 9)).grid(row=0, column=3, padx=(0, 20))
        
        s_canvas = tk.Canvas(legend_frame, width=24, height=16, highlightthickness=0, bg=BG_MAIN)
        s_canvas.grid(row=0, column=4, padx=(0, 5))
        s_canvas.create_rectangle(2, 2, 22, 14, fill='#333', outline=BORDER_SELECTED, width=2)
        ttk.Label(legend_frame, text="Selected", font=('Segoe UI', 9)).grid(row=0, column=5)
        
        # Detected processes
        detect_frame = ttk.LabelFrame(main, text="Detected Processes", padding=10)
        detect_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        self.process_labels = {}
        
        # Core selectors
        self.selector_frame = ttk.LabelFrame(main, text="Core Allocation — click and drag to select range", padding=10)
        self.selector_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        self.selector_row_idx = 0
        
        # Build selectors for each custom program
        for name, patterns in self.custom_programs.items():
            self.add_program_selector(name, patterns)
        
        # "Other" processes selector
        other_row = ttk.Frame(self.selector_frame)
        other_row.grid(row=self.selector_row_idx, column=0, sticky='w', pady=4)
        ttk.Label(other_row, text="Other", font=('Segoe UI', 10, 'bold'), width=10).pack(side='left')
        self.other_selector = CoreSelector(other_row, self.cpu_info)
        self.other_selector.pack(side='left', padx=(5, 0))
        self.selector_row_idx += 1
        
        self.update_process_labels()
        
        # Add program button
        add_frame = ttk.Frame(main)
        add_frame.grid(row=5, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(add_frame, text="+ Add Custom Program", command=self.on_add_program).pack()
        
        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=10)
        
        ttk.Button(btn_frame, text="↻ Refresh", command=self.on_refresh).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="✓ Apply", command=self.on_apply).pack(side="left", padx=5)
        
        # Status
        self.status_label = ttk.Label(main, text="Ready - showing current affinity settings", font=('Segoe UI', 9))
        self.status_label.grid(row=7, column=0, columnspan=2)
    
    def add_program_selector(self, name, patterns):
        """Add a program selector row."""
        # Find processes
        procs = find_processes(patterns)
        
        # Create selector row
        row = ttk.Frame(self.selector_frame)
        row.grid(row=self.selector_row_idx, column=0, sticky='w', pady=4)
        
        label_frame = ttk.Frame(row)
        label_frame.pack(side='left')
        ttk.Label(label_frame, text=name, font=('Segoe UI', 10, 'bold'), width=10).pack(side='left')
        
        # Add remove button for custom (non-default) programs
        if name not in DEFAULT_CUSTOM_PROGRAMS:
            ttk.Button(label_frame, text="✕", width=2, command=lambda: self.remove_program(name)).pack(side='left', padx=(2, 0))
        
        selector = CoreSelector(row, self.cpu_info)
        selector.pack(side='left', padx=(5, 0))
        
        # Store in custom_groups
        self.custom_groups[name] = (patterns, procs, selector)
        
        # Create label in detect frame
        label = ttk.Label(self.selector_frame.master.master.winfo_children()[3], text="")  # detect_frame
        label.grid(row=len(self.process_labels), column=0, sticky="w")
        self.process_labels[name] = label
        
        self.selector_row_idx += 1
    
    def remove_program(self, name):
        """Remove a custom program."""
        if name in DEFAULT_CUSTOM_PROGRAMS:
            messagebox.showwarning("Cannot Remove", "Cannot remove default programs.")
            return
        
        if messagebox.askyesno("Confirm", f"Remove {name}?"):
            del self.custom_programs[name]
            del self.custom_groups[name]
            save_custom_programs(self.custom_programs)
            
            # Rebuild GUI
            for widget in self.selector_frame.winfo_children():
                widget.destroy()
            for widget in self.selector_frame.master.master.winfo_children()[3].winfo_children():
                widget.destroy()
            
            self.process_labels = {}
            self.selector_row_idx = 0
            
            for pname, patterns in self.custom_programs.items():
                self.add_program_selector(pname, patterns)
            
            # Re-add Other
            other_row = ttk.Frame(self.selector_frame)
            other_row.grid(row=self.selector_row_idx, column=0, sticky='w', pady=4)
            ttk.Label(other_row, text="Other", font=('Segoe UI', 10, 'bold'), width=10).pack(side='left')
            self.other_selector = CoreSelector(other_row, self.cpu_info)
            self.other_selector.pack(side='left', padx=(5, 0))
            
            self.refresh_processes()
            self.update_process_labels()
    
    def on_add_program(self):
        """Add a new custom program."""
        name = simpledialog.askstring("Add Program", "Enter program name:")
        if not name:
            return
        
        if name in self.custom_programs:
            messagebox.showwarning("Duplicate", "Program already exists.")
            return
        
        pattern = simpledialog.askstring("Add Program", f"Enter process name pattern for {name}:\n(e.g., chrome, firefox.exe)")
        if not pattern:
            return
        
        patterns = [p.strip() for p in pattern.split(',')]
        self.custom_programs[name] = patterns
        save_custom_programs(self.custom_programs)
        
        # Add selector
        self.add_program_selector(name, patterns)
        self.refresh_processes()
        self.update_process_labels()
        self.status_label.config(text=f"Added {name}")
    
    def update_process_labels(self):
        def fmt(name, procs):
            if not procs:
                return f"❌ {name}: Not running"
            names = set(p['name'] for p in procs)
            threads = sum(p['threads'] for p in procs)
            return f"✅ {name}: {', '.join(names)} ({threads} threads)"
        
        for name, (patterns, procs, selector) in self.custom_groups.items():
            if name in self.process_labels:
                self.process_labels[name].config(text=fmt(name, procs))
        
        # Update Other label
        if hasattr(self, 'other_procs'):
            count = len(self.other_procs)
            threads = sum(p['threads'] for p in self.other_procs)
            if self.other_procs:
                # Find or create Other label
                detect_frame = self.selector_frame.master.master.winfo_children()[3]
                for child in detect_frame.winfo_children():
                    if isinstance(child, ttk.Label):
                        text = child.cget('text')
                        if 'Other:' in text or not text:
                            child.config(text=f"✅ Other: {count} processes ({threads} threads) — excludes system processes")
                            break
    
    def on_refresh(self):
        self.refresh_processes()
        self.update_process_labels()
        self.load_current_affinities()
        self.status_label.config(text="Refreshed!")
    
    def on_apply(self):
        all_results = []
        errors = []
        
        # Apply for each custom program
        for name, (patterns, procs, selector) in self.custom_groups.items():
            cores = selector.get_cores()
            if not procs or not cores:
                continue
            
            results = set_affinity_with_debug(procs, cores, name)
            
            ok = sum(1 for r in results if r['success'])
            failed = [r for r in results if not r['success']]
            
            all_results.append(f"{name}: {ok} OK → Cores {min(cores)}-{max(cores)}")
            
            for f in failed:
                errors.append(f"❌ {f['name']} (PID {f['pid']}):\n   {f['error']}")
        
        # Apply for Other
        if hasattr(self, 'other_procs') and self.other_procs:
            cores = self.other_selector.get_cores()
            if cores:
                results = set_affinity_with_debug(self.other_procs, cores, "Other")
                ok = sum(1 for r in results if r['success'])
                failed = [r for r in results if not r['success']]
                all_results.append(f"Other: {ok} OK → Cores {min(cores)}-{max(cores)}")
                for f in failed:
                    errors.append(f"❌ {f['name']} (PID {f['pid']}):\n   {f['error']}")
        
        if not all_results:
            messagebox.showwarning("Warning", "No processes to update!")
            return
        
        msg = "Affinity applied:\n\n" + "\n".join(all_results)
        
        if errors:
            msg += "\n\n⚠️ ERRORS:\n\n" + "\n\n".join(errors[:5])  # Limit to first 5 errors
            if len(errors) > 5:
                msg += f"\n\n... and {len(errors) - 5} more errors"
            messagebox.showwarning("Partial Success", msg)
        else:
            messagebox.showinfo("Success", msg)
        
        self.status_label.config(text="✅ Applied!")

# ============================================================================
# MAIN
# ============================================================================

def run_as_admin():
    """Relaunch the script with admin privileges via UAC."""
    try:
        script = sys.argv[0]
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{script}"', None, 1
        )
    except Exception as e:
        messagebox.showerror("Error", f"Failed to elevate privileges:\n{e}")

def main():
    if not is_admin():
        run_as_admin()
        return
    
    root = tk.Tk()
    app = AffinityManagerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
