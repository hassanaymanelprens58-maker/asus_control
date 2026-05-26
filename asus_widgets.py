import tkinter as tk
import math

def update_cockpit_speedometer(canvas, val, max_val, colors):
    canvas.delete("all")
    cx, cy, r = 52, 52, 44
    num_ticks = 20
    start_angle = -225
    end_angle = 45
    angle_range = end_angle - start_angle
    
    pct = min(max(val / max_val, 0.0), 1.0)
    active_ticks = math.ceil(pct * num_ticks)
    
    name = getattr(canvas, "gauge_name", "")
    unit = getattr(canvas, "gauge_unit", "")
    
    primary_color = colors["primary"]
    secondary_color = colors["secondary"]
    
    # 1. Draw outer dark gauge ring
    canvas.create_oval(cx-r-1, cy-r-1, cx+r+1, cy+r+1, outline="#161822", width=2)
    
    # 2. Draw glowing speedometer ticks
    for i in range(num_ticks):
        angle_deg = start_angle + (i / (num_ticks - 1)) * angle_range
        angle_rad = math.radians(angle_deg)
        
        is_major = (i % 4 == 0)
        tick_len = 8 if is_major else 4
        
        x_outer = cx + r * math.cos(angle_rad)
        y_outer = cy + r * math.sin(angle_rad)
        
        r_inner = r - tick_len
        x_inner = cx + r_inner * math.cos(angle_rad)
        y_inner = cy + r_inner * math.sin(angle_rad)
        
        if i < active_ticks:
            color = primary_color if name in ["CPU CORE", "CPU POWER", "GPU POWER"] else secondary_color
            if name == "CPU CORE" and val < 60:
                color = secondary_color
            width = 2.5 if is_major else 1.5
        else:
            color = "#1d202e"
            width = 1.5 if is_major else 1.0
            
        canvas.create_line(x_inner, y_inner, x_outer, y_outer, fill=color, width=width)
        
    # 3. Draw a gorgeous glowing sweep needle pointing to current angle
    needle_angle = start_angle + pct * angle_range
    needle_rad = math.radians(needle_angle)
    
    # Needle shadow
    nx_s = cx + (r - 4) * math.cos(needle_rad) + 1
    ny_s = cy + (r - 4) * math.sin(needle_rad) + 1
    canvas.create_line(cx, cy, nx_s, ny_s, fill="#020204", width=3)
    
    # Actual needle
    nx = cx + (r - 4) * math.cos(needle_rad)
    ny = cy + (r - 4) * math.sin(needle_rad)
    needle_color = primary_color if name in ["CPU CORE", "CPU POWER", "GPU POWER"] else secondary_color
    if name == "CPU CORE" and val < 60:
        needle_color = secondary_color
        
    canvas.create_line(cx, cy, nx, ny, fill=needle_color, width=2)
    
    # 4. Center pivot cap
    canvas.create_oval(cx-5, cy-5, cx+5, cy+5, fill="#191c28", outline="#2f3448", width=1.5)
    canvas.create_oval(cx-2, cy-2, cx+2, cy+2, fill=needle_color, outline="")
    
    # 5. Text values shifted below pivot
    val_str = f"{int(val)}" if unit != "°C" else f"{val}"
    if name in ["CPU FAN", "GPU FAN"]:
        val_str = f"{int(val)}"
        
    canvas.create_text(cx, cy+18, text=val_str, font=("Impact", 12), fill="#ffffff")
    canvas.create_text(cx, cy+29, text=unit, font=("Courier 10 Pitch", 6, "bold"), fill="#6a7282")

