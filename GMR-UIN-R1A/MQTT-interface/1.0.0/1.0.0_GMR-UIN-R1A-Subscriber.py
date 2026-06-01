# ============================================================
# GMR UIN R1A - MQTT Subscriber
# UI Redesign: Dashboard Style (Landscape, Yellow/Amber Theme)
# Revision: Layout matched to Publisher UI
# Update patch: 2026-05-08
# ============================================================

import json
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime
import pandas as pd
import paho.mqtt.client as mqtt
import sys

# ============================================================
# PLATFORM DETECTION
# ============================================================
IS_LINUX = sys.platform.startswith("linux")

if sys.platform.startswith("win"):
    DEFAULT_PORT = "COM3"
elif IS_LINUX:
    DEFAULT_PORT = "/dev/ttyUSB0"
else:
    DEFAULT_PORT = "/dev/tty.usbserial-0001"

MQTT_BROKER       = "localhost"
MQTT_PORT         = 1883
MQTT_TOPIC_DATA   = "gmr/data"
MQTT_TOPIC_STATUS = "gmr/status"
MQTT_CLIENT_ID    = "GMR-Subscriber"

# ============================================================
# GLOBAL STATE
# ============================================================
data_waktu       = []
data_b           = []
data_v           = []
mqtt_client      = None
mqtt_connected   = False
publisher_status = "unknown"
data_lock        = threading.Lock()

# ============================================================
# COLOR SCHEME (Yellow / Amber Theme)
# ============================================================
BG           = "#fdfaf0"
PANEL        = "#ffffff"
HEADER_BG    = "#4a3800"
ACCENT       = "#b45309"
ACCENT2      = "#d97706"
YELLOW       = "#ca8a04"
YELLOW_LIGHT = "#fbbf24"
RED          = "#dc2626"
GREEN        = "#16a34a"
TEXT         = "#2d1f00"
SUBTEXT      = "#7a6030"
DIVIDER      = "#e5d58a"
AMBER_DARK   = "#78350f"

# ============================================================
# MQTT CALLBACKS
# ============================================================
def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        client.subscribe(MQTT_TOPIC_DATA,   qos=1)
        client.subscribe(MQTT_TOPIC_STATUS, qos=0)
        update_mqtt_status("Connected", YELLOW_LIGHT)
        lbl_header_status.config(text="● Online", fg=YELLOW_LIGHT)
        log(f"Subscribe: {MQTT_TOPIC_DATA}")
    else:
        mqtt_connected = False
        update_mqtt_status(f"Failed rc={rc}", RED)
        lbl_header_status.config(text="● Offline", fg=RED)

def on_disconnect(client, userdata, rc):
    global mqtt_connected
    mqtt_connected = False
    update_mqtt_status("Disconnected", RED)
    try:
        lbl_header_status.config(text="● Offline", fg=RED)
    except:
        pass

def on_message(client, userdata, msg):
    global publisher_status
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        if msg.topic == MQTT_TOPIC_STATUS:
            publisher_status = payload.get("status", "unknown")
            root.after(0, lambda: update_publisher_status(publisher_status))
            log(f"Publisher: {publisher_status}")
        elif msg.topic == MQTT_TOPIC_DATA:
            t = payload.get("t_s",  0.0)
            v = payload.get("v_V",  0.0)
            b = payload.get("b_mT", 0.0)
            with data_lock:
                data_waktu.append(t)
                data_b.append(b)
                data_v.append(v)
            log(f"t={t:.2f}s  V={v:.4f}  B={b:.4f}mT")
    except Exception as e:
        log(f"Error: {e}")

