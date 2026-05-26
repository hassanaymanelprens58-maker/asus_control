import os
import sys
import subprocess
import time
import math

PASSWORD = "11221131"
BATTERY_PATH = "/sys/class/power_supply/BAT1"
HWMON_PATHS = {"coretemp": None, "asus": None, "custom_fan": None}

# Telemetry state
TELEMETRY_STATE = {
    "prev_energy": 0.0,
    "prev_time": 0.0,
    "prev_cpu_w": 0.0
}

SLOW_CACHE = {
    "tick_count": 0,
    "gpu_mode": "standard",
    "refresh_rate": 60.0,
    "power_profile": "balanced",
    "custom_cpu_active": False,
    "custom_gpu_active": False
}

# Safe read helper
def read_file(path, default="0"):
    try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                return f.read().strip()
    except Exception as e:
        print(f"Error reading {path}: {e}")
    return default

# Execute shell command with sudo password
def run_sudo_cmd(cmd):
    try:
        full_cmd = f"echo '{PASSWORD}' | sudo -S {cmd}"
        result = subprocess.run(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            print(f"Sudo command failed: {cmd}\nError: {result.stderr}")
            return False, result.stderr
        return True, result.stdout
    except Exception as e:
        print(f"Exception running command {cmd}: {e}")
        return False, str(e)

# Direct sysfs node write helper with sudo fallback
def write_file(path, value, use_sudo_fallback=True):
    try:
        if os.path.exists(path):
            with open(path, 'w') as f:
                f.write(str(value))
            return True, ""
        else:
            return False, f"Path does not exist: {path}"
    except Exception as e:
        if use_sudo_fallback:
            cmd = f"sh -c 'echo {value} > {path}'"
            return run_sudo_cmd(cmd)
        else:
            return False, str(e)

# Discover WMI and Battery paths
def discover_hardware_paths():
    global HWMON_PATHS, BATTERY_PATH
    try:
        for d in os.listdir("/sys/class/hwmon"):
            name_path = os.path.join("/sys/class/hwmon", d, "name")
            if os.path.exists(name_path):
                with open(name_path, 'r') as f:
                    name = f.read().strip()
                    if name == "coretemp":
                        HWMON_PATHS["coretemp"] = os.path.join("/sys/class/hwmon", d)
                    elif name == "asus":
                        HWMON_PATHS["asus"] = os.path.join("/sys/class/hwmon", d)
                    elif name == "asus_custom_fan_curve":
                        HWMON_PATHS["custom_fan"] = os.path.join("/sys/class/hwmon", d)
    except Exception as e:
        print(f"Error discovering hardware hwmons: {e}")

    for name in ["BAT1", "BAT0", "BATT"]:
        path = f"/sys/class/power_supply/{name}"
        if os.path.exists(path):
            BATTERY_PATH = path
            return
    try:
        for entry in os.listdir("/sys/class/power_supply"):
            if entry.startswith("BAT"):
                BATTERY_PATH = f"/sys/class/power_supply/{entry}"
                return
    except:
        pass

# Discover primary display
def get_primary_display():
    try:
        res = subprocess.run("xrandr | grep ' connected primary'", shell=True, stdout=subprocess.PIPE, text=True, timeout=1.0)
        if res.returncode == 0 and res.stdout:
            return res.stdout.split()[0]
    except:
        pass
    return "eDP-1"

# Get CPU wattage
def get_cpu_wattage():
    global TELEMETRY_STATE
    curr_time = time.time()
    try:
        energy_path = "/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"
        success = False
        res = ""
        try:
            with open(energy_path, 'r') as f:
                res = f.read().strip()
                success = True
        except PermissionError:
            success, res = run_sudo_cmd(f"cat {energy_path}")
            
        if success and res:
            curr_energy = float(res.strip())
            if TELEMETRY_STATE["prev_energy"] > 0:
                time_diff = curr_time - TELEMETRY_STATE["prev_time"]
                energy_diff = curr_energy - TELEMETRY_STATE["prev_energy"]
                if time_diff > 0 and energy_diff >= 0:
                    wattage = round((energy_diff / time_diff) / 1000000.0, 1)
                    if 0.0 <= wattage <= 150.0:
                        TELEMETRY_STATE["prev_cpu_w"] = wattage
            TELEMETRY_STATE["prev_energy"] = curr_energy
            TELEMETRY_STATE["prev_time"] = curr_time
    except Exception as e:
        print(f"Error calculating CPU wattage: {e}")
    return TELEMETRY_STATE["prev_cpu_w"]

# Get CPU current frequency
def get_cpu_freq():
    try:
        val = read_file("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", "0")
        khz = float(val)
        if khz > 0:
            return round(khz / 1000.0) # Convert to MHz
    except:
        pass
    return 3000

# Get GPU stats (wattage, graphics clock, and GPU utilization)
def get_gpu_stats():
    try:
        res = subprocess.run(["nvidia-smi", "--query-gpu=power.draw,clocks.gr,utilization.gpu", "--format=csv,noheader,nounits"], stdout=subprocess.PIPE, text=True, timeout=1.0)
        if res.returncode == 0:
            parts = res.stdout.strip().split(",")
            if len(parts) == 3:
                w = round(float(parts[0].strip()), 1)
                freq = int(float(parts[1].strip()))
                util = int(parts[2].strip())
                return w, freq, util
    except:
        pass
    return 0.0, 0, 0


# Fan Curve IO operations (with asusctl support)
def read_fan_curve(fan_idx):
    discover_hardware_paths()
    points = []
    path = HWMON_PATHS.get("custom_fan")
    if not path:
        return [(30, 35), (55, 66), (61, 81), (66, 107), (70, 135), (77, 163), (80, 193), (82, 221)]
    for i in range(1, 9):
        temp = int(read_file(os.path.join(path, f"pwm{fan_idx}_auto_point{i}_temp"), str(30 + i * 8)))
        pwm = int(read_file(os.path.join(path, f"pwm{fan_idx}_auto_point{i}_pwm"), str(30 + i * 20)))
        points.append([temp, pwm])
    return points

def write_fan_curve(fan_idx, points):
    discover_hardware_paths()
    has_asusctl = False
    try:
        res = subprocess.run(["which", "asusctl"], stdout=subprocess.PIPE, text=True)
        has_asusctl = res.returncode == 0
    except:
        pass

    if has_asusctl:
        try:
            profile = "Balanced"
            p_res = subprocess.run(["asusctl", "profile", "get"], stdout=subprocess.PIPE, text=True, timeout=1.0)
            if p_res.returncode == 0:
                for line in p_res.stdout.splitlines():
                    if "Active profile:" in line:
                        profile = line.split(":")[-1].strip()
                        break
            fan_name = "cpu" if fan_idx == 1 else "gpu"
            points_str = ",".join([f"{temp}c:{pwm}" for temp, pwm in points])
            r1 = subprocess.run(["asusctl", "fan-curve", "--mod-profile", profile, "--fan", fan_name, "--enable-fan-curve", "true"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2.0)
            r2 = subprocess.run(["asusctl", "fan-curve", "--mod-profile", profile, "--fan", fan_name, "--data", points_str], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2.0)
            r3 = subprocess.run(["asusctl", "fan-curve", "--mod-profile", profile, "--enable-fan-curves", "true"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2.0)
            if r1.returncode == 0 and r2.returncode == 0 and r3.returncode == 0:
                return True, ""
            else:
                print(f"asusctl failed with return codes: {r1.returncode}, {r2.returncode}, {r3.returncode}. Falling back to hwmon direct writes.")
        except Exception as e:
            print(f"Error applying fan curve via asusctl: {e}")

    path = HWMON_PATHS.get("custom_fan")
    if not path:
        return False, "Custom fan curves node not discovered."
    success = True
    errs = []
    for i, (temp, pwm) in enumerate(points, 1):
        s1, e1 = write_file(os.path.join(path, f"pwm{fan_idx}_auto_point{i}_temp"), temp)
        s2, e2 = write_file(os.path.join(path, f"pwm{fan_idx}_auto_point{i}_pwm"), pwm)
        success = success and s1 and s2
        if e1: errs.append(e1)
        if e2: errs.append(e2)
    s_c, e_c = write_file(os.path.join(path, f"pwm{fan_idx}_enable"), "2")
    success = success and s_c
    if e_c: errs.append(e_c)
    asus_path = HWMON_PATHS.get("asus")
    if asus_path:
        s_a, e_a = write_file(os.path.join(asus_path, f"pwm{fan_idx}_enable"), "2")
        success = success and s_a
        if e_a: errs.append(e_a)
    return success, ", ".join(errs) if errs else ""

def force_fans_max():
    """
    Force BOTH fans (CPU+GPU) to 100% PWM immediately by writing all 8 curve
    points to max (255) with strictly ascending temperatures.
    This is used for pre-cooling before performance benchmarks.
    """
    max_points = [[30 + i * 5, 255] for i in range(8)]   # Ascending temperatures to satisfy driver requirements
    ok1, _ = write_fan_curve(1, max_points)  # CPU fan
    ok2, _ = write_fan_curve(2, max_points)  # GPU fan
    return ok1 or ok2

def restore_fans_auto():
    """
    Return both fans to hardware-managed (EC) auto mode.
    """
    disable_custom_fan_curve(1)
    disable_custom_fan_curve(2)

def disable_custom_fan_curve(fan_idx):
    discover_hardware_paths()
    has_asusctl = False
    try:
        res = subprocess.run(["which", "asusctl"], stdout=subprocess.PIPE, text=True)
        has_asusctl = res.returncode == 0
    except:
        pass

    if has_asusctl:
        try:
            profile = "Balanced"
            p_res = subprocess.run(["asusctl", "profile", "get"], stdout=subprocess.PIPE, text=True, timeout=1.0)
            if p_res.returncode == 0:
                for line in p_res.stdout.splitlines():
                    if "Active profile:" in line:
                        profile = line.split(":")[-1].strip()
                        break
            fan_name = "cpu" if fan_idx == 1 else "gpu"
            subprocess.run(["asusctl", "fan-curve", "--mod-profile", profile, "--fan", fan_name, "--enable-fan-curve", "false"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2.0)
            return True
        except Exception as e:
            print(f"Error disabling fan curve via asusctl: {e}")

    path = HWMON_PATHS.get("custom_fan")
    success = True
    if path:
        s1, e1 = write_file(os.path.join(path, f"pwm{fan_idx}_enable"), "2")
        success = success and s1
    asus_path = HWMON_PATHS.get("asus")
    if asus_path:
        s2, e2 = write_file(os.path.join(asus_path, f"pwm{fan_idx}_enable"), "2")
        success = success and s2
    return success

def get_ram_usage():
    try:
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
        mem_total = 0
        mem_avail = 0
        for line in lines:
            if "MemTotal" in line:
                mem_total = int(line.split()[1])
            elif "MemAvailable" in line:
                mem_avail = int(line.split()[1])
        if mem_total > 0:
            mem_used = mem_total - mem_avail
            gb_total = round(mem_total / (1024.0 * 1024.0), 1)
            gb_used = round(mem_used / (1024.0 * 1024.0), 1)
            pct = mem_used / mem_total
            return gb_used, gb_total, pct
    except:
        pass
    return 4.0, 16.0, 0.25

def get_storage_usage():
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        gb_total = round(total / (1024.0 * 1024.0 * 1024.0), 1)
        gb_used = round(used / (1024.0 * 1024.0 * 1024.0), 1)
        pct = used / total
        return gb_used, gb_total, pct
    except:
        pass
    return 120.0, 512.0, 0.25

PREV_CPU_STAT = {"idle": 0, "total": 0}

def get_cpu_usage_pct():
    global PREV_CPU_STAT
    try:
        with open("/proc/stat", "r") as f:
            line = f.readline()
        if line.startswith("cpu"):
            parts = [int(x) for x in line.split()[1:8]] # user, nice, system, idle, iowait, irq, softirq
            idle = parts[3] + parts[4]
            total = sum(parts)
            
            diff_idle = idle - PREV_CPU_STAT["idle"]
            diff_total = total - PREV_CPU_STAT["total"]
            
            PREV_CPU_STAT["idle"] = idle
            PREV_CPU_STAT["total"] = total
            
            if diff_total > 0:
                return round((1.0 - (diff_idle / diff_total)) * 100.0, 1)
    except Exception as e:
        print(f"Error calculating CPU utilization: {e}")
    return 5.0

# System status query
def get_system_status():
    global SLOW_CACHE
    SLOW_CACHE["tick_count"] += 1
    discover_hardware_paths()
    
    capacity = int(read_file(f"{BATTERY_PATH}/capacity", "0"))
    status = read_file(f"{BATTERY_PATH}/status", "Unknown")
    threshold = int(read_file(f"{BATTERY_PATH}/charge_control_end_threshold", "100"))
    
    charge_full = float(read_file(f"{BATTERY_PATH}/charge_full", "1.0"))
    charge_full_design = float(read_file(f"{BATTERY_PATH}/charge_full_design", "1.0"))
    health = round((charge_full / charge_full_design) * 100.0, 2) if charge_full_design > 0 else 100.0
    
    try:
        power_raw = read_file(f"{BATTERY_PATH}/power_now", "-1")
        if int(power_raw) >= 0:
            wattage = round(float(power_raw) / 1000000.0, 1)
        else:
            current_now = float(read_file(f"{BATTERY_PATH}/current_now", "0"))
            voltage_now = float(read_file(f"{BATTERY_PATH}/voltage_now", "0"))
            wattage = round((current_now / 1000000.0) * (voltage_now / 1000000.0), 1)
    except:
        try:
            current_now = float(read_file(f"{BATTERY_PATH}/current_now", "0"))
            voltage_now = float(read_file(f"{BATTERY_PATH}/voltage_now", "0"))
            wattage = round((current_now / 1000000.0) * (voltage_now / 1000000.0), 1)
        except:
            wattage = 0.0
        
    temp = 0.0
    if HWMON_PATHS["coretemp"]:
        temp_raw = read_file(os.path.join(HWMON_PATHS["coretemp"], "temp1_input"), "0")
        temp = round(float(temp_raw) / 1000.0, 1)
    
    cpu_fan = 0
    gpu_fan = 0
    if HWMON_PATHS["asus"]:
        cpu_fan = int(read_file(os.path.join(HWMON_PATHS["asus"], "fan1_input"), "0"))
        gpu_fan = int(read_file(os.path.join(HWMON_PATHS["asus"], "fan2_input"), "0"))
        
    kbd_brightness = int(read_file("/sys/class/leds/asus::kbd_backlight/brightness", "0"))
    hostname = read_file("/proc/sys/kernel/hostname", "ASUS-Laptop")
    
    panel_od = int(read_file("/sys/devices/platform/asus-nb-wmi/panel_od", "0"))
    pl1 = int(read_file("/sys/devices/platform/asus-nb-wmi/ppt_pl1_spl", "45"))
    pl2 = int(read_file("/sys/devices/platform/asus-nb-wmi/ppt_pl2_sppt", "80"))
    nv_dynamic_boost = int(read_file("/sys/devices/platform/asus-nb-wmi/nv_dynamic_boost", "5"))
    nv_temp_target = int(read_file("/sys/devices/platform/asus-nb-wmi/nv_temp_target", "75"))
    
    # Query actual system RAM & Storage (instant proc/sys statvfs)
    ram_used, ram_total, ram_pct = get_ram_usage()
    disk_used, disk_total, disk_pct = get_storage_usage()
    
    # ------------------ SLOW COMMANDS CACHE ------------------
    # Query heavy subprocesses once at boot, then only every 10 ticks (e.g. every 5 seconds if poll is 500ms)
    is_slow_tick = (SLOW_CACHE["tick_count"] % 10 == 1 or SLOW_CACHE["tick_count"] == 1)
    
    if is_slow_tick:
        # 1. Query gpu_mode from supergfxctl
        try:
            res = subprocess.run(["supergfxctl", "-g"], stdout=subprocess.PIPE, text=True, timeout=0.4)
            s_mode = res.stdout.strip()
            if s_mode == "Integrated":
                SLOW_CACHE["gpu_mode"] = "eco"
            elif s_mode == "AsusMuxDgpu":
                SLOW_CACHE["gpu_mode"] = "ultimate"
            else:
                SLOW_CACHE["gpu_mode"] = "standard"
        except:
            dgpu_disable = int(read_file("/sys/devices/platform/asus-nb-wmi/dgpu_disable", "0"))
            gpu_mux_mode = int(read_file("/sys/devices/platform/asus-nb-wmi/gpu_mux_mode", "0"))
            if dgpu_disable == 1:
                SLOW_CACHE["gpu_mode"] = "eco"
            elif gpu_mux_mode == 1:
                SLOW_CACHE["gpu_mode"] = "ultimate"
            else:
                SLOW_CACHE["gpu_mode"] = "standard"
                
        # 2. Query power_profile from powerprofilesctl
        try:
            profile_res = subprocess.run(["powerprofilesctl", "get"], stdout=subprocess.PIPE, text=True, timeout=0.4)
            SLOW_CACHE["power_profile"] = profile_res.stdout.strip()
        except:
            SLOW_CACHE["power_profile"] = "balanced"
            
        # 3. Query refresh_rate from xrandr
        current_rr = 60.0
        try:
            rr_res = subprocess.run("xrandr --verbose | grep -E '\\*'", shell=True, stdout=subprocess.PIPE, text=True, timeout=0.4)
            for line in rr_res.stdout.splitlines():
                if "Hz" in line or "*" in line:
                    for part in line.split():
                        if "*" in part or part.replace(".", "", 1).isdigit():
                            part_clean = part.replace("*", "").replace("+", "")
                            try:
                                val = float(part_clean)
                                if 30 <= val <= 360:
                                    current_rr = val
                                    break
                            except:
                                pass
            SLOW_CACHE["refresh_rate"] = current_rr
        except:
            try:
                rr_res = subprocess.run("xrandr --verbose | grep -E 'connected|\\*' | grep -v disconnected", shell=True, stdout=subprocess.PIPE, text=True, timeout=0.4)
                rr_output = rr_res.stdout
                SLOW_CACHE["refresh_rate"] = 144.0 if "144.00*" in rr_output or "144.00" in rr_output else 60.0
            except:
                SLOW_CACHE["refresh_rate"] = 144.0
                
        # 4. Query custom_cpu_active & custom_gpu_active from asusctl
        SLOW_CACHE["custom_cpu_active"] = False
        SLOW_CACHE["custom_gpu_active"] = False
        has_asusctl = False
        try:
            res = subprocess.run(["asusctl", "fan-curve", "--get-enabled"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=0.4)
            if res.returncode == 0:
                has_asusctl = True
                for line in res.stdout.splitlines():
                    if "CPU: enabled: true" in line:
                        SLOW_CACHE["custom_cpu_active"] = True
                    elif "GPU: enabled: true" in line:
                        SLOW_CACHE["custom_gpu_active"] = True
        except:
            pass
            
        if not has_asusctl:
            path = HWMON_PATHS.get("custom_fan")
            if path:
                SLOW_CACHE["custom_cpu_active"] = read_file(os.path.join(path, "pwm1_enable"), "0") == "2"
                SLOW_CACHE["custom_gpu_active"] = read_file(os.path.join(path, "pwm2_enable"), "0") == "2"
                
    # ------------------ READ FROM SLOW_CACHE ------------------
    gpu_mode = SLOW_CACHE["gpu_mode"]
    power_profile = SLOW_CACHE["power_profile"]
    current_rr = SLOW_CACHE["refresh_rate"]
    custom_cpu_active = SLOW_CACHE["custom_cpu_active"]
    custom_gpu_active = SLOW_CACHE["custom_gpu_active"]
    
    cpu_w = get_cpu_wattage()
    cpu_freq = get_cpu_freq()
    gpu_w = 0.0
    gpu_freq = 0
    gpu_util = 0
    if gpu_mode != "eco":
        gpu_w, gpu_freq, gpu_util = get_gpu_stats()
        
    acad_online = read_file("/sys/class/power_supply/ACAD/online", "0") == "1"
    usbc_online = False
    usbc_wattage = 0.0
    for usbc_node in ["ucsi-source-psy-USBC000:001", "ucsi-source-psy-USBC000:002"]:
        path = f"/sys/class/power_supply/{usbc_node}"
        if os.path.exists(path) and read_file(f"{path}/online", "0") == "1":
            usbc_online = True
            try:
                v_max = float(read_file(f"{path}/voltage_max", "0")) / 1000000.0
                c_max = float(read_file(f"{path}/current_max", "0")) / 1000000.0
                usbc_wattage = round(v_max * c_max, 1)
            except:
                pass
            break
            
    ac_input_wattage = 0.0
    if acad_online or usbc_online:
        overhead = 10.0
        if power_profile == "performance":
            overhead = 15.0
        elif power_profile == "power-saver":
            overhead = 8.0
            
        battery_charge_w = 0.0
        if status == "Charging":
            try:
                curr = float(read_file(f"{BATTERY_PATH}/current_now", "0")) / 1000000.0
                volt = float(read_file(f"{BATTERY_PATH}/voltage_now", "0")) / 1000000.0
                battery_charge_w = curr * volt
            except:
                pass
        ac_input_wattage = round(cpu_w + gpu_w + overhead + battery_charge_w, 1)

    return {
        "cpu_usage": get_cpu_usage_pct(),
        "capacity": capacity,
        "battery_status": status,
        "threshold": threshold,
        "battery_health": health,
        "discharge_wattage": wattage,
        "cpu_wattage": cpu_w,
        "cpu_freq": cpu_freq,
        "gpu_wattage": gpu_w,
        "gpu_freq": gpu_freq,
        "gpu_util": gpu_util,
        "cpu_temp": temp,
        "cpu_fan": cpu_fan,
        "gpu_fan": gpu_fan,
        "power_profile": power_profile,
        "kbd_brightness": kbd_brightness,
        "hostname": hostname,
        "gpu_mode": gpu_mode,
        "refresh_rate": current_rr,
        "panel_od": panel_od,
        "pl1": pl1,
        "pl2": pl2,
        "nv_dynamic_boost": nv_dynamic_boost,
        "nv_temp_target": nv_temp_target,
        "custom_cpu_active": custom_cpu_active,
        "custom_gpu_active": custom_gpu_active,
        "acad_online": acad_online,
        "usbc_online": usbc_online,
        "usbc_wattage": usbc_wattage,
        "ac_input_wattage": ac_input_wattage,
        "ram_used": ram_used,
        "ram_total": ram_total,
        "ram_pct": ram_pct,
        "disk_used": disk_used,
        "disk_total": disk_total,
        "disk_pct": disk_pct
    }

def park_cores(park=True):
    success = True
    errs = []
    try:
        for i in range(4, 32):
            path = f"/sys/devices/system/cpu/cpu{i}/online"
            if os.path.exists(path):
                val = "0" if park else "1"
                try:
                    with open(path, 'w') as f:
                        f.write(val)
                except PermissionError:
                    cmd = f"sh -c 'echo {val} > {path}'"
                    s, e = run_sudo_cmd(cmd)
                    if not s:
                        success = False
                        errs.append(f"cpu{i}: {e}")
                except Exception as ex:
                    success = False
                    errs.append(f"cpu{i}: {ex}")
    except Exception as e:
        success = False
        errs.append(str(e))
    return success, ", ".join(errs) if errs else ""

def query_service_status(service_name):
    try:
        is_user = service_name == "asusd-user.service"
        cmd = ["systemctl"]
        if is_user:
            cmd.append("--user")
        cmd.extend(["is-active", service_name])
        
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.0)
        status = res.stdout.strip()
        
        if status != "active":
            cmd[-2] = "is-failed"
            res2 = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.0)
            if res2.stdout.strip() == "failed":
                return "failed"
            return "inactive"
        return "active"
    except Exception as e:
        print(f"Error querying status of {service_name}: {e}")
        return "inactive"

def get_cpu_model():
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "model name" in line:
                    model = line.split(":", 1)[1].strip()
                    # Clean up common boilerplate text in Intel/AMD CPU names
                    model = model.replace("(R)", "").replace("(TM)", "").replace("CPU", "").strip()
                    # Condense spaces
                    import re
                    model = re.sub(r'\s+', ' ', model)
                    return model
    except:
        pass
    return "Intel/AMD High Performance Processor"

def get_gpu_model():
    import re
    try:
        # 1. Try nvidia-smi if NVIDIA card is active
        import shutil
        if shutil.which("nvidia-smi"):
            res = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=0.5)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
    except:
        pass
        
    try:
        # 2. Try lspci to find GPU names dynamically
        import shutil
        if shutil.which("lspci"):
            res = subprocess.run("lspci", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=0.5)
            if res.returncode == 0 and res.stdout:
                lines = res.stdout.strip().splitlines()
                # Prioritize dedicated GPUs (NVIDIA/AMD)
                for line in lines:
                    if "3d controller" in line.lower() or "vga compatible" in line.lower():
                        if "nvidia" in line.lower() or "geforce" in line.lower() or "radeon" in line.lower():
                            parts = line.split("controller:", 1)
                            if len(parts) > 1: return parts[1].strip()
                            parts = line.split("VGA compatible controller:", 1)
                            if len(parts) > 1: return parts[1].strip()
                            # Clean up hex PCI addresses like [10de:25a2]
                            clean_line = re.sub(r'\[[0-9a-fA-F:]+\]', '', line).strip()
                            # Split by colon after address
                            p_parts = clean_line.split(":")
                            return p_parts[-1].strip() if len(p_parts) > 1 else clean_line
                
                # Fallback to first graphics adapter found
                for line in lines:
                    if "vga" in line.lower() or "3d" in line.lower() or "display" in line.lower():
                        p_parts = line.split(":")
                        return p_parts[-1].strip() if len(p_parts) > 1 else line
    except:
        pass
    return "ASUS Standard Graphics Card"

def get_system_specs():
    cpu = get_cpu_model()
    gpu = get_gpu_model()
    _, ram_tot, _ = get_ram_usage()
    _, disk_tot, _ = get_storage_usage()
    
    # Return formatted system specs text block
    return f"{cpu}\n{gpu}\nMemory: {ram_tot} GB | Storage: {disk_tot} GB"
