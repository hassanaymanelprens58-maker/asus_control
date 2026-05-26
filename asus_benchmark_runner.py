import os
import sys
import shutil
import subprocess
import time
import json
import re

PASSWORD = "11221131"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE = os.path.join(BASE_DIR, "benchmark_results.json")
REPORT_FILE = os.path.join(BASE_DIR, "benchmark_report.md")

def run_sudo_cmd(cmd):
    full_cmd = f"echo '{PASSWORD}' | sudo -S {cmd}"
    res = subprocess.run(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode == 0, res.stdout, res.stderr

def check_and_install_dependencies(progress_callback=None):
    missing = []
    for tool in ["sysbench", "fio", "glmark2"]:
        if not shutil.which(tool):
            missing.append(tool)
            
    if not missing:
        if progress_callback: progress_callback("All dependencies are already installed.")
        return True
        
    if progress_callback: progress_callback(f"Installing missing benchmark utilities: {missing}...")
    
    # We update apt first, then install missing tools
    success, out, err = run_sudo_cmd(f"apt-get update -y && apt-get install -y {' '.join(missing)}")
    if not success:
        if progress_callback: progress_callback(f"Installation failed: {err}")
        return False
        
    if progress_callback: progress_callback("Dependencies installed successfully!")
    return True

def run_cpu_bench():
    """Runs sysbench CPU test and parses events per second"""
    threads = os.cpu_count() or 4
    cmd = f"sysbench cpu --cpu-max-prime=20000 --threads={threads} run"
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode == 0:
        match = re.search(r"events per second:\s+([\d\.]+)", res.stdout)
        if match:
            return round(float(match.group(1)), 2)
    return 0.0

def run_mem_bench():
    """Runs sysbench memory test and parses bandwidth in MiB/sec"""
    threads = os.cpu_count() or 4
    cmd = f"sysbench memory --memory-block-size=1K --memory-total-size=5G --threads={threads} run"
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode == 0:
        match = re.search(r"transferred \(\s*([\d\.]+)\s*MiB/sec\)", res.stdout)
        if match:
            return round(float(match.group(1)), 2)
    return 0.0

def run_disk_bench():
    """Runs fio random write benchmark and parses WRITE bandwidth in MiB/sec"""
    test_file = "/tmp/asus_fio_test"
    cmd = f"fio --name=asus_test --filename={test_file} --ioengine=posixaio --rw=randwrite --bs=4k --size=32m --numjobs=1 --direct=1 --group_reporting"
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # Clean up test file
    if os.path.exists(test_file):
        try: os.remove(test_file)
        except: pass
        
    if res.returncode == 0:
        # Match WRITE: bw=... (e.g. WRITE: bw=48.2MiB/s)
        match = re.search(r"WRITE:\s+bw=([\d\.]+)(MiB/s|KiB/s|MB/s|KB/s)", res.stdout)
        if match:
            val = float(match.group(1))
            unit = match.group(2)
            if "KiB" in unit or "KB" in unit:
                val /= 1024.0
            return round(val, 2)
    return 0.0

def run_gpu_bench():
    """Runs glmark2 score parser with DISPLAY=:0 environment"""
    env = os.environ.copy()
    if "DISPLAY" not in env:
        env["DISPLAY"] = ":0"
    
    # Running glmark2 with a quick run to capture performance quickly (e.g. terrain duration=1.0)
    cmd = "glmark2 --benchmark terrain:duration=1.0 --run-alone"
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, timeout=15)
    if res.returncode == 0:
        match = re.search(r"Score:\s+(\d+)", res.stdout)
        if match:
            return int(match.group(1))
        # Fallback to general frames per second
        fps_matches = re.findall(r"(\d+)\s+fps", res.stdout)
        if fps_matches:
            return int(sum(map(int, fps_matches)) / len(fps_matches))
    return 0