def connect_mqtt():
    global mqtt_client
    broker = broker_var.get().strip()
    try:
        port = int(mqttport_var.get().strip())
    except ValueError:
        log("Invalid MQTT port.")
        return
    try:
        if mqtt_client:
            try:
                mqtt_client.loop_stop()
                mqtt_client.disconnect()
            except:
                pass
        mqtt_client = mqtt.Client(
            client_id=MQTT_CLIENT_ID,
            protocol=mqtt.MQTTv311
        )
        mqtt_client.on_connect    = on_connect
        mqtt_client.on_disconnect = on_disconnect
        mqtt_client.on_message    = on_message
        mqtt_client.connect_async(broker, port, keepalive=60)
        mqtt_client.loop_start()
        log(f"Connecting MQTT to {broker}:{port}...")
    except Exception as e:
        update_mqtt_status("Error", RED)
        log(f"MQTT Error: {e}")

def disconnect_mqtt():
    global mqtt_client, mqtt_connected
    if mqtt_client:
        try:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        except:
            pass
    mqtt_connected = False
    update_mqtt_status("Disconnected", RED)
    try:
        lbl_header_status.config(text="● Offline", fg=RED)
    except:
        pass
    log("Connection closed.")

# ============================================================
# GUI HELPERS
# ============================================================
def update_mqtt_status(text, color):
    try:
        lbl_mqtt_conn_val.config(text=f"● {text}", fg=color)
    except:
        pass

def update_publisher_status(s):
    m = {
        "publisher_online":  ("Online",     GREEN),
        "collecting":        ("Collecting", YELLOW_LIGHT),
        "stopped":           ("Stopped",    ACCENT2),
        "publisher_offline": ("Offline",    RED),
    }
    txt, col = m.get(s, (s, SUBTEXT))
    try:
        lbl_pub_status_val.config(text=txt, fg=col)
    except:
        pass

def log(msg):
    try:
        ts = datetime.now().strftime("%H:%M:%S")
        txt_log.config(state=tk.NORMAL)
        txt_log.insert(tk.END, f"[{ts}]  {msg}\n")
        txt_log.see(tk.END)
        txt_log.config(state=tk.DISABLED)
    except:
        pass

# ============================================================
# CONTROLS
# ============================================================
def reset_data():
    global data_waktu, data_b, data_v
    with data_lock:
        data_waktu.clear()
        data_b.clear()
        data_v.clear()
    line.set_data([], [])
    ax.relim()
    ax.autoscale_view()
    canvas.draw()
    log("Data reset.")
    lbl_count.config(text="0 sample")
    lbl_last_b.config(text="B = -- mT")
    lbl_last_v.config(text="-- V")
    lbl_bmax.config(text="Max: --")
    lbl_bmin.config(text="Min: --")
    lbl_bavg.config(text="Avg: --")

def simpan_excel():
    with data_lock:
        if not data_waktu:
            messagebox.showwarning("Warning", "No data available.")
            return
        df = pd.DataFrame({
            "t (s)":  list(data_waktu),
            "V (V)":  list(data_v),
            "B (mT)": list(data_b)
        })
    fp = filedialog.asksaveasfilename(
        defaultextension=".xlsx",
        filetypes=[("Excel", "*.xlsx")]
    )
    if fp:
        try:
            df.to_excel(fp, index=False)
            log(f"Saved: {fp}")
        except Exception as e:
            messagebox.showerror("Failed", str(e))

def simpan_gambar():
    fp = filedialog.asksaveasfilename(
        defaultextension=".png",
        filetypes=[("PNG", "*.png")]
    )
    if fp:
        fig.savefig(fp, dpi=150)
        log(f"Image saved: {fp}")

def keluar():
    if messagebox.askokcancel("Exit", "Are you sure you want to exit?"):
        try:
            if mqtt_client:
                mqtt_client.loop_stop()
                mqtt_client.disconnect()
        except:
            pass
        root.destroy()

# ============================================================
# ANIMATION / PLOT UPDATE
# ============================================================
def update_plot(frame):
    with data_lock:
        if not data_waktu:
            return line,
        x = list(data_waktu)
        y = list(data_b)
        v = data_v[-1] if data_v else 0.0
        n = len(x)
    line.set_data(x, y)
    ax.relim()
    ax.autoscale_view()
    canvas.draw()
    lbl_count.config(text=f"{n} sample")
    lbl_last_b.config(text=f"B = {y[-1]:.4f} mT")
    lbl_last_v.config(text=f"{v:.4f} V")
    if n > 1:
        lbl_bmax.config(text=f"Max: {max(y):.4f} mT")
        lbl_bmin.config(text=f"Min: {min(y):.4f} mT")
        lbl_bavg.config(text=f"Avg: {sum(y)/n:.4f} mT")
    return line,

