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
import threading
import time

# Debug timing
DEBUG_TIMING = True
_start_time = time.perf_counter()

def debug_ts(msg):
    if DEBUG_TIMING:
        elapsed = (time.perf_counter() - _start_time) * 1000
        print(f"[{elapsed:8.1f}ms] {msg}")

# ============================================================================
# CONFIGURATION
# ============================================================================

# Known process patterns to check
KNOWN_PATTERNS = {
    'Minecraft': ['javaw', 'java', 'lunar', 'badlion', 'feather'],
    'Discord': ['discord'],
    'OBS': ['obs64', 'obs32', 'obs-browser']
}

SKIP_ALWAYS = {
    'system', 'system idle process', 'idle', 'registry', 'memcompression', 'memory compression',
    'smss.exe', 'csrss.exe', 'wininit.exe', 'services.exe', 'lsass.exe', 'winlogon.exe',
    'dwm.exe', 'fontdrvhost.exe', 'sihost.exe', 'startmenuexperiencehost.exe',
    'shellexperiencehost.exe', 'searchui.exe', 'searchapp.exe', 'runtimebroker.exe',
    'ctfmon.exe', 'audiodg.exe', 'mc-fw-host.exe', 'affinity_manager.exe'
}

# Thresholds for warnings
MAX_THREADS_PER_CORE = 300  # Warn if threads/core exceeds this

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

def discover_all_processes_single_pass():
    """Single pass through all processes - discovers known patterns AND top CPU at once."""
    debug_ts("discover_all_processes_single_pass start")
    
    try:
        current_user = psutil.Process(os.getpid()).username()
    except Exception:
        current_user = None
    
    my_pid = os.getpid()
    
    # Results by category
    results = {name: [] for name in KNOWN_PATTERNS.keys()}
    top_cpu_candidates = []
    
    debug_ts("starting process iteration")
    for proc in psutil.process_iter(['pid', 'name', 'cpu_affinity', 'num_threads', 'cpu_percent', 'username']):
        try:
            pid = proc.info['pid']
            name_lower = (proc.info['name'] or '').lower()
            
            if not name_lower or pid == my_pid:
                continue
            
            proc_data = {
                'pid': pid,
                'name': proc.info['name'],
                'threads': proc.info['num_threads'],
                'cores': set(proc.cpu_affinity()),
                'cpu_percent': proc.info.get('cpu_percent', 0) or 0,
                'proc': proc
            }
            
            # Check against known patterns
            matched = False
            for category, patterns in KNOWN_PATTERNS.items():
                if any(p.lower() in name_lower for p in patterns):
                    results[category].append(proc_data)
                    matched = True
                    break
            
            # If not matched to known category, consider for top CPU
            if not matched and name_lower not in SKIP_ALWAYS:
                if current_user and proc.info.get('username'):
                    if proc.info['username'].lower() != current_user.lower():
                        continue
                
                if proc_data['cpu_percent'] > 0.5:
                    top_cpu_candidates.append(proc_data)
                    
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    debug_ts("process iteration done")
    
    # Get top CPU process
    top_cpu = []
    if top_cpu_candidates:
        top_cpu = sorted(top_cpu_candidates, key=lambda x: x['cpu_percent'], reverse=True)[:1]
    
    debug_ts(f"discover_all_processes_single_pass done: MC={len(results.get('Minecraft',[]))}, Discord={len(results.get('Discord',[]))}, OBS={len(results.get('OBS',[]))}, topCPU={len(top_cpu)}")
    return results, top_cpu

