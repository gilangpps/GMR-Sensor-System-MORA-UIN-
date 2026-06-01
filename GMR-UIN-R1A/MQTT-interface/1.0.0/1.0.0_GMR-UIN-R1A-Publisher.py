# ============================================================
# GMR UIN R1A - MQTT Publisher
# UI Redesign: Dashboard Style (Landscape, Green Theme)
# Revision: Live Data 2 col, Linux/RPi layout fix
# Update patch: 2026-05-08
# ============================================================

import serial
import json
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
# DETEKSI PLATFORM
# ============================================================
IS_LINUX = sys.platform.startswith("linux")

if sys.platform.startswith("win"):
    DEFAULT_PORT = "COM3"
elif IS_LINUX:
    DEFAULT_PORT = "/dev/ttyUSB0"
else:
    DEFAULT_PORT = "/dev/tty.usbserial-0001"

BAUD_RATE         = 9600
MQTT_BROKER       = "localhost"
MQTT_PORT         = 1883
MQTT_TOPIC_DATA   = "gmr/data"
MQTT_TOPIC_STATUS = "gmr/status"
MQTT_CLIENT_ID    = "GMR-Publisher"

def tegangan_ke_b(v):
    return 5.3381 * v - 4.2983

# ============================================================
# STATE GLOBAL
# ============================================================
data_waktu     = []
data_b         = []
data_v         = []
collecting     = False
start_time     = None
ser            = None
mqtt_client    = None
mqtt_connected = False

# ============================================================
# WARNA (Green Teal Theme)
# ============================================================
BG          = "#f0f4f0"
PANEL       = "#ffffff"
HEADER_BG   = "#1a4a3a"
ACCENT      = "#1a6b55"
ACCENT2     = "#0d9b6e"
GREEN       = "#16a34a"
GREEN_LIGHT = "#22c55e"
RED         = "#dc2626"
YELLOW      = "#d97706"
TEXT        = "#0f2d1f"
SUBTEXT     = "#4a7a5a"
DIVIDER     = "#c6ddd0"
TEAL_DARK   = "#134e3a"

# ============================================================
# MQTT CALLBACKS
# ============================================================
def on_mqtt_connect(client, userdata, flags, rc):
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        update_mqtt_status("Connected", GREEN_LIGHT)
        client.publish(
            MQTT_TOPIC_STATUS,
            json.dumps({"status": "publisher_online"}),
            retain=True
        )
    else:
        mqtt_connected = False
        update_mqtt_status(f"Failed rc={rc}", RED)

def on_mqtt_disconnect(client, userdata, rc):
    global mqtt_connected
    mqtt_connected = False
    update_mqtt_status("Disconnected", RED)

def connect_mqtt():
    global mqtt_client, MQTT_BROKER, MQTT_PORT
    MQTT_BROKER = broker_var.get().strip()
    try:
        MQTT_PORT = int(mqttport_var.get().strip())
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
        mqtt_client.on_connect    = on_mqtt_connect
        mqtt_client.on_disconnect = on_mqtt_disconnect
        mqtt_client.will_set(
            MQTT_TOPIC_STATUS,
            json.dumps({"status": "publisher_offline"}),
            retain=True
        )
        mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()
        log(f"Connecting MQTT to {MQTT_BROKER}:{MQTT_PORT}...")
    except Exception as e:
        update_mqtt_status("Error", RED)
        log(f"MQTT Error: {e}")

def publish_data(t, v, b):
    if mqtt_client and mqtt_connected:
        payload = json.dumps({
            "timestamp": datetime.now().isoformat(),
            "t_s":  round(t, 4),
            "v_V":  round(v, 4),
            "b_mT": round(b, 4)
        })
        mqtt_client.publish(MQTT_TOPIC_DATA, payload, qos=1)

# ============================================================
# SERIAL
# ============================================================
def connect_serial():
    global ser
    port = port_var.get().strip()
    try:
        baud = int(baud_var.get())
    except ValueError:
        log("Invalid baud rate.")
        return
    try:
        if ser and ser.is_open:
            ser.close()
        ser = serial.Serial(port, baud, timeout=1)
        ser.flush()
        update_serial_status("Connected", GREEN_LIGHT)
        log(f"Serial connected: {port} @ {baud}")
    except Exception as e:
        ser = None
        update_serial_status("Disconnected", RED)
        log(f"Serial error: {e}")

