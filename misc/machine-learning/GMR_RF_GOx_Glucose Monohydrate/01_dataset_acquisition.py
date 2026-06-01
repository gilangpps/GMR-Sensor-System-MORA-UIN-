import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import tkinter as tk
from tkinter import filedialog, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime
import pandas as pd  # Tambahkan untuk Excel

# --- Konfigurasi Serial ---
PORT = 'COM7'         # Ganti sesuai dengan port Arduino kamu
BAUD_RATE = 9600

# --- Inisialisasi Serial ---
ser = serial.Serial(PORT, BAUD_RATE)
ser.flush()

# --- Buffer Data ---
data_waktu = []
data_tegangan = []
collecting = False
start_time = None

# --- Buat GUI ---
root = tk.Tk()
root.title("Monitor Tegangan Arduino")

# --- Setup Plot ---
fig, ax = plt.subplots()
line, = ax.plot([], [], lw=2)
ax.set_title("Grafik Tegangan dari Arduino")
ax.set_xlabel("Waktu (detik)")
ax.set_ylabel("Tegangan (V)")
ax.grid(True)

canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

# --- Fungsi Update Grafik ---
def update(frame):
    global start_time
    if collecting:
        try:
            if ser.in_waiting:
                baris = ser.readline().decode('utf-8').strip()
                tegangan = float(baris)

                if start_time is None:
                    start_time = datetime.now()

                waktu = (datetime.now() - start_time).total_seconds()
                data_waktu.append(waktu)
                data_tegangan.append(tegangan)

                # Update grafik (sumbu x terus bertambah)
                line.set_data(data_waktu, data_tegangan)
                ax.relim()
                ax.autoscale_view()
                canvas.draw()
        except:
            pass
    return line,

# --- Animasi Plot TANPA WARNING ---
ani = animation.FuncAnimation(fig, update, interval=100, cache_frame_data=False)

# --- Fungsi Tombol ---
def mulai():
    global collecting, start_time
    collecting = True
    if start_time is None:
        start_time = datetime.now()

def berhenti():
    global collecting
    collecting = False

def reset_data():
    global data_waktu, data_tegangan, start_time
    collecting = False
    data_waktu = []
    data_tegangan = []
    start_time = None
    line.set_data([], [])
    ax.set_xlim(auto=True)
    ax.set_ylim(auto=True)
    ax.relim()
    ax.autoscale_view()
    canvas.draw()

def simpan_excel():
    if not data_waktu:
        messagebox.showwarning("Peringatan", "Belum ada data untuk disimpan.")
        return
    filepath = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                            filetypes=[("Excel Files", "*.xlsx")],
                                            title="Simpan Data Excel")
    if filepath:
        df = pd.DataFrame({
            'Waktu (detik)': data_waktu,
            'Tegangan (V)': data_tegangan
        })
        try:
            df.to_excel(filepath, index=False)
            messagebox.showinfo("Sukses", f"Data berhasil disimpan ke:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Gagal", f"Terjadi kesalahan saat menyimpan:\n{e}")

def simpan_gambar():
    filepath = filedialog.asksaveasfilename(defaultextension=".png",
                                            filetypes=[("PNG Image", "*.png")],
                                            title="Simpan Gambar Plot")
    if filepath:
        fig.savefig(filepath)
        messagebox.showinfo("Sukses", f"Gambar berhasil disimpan ke:\n{filepath}")

def keluar():
    if messagebox.askokcancel("Keluar", "Yakin ingin keluar?"):
        try:
            ser.close()
        except:
            pass
        root.destroy()

# --- Tombol ---
frame_btn = tk.Frame(root)
frame_btn.pack(pady=10)

tk.Button(frame_btn, text="▶ Mulai", command=mulai, width=10, bg='lightgreen').grid(row=0, column=0, padx=5)
tk.Button(frame_btn, text="⏸️ Berhenti", command=berhenti, width=10, bg='khaki').grid(row=0, column=1, padx=5)
tk.Button(frame_btn, text="🔄 Reset", command=reset_data, width=10).grid(row=0, column=2, padx=5)
tk.Button(frame_btn, text="💾 Simpan Excel", command=simpan_excel, width=12).grid(row=0, column=3, padx=5)
tk.Button(frame_btn, text="🖼 Simpan Gambar", command=simpan_gambar, width=15).grid(row=0, column=4, padx=5)
tk.Button(frame_btn, text="❌ Keluar", command=keluar, width=10, bg='salmon').grid(row=0, column=5, padx=5)

# --- Jalankan GUI ---
root.protocol("WM_DELETE_WINDOW", keluar)
root.mainloop()