def update_battery_cell(canvas, capacity, is_charging, colors):
    canvas.delete("all")
    w_max = 300
    num_segments = 10
    gap = 4
    seg_w = (w_max - (num_segments - 1) * gap) / num_segments
    active_segments = math.ceil((capacity / 100.0) * num_segments)
    
    for i in range(num_segments):
        x0 = i * (seg_w + gap)
        x1 = x0 + seg_w
        if i < active_segments:
            color = colors["primary"] if is_charging else colors["secondary"]
        else:
            color = "#181a24"
        canvas.create_rectangle(x0, 0, x1, 18, fill=color, outline="", width=0)

def update_aura_brightness_bars(canvas, level, colors):
    canvas.delete("all")
    w_max = 300
    num_segments = 4
    gap = 6
    seg_w = (w_max - (num_segments - 1) * gap) / num_segments
    
    for i in range(num_segments):
        x0 = i * (seg_w + gap)
        x1 = x0 + seg_w
        if i <= level and level > 0:
            color = colors["primary"]
        else:
            color = "#181a24"
        canvas.create_rectangle(x0, 0, x1, 10, fill=color, outline="", width=0)

def draw_fan_curve_graph(canvas, points, colors, cw=280, ch=180):
    canvas.delete("all")
    
    # Grid axes
    canvas.create_line(35, 15, 35, ch - 25, fill="#222530", width=1)
    canvas.create_line(35, ch - 25, cw - 15, ch - 25, fill="#222530", width=1)
    
    # Temperature grid guides
    for temp in [20, 40, 60, 80, 100]:
        x = 35 + (temp / 100.0) * (cw - 50)
        canvas.create_line(x, 15, x, ch - 25, fill="#151722", dash=(2, 2))
        canvas.create_text(x, ch - 12, text=f"{temp}°", font=("Courier 10 Pitch", 7), fill="#6a7282")
        
    # Fan speed percentage guides
    for pwm_val in [0, 64, 128, 192, 255]:
        y = ch - 25 - (pwm_val / 255.0) * (ch - 40)
        canvas.create_line(35, y, cw - 15, y, fill="#151722", dash=(2, 2))
        pct = int((pwm_val / 255.0) * 100)
        canvas.create_text(18, y, text=f"{pct}%", font=("Courier 10 Pitch", 7), fill="#6a7282")
        
    # Plot custom dots
    coords = []
    for temp, pwm in points:
        x = 35 + (temp / 100.0) * (cw - 50)
        y = ch - 25 - (pwm / 255.0) * (ch - 40)
        coords.append((x, y))
        canvas.create_oval(x-3, y-3, x+3, y+3, fill=colors["secondary"], outline=colors["primary"], width=1)
        
    for idx in range(len(coords) - 1):
        canvas.create_line(coords[idx][0], coords[idx][1], coords[idx+1][0], coords[idx+1][1], fill=colors["primary"], width=2)

def draw_power_history_graph(canvas, history, colors, max_scale=200.0, cw=300, ch=125):
    canvas.delete("all")
    
    # Grid axes
    canvas.create_line(35, 10, 35, ch - 20, fill="#222530", width=1)
    canvas.create_line(35, ch - 20, cw - 10, ch - 20, fill="#222530", width=1)
    
    # Horizontal grid guides (0W, 50W, 100W, 150W, 200W)
    steps = [0, int(max_scale * 0.25), int(max_scale * 0.5), int(max_scale * 0.75), int(max_scale)]
    for p_val in steps:
        y = ch - 20 - (p_val / float(max_scale)) * (ch - 30)
        canvas.create_line(35, y, cw - 10, y, fill="#151722", dash=(2, 2))
        canvas.create_text(18, y, text=f"{p_val}W", font=("Courier 10 Pitch", 7), fill="#6a7282")
        
    # Time guides (-10s, -20s, -30s)
    for t_step in [10, 20, 30]:
        x = cw - 10 - (t_step / 30.0) * (cw - 45)
        canvas.create_line(x, 10, x, ch - 20, fill="#151722", dash=(2, 2))
        canvas.create_text(x, ch - 10, text=f"-{t_step}s", font=("Courier 10 Pitch", 7), fill="#6a7282")
        
    # Draw line
    coords = []
    num_points = len(history)
    for i, val in enumerate(history):
        x = 35 + (i / (num_points - 1)) * (cw - 45)
        y = ch - 20 - (min(val, max_scale) / float(max_scale)) * (ch - 30)
        coords.append((x, y))
        
    for idx in range(len(coords) - 1):
        canvas.create_line(coords[idx][0], coords[idx][1] + 1, coords[idx+1][0], coords[idx+1][1] + 1, fill="#020204", width=3)
        canvas.create_line(coords[idx][0], coords[idx][1], coords[idx+1][0], coords[idx+1][1], fill=colors["secondary"], width=2)