# ============================================================
# ROOT WINDOW
# ============================================================
root = tk.Tk()
root.title("GMR UIN R1A - MQTT Subscriber")
root.configure(bg=BG)
root.resizable(True, True)

root.update_idletasks()
sw = root.winfo_screenwidth()
sh = root.winfo_screenheight()
root.geometry(f"{sw}x{sh}+0+0")

try:
    root.state("zoomed")
except tk.TclError:
    try:
        root.attributes("-zoomed", True)
    except:
        pass

# ============================================================
# HEADER BAR
# ============================================================
frm_hdr = tk.Frame(root, bg=HEADER_BG, pady=7)
frm_hdr.pack(fill=tk.X, side=tk.TOP)

frm_hdr_left = tk.Frame(frm_hdr, bg=HEADER_BG)
frm_hdr_left.pack(side=tk.LEFT, padx=14)

tk.Label(
    frm_hdr_left, text="⊙",
    font=("Courier New", 20, "bold"),
    bg=HEADER_BG, fg=YELLOW_LIGHT
).pack(side=tk.LEFT, padx=(0, 8))

frm_hdr_title = tk.Frame(frm_hdr_left, bg=HEADER_BG)
frm_hdr_title.pack(side=tk.LEFT)
tk.Label(
    frm_hdr_title,
    text="GMR Real-Time Monitoring",
    font=("Courier New", 13, "bold"),
    bg=HEADER_BG, fg="#ffffff"
).pack(anchor=tk.W)
tk.Label(
    frm_hdr_title,
    text="(MQTT Subscriber — GMR UIN R1A)",
    font=("Courier New", 8, "italic"),
    bg=HEADER_BG, fg="#c4a84a"
).pack(anchor=tk.W)

frm_hdr_right = tk.Frame(frm_hdr, bg=HEADER_BG)
frm_hdr_right.pack(side=tk.RIGHT, padx=18)
tk.Label(
    frm_hdr_right,
    text="System Status",
    font=("Courier New", 8, "bold"),
    bg=HEADER_BG, fg="#c4a84a"
).pack(anchor=tk.E)
lbl_header_status = tk.Label(
    frm_hdr_right,
    text="● Offline",
    font=("Courier New", 10, "bold"),
    bg=HEADER_BG, fg=RED
)
lbl_header_status.pack(anchor=tk.E)

# ============================================================
# MAIN BODY
# ============================================================
frm_body = tk.Frame(root, bg=BG)
frm_body.pack(fill=tk.BOTH, expand=True, padx=8, pady=6, side=tk.TOP)

# ============================================================
# RIGHT COLUMN — scrollable
# ============================================================
frm_right_outer = tk.Frame(frm_body, bg=BG, width=288)
frm_right_outer.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
frm_right_outer.pack_propagate(False)

cv_right = tk.Canvas(frm_right_outer, bg=BG, highlightthickness=0)
sb_right = tk.Scrollbar(
    frm_right_outer, orient=tk.VERTICAL, command=cv_right.yview
)
cv_right.configure(yscrollcommand=sb_right.set)
sb_right.pack(side=tk.RIGHT, fill=tk.Y)
cv_right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

frm_right = tk.Frame(cv_right, bg=BG)
win_right = cv_right.create_window((0, 0), window=frm_right, anchor="nw")

def _on_frame_configure(e):
    cv_right.configure(scrollregion=cv_right.bbox("all"))

def _on_canvas_configure(e):
    cv_right.itemconfig(win_right, width=e.width)

frm_right.bind("<Configure>", _on_frame_configure)
cv_right.bind("<Configure>",  _on_canvas_configure)

