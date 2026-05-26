import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILES_FILE = os.path.join(BASE_DIR, "asus_custom_profiles.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "asus_settings.json")

def load_custom_profiles():
    if os.path.exists(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading custom profiles: {e}")
            
    # Load defaults
    defaults = {
        "Silent Eco Save": {
            "pl1": 15,
            "pl2": 25,
            "gpu_mode": "eco",
            "power_profile": "power-saver",
            "battery_limit": 60,
            "refresh_rate": 60.0,
            "panel_od": 0,
            "kbd_brightness": 1,
            "kbd_effect": "Breathing",
            "kbd_rgb": {"r": 0, "g": 243, "b": 255},
            "core_overclock": 0,
            "mem_overclock": 0,
            "cpu_curve": [[30, 20], [45, 30], [55, 45], [65, 60], [75, 80], [80, 100], [85, 120], [90, 150]],
            "gpu_curve": [[30, 20], [45, 30], [55, 45], [65, 60], [75, 80], [80, 100], [85, 120], [90, 150]]
        },
        "Turbo Gaming Ultimate": {
            "pl1": 80,
            "pl2": 115,
            "gpu_mode": "ultimate",
            "power_profile": "performance",
            "battery_limit": 100,
            "refresh_rate": 144.0,
            "panel_od": 1,
            "kbd_brightness": 3,
            "kbd_effect": "Static",
            "kbd_rgb": {"r": 255, "g": 0, "b": 60},
            "core_overclock": 120,
            "mem_overclock": 600,
            "cpu_curve": [[30, 45], [55, 75], [61, 95], [66, 120], [70, 150], [77, 185], [80, 220], [82, 255]],
            "gpu_curve": [[30, 45], [55, 75], [61, 95], [66, 120], [70, 150], [77, 185], [80, 220], [82, 255]]
        }
    }
    save_custom_profiles(defaults)
    return defaults

def save_custom_profiles(profiles):
    try:
        with open(PROFILES_FILE, 'w') as f:
            json.dump(profiles, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving custom profiles: {e}")
        return False

def load_active_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading active settings: {e}")
            
    # Default values matching active hardware capabilities/defaults
    return {
        "battery_limit": 100,
        "power_profile": "balanced",
        "gpu_mode": "standard",
        "refresh_rate": 60.0,
        "panel_od": 0,
        "kbd_brightness": 1,
        "kbd_effect": "Static",
        "kbd_rgb": {"r": 0, "g": 243, "b": 255},
        "custom_cpu_active": False,
        "custom_gpu_active": False,
        "pl1": 45,
        "pl2": 80,
        "max_cpu_tdp": 85,
        "max_combined_tdp": 115,
        "core_overclock": 0,
        "mem_overclock": 0,
        "nv_dynamic_boost": 25,
        "nv_temp_target": 87,
        "cpu_curve": [[30, 35], [55, 66], [61, 81], [66, 107], [70, 135], [77, 163], [80, 193], [82, 221]],
        "gpu_curve": [[30, 35], [55, 66], [61, 81], [66, 107], [70, 135], [77, 163], [80, 193], [82, 221]]
    }