def draw_vector_laptop(canvas, colors):
    canvas.delete("all")
    cw, ch = 300, 200
    cx, cy = 150, 100
    
    primary = colors["primary"]
    secondary = colors["secondary"]
    
    # Screen bezel
    canvas.create_rectangle(cx-80, cy-55, cx+80, cy+30, outline="#1a1a24", fill="#0d0d12", width=2)
    # Inner display screen
    canvas.create_rectangle(cx-75, cy-50, cx+75, cy+25, outline="#0d0d12", fill="#08080a", width=1)
    
    # Glowing TUF Wallpaper pattern inside display screen!
    canvas.create_polygon(cx-20, cy-15, cx-15, cy-25, cx-5, cy-25, cx-10, cy-15, fill=secondary, outline="")
    canvas.create_polygon(cx+20, cy-15, cx+15, cy-25, cx+5, cy-25, cx+10, cy-15, fill=secondary, outline="")
    canvas.create_text(cx, cy, text="◢◤ ASUS", font=("Impact", 12, "italic"), fill=primary)
    
    # Hinge connectors
    canvas.create_rectangle(cx-60, cy+30, cx-40, cy+33, fill="#1c1d24", outline="")
    canvas.create_rectangle(cx+40, cy+30, cx+60, cy+33, fill="#1c1d24", outline="")
    
    # Laptop Base (perspective trapezoid)
    canvas.create_polygon(cx-90, cy+33, cx+90, cy+33, cx+110, cy+55, cx-110, cy+55, fill="#101115", outline="#1a1a24", width=1.5)
    
    # Keyboard area glow
    canvas.create_polygon(cx-80, cy+37, cx+80, cy+37, cx+95, cy+50, cx-95, cy+50, fill="#1a1a24", outline=primary, width=1)
    
    # Touchpad
    canvas.create_rectangle(cx-20, cy+50, cx+20, cy+54, fill="#0d0d12", outline="#1a1a24", width=1)

def draw_connected_devices(canvas, colors):
    canvas.delete("all")
    cw, ch = 300, 80
    primary = colors["primary"]
    
    devs = [("ROG Harpe", 40), ("ROG Azoth", 150), ("ROG Delta", 260)]
    for name, x in devs:
        canvas.create_rectangle(x-35, 10, x+35, 70, fill="#101115", outline="#1a1a24", width=1)
        if "Harpe" in name:
            canvas.create_oval(x-8, 20, x+8, 45, outline=primary, width=1)
            canvas.create_line(x, 20, x, 32, fill=primary, width=1)
        elif "Azoth" in name:
            canvas.create_rectangle(x-18, 24, x+18, 40, outline=primary, width=1)
            canvas.create_line(x-12, 32, x+12, 32, fill=primary, dash=(2,2))
        else:
            canvas.create_arc(x-12, 18, x+12, 42, start=0, extent=180, outline=primary, width=2, style="arc")
            canvas.create_oval(x-15, 30, x-9, 42, fill=primary, outline="")
            canvas.create_oval(x+9, 30, x+15, 42, fill=primary, outline="")
            
        canvas.create_text(x, 58, text=name, font=("Helvetica Neue", 7, "bold"), fill="#808695")