def _on_mousewheel(e):
    if e.num == 4:
        cv_right.yview_scroll(-1, "units")
    elif e.num == 5:
        cv_right.yview_scroll(1, "units")
    else:
        cv_right.yview_scroll(int(-1 * (e.delta / 120)), "units")

cv_right.bind("<MouseWheel>", _on_mousewheel)
cv_right.bind("<Button-4>",   _on_mousewheel)
cv_right.bind("<Button-5>",   _on_mousewheel)

# ============================================================
# LEFT COLUMN — grafik + live data + log
# ============================================================
frm_left = tk.Frame(frm_body, bg=BG)
frm_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

# --- GRAPH CARD ---
frm_graph_card = tk.Frame(
    frm_left, bg=PANEL,
    highlightbackground=DIVIDER, highlightthickness=1
)
frm_graph_card.pack(fill=tk.BOTH, expand=True)

fig, ax = plt.subplots(figsize=(8, 3.0), facecolor=PANEL)
ax.set_facecolor("#fffbeb")
ax.set_title(
    "Magnetic Field vs. Time",
    color=AMBER_DARK, fontsize=10, fontweight="bold", pad=6
)
ax.set_xlabel("Time, t (s)", color=SUBTEXT, fontsize=8)
ax.set_ylabel("Magnetic Field, B (mT)", color=SUBTEXT, fontsize=8)
ax.tick_params(colors=SUBTEXT, labelsize=7)
for sp in ax.spines.values():
    sp.set_color(DIVIDER)
ax.grid(True, color="#e5d58a", linewidth=0.7, linestyle="--")
line, = ax.plot([], [], lw=1.8, color=AMBER_DARK, label="Magnetic Field (mT)")
ax.legend(loc="upper right", fontsize=7, framealpha=0.7)

canvas = FigureCanvasTkAgg(fig, master=frm_graph_card)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

# --- LIVE DATA CARD ---
frm_live_card = tk.Frame(
    frm_left, bg=PANEL,
    highlightbackground=DIVIDER, highlightthickness=1
)
frm_live_card.pack(fill=tk.X, pady=(5, 0))

frm_live_hdr = tk.Frame(frm_live_card, bg=PANEL)
frm_live_hdr.pack(fill=tk.X, padx=10, pady=(6, 2))
tk.Label(
    frm_live_hdr,
    text="↗  LIVE DATA",
    font=("Courier New", 9, "bold"),
    bg=PANEL, fg=AMBER_DARK
).pack(side=tk.LEFT)
tk.Frame(frm_live_card, bg=DIVIDER, height=1).pack(fill=tk.X, padx=10)

frm_live_cols = tk.Frame(frm_live_card, bg=PANEL)
frm_live_cols.pack(fill=tk.X, padx=10, pady=8)

# Column 1: Magnetic Field B
frm_col_b = tk.Frame(frm_live_cols, bg=PANEL)
frm_col_b.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

tk.Label(
    frm_col_b,
    text="MAGNETIC FIELD",
    font=("Courier New", 8, "bold"),
    bg=PANEL, fg=AMBER_DARK
).pack(anchor=tk.W)

lbl_last_b = tk.Label(
    frm_col_b,
    text="B = -- mT",
    font=("Courier New", 20, "bold"),
    bg=PANEL, fg=AMBER_DARK
)
lbl_last_b.pack(anchor=tk.W, pady=(2, 0))

lbl_count = tk.Label(
    frm_col_b,
    text="0 sample",
    font=("Courier New", 9),
    bg=PANEL, fg=SUBTEXT
)
lbl_count.pack(anchor=tk.W)

# Vertical divider
tk.Frame(frm_live_cols, bg=DIVIDER, width=1).pack(
    side=tk.LEFT, fill=tk.Y, padx=20
)

# Column 2: Sensor Voltage V
frm_col_v = tk.Frame(frm_live_cols, bg=PANEL)
frm_col_v.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

tk.Label(
    frm_col_v,
    text="SENSOR VOLTAGE",
    font=("Courier New", 8, "bold"),
    bg=PANEL, fg=AMBER_DARK
).pack(anchor=tk.W)

