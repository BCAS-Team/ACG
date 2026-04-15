import sys
import os
import subprocess
import platform
import socket
import json
import time
from datetime import datetime
import psutil
import cpuinfo

# ================= VENDOR SETUP (Local ./vendor) =================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENDOR_DIR = os.path.join(SCRIPT_DIR, "vendor")
os.makedirs(VENDOR_DIR, exist_ok=True)
if VENDOR_DIR not in sys.path:
    sys.path.insert(0, VENDOR_DIR)

print(f"[VENDOR] Using local dependencies folder: {VENDOR_DIR}")

def ensure_packages():
    required = ["psutil", "py-cpuinfo", "gputil", "PyQt6", "pyusb", "sounddevice", "numpy"]
    if platform.system() == "Windows":
        required.append("wmi")

    for pkg in required:
        pkg_name = pkg.replace("PyQt6", "PyQt6").replace("-", "_").split("[")[0]
        try:
            __import__(pkg_name)
            print(f"[+] {pkg} already available")
        except ImportError:
            print(f"[+] Installing {pkg} into ./vendor ...")
            try:
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install",
                    "--target", VENDOR_DIR, "--upgrade", pkg
                ])
                print(f"[+] {pkg} installed successfully.")
            except Exception as e:
                print(f"[-] Failed to install {pkg}: {e}")

ensure_packages()

# ================= IMPORTS =================
import GPUtil
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QLabel, QVBoxLayout, QWidget, QPushButton, QHBoxLayout, QLineEdit,
    QMenu, QMessageBox, QStatusBar, QHeaderView
)
from PyQt6.QtCore import QTimer, Qt

# Dark modern theme
app = QApplication(sys.argv)
app.setStyle('Fusion')
DARK_STYLE = """
QMainWindow, QTreeWidget, QLineEdit, QLabel, QPushButton { background-color: #1e1e1e; color: #ffffff; }
QTreeWidget { alternate-background-color: #252526; }
QTreeWidget::item:selected { background-color: #007acc; }
QHeaderView::section { background-color: #2d2d2d; padding: 6px; }
QLineEdit { padding: 8px; border: 1px solid #444; }
QPushButton { background-color: #007acc; padding: 8px 16px; border: none; }
QPushButton:hover { background-color: #1e90ff; }
"""
app.setStyleSheet(DARK_STYLE)