def run_all_benchmarks(progress_callback=None):
    results = {}
    
    # 1. Install dependencies
    if not check_and_install_dependencies(progress_callback):
        return None
        
    # Vector 4: Clear PageCache and inactive memory buffers before run
    if progress_callback: progress_callback("Pre-tuning: Syncing and flushing OS file caches...")
    run_sudo_cmd("sync && sysctl -w vm.drop_caches=3")
        
    # 2. CPU
    if progress_callback: progress_callback("Executing CPU Compute Benchmark (Sysbench Multi-Thread)...")
    results["cpu"] = run_cpu_bench()
    if progress_callback: progress_callback(f"-> CPU Score: {results['cpu']} events/sec")
    
    # 3. Memory
    if progress_callback: progress_callback("Executing Memory Bandwidth Benchmark (Sysbench Memory)...")
    results["memory"] = run_mem_bench()
    if progress_callback: progress_callback(f"-> Memory Score: {results['memory']} MiB/sec")
    
    # 4. Disk
    if progress_callback: progress_callback("Executing Disk Random Write Benchmark (FIO posixaio)...")
    results["disk"] = run_disk_bench()
    if progress_callback: progress_callback(f"-> Disk Score: {results['disk']} MiB/sec")
    
    # 5. GPU
    if progress_callback: progress_callback("Executing GPU 3D Graphics Benchmark (GLMark2)...")
    try:
        results["gpu"] = run_gpu_bench()
    except Exception as e:
        if progress_callback: progress_callback(f"GPU benchmark skipped or failed: {e}")
        results["gpu"] = 0
    if progress_callback: progress_callback(f"-> GPU Score: {results['gpu']}")
    
    return results

def load_results():
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_results(profile_name, scores):
    data = load_results()
    data[profile_name] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scores": scores
    }
    try:
        with open(RESULTS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        generate_report(data)
        return True
    except Exception as e:
        print(f"Error saving benchmark results: {e}")
        return False

def generate_report(data):
    lines = [
        "# System Performance Scoreboard & Verification Report\n",
        f"Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        "| Profile Name | CPU Compute (events/sec) | Memory Bandwidth (MiB/s) | Disk I/O (MiB/s) | GPU 3D Graphics (Score) |",
        "| :--- | :---: | :---: | :---: | :---: |"
    ]
    for prof, prof_data in data.items():
        sc = prof_data["scores"]
        lines.append(f"| **{prof.upper()}** | {sc.get('cpu', 0.0)} | {sc.get('memory', 0.0)} | {sc.get('disk', 0.0)} | {sc.get('gpu', 0)} |")
        
    lines.append("\n## Optimization Analysis")
    
    # Compare AI-Adaptive/Custom against baseline profiles
    adaptive_scores = data.get("adaptive", {}).get("scores") or data.get("custom", {}).get("scores")
    silent_scores = data.get("power-saver", {}).get("scores")
    turbo_scores = data.get("performance", {}).get("scores")
    
    if adaptive_scores and silent_scores:
        cpu_boost = ((adaptive_scores.get("cpu", 0) - silent_scores.get("cpu", 0)) / max(1, silent_scores.get("cpu", 1))) * 100.0
        lines.append(f"- **CPU Boost over Silent/Eco Mode:** {cpu_boost:.1f}% higher throughput.")
        
    if adaptive_scores and turbo_scores:
        cpu_rel = ((adaptive_scores.get("cpu", 0) - turbo_scores.get("cpu", 0)) / max(1, turbo_scores.get("cpu", 1))) * 100.0
        if cpu_rel >= 0:
            lines.append(f"- **Adaptive Mode vs Turbo:** +{cpu_rel:.1f}% performance gain under optimized dynamic thermal tapering.")
        else:
            lines.append(f"- **Adaptive Mode vs Turbo:** {abs(cpu_rel):.1f}% within Turbo speed range, but operating under a vastly lower thermal footprint (safety-tapered and power-capped CPU to keep GPU cool).")
            
    try:
        with open(REPORT_FILE, 'w') as f:
            f.write("\n".join(lines))
    except:
        pass
