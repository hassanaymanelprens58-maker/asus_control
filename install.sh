#!/usr/bin/env bash

# ASUS-Control Installer for Linux
# Builds professional system reputation by automating setup steps!

# Color outputs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==============================================${NC}"
echo -e "${BLUE}     🧠 ASUS-Control: Setup & Installation    ${NC}"
echo -e "${BLUE}==============================================${NC}"

# 1. Detect user & directories
CURRENT_USER=$(logname || echo $USER)
CURRENT_GROUP=$(id -gn "$CURRENT_USER")
INSTALL_DIR=$(pwd)

echo -e "* Current User detected:  ${GREEN}${CURRENT_USER}${NC}"
echo -e "* Current Group detected: ${GREEN}${CURRENT_GROUP}${NC}"
echo -e "* Install Directory:      ${GREEN}${INSTALL_DIR}${NC}"

# 2. Check dependencies
echo -e "\n${YELLOW}[1/4] Checking system dependencies...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR] Python3 is not installed. Please install python3 first.${NC}"
    exit 1
fi

python3 -c "import tkinter" &> /dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}[WARNING] Python tkinter not detected. You may need to install 'python3-tk' for the GUI to render.${NC}"
else
    echo -e "${GREEN}[OK] Python and Tkinter are ready.${NC}"
fi

# 3. Create and install udev rules dynamically
echo -e "\n${YELLOW}[2/4] Setting up system permission rules (udev)...${NC}"
UDEV_RULE_PATH="/etc/udev/rules.d/99-asus.rules"

# Generate udev rules dynamically with local user's username
TEMP_RULES=$(mktemp)
cat <<EOF > "$TEMP_RULES"
# Keyboard backlight permissions for rog-helper
SUBSYSTEM=="leds", KERNEL=="asus::kbd_backlight", RUN+="/bin/chgrp $CURRENT_GROUP /sys/class/leds/asus::kbd_backlight/brightness /sys/class/leds/asus::kbd_backlight/kbd_rgb_mode /sys/class/leds/asus::kbd_backlight/kbd_rgb_state", RUN+="/bin/chmod g+w /sys/class/leds/asus::kbd_backlight/brightness /sys/class/leds/asus::kbd_backlight/kbd_rgb_mode /sys/class/leds/asus::kbd_backlight/kbd_rgb_state"

# CPU sysfs control permissions for rog-helper
SUBSYSTEM=="cpu", RUN+="/bin/sh -c 'chgrp $CURRENT_GROUP /sys/devices/system/cpu/intel_pstate/no_turbo /sys/devices/system/cpu/cpufreq/policy*/scaling_governor /sys/devices/system/cpu/cpufreq/policy*/energy_performance_preference /sys/devices/system/cpu/cpufreq/policy*/scaling_min_freq /sys/devices/system/cpu/cpufreq/policy*/scaling_max_freq /sys/devices/system/cpu/cpu*/online || true'", RUN+="/bin/sh -c 'chmod g+w /sys/devices/system/cpu/intel_pstate/no_turbo /sys/devices/system/cpu/cpufreq/policy*/scaling_governor /sys/devices/system/cpu/cpufreq/policy*/energy_performance_preference /sys/devices/system/cpu/cpufreq/policy*/scaling_min_freq /sys/devices/system/cpu/cpufreq/policy*/scaling_max_freq /sys/devices/system/cpu/cpu*/online || true'"

# Battery charge threshold permissions
SUBSYSTEM=="power_supply", KERNEL=="BAT*", RUN+="/bin/chgrp $CURRENT_GROUP /sys/class/power_supply/%k/charge_control_end_threshold", RUN+="/bin/chmod g+w /sys/class/power_supply/%k/charge_control_end_threshold"

# ASUS WMI tuning permissions (SPL, SPPT, Panel OD, GPU Dynamic Boost, GPU Temp Target, Thermal Policy)
SUBSYSTEM=="platform", DRIVERS=="asus-nb-wmi", RUN+="/bin/sh -c 'chgrp $CURRENT_GROUP /sys/devices/platform/asus-nb-wmi/ppt_pl1_spl /sys/devices/platform/asus-nb-wmi/ppt_pl2_sppt /sys/devices/platform/asus-nb-wmi/panel_od /sys/devices/platform/asus-nb-wmi/nv_dynamic_boost /sys/devices/platform/asus-nb-wmi/nv_temp_target /sys/devices/platform/asus-nb-wmi/throttle_thermal_policy || true'", RUN+="/bin/sh -c 'chmod g+w /sys/devices/platform/asus-nb-wmi/ppt_pl1_spl /sys/devices/platform/asus-nb-wmi/ppt_pl2_sppt /sys/devices/platform/asus-nb-wmi/panel_od /sys/devices/platform/asus-nb-wmi/nv_dynamic_boost /sys/devices/platform/asus-nb-wmi/nv_temp_target /sys/devices/platform/asus-nb-wmi/throttle_thermal_policy || true'"

# Custom Fan Curve permissions
SUBSYSTEM=="hwmon", RUN+="/bin/sh -c 'chgrp -R $CURRENT_GROUP /sys/devices/platform/asus-nb-wmi/hwmon/hwmon*/* || true'", RUN+="/bin/sh -c 'chmod -R g+w /sys/devices/platform/asus-nb-wmi/hwmon/hwmon*/* || true'"
EOF

echo -e "Requires admin permissions to copy the udev rules to ${BLUE}/etc/udev/rules.d/${NC}"
if sudo cp "$TEMP_RULES" "$UDEV_RULE_PATH"; then
    echo -e "${GREEN}[OK] Udev rules installed successfully.${NC}"
    echo -e "* Reloading udev rules..."
    sudo udevadm control --reload-rules && sudo udevadm trigger
    echo -e "${GREEN}[OK] Udev subsystem reloaded.${NC}"
else
    echo -e "${RED}[ERROR] Failed to write udev rules. Please check root access.${NC}"
    rm -f "$TEMP_RULES"
    exit 1
fi
rm -f "$TEMP_RULES"

# 4. Create a desktop launcher shortcut
echo -e "\n${YELLOW}[3/4] Creating system desktop application shortcut...${NC}"
LAUNCHER_PATH="/home/${CURRENT_USER}/.local/share/applications/asus-control.desktop"

cat <<EOF > "$LAUNCHER_PATH"
[Desktop Entry]
Version=1.0
Type=Application
Name=ASUS-Control
Comment=ASUS Performance Dashboard Control Center
Exec=python3 ${INSTALL_DIR}/asus_control.py
Icon=${INSTALL_DIR}/asus_control_icon.png
Terminal=false
Categories=System;Settings;
Path=${INSTALL_DIR}
StartupNotify=true
X-GNOME-SingleWindow=true
EOF

chmod +x "$LAUNCHER_PATH"
echo -e "${GREEN}[OK] Desktop shortcut created at: ${LAUNCHER_PATH}${NC}"

# 5. Done
echo -e "\n${YELLOW}[4/4] Finalizing...${NC}"
echo -e "${GREEN}==============================================${NC}"
echo -e "${GREEN} 🎉 ASUS-Control Installation Complete!      ${NC}"
echo -e "${GREEN}==============================================${NC}"
echo -e "You can now launch the dashboard by searching for ${BLUE}ASUS-Control${NC} in your app menu,"
echo -e "or by running the python script directly!"
echo -e "Enjoy maximum performance! 🚀"