# ============================================================
# GUI HELPERS
# ============================================================
def update_mqtt_status(text, color):
    try:
        lbl_mqtt_conn_val.config(text=f"● {text}", fg=color)
        if color == GREEN_LIGHT:
            lbl_header_status.config(text="● Loaded", fg=GREEN_LIGHT)
        else:
            lbl_header_status.config(text="● Offline", fg=RED)
    except:
        pass

def update_serial_status(text, color):
    try:
        lbl_serial_conn_val.config(text=f"● {text}", fg=color)
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
# KONTROL
# ============================================================
def mulai():
    global collecting, start_time
    if ser is None or not ser.is_open:
        messagebox.showwarning(
            "Warning",
            "Please connect the serial port first."
        )
        return
    collecting = True
    if start_time is None:
        start_time = datetime.now()
    log("Acquisition started")
    if mqtt_connected:
        mqtt_client.publish(
            MQTT_TOPIC_STATUS,
            json.dumps({"status": "collecting"})
        )

def berhenti():
    global collecting
    collecting = False
    log("Acquisition stopped")
    if mqtt_connected and mqtt_client:
        mqtt_client.publish(
            MQTT_TOPIC_STATUS,
            json.dumps({"status": "stopped"})
        )

def reset_data():
    global data_waktu, data_b, data_v, start_time, collecting
    collecting = False
    data_waktu.clear()
    data_b.clear()
    data_v.clear()
    start_time = None
    line.set_data([], [])
    ax.relim()
    ax.autoscale_view()
    canvas.draw()
    log("Data reset.")
    lbl_count.config(text="0 sample")
    lbl_last_b.config(text="B = -- mT")
    lbl_last_v.config(text="-- V")

def simpan_excel():
    if not data_waktu:
        messagebox.showwarning("Warning", "No data available.")
        return
    fp = filedialog.asksaveasfilename(
        defaultextension=".xlsx",
        filetypes=[("Excel", "*.xlsx")]
    )
    if fp:
        try:
            pd.DataFrame({
                "t (s)":  data_waktu,
                "V (V)":  data_v,
                "B (mT)": data_b
            }).to_excel(fp, index=False)
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
        berhenti()
        if mqtt_client:
            try:
                mqtt_client.publish(
                    MQTT_TOPIC_STATUS,
                    json.dumps({"status": "publisher_offline"}),
                    retain=True
                )
                mqtt_client.loop_stop()
                mqtt_client.disconnect()
            except:
                pass
        try:
            if ser and ser.is_open:
                ser.close()
        except:
            pass
        root.destroy()

# ============================================================
# ANIMASI
# ============================================================
def update(frame):
    global start_time
    if collecting and ser and ser.is_open:
        try:
            if ser.in_waiting:
                baris    = ser.readline().decode("utf-8").strip()
                tegangan = float(baris)
                b_mT     = tegangan_ke_b(tegangan)
                if start_time is None:
                    start_time = datetime.now()
                waktu = (datetime.now() - start_time).total_seconds()
                data_waktu.append(waktu)
                data_b.append(b_mT)
                data_v.append(tegangan)
                publish_data(waktu, tegangan, b_mT)
                ts = datetime.now().strftime("%H:%M:%S")
                txt_log.config(state=tk.NORMAL)
                txt_log.insert(
                    tk.END,
                    f"[{ts}]  t={waktu:.2f}s   "
                    f"V={tegangan:.4f}   B={b_mT:.4f}mT\n"
                )
                txt_log.see(tk.END)
                txt_log.config(state=tk.DISABLED)
                lbl_count.config(text=f"{len(data_waktu)} sample")
                lbl_last_b.config(text=f"B = {b_mT:.4f} mT")
                lbl_last_v.config(text=f"{tegangan:.4f} V")
                line.set_data(data_waktu, data_b)
                ax.relim()
                ax.autoscale_view()
                canvas.draw()
        except Exception as e:
            log(f"Error: {e}")
    return line,

# ============================================================
# ROOT WINDOW
# ============================================================
root = tk.Tk()
root.title("GMR UIN R1A - MQTT Publisher")
root.configure(bg=BG)
root.resizable(True, True)

# Geometry eksplisit agar aman di Linux/RPi (tidak bergantung state zoomed)
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
    bg=HEADER_BG, fg=GREEN_LIGHT
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
    text="(MQTT Publisher — GMR UIN R1A)",
    font=("Courier New", 8, "italic"),
    bg=HEADER_BG, fg="#a0c4b0"
).pack(anchor=tk.W)