def find_other_processes(known_pids):
    """Find user-owned processes not in known sets and not critical OS services."""
    debug_ts("find_other_processes start")
    procs = []
    try:
        current_user = psutil.Process(os.getpid()).username()
    except Exception:
        current_user = None

    debug_ts("find_other_processes iterating")
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
    debug_ts(f"find_other_processes done, found {len(procs)}")
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
        
        # Selection range (start, end) - both inclusive, default to all cores
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
        debug_ts("AffinityManagerApp.__init__ start")
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
        debug_ts("setup_dark_theme start")
        self.setup_dark_theme()
        debug_ts("setup_dark_theme done")
        
        debug_ts("get_cpu_info start")
        self.cpu_info = get_cpu_info()
        debug_ts("get_cpu_info done")
        self.active_groups = {}  # name -> (patterns, procs, selector, label)
        self.other_procs = []
        self.other_discovery_done = False
        
        debug_ts("refresh_processes_sync start")
        self.refresh_processes_sync()  # Sync discovery of known patterns + top CPU FIRST
        debug_ts("refresh_processes_sync done")
        debug_ts("build_gui start")
        self.build_gui()  # Then build GUI with discovered processes
        debug_ts("build_gui done")
        self.start_async_other_discovery()  # Async discovery of "Other"
        debug_ts("AffinityManagerApp.__init__ done")
    
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
        style.map('TButton', background=[('active', '#2ea043'), ('disabled', '#1f1f1f')],
                  foreground=[('disabled', '#666666')])
    
    def refresh_processes_sync(self):
        """Synchronously discover known programs and top CPU process in single pass."""
        self.active_groups.clear()
        
        # Single pass discovery
        results, top_cpu = discover_all_processes_single_pass()
        
        all_pids = set()
        
        # Add discovered categories
        for name, procs in results.items():
            if procs:  # Only add if running
                all_pids.update(p['pid'] for p in procs)
                self.active_groups[name] = (KNOWN_PATTERNS[name], procs, None, None)
        
        # Add top CPU process
        if top_cpu:
            top_name = f"Top CPU ({top_cpu[0]['name']})"
            all_pids.add(top_cpu[0]['pid'])
            self.active_groups[top_name] = ([], top_cpu, None, None)
        
        self.known_pids = all_pids
    
    def start_async_other_discovery(self):
        """Start async discovery of 'Other' processes."""
        debug_ts("start_async_other_discovery start")
        self.other_discovery_done = False
        if hasattr(self, 'other_selector'):
            self.other_selector.configure(state='disabled')
        if hasattr(self, 'apply_btn'):
            self.apply_btn.configure(state='disabled')
        
        def discover():
            debug_ts("async discover thread started")
            time.sleep(0.1)  # Small delay to let UI render
            debug_ts("calling find_other_processes")
            self.other_procs = find_other_processes(self.known_pids)
            debug_ts(f"find_other_processes done, found {len(self.other_procs)}")
            self.other_discovery_done = True
            
            # Update UI on main thread
            self.root.after(0, self.on_other_discovery_complete)
            debug_ts("async discover thread done")
        
        debug_ts("creating thread")
        thread = threading.Thread(target=discover, daemon=True)
        debug_ts("starting thread")
        thread.start()
        debug_ts("start_async_other_discovery done")
    
    def on_other_discovery_complete(self):
        """Called when async discovery completes."""
        if hasattr(self, 'apply_btn'):
            self.apply_btn.configure(state='normal')
        self.update_other_label()
        self.status_label.config(text="Ready")
    
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
        self.detect_frame = ttk.LabelFrame(main, text="Detected Processes", padding=10)
        self.detect_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        # Core selectors
        self.selector_frame = ttk.LabelFrame(main, text="Core Allocation — click and drag to select range", padding=10)
        self.selector_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        self.build_selectors()
        
        # "Other" processes selector
        other_row = ttk.Frame(self.selector_frame)
        other_row.grid(row=len(self.active_groups), column=0, sticky='w', pady=4)
        ttk.Label(other_row, text="Other", font=('Segoe UI', 10, 'bold'), width=25, anchor='w').pack(side='left')
        self.other_selector = CoreSelector(other_row, self.cpu_info)
        self.other_selector.pack(side='left', padx=(5, 0))
        
        # Disclaimer
        disclaimer_frame = ttk.Frame(main)
        disclaimer_frame.grid(row=5, column=0, columnspan=2, pady=(0, 10))
        disclaimer_text = ("⚠️ NOT GUARANTEED TO IMPROVE PERFORMANCE • RESTART PROCESS = SETTINGS REVERT!\n"
                          "This tool compartmentalizes CPU load to prevent one process from slowing another.\n"
                          "If no background processes are intensive, this may not help you at all.")
        ttk.Label(disclaimer_frame, text=disclaimer_text, font=('Segoe UI', 8), 
                 foreground=TEXT_DIM, justify='center').pack()
        
        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=10)
        
        ttk.Button(btn_frame, text="↻ Refresh", command=self.on_refresh).pack(side="left", padx=5)
        self.apply_btn = ttk.Button(btn_frame, text="✓ Apply", command=self.on_apply, state='disabled')
        self.apply_btn.pack(side="left", padx=5)
        
        # Status
        self.status_label = ttk.Label(main, text="Loading other processes...", font=('Segoe UI', 9))
        self.status_label.grid(row=7, column=0, columnspan=2)
    
    def build_selectors(self):
        """Build selector rows for active groups."""
        row_idx = 0
        for name, (patterns, procs, _, _) in self.active_groups.items():
            row = ttk.Frame(self.selector_frame)
            row.grid(row=row_idx, column=0, sticky='w', pady=4)
            
            ttk.Label(row, text=name, font=('Segoe UI', 10, 'bold'), width=25, anchor='w').pack(side='left')
            
            selector = CoreSelector(row, self.cpu_info)
            selector.pack(side='left', padx=(5, 0))
            
            # Create label in detect frame
            label = ttk.Label(self.detect_frame, text="")
            label.grid(row=row_idx, column=0, sticky="w")
            
            # Update active_groups with selector and label
            self.active_groups[name] = (patterns, procs, selector, label)
            self.update_process_label(name)
            
            row_idx += 1
    
    def update_process_label(self, name):
        """Update process label for a group."""
        patterns, procs, selector, label = self.active_groups[name]
        if not procs:
            label.config(text=f"❌ {name}: Not running")
        else:
            names = set(p['name'] for p in procs)
            threads = sum(p['threads'] for p in procs)
            label.config(text=f"✅ {name}: {', '.join(names)} ({threads} threads)")
    
    def update_other_label(self):
        """Update the Other processes label."""
        count = len(self.other_procs)
        threads = sum(p['threads'] for p in self.other_procs)
        
        # Find or create Other label
        found = False
        for child in self.detect_frame.winfo_children():
            if isinstance(child, ttk.Label):
                text = child.cget('text')
                if 'Other:' in text or (not text and not found):
                    if self.other_procs:
                        child.config(text=f"✅ Other: {count} processes ({threads} threads) — excludes system processes")
                    else:
                        child.config(text="❌ Other: none")
                    found = True
                    break
        
        if not found and self.other_procs:
            label = ttk.Label(self.detect_frame, text=f"✅ Other: {count} processes ({threads} threads) — excludes system processes")
            label.grid(row=len(self.active_groups), column=0, sticky="w")
    
    def on_refresh(self):
        # Clear selectors
        for widget in self.selector_frame.winfo_children():
            widget.destroy()
        for widget in self.detect_frame.winfo_children():
            widget.destroy()
        
        self.refresh_processes_sync()
        self.build_selectors()
        
        # Re-add Other selector
        other_row = ttk.Frame(self.selector_frame)
        other_row.grid(row=len(self.active_groups), column=0, sticky='w', pady=4)
        ttk.Label(other_row, text="Other", font=('Segoe UI', 10, 'bold'), width=25, anchor='w').pack(side='left')
        self.other_selector = CoreSelector(other_row, self.cpu_info)
        self.other_selector.pack(side='left', padx=(5, 0))
        
        self.start_async_other_discovery()
        self.status_label.config(text="Refreshing...")
    
    def validate_other_affinity(self, cores, threads):
        """Check if Other affinity settings are reasonable."""
        if not cores:
            return True, None
        
        # Check if only E-cores selected
        has_p_core = any(self.cpu_info['core_types'][c] == 'P' for c in cores)
        if not has_p_core and self.cpu_info['p_count'] > 0:
            return False, ("⚠️ WARNING: You've selected only E-cores for 'Other' processes.\n\n"
                          "This may cause performance issues for background tasks that need performance cores.\n\n"
                          "Continue anyway?")
        
        # Check threads per core ratio
        threads_per_core = threads / len(cores) if len(cores) > 0 else 0
        if threads_per_core > MAX_THREADS_PER_CORE:
            return False, (f"⚠️ WARNING: Thread density is very high ({threads_per_core:.0f} threads/core).\n\n"
                          f"This exceeds the recommended maximum of {MAX_THREADS_PER_CORE} threads/core "
                          "and may cause thread contention issues.\n\n"
                          "Consider selecting more cores or applying to fewer processes.\n\n"
                          "Continue anyway?")
        
        return True, None
    
    def on_apply(self):
        if not self.other_discovery_done:
            messagebox.showwarning("Not Ready", "Still discovering processes, please wait...")
            return
        
        all_results = []
        errors = []
        
        # Apply for each active group
        for name, (patterns, procs, selector, label) in self.active_groups.items():
            cores = selector.get_cores()
            if not procs or not cores:
                continue
            
            results = set_affinity_with_debug(procs, cores, name)
            
            ok = sum(1 for r in results if r['success'])
            failed = [r for r in results if not r['success']]
            
            all_results.append(f"{name}: {ok} OK → Cores {min(cores)}-{max(cores)}")
            
            for f in failed:
                errors.append(f"❌ {f['name']} (PID {f['pid']}):\n   {f['error']}")
        
        # Apply for Other with validation
        if self.other_procs:
            cores = self.other_selector.get_cores()
            threads = sum(p['threads'] for p in self.other_procs)
            
            valid, warning_msg = self.validate_other_affinity(cores, threads)
            if not valid:
                response = messagebox.askyesno("Warning", warning_msg)
                if not response:
                    return  # User cancelled
            
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
    try:
        debug_ts("main() start")
        if not is_admin():
            debug_ts("not admin, elevating")
            run_as_admin()
            return
        
        debug_ts("is admin, creating Tk root")
        root = tk.Tk()
        debug_ts("Tk root created, creating app")
        app = AffinityManagerApp(root)
        debug_ts("app created, entering mainloop")
        root.mainloop()
    except Exception as e:
        import traceback
        error_msg = f"Error: {e}\n\n{traceback.format_exc()}"
        print(error_msg)
        try:
            messagebox.showerror("Startup Error", error_msg)
        except:
            pass
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()
