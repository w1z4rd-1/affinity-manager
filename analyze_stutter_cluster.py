import csv
import statistics

# Deep dive into what happens during the big stutter cluster at ~7-12s
with open(r'C:\Users\Terac\Documents\PresentMon\Captures\wizSS\pmcap-javaw.exe-251207-105743.csv', 'r') as f:
    reader = csv.reader(f)
    header = next(reader)
    
    idx_time = header.index('TimeInSeconds')
    idx_between_presents = header.index('MsBetweenPresents')
    idx_cpu_busy = header.index('MsCPUBusy')
    idx_gpu_busy = header.index('MsGPUBusy')
    idx_gpu_util = header.index('GPUUtilization')
    idx_cpu_util = header.index('CPUUtilization')
    idx_cpu_freq = header.index('CPUFrequency')
    idx_gpu_freq = header.index('GPUFrequency')
    idx_present_mode = header.index('PresentMode')
    
    rows = list(reader)
    
    # Get frames during stutter period (7-13s) vs normal period (50-60s)
    stutter_frames = []
    normal_frames = []
    
    for row in rows:
        try:
            t = float(row[idx_time])
            bp = float(row[idx_between_presents])
            cpu_busy = float(row[idx_cpu_busy]) if row[idx_cpu_busy] else 0
            gpu_busy = float(row[idx_gpu_busy]) if row[idx_gpu_busy] else 0
            cpu_util = float(row[idx_cpu_util]) if row[idx_cpu_util] else 0
            cpu_freq = float(row[idx_cpu_freq]) if row[idx_cpu_freq] else 0
            gpu_freq = float(row[idx_gpu_freq]) if row[idx_gpu_freq] else 0
            
            frame = {
                'time': t,
                'frame_time': bp,
                'cpu_busy': cpu_busy,
                'gpu_busy': gpu_busy,
                'cpu_util': cpu_util,
                'cpu_freq': cpu_freq,
                'gpu_freq': gpu_freq
            }
            
            if 7 <= t <= 13:
                stutter_frames.append(frame)
            elif 50 <= t <= 60:
                normal_frames.append(frame)
        except:
            pass
    
    print("=== Comparison: Stutter Period (7-13s) vs Normal Period (50-60s) ===\n")
    
    def summarize(name, frames):
        if not frames:
            print(f"{name}: No data")
            return
        print(f"{name}:")
        print(f"  Frames: {len(frames)}")
        ft = [f['frame_time'] for f in frames]
        print(f"  Frame time: avg={statistics.mean(ft):.2f}ms, med={statistics.median(ft):.2f}ms, max={max(ft):.2f}ms")
        print(f"  Effective FPS: {1000/statistics.mean(ft):.1f}")
        
        cpu = [f['cpu_busy'] for f in frames if f['cpu_busy']]
        gpu = [f['gpu_busy'] for f in frames if f['gpu_busy']]
        cpu_util = [f['cpu_util'] for f in frames if f['cpu_util']]
        
        if cpu:
            print(f"  CPU busy: avg={statistics.mean(cpu):.2f}ms, max={max(cpu):.2f}ms")
        if gpu:
            print(f"  GPU busy: avg={statistics.mean(gpu):.2f}ms, max={max(gpu):.2f}ms")
        if cpu_util:
            print(f"  CPU util: avg={statistics.mean(cpu_util):.1f}%, max={max(cpu_util):.1f}%")
        
        # Count frames over threshold
        over_16 = len([f for f in frames if f['frame_time'] > 16.67])
        over_33 = len([f for f in frames if f['frame_time'] > 33.33])
        print(f"  Frames >16.67ms (60fps): {over_16} ({100*over_16/len(frames):.1f}%)")
        print(f"  Frames >33.33ms (30fps): {over_33} ({100*over_33/len(frames):.1f}%)")
        print()
    
    summarize("Stutter Period (7-13s)", stutter_frames)
    summarize("Normal Period (50-60s)", normal_frames)
    
    # Look at the exact frames around the worst stutter (10.9s, 331ms)
    print("=== Frames around worst stutter (10.2s-11.5s) ===")
    for row in rows:
        try:
            t = float(row[idx_time])
            if 10.0 <= t <= 11.5:
                bp = float(row[idx_between_presents])
                cpu_busy = float(row[idx_cpu_busy]) if row[idx_cpu_busy] else 0
                gpu_busy = float(row[idx_gpu_busy]) if row[idx_gpu_busy] else 0
                if bp > 10:  # Only show significant frames
                    print(f"  {t:.3f}s: {bp:.1f}ms (CPU:{cpu_busy:.1f}ms, GPU:{gpu_busy:.1f}ms)")
        except:
            pass

    # Frame time histogram
    print("\n=== Frame Time Distribution (all frames) ===")
    all_ft = [float(row[idx_between_presents]) for row in rows if row[idx_between_presents]]
    
    buckets = {
        '<4ms (250+ fps)': 0,
        '4-8ms (125-250 fps)': 0,
        '8-16ms (60-125 fps)': 0,
        '16-33ms (30-60 fps)': 0,
        '33-100ms (10-30 fps)': 0,
        '>100ms (<10 fps)': 0
    }
    
    for ft in all_ft:
        if ft < 4:
            buckets['<4ms (250+ fps)'] += 1
        elif ft < 8:
            buckets['4-8ms (125-250 fps)'] += 1
        elif ft < 16:
            buckets['8-16ms (60-125 fps)'] += 1
        elif ft < 33:
            buckets['16-33ms (30-60 fps)'] += 1
        elif ft < 100:
            buckets['33-100ms (10-30 fps)'] += 1
        else:
            buckets['>100ms (<10 fps)'] += 1
    
    total = len(all_ft)
    for bucket, count in buckets.items():
        bar = '#' * int(50 * count / total)
        print(f"  {bucket:25s}: {count:6d} ({100*count/total:5.1f}%) {bar}")