frm_hdr_right = tk.Frame(frm_hdr, bg=HEADER_BG)
frm_hdr_right.pack(side=tk.RIGHT, padx=18)
tk.Label(
    frm_hdr_right,
    text="System Status",
    font=("Courier New", 8, "bold"),
    bg=HEADER_BG, fg="#a0c4b0"
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
# RIGHT COLUMN — scrollable agar tidak terpotong di RPi/Linux
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
ax.set_facecolor("#f2f9f5")
ax.set_title(
    "Magnetic Field vs. Time",
    color=TEAL_DARK, fontsize=10, fontweight="bold", pad=6
)
ax.set_xlabel("Time, t (s)", color=SUBTEXT, fontsize=8)
ax.set_ylabel("Magnetic Field, B (mT)", color=SUBTEXT, fontsize=8)
ax.tick_params(colors=SUBTEXT, labelsize=7)
for sp in ax.spines.values():
    sp.set_color(DIVIDER)
ax.grid(True, color="#c6ddd0", linewidth=0.7, linestyle="--")
line, = ax.plot([], [], lw=1.8, color=TEAL_DARK, label="Magnetic Field (mT)")
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
    bg=PANEL, fg=TEAL_DARK
).pack(side=tk.LEFT)
tk.Frame(frm_live_card, bg=DIVIDER, height=1).pack(fill=tk.X, padx=10)

frm_live_cols = tk.Frame(frm_live_card, bg=PANEL)
frm_live_cols.pack(fill=tk.X, padx=10, pady=8)

# Kolom 1: Magnetic Field B
frm_col_b = tk.Frame(frm_live_cols, bg=PANEL)
frm_col_b.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

tk.Label(
    frm_col_b,
    text="MAGNETIC FIELD",
    font=("Courier New", 8, "bold"),
    bg=PANEL, fg=TEAL_DARK
).pack(anchor=tk.W)

lbl_last_b = tk.Label(
    frm_col_b,
    text="B = -- mT",
    font=("Courier New", 20, "bold"),
    bg=PANEL, fg=TEAL_DARK
)
lbl_last_b.pack(anchor=tk.W, pady=(2, 0))

lbl_count = tk.Label(
    frm_col_b,
    text="0 sample",
    font=("Courier New", 9),
    bg=PANEL, fg=SUBTEXT
)
lbl_count.pack(anchor=tk.W)

# Divider vertikal
tk.Frame(frm_live_cols, bg=DIVIDER, width=1).pack(
    side=tk.LEFT, fill=tk.Y, padx=20
)

# Kolom 2: Sensor Voltage V
frm_col_v = tk.Frame(frm_live_cols, bg=PANEL)
frm_col_v.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

tk.Label(
    frm_col_v,
    text="SENSOR VOLTAGE",
    font=("Courier New", 8, "bold"),
    bg=PANEL, fg=TEAL_DARK
).pack(anchor=tk.W)

lbl_last_v = tk.Label(
    frm_col_v,
    text="V = -- V",
    font=("Courier New", 20, "bold"),
    bg=PANEL, fg=TEAL_DARK
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
    bg=PANEL, fg=TEAL_DARK
).pack(side=tk.LEFT)
tk.Frame(frm_log_card, bg=DIVIDER, height=1).pack(fill=tk.X, padx=10)

