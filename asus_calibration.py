import os
import sys
import time
import threading
import multiprocessing
import subprocess
import glob

# Ensure local imports work cleanly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from asus_hardware import write_file, force_fans_max, restore_fans_auto, get_system_status, park_cores
from asus_custom_benchmark import cpu_worker, _gpu_worker

class AsusHardwareCalibrator:
    def __init__(self, log_callback=None, progress_callback=None):
        self.log_callback = log_callback
        self.progress_callback = progress_callback
        self.running = False
        self.cpu_processes = []
        self.gpu_processes = []
        
        # Discovered bounds
        self.max_cpu_tdp = 45 # Default fallback
        self.max_combined_tdp = 80 # Default fallback
        self.suspended_services = []

    def log(self, msg, level="info"):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{level.upper()}] {msg}\n"
        
        # 1. Print to console / execute callback
        if self.log_callback:
            self.log_callback(msg, level)
        else:
            print(log_line, end="")
            
        # 2. Append to persistent log file on disk
        try:
            log_file = os.path.join(BASE_DIR, "calibration.log")
            with open(log_file, "a") as f:
                f.write(log_line)
        except Exception as e:
            print(f"[ERROR] Failed to write to calibration.log: {e}")

    def progress(self, pct, phase_text):
        if self.progress_callback:
            self.progress_callback(pct, phase_text)

    def wait_for_fans_ramp_up(self, target_pct=0.90, max_wait=60.0):
        """Polls fan speeds until they reach target_pct of max speed (6000 RPM)
           OR until the fan speeds plateau and stop increasing for 20 consecutive seconds."""
        max_rpm = 6000.0
        target_rpm = int(max_rpm * target_pct)
        self.log(f"Waiting for fans to reach 90% of max speed ({target_rpm} RPM)...", "info")
        
        # Give fans a tiny bit of time to start spinning up initially
        time.sleep(2.0)
        
        start_time = time.time()
        
        max_cpu_seen = 0
        max_gpu_seen = 0
        cpu_no_increase_ticks = 0
        gpu_no_increase_ticks = 0
        
        while self.running and (time.time() - start_time < max_wait):
            status = get_system_status()
            cpu_fan = status.get("cpu_fan", 0)
            gpu_fan = status.get("gpu_fan", 0)
            
            self.log(f"-> Fan Speeds: CPU: {cpu_fan} RPM | GPU: {gpu_fan} RPM (Target: {target_rpm} RPM)", "info")
            
            # Check target threshold
            cpu_ready = (cpu_fan >= target_rpm) or (cpu_fan == 0 and time.time() - start_time > 4.0)
            gpu_ready = (gpu_fan >= target_rpm) or (gpu_fan == 0 and time.time() - start_time > 4.0)
            
            if cpu_ready and gpu_ready:
                self.log(f"Fans successfully spun up to target! CPU: {cpu_fan} RPM | GPU: {gpu_fan} RPM", "success")
                return True
                
            # Track CPU fan plateau (only track if fan is active/present)
            if cpu_fan > 0:
                if cpu_fan > max_cpu_seen:
                    max_cpu_seen = cpu_fan
                    cpu_no_increase_ticks = 0
                else:
                    cpu_no_increase_ticks += 1
            
            # Track GPU fan plateau (only track if fan is active/present)
            if gpu_fan > 0:
                if gpu_fan > max_gpu_seen:
                    max_gpu_seen = gpu_fan
                    gpu_no_increase_ticks = 0
                else:
                    gpu_no_increase_ticks += 1
            
            # A fan is stagnant if it hasn't increased for 20s, or if it reads 0 (not present) after 4s
            cpu_stagnant = (cpu_no_increase_ticks >= 20) or (cpu_fan == 0 and time.time() - start_time > 4.0)
            gpu_stagnant = (gpu_no_increase_ticks >= 20) or (gpu_fan == 0 and time.time() - start_time > 4.0)
            
            if cpu_stagnant and gpu_stagnant:
                self.log(f"Fan speeds have plateaued and stopped increasing (CPU Max: {max_cpu_seen} RPM, GPU Max: {max_gpu_seen} RPM). Proceeding with calibration.", "success")
                return True
                
            time.sleep(1.0)
            
        self.log("Fan ramp-up monitoring timed out. Proceeding with calibration anyway.", "warning")
        return False

    def suspend_interfering_services(self):
        """Finds active system daemons (thermald, power-profiles-daemon, tlp) and suspends them, while ensuring asusd is running."""
        # Ensure asusd.service is running because asusctl commands rely on it
        try:
            self.log("Ensuring asusd.service is active for D-Bus control...", "info")
            subprocess.run(["systemctl", "start", "asusd.service"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2.0)
        except Exception as e:
            self.log(f"Warning: Failed to start/ensure asusd.service: {e}", "warning")

        self.suspended_services = []
        services_to_check = [
            "thermald.service",
            "power-profiles-daemon.service",
            "tlp.service"
        ]
        self.log("Identifying system services that may override fan or power limits...", "info")
        for svc in services_to_check:
            try:
                # Check if active
                res = subprocess.run(["systemctl", "is-active", svc], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.0)
                if res.stdout.strip() == "active":
                    self.log(f"Suspending service: {svc} to prevent interference...", "info")
                    subprocess.run(["systemctl", "stop", svc], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2.0)
                    self.suspended_services.append(svc)
            except Exception as e:
                self.log(f"Error checking/stopping {svc}: {e}", "warning")

    def restore_suspended_services(self):
        """Restores any services that were suspended at the beginning of the calibration."""
        if not self.suspended_services:
            return
        self.log("Restoring suspended system services...", "info")
        for svc in self.suspended_services:
            try:
                self.log(f"Resuming service: {svc}...", "info")
                subprocess.run(["systemctl", "start", svc], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2.0)
            except Exception as e:
                self.log(f"Error restarting {svc}: {e}", "warning")
        self.suspended_services = []

    def stop_all_workloads(self):
        self.running = False
        # Terminate any running stress processes
        for p in self.cpu_processes:
            if p.is_alive():
                p.terminate()
        for p in self.gpu_processes:
            if p.is_alive():
                p.terminate()
        self.cpu_processes = []
        self.gpu_processes = []
        
        # Restore hardware defaults
        restore_fans_auto()
        park_cores(park=False)
        self.log("Hardware stress workloads terminated. Fans restored to auto.", "info")
        self.restore_suspended_services()

    def run_cpu_stress_daemon(self, duration=30):
        """Spawns prime stress threads on all cores to generate heat."""
        cores = multiprocessing.cpu_count() or 4
        q = multiprocessing.Queue()
        self.cpu_processes = []
        for _ in range(cores):
            p = multiprocessing.Process(target=cpu_worker, args=(duration, q))
            self.cpu_processes.append(p)
            p.start()

    def run_gpu_stress_daemon(self, duration=30):
        """Spawns trigonometric vertex shader threads on all cores to generate GPU/joint load."""
        cores = max(2, (multiprocessing.cpu_count() or 4) // 2)
        q = multiprocessing.Queue()
        self.gpu_processes = []
        for _ in range(cores):
            p = multiprocessing.Process(target=_gpu_worker, args=(duration, q))
            self.gpu_processes.append(p)
            p.start()

    def calibrate_cpu(self):
        """Step-by-step CPU thermal bounds discovery loop (Safe target: 95°C)."""
        self.log("--- STARTING PHASE 1: CPU THERMAL LIMIT DISCOVERY ---", "info")
        self.log("Forcing both laptop fans to 100% max cooling hyper-drive...", "info")
        force_fans_max()
        self.wait_for_fans_ramp_up()
        
        target_temp = 95.0
        current_pl1 = 25 # Start low
        settle_time = 12 # Seconds to settle heatpipe thermal inertia
        sample_time = 3  # Seconds to average temperature
        
        self.log(f"Initiating CPU Prime Stress workloads. Calibrating safe limit up to {target_temp}°C...", "info")
        
        try:
            while self.running and current_pl1 <= 135:
                self.progress(15 + int((current_pl1 / 100) * 20), f"Testing CPU PL1 = {current_pl1}W...")
                self.log(f"Setting CPU SPL (PL1) to {current_pl1}W...", "info")
                write_file("/sys/devices/platform/asus-nb-wmi/ppt_pl1_spl", current_pl1)
                write_file("/sys/devices/platform/asus-nb-wmi/ppt_pl2_sppt", current_pl1)
                
                # Start stress threads for this step
                self.run_cpu_stress_daemon(duration=settle_time + sample_time + 2)
                
                # Settle phase
                self.log(f"Allowing heatpipes to settle at {current_pl1}W (12s)...", "info")
                t0 = time.time()
                while time.time() - t0 < settle_time:
                    if not self.running: return False
                    status = get_system_status()
                    self.log(f"-> Telemetry: {status['cpu_temp']}°C | CPU Wattage: {status['cpu_wattage']}W", "info")
                    time.sleep(3)
                
                # Sample phase
                self.log("Averaging CPU core temperature and power over 3 seconds...", "info")
                temps = []
                wattages = []
                t0 = time.time()
                while time.time() - t0 < sample_time:
                    if not self.running: return False
                    status = get_system_status()
                    temps.append(status["cpu_temp"])
                    wattages.append(status["cpu_wattage"])
                    time.sleep(1)
                
                avg_temp = sum(temps) / len(temps) if temps else 50.0
                avg_w = sum(wattages) / len(wattages) if wattages else float(current_pl1)
                self.log(f"Average CPU Temp: {avg_temp:.1f}°C (Average CPU Draw: {avg_w:.1f}W)", "success")
                
                # Clean up stress threads for this step
                for p in self.cpu_processes: p.terminate()
                
                # Decision logic
                if avg_temp >= target_temp + 1.5:
                    # Temperature exceeded target! Back off from actual draw and settle.
                    self.max_cpu_tdp = max(25, int(avg_w) - 5)
                    self.log(f"CPU TjMax buffer limit reached! Setting maximum CPU TDP to: {self.max_cpu_tdp}W", "success")
                    break
                elif avg_temp >= target_temp - 2.0:
                    # Within safe target window
                    self.max_cpu_tdp = int(avg_w)
                    self.log(f"CPU sweet-spot discovered! Setting maximum CPU TDP to: {self.max_cpu_tdp}W", "success")
                    break
                else:
                    # Still below target limit. Boost TDP for next step.
                    self.max_cpu_tdp = int(avg_w)
                    current_pl1 += 5
                    
            return True
        except Exception as e:
            self.log(f"Error during CPU calibration: {e}", "error")
            return False

    def calibrate_joint(self):
        """Step-by-step CPU + GPU combined bounds discovery loop (Safe targets: CPU 95°C, GPU 82°C)."""
        self.log("\n--- STARTING PHASE 2: JOINT CPU+GPU THERMAL LIMIT DISCOVERY ---", "info")
        self.log("Forcing both laptop fans to 100% max cooling hyper-drive...", "info")
        force_fans_max()
        self.wait_for_fans_ramp_up()
        
        cpu_target_temp = 95.0
        gpu_target_temp = 82.0
        current_cpu_pl1 = 20 # Start very conservative
        settle_time = 12
        sample_time = 3
        
        self.log(f"Initiating Combined Workloads. Calibrating CPU up to {cpu_target_temp}°C and GPU up to {gpu_target_temp}°C...", "info")
        
        try:
            while self.running and current_cpu_pl1 <= 95:
                self.progress(60 + int((current_cpu_pl1 / 80) * 30), f"Testing Combined (CPU PL1 = {current_cpu_pl1}W + GPU)...")
                self.log(f"Setting CPU SPL (PL1) to {current_cpu_pl1}W under joint GPU stress...", "info")
                write_file("/sys/devices/platform/asus-nb-wmi/ppt_pl1_spl", current_cpu_pl1)
                write_file("/sys/devices/platform/asus-nb-wmi/ppt_pl2_sppt", current_cpu_pl1)
                
                # Start both CPU and GPU stress threads
                self.run_cpu_stress_daemon(duration=settle_time + sample_time + 2)
                self.run_gpu_stress_daemon(duration=settle_time + sample_time + 2)
                
                # Settle phase
                self.log(f"Allowing shared heatpipes to settle under joint load (12s)...", "info")
                t0 = time.time()
                while time.time() - t0 < settle_time:
                    if not self.running: return False
                    status = get_system_status()
                    self.log(f"-> Telemetry: CPU: {status['cpu_temp']}°C ({status['cpu_wattage']}W) | GPU: {status['gpu_wattage']}W", "info")
                    time.sleep(3)
                
                # Sample phase
                self.log("Averaging CPU/GPU temperatures and power...", "info")
                cpu_temps = []
                cpu_wattages = []
                gpu_wattages = []
                t0 = time.time()
                while time.time() - t0 < sample_time:
                    if not self.running: return False
                    status = get_system_status()
                    cpu_temps.append(status["cpu_temp"])
                    cpu_wattages.append(status["cpu_wattage"])
                    gpu_wattages.append(status["gpu_wattage"])
                    time.sleep(1)
                
                avg_cpu_temp = sum(cpu_temps) / len(cpu_temps) if cpu_temps else 50.0
                avg_cpu_w = sum(cpu_wattages) / len(cpu_wattages) if cpu_wattages else float(current_cpu_pl1)
                avg_gpu_w = sum(gpu_wattages) / len(gpu_wattages) if gpu_wattages else 30.0
                
                self.log(f"Average CPU Temp under joint load: {avg_cpu_temp:.1f}°C (CPU: {avg_cpu_w:.1f}W, GPU: {avg_gpu_w:.1f}W)", "success")
                
                # Clean up stress threads
                for p in self.cpu_processes: p.terminate()
                for p in self.gpu_processes: p.terminate()
                
                # Decision logic: stop if CPU hits 95°C
                if avg_cpu_temp >= cpu_target_temp + 1.0:
                    # Shared heatpipe saturated! Back off CPU by 5W.
                    self.max_combined_tdp = max(35, int(avg_cpu_w) - 5 + int(avg_gpu_w))
                    self.log(f"Shared Heatpipe saturation point detected! Setting maximum Combined TDP to: {self.max_combined_tdp}W (CPU PL1: {int(avg_cpu_w) - 5}W + GPU: {int(avg_gpu_w)}W)", "success")
                    break
                elif avg_cpu_temp >= cpu_target_temp - 2.0:
                    # In sweet-spot
                    self.max_combined_tdp = int(avg_cpu_w) + int(avg_gpu_w)
                    self.log(f"Joint sweet-spot discovered! Setting maximum Combined TDP to: {self.max_combined_tdp}W (CPU PL1: {int(avg_cpu_w)}W + GPU: {int(avg_gpu_w)}W)", "success")
                    break
                else:
                    # Below limit.
                    self.max_combined_tdp = int(avg_cpu_w) + int(avg_gpu_w)
                    current_cpu_pl1 += 5
                    
            return True
        except Exception as e:
            self.log(f"Error during joint calibration: {e}", "error")
            return False

    def execute_calibration(self):
        """Main calibration entry point running in background thread."""
        self.running = True
        self.suspend_interfering_services()
        
        # Write visual run separator in persistent log file
        try:
            log_file = os.path.join(BASE_DIR, "calibration.log")
            with open(log_file, "a") as f:
                f.write("\n" + "=" * 80 + "\n")
        except:
            pass
            
        # We keep Turbo Boost enabled, but write PL1 and PL2 as equal values to restrict short-term boost headroom during sweeps.
            
        self.progress(5, "Initializing Calibrator...")
        self.log("=== INITIATING AUTONOMOUS HARDWARE THERMAL CALIBRATION ===", "success")
        
        try:
            # 1. Calibrate CPU only
            self.progress(10, "Calibrating CPU...")
            ok1 = self.calibrate_cpu()
            if not ok1 or not self.running:
                self.stop_all_workloads()
                self.progress(0, "Calibration Aborted.")
                return False
                
            # Allow system to cool down slightly before phase 2
            self.progress(50, "Cooling down system (10s)...")
            self.log("Cooling down CPU for 10 seconds before Joint Calibration...", "info")
            restore_fans_auto()
            t0 = time.time()
            while time.time() - t0 < 10:
                if not self.running: return False
                time.sleep(2)
                
            # 2. Calibrate Joint
            self.progress(55, "Calibrating Joint Workloads...")
            ok2 = self.calibrate_joint()
            
            # 3. Save discovered settings
            was_running = self.running
            self.stop_all_workloads()
            if ok2 and was_running:
                self.progress(100, "Calibration Complete!")
                self.log("=== HARDWARE CALIBRATION COMPLETED SUCCESSFULLY ===", "success")
                self.log(f"Discovered CPU Maximum TDP: {self.max_cpu_tdp}W", "success")
                self.log(f"Discovered Combined Joint TDP: {self.max_combined_tdp}W", "success")
                
                # Save dynamically to settings
                from asus_settings import load_active_settings
                import json
                
                # Save settings back to file
                SETTINGS_FILE = os.path.join(BASE_DIR, "asus_settings.json")
                try:
                    data = {}
                    if os.path.exists(SETTINGS_FILE):
                        with open(SETTINGS_FILE, 'r') as f:
                            data = json.load(f)
                    
                    data["max_cpu_tdp"] = self.max_cpu_tdp
                    data["max_combined_tdp"] = self.max_combined_tdp
                    data["calibration_timestamp"] = time.time()
                    
                    with open(SETTINGS_FILE, 'w') as f:
                        json.dump(data, f, indent=4)
                    self.log(f"Successfully saved dynamic calibration bounds to {SETTINGS_FILE}", "success")
                except Exception as ex:
                    self.log(f"Failed to save settings: {ex}", "error")
            else:
                self.progress(0, "Calibration Aborted.")
                
            return True
        except Exception as e:
            self.stop_all_workloads()
            self.log(f"Calibration failed: {e}", "error")
            self.progress(0, "Calibration Failed.")
            return False

if __name__ == "__main__":
    # Standardize pathing when running directly
    from asus_hardware import discover_hardware_paths
    discover_hardware_paths()
    calibrator = AsusHardwareCalibrator()
    calibrator.execute_calibration()
