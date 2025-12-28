"""
Affinity Manager
Manages CPU core affinity for processes to optimize performance.

Created by wizard1
"""
import sys
import os
import ctypes
import psutil
import tkinter as tk
from tkinter import ttk, messagebox

# ============================================================================
# CONFIGURATION
# ============================================================================

MC_PATTERNS = ['javaw', 'java', 'lunar', 'badlion', 'feather']
DISCORD_PATTERNS = ['discord']
OBS_PATTERNS = ['obs64', 'obs32', 'obs-browser']
SKIP_ALWAYS = {
    'system', 'system idle process', 'idle', 'registry', 'memcompression', 'memory compression',
    'smss.exe', 'csrss.exe', 'wininit.exe', 'services.exe', 'lsass.exe', 'winlogon.exe',
    'dwm.exe', 'fontdrvhost.exe', 'sihost.exe', 'startmenuexperiencehost.exe',
    'shellexperiencehost.exe', 'searchui.exe', 'searchapp.exe', 'runtimebroker.exe',
    'ctfmon.exe', 'audiodg.exe', 'mc-fw-host.exe'
}

# Colors - Modern dark theme palette
BG_DARK = "#1a1a2e"           # Dark background
BG_TRACK = "#16213e"          # Track background
P_CORE_BASE = "#0f3d3e"       # P-core unselected (dark teal)
P_CORE_SELECTED = "#00d9a0"   # P-core selected (bright teal/mint)
E_CORE_BASE = "#1e3a5f"       # E-core unselected (dark blue)
E_CORE_SELECTED = "#00b4d8"   # E-core selected (bright cyan)
TEXT_DIM = "#6c757d"          # Dimmed text
TEXT_BRIGHT = "#ffffff"       # Bright text
BORDER_SELECTED = "#ffd700"   # Gold border for selection

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
            if any(p in name for p in patterns):
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

            # skip ones we already target elsewhere
            if pid in known_pids:
                continue

            # skip empty or critical names
            if not name or name in SKIP_ALWAYS:
                continue

            # keep only processes owned by the current user when known, to avoid system services
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
        self.threads_per_core = cpu_info.get('threads_per_core', 1)
        self.physical_cores = max(1, cpu_info.get('physical', self.total_cores))
        
        # Selection range (start, end) - both inclusive
        self.start = 0
        self.end = cpu_info['p_count'] - 1
        
        # Drag state
        self.drag_anchor = None
        
        # Dimensions
        self.core_width = 32
        self.core_height = 36
        self.core_spacing = 4
        self.padding_x = 12
        self.padding_y = 16  # extra room for physical-core labels
        self.corner_radius = 6
        
        # Configure size
        width = self.total_cores * (self.core_width + self.core_spacing) - self.core_spacing + self.padding_x * 2 + 110
        height = self.core_height + self.padding_y * 2 + 6
        self.configure(width=width, height=height, bg=BG_DARK, highlightthickness=0)
        
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

        # Shade physical core groupings to show which logical cores share hardware
        if self.threads_per_core > 1:
            group_width = self.threads_per_core * (self.core_width + self.core_spacing) - self.core_spacing
            for g in range(self.physical_cores):
                gx1 = self.padding_x + g * group_width
                gx2 = gx1 + group_width
                # subtle overlay strip behind the group
                self.create_rectangle(
                    gx1, track_y1,
                    gx2, track_y2,
                    fill='#0c1a2f' if g % 2 == 0 else '#0a1323',
                    outline=''
                )
                # physical core index label above group
                self.create_text(
                    (gx1 + gx2) / 2,
                    track_y1 - 8,
                    text=f"Phys {g}",
                    font=('Segoe UI', 8, 'bold'),
                    fill='#cbd5e1'
                )
        
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

        # Draw separators between physical cores to highlight HT siblings
        if self.threads_per_core > 1:
            step = self.threads_per_core * (self.core_width + self.core_spacing)
            for g in range(1, self.physical_cores):
                sx = self.padding_x + g * step - self.core_spacing / 2
                self.create_line(
                    sx, track_y1 + 2,
                    sx, track_y2 - 2,
                    fill='#ffb703',
                    width=2,
                    dash=(3, 3)
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
            self.root.minsize(1100, 720)
            self.root.geometry("1200x780")
        except Exception:
            pass
        self.root.configure(bg='#f0f0f0')
        
        self.cpu_info = get_cpu_info()
        self.refresh_processes()
        self.build_gui()
        self.apply_recommended()
    
    def refresh_processes(self):
        self.mc_procs = find_processes(MC_PATTERNS)
        self.dc_procs = find_processes(DISCORD_PATTERNS)
        self.obs_procs = find_processes(OBS_PATTERNS)

        known_pids = {p['pid'] for p in self.mc_procs + self.dc_procs + self.obs_procs}
        self.other_procs = find_other_processes(known_pids)
    
    def build_gui(self):
        main = ttk.Frame(self.root, padding=15)
        main.grid(row=0, column=0, sticky="nsew")
        
        # Title
        ttk.Label(main, text="🎮 Affinity Manager", 
                 font=('Segoe UI', 14, 'bold')).grid(row=0, column=0, columnspan=2, pady=(0, 2))
        ttk.Label(main, text="by wizard1", 
                 font=('Segoe UI', 9, 'italic')).grid(row=1, column=0, columnspan=2, pady=(0, 10))
        
        # CPU Info with legend
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
        
        # P-core legend
        p_canvas = tk.Canvas(legend_frame, width=24, height=16, highlightthickness=0, bg='#f0f0f0')
        p_canvas.grid(row=0, column=0, padx=(0, 5))
        p_canvas.create_rectangle(2, 2, 22, 14, fill=P_CORE_SELECTED, outline='')
        ttk.Label(legend_frame, text=f"P-core ({cpu['p_count']})", font=('Segoe UI', 9)).grid(row=0, column=1, padx=(0, 20))
        
        # E-core legend
        if cpu['e_count'] > 0:
            e_canvas = tk.Canvas(legend_frame, width=24, height=16, highlightthickness=0, bg='#f0f0f0')
            e_canvas.grid(row=0, column=2, padx=(0, 5))
            e_canvas.create_rectangle(2, 2, 22, 14, fill=E_CORE_SELECTED, outline='')
            ttk.Label(legend_frame, text=f"E-core ({cpu['e_count']})", font=('Segoe UI', 9)).grid(row=0, column=3, padx=(0, 20))
        
        # Selected legend
        s_canvas = tk.Canvas(legend_frame, width=24, height=16, highlightthickness=0, bg='#f0f0f0')
        s_canvas.grid(row=0, column=4, padx=(0, 5))
        s_canvas.create_rectangle(2, 2, 22, 14, fill='#333', outline=BORDER_SELECTED, width=2)
        ttk.Label(legend_frame, text="Selected", font=('Segoe UI', 9)).grid(row=0, column=5)
        
        # Detected processes
        detect_frame = ttk.LabelFrame(main, text="Detected Processes", padding=10)
        detect_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        self.mc_label = ttk.Label(detect_frame, text="")
        self.mc_label.grid(row=0, column=0, sticky="w")
        self.dc_label = ttk.Label(detect_frame, text="")
        self.dc_label.grid(row=1, column=0, sticky="w")
        self.obs_label = ttk.Label(detect_frame, text="")
        self.obs_label.grid(row=2, column=0, sticky="w")
        self.other_label = ttk.Label(detect_frame, text="")
        self.other_label.grid(row=3, column=0, sticky="w")
        
        self.update_process_labels()
        
        # Core selectors
        selector_frame = ttk.LabelFrame(main, text="Core Allocation — click and drag to select range", padding=10)
        selector_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        # Minecraft selector
        mc_row = ttk.Frame(selector_frame)
        mc_row.grid(row=0, column=0, sticky='w', pady=4)
        ttk.Label(mc_row, text="Minecraft", font=('Segoe UI', 10, 'bold'), width=10).pack(side='left')
        self.mc_selector = CoreSelector(mc_row, self.cpu_info)
        self.mc_selector.pack(side='left', padx=(5, 0))
        
        # Discord selector
        dc_row = ttk.Frame(selector_frame)
        dc_row.grid(row=1, column=0, sticky='w', pady=4)
        ttk.Label(dc_row, text="Discord", font=('Segoe UI', 10, 'bold'), width=10).pack(side='left')
        self.dc_selector = CoreSelector(dc_row, self.cpu_info)
        self.dc_selector.pack(side='left', padx=(5, 0))
        
        # OBS selector
        obs_row = ttk.Frame(selector_frame)
        obs_row.grid(row=2, column=0, sticky='w', pady=4)
        ttk.Label(obs_row, text="OBS", font=('Segoe UI', 10, 'bold'), width=10).pack(side='left')
        self.obs_selector = CoreSelector(obs_row, self.cpu_info)
        self.obs_selector.pack(side='left', padx=(5, 0))

        # Other processes selector
        other_row = ttk.Frame(selector_frame)
        other_row.grid(row=3, column=0, sticky='w', pady=4)
        ttk.Label(other_row, text="Other", font=('Segoe UI', 10, 'bold'), width=10).pack(side='left')
        self.other_selector = CoreSelector(other_row, self.cpu_info)
        self.other_selector.pack(side='left', padx=(5, 0))
        
        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=10)
        
        ttk.Button(btn_frame, text="↻ Refresh", command=self.on_refresh).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="★ Recommended", command=self.apply_recommended).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="✓ Apply", command=self.on_apply).pack(side="left", padx=5)
        
        # Status
        self.status_label = ttk.Label(main, text="", font=('Segoe UI', 9))
        self.status_label.grid(row=6, column=0, columnspan=2)
    
    def update_process_labels(self):
        def fmt(name, procs, show_names=True):
            if not procs:
                return f"❌ {name}: Not running"
            threads = sum(p['threads'] for p in procs)
            if show_names:
                names = set(p['name'] for p in procs)
                return f"✅ {name}: {', '.join(names)} ({threads} threads)"
            return f"✅ {name}: {threads} threads"
        
        self.mc_label.config(text=fmt("Minecraft", self.mc_procs))
        self.dc_label.config(text=fmt("Discord", self.dc_procs))
        self.obs_label.config(text=fmt("OBS", self.obs_procs))
        if self.other_procs:
            count = len(self.other_procs)
            threads = sum(p['threads'] for p in self.other_procs)
            self.other_label.config(text=f"✅ Other: {count} processes ({threads} threads) — excludes system processes")
        else:
            self.other_label.config(text="❌ Other: none (user processes only; excludes system processes)")
    
    def on_refresh(self):
        self.refresh_processes()
        self.update_process_labels()
        self.status_label.config(text="Refreshed!")
    
    def apply_recommended(self):
        """Apply recommended core split."""
        cpu = self.cpu_info
        
        if cpu['e_count'] > 0:
            # Hybrid CPU: MC gets P-cores, Discord/OBS split E-cores
            mc_start, mc_end = 0, cpu['p_count'] - 1
            
            e_start = cpu['p_count']
            e_mid = e_start + cpu['e_count'] // 2
            
            dc_start, dc_end = e_start, e_mid - 1
            obs_start, obs_end = e_mid, cpu['logical'] - 1

            # Other processes -> keep to last part of E-cores (or last cores)
            other_end = cpu['logical'] - 1
            other_start = max(e_mid, other_end - max(1, cpu['threads_per_core']))
        else:
            # Standard CPU: 60% MC, 20% Discord, 20% OBS
            total = cpu['logical']
            mc_end = int(total * 0.6) - 1
            dc_start = mc_end + 1
            dc_end = int(total * 0.8) - 1
            obs_start = dc_end + 1
            obs_end = total - 1
            mc_start = 0
            other_end = total - 1
            other_start = max(int(total * 0.9), other_end - 1)
        
        self.mc_selector.set_range(mc_start, mc_end)
        self.dc_selector.set_range(dc_start, dc_end)
        self.obs_selector.set_range(obs_start, obs_end)
        self.other_selector.set_range(other_start, other_end)
    
    def on_apply(self):
        all_results = []
        errors = []
        
        # Apply each
        apps = [
            ('Minecraft', self.mc_procs, self.mc_selector.get_cores()),
            ('Discord', self.dc_procs, self.dc_selector.get_cores()),
            ('OBS', self.obs_procs, self.obs_selector.get_cores()),
            ('Other', self.other_procs, self.other_selector.get_cores())
        ]
        
        for app_name, procs, cores in apps:
            if not procs or not cores:
                continue
            
            results = set_affinity_with_debug(procs, cores, app_name)
            
            ok = sum(1 for r in results if r['success'])
            failed = [r for r in results if not r['success']]
            
            all_results.append(f"{app_name}: {ok} OK → Cores {min(cores)}-{max(cores)}")
            
            for f in failed:
                errors.append(f"❌ {f['name']} (PID {f['pid']}):\n   {f['error']}")
        
        if not all_results:
            messagebox.showwarning("Warning", "No processes to update!")
            return
        
        msg = "Affinity applied:\n\n" + "\n".join(all_results)
        
        if errors:
            msg += "\n\n⚠️ ERRORS:\n\n" + "\n\n".join(errors)
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
        # Get the Python executable and script path
        script = sys.argv[0]
        
        # Use ShellExecute to run with 'runas' verb (triggers UAC)
        ctypes.windll.shell32.ShellExecuteW(
            None,           # hwnd
            "runas",        # operation - triggers UAC elevation
            sys.executable, # program - python.exe
            f'"{script}"',  # parameters - this script
            None,           # directory
            1               # show window
        )
    except Exception as e:
        messagebox.showerror("Error", f"Failed to elevate privileges:\n{e}")

def main():
    if not is_admin():
        # Relaunch with admin rights
        run_as_admin()
        return
    
    root = tk.Tk()
    
    style = ttk.Style()
    if 'vista' in style.theme_names():
        style.theme_use('vista')
    elif 'clam' in style.theme_names():
        style.theme_use('clam')
    
    app = AffinityManagerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