lbl_last_v = tk.Label(
    frm_col_v,
    text="V = -- V",
    font=("Courier New", 20, "bold"),
    bg=PANEL, fg=AMBER_DARK
)
lbl_last_v.pack(anchor=tk.W, pady=(2, 0))

# --- LOG OUTPUT CARD ---
frm_log_card = tk.Frame(
    frm_left, bg=PANEL,
    highlightbackground=DIVIDER, highlightthickness=1
)
frm_log_card.pack(fill=tk.X, pady=(5, 0))

frm_log_hdr = tk.Frame(frm_log_card, bg=PANEL)
frm_log_hdr.pack(fill=tk.X, padx=10, pady=(6, 2))
tk.Label(
    frm_log_hdr,
    text="≡  LOG OUTPUT (Latest)",
    font=("Courier New", 9, "bold"),
    bg=PANEL, fg=AMBER_DARK
).pack(side=tk.LEFT)
tk.Frame(frm_log_card, bg=DIVIDER, height=1).pack(fill=tk.X, padx=10)

txt_log = tk.Text(
    frm_log_card,
    height=4,
    bg="#fffbeb", fg=AMBER_DARK,
    font=("Courier New", 8),
    state=tk.DISABLED,
    relief=tk.FLAT, bd=0,
    wrap=tk.WORD
)
txt_log.pack(fill=tk.X, padx=10, pady=(4, 8))

# ============================================================
# RIGHT PANEL HELPER FUNCTIONS
# ============================================================
def make_card(parent, title):
    card = tk.Frame(
        parent, bg=PANEL,
        highlightbackground=DIVIDER, highlightthickness=1
    )
    card.pack(fill=tk.X, pady=(0, 6))
    hdr = tk.Frame(card, bg=PANEL)
    hdr.pack(fill=tk.X, padx=10, pady=(8, 2))
    tk.Label(
        hdr, text=title,
        font=("Courier New", 9, "bold"),
        bg=PANEL, fg=AMBER_DARK
    ).pack(anchor=tk.W)
    tk.Frame(card, bg=DIVIDER, height=1).pack(
        fill=tk.X, padx=10, pady=(2, 6)
    )
    body = tk.Frame(card, bg=PANEL)
    body.pack(fill=tk.X, padx=10, pady=(0, 8))
    return body

def make_row(parent, label, width_label=11):
    f = tk.Frame(parent, bg=PANEL)
    f.pack(fill=tk.X, pady=2)
    tk.Label(
        f, text=label,
        font=("Courier New", 8),
        bg=PANEL, fg=SUBTEXT,
        width=width_label, anchor=tk.W
    ).pack(side=tk.LEFT)
    return f

# --- CONNECTION STATUS CARD ---
conn_body = make_card(frm_right, "(ᵠ)  CONNECTION STATUS")

# MQTT section header
tk.Label(
    conn_body,
    text="(ᵠ)  MQTT BROKER",
    font=("Courier New", 8, "bold"),
    bg=PANEL, fg=AMBER_DARK
).pack(anchor=tk.W, pady=(0, 4))

# Broker IP
r_broker = make_row(conn_body, "Broker IP")
broker_var = tk.StringVar(value=MQTT_BROKER)
tk.Entry(
    r_broker, textvariable=broker_var,
    font=("Courier New", 8),
    bg="#fffbeb", fg=AMBER_DARK,
    relief=tk.FLAT, bd=2, width=13,
    insertbackground=AMBER_DARK
).pack(side=tk.LEFT)

# MQTT Port
r_mport = make_row(conn_body, "Port")
mqttport_var = tk.StringVar(value=str(MQTT_PORT))
tk.Entry(
    r_mport, textvariable=mqttport_var,
    font=("Courier New", 8),
    bg="#fffbeb", fg=AMBER_DARK,
    relief=tk.FLAT, bd=2, width=7,
    insertbackground=AMBER_DARK
).pack(side=tk.LEFT)