txt_log = tk.Text(
    frm_log_card,
    height=4,
    bg="#f2f9f5", fg=TEAL_DARK,
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
        bg=PANEL, fg=TEAL_DARK
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

# Serial section header
tk.Label(
    conn_body,
    text="⊟  SERIAL PORT",
    font=("Courier New", 8, "bold"),
    bg=PANEL, fg=TEAL_DARK
).pack(anchor=tk.W, pady=(0, 4))

# Port
r_port = make_row(conn_body, "Port")
port_var = tk.StringVar(value=DEFAULT_PORT)
tk.Entry(
    r_port, textvariable=port_var,
    font=("Courier New", 8),
    bg="#f2f9f5", fg=TEAL_DARK,
    relief=tk.FLAT, bd=2, width=13,
    insertbackground=TEAL_DARK
).pack(side=tk.LEFT)

# Shortcut khusus Linux
if IS_LINUX:
    sc_f = tk.Frame(conn_body, bg=PANEL)
    sc_f.pack(fill=tk.X, pady=(0, 2))
    tk.Label(
        sc_f, text="Shortcut:",
        font=("Courier New", 7),
        bg=PANEL, fg=SUBTEXT
    ).pack(side=tk.LEFT)
    for p in ["/dev/ttyUSB0", "/dev/ttyACM0"]:
        tk.Button(
            sc_f, text=p.split("/")[-1],
            command=lambda x=p: port_var.set(x),
            bg=DIVIDER, fg=TEXT,
            font=("Courier New", 7),
            relief=tk.FLAT, padx=3,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=2)

# Baud Rate
r_baud = make_row(conn_body, "Baud Rate")
baud_var = tk.StringVar(value=str(BAUD_RATE))
ttk.Combobox(
    r_baud, textvariable=baud_var,
    values=["9600","19200","38400","57600","115200"],
    font=("Courier New", 8), width=9
).pack(side=tk.LEFT)

# Serial connection status
r_sconn = make_row(conn_body, "Connection")
lbl_serial_conn_val = tk.Label(
    r_sconn,
    text="● Disconnected",
    font=("Courier New", 8, "bold"),
    bg=PANEL, fg=RED
)
lbl_serial_conn_val.pack(side=tk.LEFT)

tk.Button(
    conn_body, text="Connect Serial",
    command=connect_serial,
    bg=ACCENT2, fg="#ffffff",
    font=("Courier New", 8, "bold"),
    relief=tk.FLAT, cursor="hand2", pady=4
).pack(fill=tk.X, pady=(6, 0))

# Divider antar serial dan mqtt
tk.Frame(conn_body, bg=DIVIDER, height=1).pack(fill=tk.X, pady=8)

# MQTT section header
tk.Label(
    conn_body,
    text="(ᵠ)  MQTT BROKER",
    font=("Courier New", 8, "bold"),
    bg=PANEL, fg=TEAL_DARK
).pack(anchor=tk.W, pady=(0, 4))

# Broker IP
r_broker = make_row(conn_body, "Broker IP")
broker_var = tk.StringVar(value=MQTT_BROKER)
tk.Entry(
    r_broker, textvariable=broker_var,
    font=("Courier New", 8),
    bg="#f2f9f5", fg=TEAL_DARK,
    relief=tk.FLAT, bd=2, width=13,
    insertbackground=TEAL_DARK
).pack(side=tk.LEFT)

# MQTT Port
r_mport = make_row(conn_body, "Port")
mqttport_var = tk.StringVar(value=str(MQTT_PORT))
tk.Entry(
    r_mport, textvariable=mqttport_var,
    font=("Courier New", 8),
    bg="#f2f9f5", fg=TEAL_DARK,
    relief=tk.FLAT, bd=2, width=7,
    insertbackground=TEAL_DARK
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
    conn_body, text="Connect MQTT",
    command=connect_mqtt,
    bg=YELLOW, fg="#1a1a2e",
    font=("Courier New", 8, "bold"),
    relief=tk.FLAT, cursor="hand2", pady=4
).pack(fill=tk.X, pady=(6, 0))

# --- ACQUISITION CONTROL CARD ---
ctrl_body = make_card(frm_right, "⚙  ACQUISITION CONTROL")

tk.Button(
    ctrl_body, text="▶  START",
    command=mulai,
    bg=GREEN, fg="#ffffff",
    font=("Courier New", 9, "bold"),
    relief=tk.FLAT, cursor="hand2", pady=6
).pack(fill=tk.X, pady=(0, 4))

tk.Button(
    ctrl_body, text="■  STOP",
    command=berhenti,
    bg=YELLOW, fg="#1a1a2e",
    font=("Courier New", 9, "bold"),
    relief=tk.FLAT, cursor="hand2", pady=6
).pack(fill=tk.X, pady=(0, 4))

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
        bg="#d6ede0", fg=TEXT,
        font=("Courier New", 8, "bold"),
        relief=tk.FLAT, cursor="hand2", pady=5
    ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)

tk.Button(
    ctrl_body, text="EXIT PROGRAM",
    command=keluar,
    bg=RED, fg="#ffffff",
    font=("Courier New", 9, "bold"),
    relief=tk.FLAT, cursor="hand2", pady=6
).pack(fill=tk.X, pady=(0, 0))

# ============================================================
# RUN
# ============================================================
ani = animation.FuncAnimation(
    fig, update, interval=100, cache_frame_data=False
)
root.protocol("WM_DELETE_WINDOW", keluar)
log(f"Platform: {sys.platform} | Default port: {DEFAULT_PORT}")
log("Connect Serial & MQTT, then press START.")
root.mainloop()
# signed by: Gilang Pratama Putra Siswanto (2026-05-08)