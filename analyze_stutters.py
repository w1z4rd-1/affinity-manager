import csv
import statistics

# Analyze when stutters happen and what correlates with them
with open(r'C:\Users\Terac\Documents\PresentMon\Captures\wizSS\pmcap-javaw.exe-251207-105743.csv', 'r') as f:
    reader = csv.reader(f)
    header = next(reader)
    
    idx_time = header.index('TimeInSeconds')
    idx_between_presents = header.index('MsBetweenPresents')
    idx_cpu_busy = header.index('MsCPUBusy')
    idx_gpu_busy = header.index('MsGPUBusy')
    idx_gpu_util = header.index('GPUUtilization')
    idx_cpu_util = header.index('CPUUtilization')
    
    rows = list(reader)
    
    # Find stutter events (>20ms frame time)
    avg = 3.83
    stutters = []
    for i, row in enumerate(rows):
        try:
            bp = float(row[idx_between_presents])
            if bp > 20:  # 20ms = 50fps
                stutters.append({
                    'index': i,
                    'time': float(row[idx_time]),
                    'frame_time': bp,
                    'cpu_busy': float(row[idx_cpu_busy]) if row[idx_cpu_busy] else 0,
                    'gpu_busy': float(row[idx_gpu_busy]) if row[idx_gpu_busy] else 0,
                    'cpu_util': float(row[idx_cpu_util]) if row[idx_cpu_util] else 0,
                    'gpu_util': float(row[idx_gpu_util]) if row[idx_gpu_util] else 0
                })
        except:
            pass
    
    print(f'=== Stutter Events (>20ms) ===')
    print(f'Total: {len(stutters)} events')
    print()
    
    # Analyze correlation
    cpu_limited = [s for s in stutters if s['cpu_busy'] > s['gpu_busy'] * 1.5]
    gpu_limited = [s for s in stutters if s['gpu_busy'] > s['cpu_busy'] * 1.5]
    
    print(f'CPU-limited stutters: {len(cpu_limited)} ({100*len(cpu_limited)/len(stutters):.1f}%)')
    print(f'GPU-limited stutters: {len(gpu_limited)} ({100*len(gpu_limited)/len(stutters):.1f}%)')
    
    print()
    print('Top 15 worst stutters:')
    for s in sorted(stutters, key=lambda x: -x['frame_time'])[:15]:
        bottleneck = 'CPU' if s['cpu_busy'] > s['gpu_busy'] else 'GPU'
        print(f"  {s['time']:.1f}s: {s['frame_time']:.1f}ms (CPU:{s['cpu_busy']:.1f}ms, GPU:{s['gpu_busy']:.1f}ms) -> {bottleneck} bound")

    # Check if stutters are clustered
    print()
    print('=== Stutter Clustering ===')
    clusters = []
    current_cluster = []
    for s in stutters:
        if not current_cluster or s['time'] - current_cluster[-1]['time'] < 1.0:
            current_cluster.append(s)
        else:
            if len(current_cluster) > 1:
                clusters.append(current_cluster)
            current_cluster = [s]
    if len(current_cluster) > 1:
        clusters.append(current_cluster)
    
    print(f'Found {len(clusters)} stutter clusters (multiple stutters within 1s)')
    for i, c in enumerate(clusters[:5]):
        print(f'  Cluster at ~{c[0]["time"]:.1f}s: {len(c)} stutters')