# Topic (static)
r_topic = make_row(conn_body, "Topic")
tk.Label(
    r_topic,
    text=MQTT_TOPIC_DATA,
    font=("Courier New", 8),
    bg=PANEL, fg=TEXT
).pack(side=tk.LEFT)

# MQTT connection status
r_mconn = make_row(conn_body, "Connection")
lbl_mqtt_conn_val = tk.Label(
    r_mconn,
    text="● Disconnected",
    font=("Courier New", 8, "bold"),
    bg=PANEL, fg=RED
)
lbl_mqtt_conn_val.pack(side=tk.LEFT)

tk.Button(
    conn_body, text="Subscribe MQTT",
    command=connect_mqtt,
    bg=YELLOW_LIGHT, fg="#1a1a00",
    font=("Courier New", 8, "bold"),
    relief=tk.FLAT, cursor="hand2", pady=4
).pack(fill=tk.X, pady=(4, 2))

tk.Button(
    conn_body, text="Disconnect MQTT",
    command=disconnect_mqtt,
    bg=DIVIDER, fg=TEXT,
    font=("Courier New", 8, "bold"),
    relief=tk.FLAT, cursor="hand2", pady=4
).pack(fill=tk.X, pady=(0, 0))

# --- PUBLISHER STATUS CARD ---
pub_body = make_card(frm_right, "⊟  PUBLISHER STATUS")

r_pub = make_row(pub_body, "Status")
lbl_pub_status_val = tk.Label(
    r_pub,
    text="Unknown",
    font=("Courier New", 9, "bold"),
    bg=PANEL, fg=SUBTEXT
)
lbl_pub_status_val.pack(side=tk.LEFT)

# --- STATISTICS CARD ---
stat_body = make_card(frm_right, "≡  STATISTICS B (mT)")

r_bmax = make_row(stat_body, "Max")
lbl_bmax = tk.Label(
    r_bmax,
    text="Max: --",
    font=("Courier New", 8, "bold"),
    bg=PANEL, fg=GREEN
)
lbl_bmax.pack(side=tk.LEFT)

r_bmin = make_row(stat_body, "Min")
lbl_bmin = tk.Label(
    r_bmin,
    text="Min: --",
    font=("Courier New", 8, "bold"),
    bg=PANEL, fg=RED
)
lbl_bmin.pack(side=tk.LEFT)

r_bavg = make_row(stat_body, "Avg")
lbl_bavg = tk.Label(
    r_bavg,
    text="Avg: --",
    font=("Courier New", 8, "bold"),
    bg=PANEL, fg=AMBER_DARK
)
lbl_bavg.pack(side=tk.LEFT)

# --- ACQUISITION CONTROL CARD ---
ctrl_body = make_card(frm_right, "⚙  DATA CONTROL")

frm_btns2 = tk.Frame(ctrl_body, bg=PANEL)
frm_btns2.pack(fill=tk.X, pady=(0, 4))
for label, cmd in [
    ("RESET", reset_data),
    ("EXCEL", simpan_excel),
    ("IMAGE", simpan_gambar)
]:
    tk.Button(
        frm_btns2, text=label,
        command=cmd,
        bg="#fef3c7", fg=TEXT,
        font=("Courier New", 8, "bold"),
        relief=tk.FLAT, cursor="hand2", pady=5
    ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)

tk.Button(
    ctrl_body, text="EXIT PROGRAM",
    command=keluar,
    bg=RED, fg="#ffffff",
    font=("Courier New", 9, "bold"),
    relief=tk.FLAT, cursor="hand2", pady=6
).pack(fill=tk.X, pady=(4, 0))

# ============================================================
# RUN
# ============================================================
ani = animation.FuncAnimation(
    fig, update_plot, interval=200, cache_frame_data=False
)
root.protocol("WM_DELETE_WINDOW", keluar)
log(f"Platform: {sys.platform}")
log("Click 'Subscribe MQTT' to start receiving data.")
root.mainloop()
# signed by: Gilang Pratama Putra Siswanto (2026-05-08)