# ================= SAFE DATA COLLECTION =================
def safe_get(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except:
        return None

def get_cpu_info():
    info = cpuinfo.get_cpu_info()
    # Temperature only on Linux (safe check)
    temps = {}
    try:
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
    except:
        pass

    return {
        "brand": info.get("brand_raw"),
        "arch": info.get("arch"),
        "hz_advertised": info.get("hz_advertised_friendly"),
        "hz_actual": info.get("hz_actual_friendly"),
        "cores_logical": psutil.cpu_count(logical=True),
        "cores_physical": psutil.cpu_count(logical=False),
        "usage_percent": psutil.cpu_percent(interval=0.5),
        "temperature_c": [t.current for t in temps.get("coretemp", [])] if temps else "N/A (Windows limited)"
    }

def get_processes():
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent', 'status', 'create_time']):
        try:
            info = p.info
            info['memory_mb'] = round((info.get('memory_percent') or 0) * psutil.virtual_memory().total / 100 / (1024**2), 1)
            info['runtime'] = str(datetime.now() - datetime.fromtimestamp(info.get('create_time', time.time()))).split('.')[0]
            procs.append(info)
        except:
            continue
    return sorted(procs, key=lambda x: x.get('cpu_percent') or 0, reverse=True)

def get_detailed_system_info():
    return {
        "timestamp": datetime.now().isoformat(),
        "os": {
            "system": platform.system(),
            "node": platform.node(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "boot_time": datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
        },
        "cpu": get_cpu_info(),
        "ram": {
            "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
            "available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
            "percent": psutil.virtual_memory().percent,
            "swap_total_gb": round(psutil.swap_memory().total / (1024**3), 2),
            "swap_used_gb": round(psutil.swap_memory().used / (1024**3), 2)
        },
        "gpu": [
            {
                "name": g.name,
                "load_percent": round(g.load * 100, 1),
                "memory_total_mb": g.memoryTotal,
                "memory_used_mb": g.memoryUsed,
                "memory_free_mb": g.memoryFree,
                "temperature_c": g.temperature
            } for g in GPUtil.getGPUs()
        ] or {"status": "No GPU detected"},
        "network": {
            "hostname": socket.gethostname(),
            "primary_ip": safe_get(socket.gethostbyname, socket.gethostname()),
            "interfaces": {iface: [addr._asdict() for addr in addrs] for iface, addrs in psutil.net_if_addrs().items()},
            "io_counters": psutil.net_io_counters()._asdict()
        },
        "disks": [
            {
                "device": p.device,
                "mountpoint": p.mountpoint,
                "fstype": p.fstype,
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent": usage.percent
            } for p in psutil.disk_partitions() if (usage := safe_get(psutil.disk_usage, p.mountpoint))
        ],
        "usb": get_usb_devices(),
        "audio": get_audio_devices(),
        "battery": get_battery_info(),
        "processes": get_processes()
    }


def get_usb_devices():
    try:
        import usb.core
        import usb.util
        devices = []
        for dev in usb.core.find(find_all=True):
            devices.append({
                "vendor_id": hex(dev.idVendor),
                "product_id": hex(dev.idProduct),
                "manufacturer": usb.util.get_string(dev, dev.iManufacturer) if dev.iManufacturer else "Unknown",
                "product": usb.util.get_string(dev, dev.iProduct) if dev.iProduct else "Unknown"
            })
        return devices
    except:
        return {"error": "pyusb not available"}


def get_audio_devices():
    try:
        import sounddevice as sd
        return [dict(dev) for dev in sd.query_devices()]
    except:
        return {"error": "sounddevice not available"}


def get_battery_info():
    try:
        battery = psutil.sensors_battery()
        if battery:
            return {
                "percent": battery.percent,
                "secs_left": battery.secsleft if battery.secsleft != psutil._common.POWER_TIME_UNLIMITED else "Unlimited",
                "power_plugged": battery.power_plugged
            }
    except:
        pass
    return {"status": "No battery or not supported"}


# ================= KILL PROCESS (Safe, No Admin) =================
def kill_process(pid: int):
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        proc.terminate()
        proc.wait(timeout=4)
        return True, f"✓ Terminated PID {pid} ({name})"
    except psutil.NoSuchProcess:
        return False, f"Process {pid} no longer exists"
    except psutil.AccessDenied:
        return False, f"✗ Access denied — you can only kill your own processes"
    except Exception as e:
        return False, f"✗ Failed to kill {pid}: {str(e)}"


# ================= GUI =================
class UltimateSystemInfoGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ultimate System Info — Vendor Mode")
        self.resize(1480, 920)
        self.data = get_detailed_system_info()

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Toolbar
        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search keys, values, processes...")
        self.search_edit.textChanged.connect(self.global_search)

        btn_refresh = QPushButton("Refresh All")
        btn_refresh.clicked.connect(self.full_refresh)
        btn_expand = QPushButton("Expand All")
        btn_collapse = QPushButton("Collapse All")
        btn_expand.clicked.connect(lambda: self.current_tree.expandAll())
        btn_collapse.clicked.connect(lambda: self.current_tree.collapseAll())

        toolbar.addWidget(QLabel("🔍"))
        toolbar.addWidget(self.search_edit)
        toolbar.addWidget(btn_refresh)
        toolbar.addWidget(btn_expand)
        toolbar.addWidget(btn_collapse)
        main_layout.addLayout(toolbar)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Overview Tree
        self.overview_tab = QWidget()
        ov_layout = QVBoxLayout(self.overview_tab)
        self.overview_tree = QTreeWidget()
        self.overview_tree.setHeaderLabels(["Key", "Value"])
        self.overview_tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.populate_overview()
        ov_layout.addWidget(self.overview_tree)
        self.tabs.addTab(self.overview_tab, "Overview")

        # Processes Tab with Kill
        self.proc_tab = QWidget()
        proc_layout = QVBoxLayout(self.proc_tab)
        self.proc_tree = QTreeWidget()
        self.proc_tree.setHeaderLabels(["PID", "Name", "User", "CPU%", "MEM%", "MEM MB", "Runtime", "Status"])
        self.proc_tree.setSortingEnabled(True)
        self.proc_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.proc_tree.customContextMenuRequested.connect(self.show_process_menu)
        self.populate_processes()
        proc_layout.addWidget(self.proc_tree)
        self.tabs.addTab(self.proc_tab, "Processes")

        # Live Monitor
        live_tab = QWidget()
        live_layout = QVBoxLayout(live_tab)
        self.live_label = QLabel("Live Monitoring")
        self.live_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        live_layout.addWidget(self.live_label)
        self.tabs.addTab(live_tab, "Live Monitor")

        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage(f"Ready • {len(self.data.get('processes', []))} processes")

        self.current_tree = self.overview_tree
        self.tabs.currentChanged.connect(self.tab_changed)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_live)
        self.timer.start(1800)

    def populate_overview(self):
        self.overview_tree.clear()
        root = QTreeWidgetItem(self.overview_tree, ["System Information"])
        self._add_to_tree(root, self.data)
        root.setExpanded(True)

    def _add_to_tree(self, parent, data):
        if isinstance(data, dict):
            for k, v in sorted(data.items()):
                item = QTreeWidgetItem(parent, [str(k), ""])
                self._add_to_tree(item, v)
        elif isinstance(data, list):
            for i, v in enumerate(data[:100]):
                item = QTreeWidgetItem(parent, [f"[{i}]", ""])
                self._add_to_tree(item, v)
        else:
            parent.setText(1, str(data)[:280])

    def populate_processes(self):
        self.proc_tree.clear()
        for p in self.data.get("processes", []):
            item = QTreeWidgetItem(self.proc_tree, [
                str(p.get('pid', '')), p.get('name', '?'), p.get('username', '?'),
                f"{p.get('cpu_percent', 0):.1f}", f"{p.get('memory_percent', 0):.1f}",
                f"{p.get('memory_mb', 0):.1f}", p.get('runtime', '?'), p.get('status', '?')
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, p.get('pid'))

    def show_process_menu(self, position):
        item = self.proc_tree.itemAt(position)
        if not item:
            return
        pid = item.data(0, Qt.ItemDataRole.UserRole)
        if pid is None:
            return
        menu = QMenu()
        menu.addAction(f"Kill Process {pid}").triggered.connect(lambda: self.kill_selected(pid))
        menu.exec(self.proc_tree.viewport().mapToGlobal(position))

    def kill_selected(self, pid):
        reply = QMessageBox.question(self, "Confirm Kill", f"Terminate PID {pid}?", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            success, msg = kill_process(pid)
            QMessageBox.information(self, "Result", msg)
            if success:
                self.refresh_processes()

    def refresh_processes(self):
        self.data["processes"] = get_processes()
        self.populate_processes()

    def full_refresh(self):
        self.data = get_detailed_system_info()
        self.populate_overview()
        self.populate_processes()
        self.statusBar.showMessage("Full refresh completed")

    def tab_changed(self, index):
        self.current_tree = self.proc_tree if index == 1 else self.overview_tree

    def global_search(self, text):
        text = text.lower().strip()
        if not text:
            if self.tabs.currentIndex() == 0:
                self.populate_overview()
            else:
                self.populate_processes()
            return

        if self.tabs.currentIndex() == 0:
            self.overview_tree.clear()
            root = QTreeWidgetItem(self.overview_tree, ["Search Results"])
            self._filter_tree(root, self.data, text)
            root.setExpanded(True)
        else:
            self.proc_tree.clear()
            for p in self.data.get("processes", []):
                if any(text in str(val).lower() for val in p.values() if val):
                    item = QTreeWidgetItem(self.proc_tree, [
                        str(p.get('pid')), p.get('name','?'), p.get('username','?'),
                        f"{p.get('cpu_percent',0):.1f}", f"{p.get('memory_percent',0):.1f}",
                        f"{p.get('memory_mb',0):.1f}", p.get('runtime','?'), p.get('status','?')
                    ])
                    item.setData(0, Qt.ItemDataRole.UserRole, p.get('pid'))

    def _filter_tree(self, parent, data, query):
        if isinstance(data, dict):
            for k, v in data.items():
                if query in str(k).lower() or query in str(v).lower():
                    item = QTreeWidgetItem(parent, [str(k), str(v)[:250]])
                    self._filter_tree(item, v, query)
                else:
                    temp = QTreeWidgetItem(parent, [str(k), ""])
                    self._filter_tree(temp, v, query)
                    if temp.childCount() > 0:
                        parent.addChild(temp)
        elif isinstance(data, list):
            for i, v in enumerate(data):
                if query in str(v).lower():
                    item = QTreeWidgetItem(parent, [f"[{i}]", str(v)[:250]])
                else:
                    temp = QTreeWidgetItem(parent, [f"[{i}]", ""])
                    self._filter_tree(temp, v, query)
                    if temp.childCount() > 0:
                        parent.addChild(temp)

    def update_live(self):
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        gpu = self.data.get("gpu")
        gpu_text = f"{gpu[0].get('load_percent', 'N/A')}%" if isinstance(gpu, list) and gpu else "N/A"
        self.live_label.setText(f"CPU: {cpu:.1f}%   RAM: {ram:.1f}%   GPU: {gpu_text}   •   {datetime.now().strftime('%H:%M:%S')}")


def run_console_mode():
    print("\n[+] Collecting system information...")
    data = get_detailed_system_info()
    filename = f"system_info_{platform.node()}_{int(time.time())}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, default=str)
    print(f"[+] Saved to {filename}")

    while True:
        cmd = input("\nCommand (search <term> | kill <pid> | list | exit): ").strip().lower()
        if cmd == "exit":
            break
        elif cmd.startswith("kill "):
            try:
                pid = int(cmd[5:].strip())
                success, msg = kill_process(pid)
                print(msg)
                if success:
                    data["processes"] = get_processes()
            except:
                print("Usage: kill <pid>")
        elif cmd == "list":
            for p in data["processes"][:30]:
                print(p)
        else:
            # simple search
            term = cmd.replace("search ", "").strip()
            print(f"Results for '{term}':")
            for section, content in data.items():
                if term in str(section).lower() or term in str(content).lower():
                    print(f"\n{section.upper()}: {content}")


# ================= MAIN =================
if __name__ == "__main__":
    print("=" * 70)
    print("   ULTIMATE SYSTEM INFO TOOL (Vendor + Kill + Dark UI)")
    print("=" * 70)

    choice = input("\n1. Console mode\n2. GUI mode (recommended)\nChoice [2]: ").strip()
    if choice == "1":
        run_console_mode()
    else:
        window = UltimateSystemInfoGUI()
        window.show()
        sys.exit(app.exec())