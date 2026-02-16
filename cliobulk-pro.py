"""
---------------------------------------------------------------------------------------
ClioBulk-X: Professional Edition GUI
---------------------------------------------------------------------------------------
A high-fidelity, PySide6-based digital asset management and processing application.
Designed for professional photographers requiring high-performance batch workflows 
on large-scale RAW image datasets.

KEY ARCHITECTURAL FEATURES:
- Asynchronous Native Orchestration: Multi-threaded execution using the Rust core.
- Scalable Queue Management: Handles thousands of files using JSON manifests to 
  bypass OS command-line length limitations.
- Modern UX/UI: Hardware-accelerated rendering with a "Dark Mode" aesthetic.
- Enhanced Metadata Handling: Support for complex filter chains and asset tagging.

@author Alejandro Ramírez
@version 2.2.0
@license MIT
---------------------------------------------------------------------------------------
"""

import sys
import os
import json
import base64
import subprocess
import tempfile
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QListWidget, QFileDialog, QSlider, QLabel, 
                             QCheckBox, QProgressBar, QFrame, QScrollArea, QGraphicsView,
                             QGraphicsScene, QSplitter, QListWidgetItem, QLineEdit, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QPixmap, QImage, QIcon, QFont, QColor, QPalette

class ProcessingThread(QThread):
    """
    High-performance orchestration thread for the native image engine.
    
    Implements a manifest-based IPC strategy to allow processing of virtually 
    unlimited file counts in a single batch, avoiding shell buffer overflows.
    """
    progress_update = Signal(dict)
    finished_signal = Signal()
    error_signal = Signal(str)

    def __init__(self, core_path, inputs, output_dir, options):
        """
        Initializes the thread with processing context.
        
        Args:
            core_path (str): Path to cliobulk-core.exe.
            inputs (list): Absolute paths of assets to process.
            output_dir (str): Destination directory.
            options (dict): Global filter settings.
        """
        super().__init__()
        self.core_path = core_path
        self.inputs = inputs
        self.output_dir = output_dir
        self.options = options
        self._temp_file = None

    def run(self):
        """Entry point for parallel execution orchestration."""
        try:
            # Manifest Generation: Dump path list to a temporary JSON file.
            # This allows the core to read thousands of paths without CLI overhead.
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(self.inputs, f)
                self._temp_file = f.name

            cmd = [
                self.core_path,
                "--inputs", self._temp_file,
                "--output", self.output_dir,
                "--options", json.dumps(self.options)
            ]
            
            # Execute Core in background
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                     text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            # Continuous Polling of Core's output stream
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    try:
                        data = json.loads(line.strip())
                        self.progress_update.emit(data)
                    except (json.JSONDecodeError, ValueError):
                        pass
            
            # Catch non-zero exit codes and capture stderr
            if process.returncode != 0:
                err = process.stderr.read()
                self.error_signal.emit(f"Core error ({process.returncode}): {err}")
            
        except Exception as e:
            self.error_signal.emit(f"Failed to start core: {str(e)}")
        finally:
            # Cleanup manifest
            if self._temp_file and os.path.exists(self._temp_file):
                try: os.unlink(self._temp_file)
                except: pass
            self.finished_signal.emit()

class ModernSlider(QWidget):
    """
    Custom Styled UI Control for professional adjustments.
    
    Combines a header with real-time value display and a sleek horizontal slider.
    """
    def __init__(self, label, min_v, max_v, default_v, scale=1.0):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        
        self.scale = scale
        header = QHBoxLayout()
        self.title = QLabel(label)
        self.title.setStyleSheet("color: #888; font-weight: bold; font-size: 10px; text-transform: uppercase;")
        self.value_label = QLabel(f"{default_v/scale:.1f}")
        self.value_label.setStyleSheet("color: #00C3FF; font-weight: bold;")
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.value_label)
        layout.addLayout(header)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(min_v, max_v)
        self.slider.setValue(default_v)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal { background: #333; height: 4px; border-radius: 2px; }
            QSlider::handle:horizontal { background: #00C3FF; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
        """)
        self.slider.valueChanged.connect(self.update_val)
        layout.addWidget(self.slider)

    def update_val(self, v):
        """Synchronizes label text with current slider position."""
        self.value_label.setText(f"{v/self.scale:.1f}")
    
    def value(self):
        """Returns the scaled floating-point value of the control."""
        return self.slider.value() / self.scale

class ClioBulkX(QMainWindow):
    """
    Primary Application Logic and Window Management.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CLIOBULK PRO X")
        self.setMinimumSize(1280, 800)
        
        # Binary Path Resolution
        base_dir = Path(__file__).parent
        self.core_path = base_dir / "cliobulk-core" / "target" / "release" / "cliobulk-core.exe"
        
        self.files = []
        self.setup_ui()
        
        # Core Verification Delay
        QTimer.singleShot(500, self.check_core)

    def check_core(self):
        """Verifies that the compiled Rust core is available."""
        if not self.core_path.exists():
            QMessageBox.warning(self, "Core Missing", 
                f"Native core not found at:\n{self.core_path}\n\nPlease build the Rust project first.")
            self.status_msg.setText("ERROR: NATIVE CORE NOT FOUND")
            self.status_msg.setStyleSheet("color: #FF4B4B; font-size: 11px; font-weight: bold;")

    def setup_ui(self):
        """Constructs the modern application layout using component-based styling."""
        self.setStyleSheet("""
            QMainWindow { background-color: #0A0A0C; }
            QWidget { color: #E0E0E0; font-family: 'Inter', 'Segoe UI'; }
            QFrame#Sidebar { background-color: #121216; border-right: 1px solid #1F1F24; }
            QFrame#PreviewArea { background-color: #000; border-radius: 15px; }
            QPushButton#PrimaryAction { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0072FF, stop:1 #00C3FF); border: none; padding: 15px; border-radius: 8px; font-weight: 800; color: white; font-size: 14px; }
            QPushButton#PrimaryAction:hover { background: #00D4FF; }
            QPushButton#PrimaryAction:disabled { background: #333; color: #666; }
            QPushButton#Secondary { background: #1F1F24; border: 1px solid #2F2F36; border-radius: 8px; padding: 8px; font-weight: bold; }
            QPushButton#Secondary:hover { background: #2F2F36; }
            QLineEdit { background: #1F1F24; border: 1px solid #2F2F36; padding: 10px; border-radius: 8px; }
            QProgressBar { border: none; background: #1F1F24; height: 6px; border-radius: 3px; text-align: center; }
            QProgressBar::chunk { background: #00C3FF; border-radius: 3px; }
            QListWidget { background: #0A0A0C; border: none; outline: none; }
            QListWidget::item:selected { background: #1F1F24; border-radius: 8px; }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        # ---------------------------------------------------------
        # Left Sidebar: Controls & Branding
        # ---------------------------------------------------------
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(320)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(25, 25, 25, 25)

        title = QLabel("CLIOBULK PRO X")
        title.setStyleSheet("font-size: 20px; font-weight: 900; color: white; margin-bottom: 20px;")
        side_layout.addWidget(title)

        # Image Processing Parameters
        side_layout.addWidget(QLabel("IMAGE ENGINE"))
        self.bright = ModernSlider("Brightness", -100, 100, 0, 100.0)
        self.contrast = ModernSlider("Contrast", 0, 30, 10, 10.0)
        self.satur = ModernSlider("Saturation", 0, 20, 10, 10.0)
        side_layout.addWidget(self.bright)
        side_layout.addWidget(self.contrast)
        side_layout.addWidget(self.satur)

        # Advanced Pipeline Switches
        side_layout.addSpacing(20)
        side_layout.addWidget(QLabel("FILTERS"))
        self.denoise = QCheckBox("High-Frequency Denoise")
        self.threshold = QCheckBox("Adaptive B&W Threshold")
        side_layout.addWidget(self.denoise)
        side_layout.addWidget(self.threshold)

        # Look Management
        side_layout.addSpacing(20)
        side_layout.addWidget(QLabel("ASSETS & LOOKS"))
        self.lut_btn = QPushButton("UPLOAD LUT (.CUBE)")
        self.lut_btn.setObjectName("Secondary")
        side_layout.addWidget(self.lut_btn)

        # Branding Tools
        side_layout.addSpacing(20)
        side_layout.addWidget(QLabel("WATERMARK & BRANDING"))
        self.wm_text = QLineEdit()
        self.wm_text.setPlaceholderText("Enter watermark text...")
        side_layout.addWidget(self.wm_text)
        self.logo_btn = QPushButton("SELECT BRAND LOGO (PNG)")
        self.logo_btn.setObjectName("Secondary")
        side_layout.addWidget(self.logo_btn)

        side_layout.addStretch()
        
        self.process_btn = QPushButton("EXECUTE BATCH")
        self.process_btn.setObjectName("PrimaryAction")
        self.process_btn.clicked.connect(self.start_processing)
        side_layout.addWidget(self.process_btn)

        main_layout.addWidget(sidebar)

        # ---------------------------------------------------------
        # Right Content: Dynamic Preview & Workspace
        # ---------------------------------------------------------
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(30, 30, 30, 30)

        # Workspace Toolbar
        top_bar = QHBoxLayout()
        count_lbl = QLabel("QUEUE")
        count_lbl.setStyleSheet("font-weight: 800; font-size: 14px;")
        top_bar.addWidget(count_lbl)
        top_bar.addStretch()
        add_btn = QPushButton("ADD SOURCE FILES")
        add_btn.setObjectName("Secondary")
        add_btn.clicked.connect(self.add_files)
        top_bar.addWidget(add_btn)
        clear_btn = QPushButton("PURGE")
        clear_btn.setObjectName("Secondary")
        clear_btn.clicked.connect(self.clear_files)
        top_bar.addWidget(clear_btn)
        content_layout.addLayout(top_bar)

        # Workspace Splitter (Vertical Partitioning)
        splitter = QSplitter(Qt.Vertical)
        
        # Asset Grid Visualization
        self.file_list = QListWidget()
        self.file_list.setViewMode(QListWidget.IconMode)
        self.file_list.setIconSize(QSize(120, 120))
        self.file_list.setResizeMode(QListWidget.Adjust)
        self.file_list.setSpacing(10)
        self.file_list.itemClicked.connect(self.update_preview)
        splitter.addWidget(self.file_list)

        # Cinematic Preview Frame
        preview_frame = QFrame()
        preview_frame.setObjectName("PreviewArea")
        prev_layout = QVBoxLayout(preview_frame)
        self.preview_lbl = QLabel("Select an image to preview results")
        self.preview_lbl.setAlignment(Qt.AlignCenter)
        self.preview_lbl.setStyleSheet("color: #444; font-weight: bold;")
        prev_layout.addWidget(self.preview_lbl)
        splitter.addWidget(preview_frame)
        
        content_layout.addWidget(splitter)

        # ---------------------------------------------------------
        # Progress & Operational Telemetry
        # ---------------------------------------------------------
        self.progress_bar = QProgressBar()
        content_layout.addWidget(self.progress_bar)
        
        self.status_bar = QHBoxLayout()
        self.status_msg = QLabel("READY")
        self.status_msg.setStyleSheet("color: #888; font-size: 11px; font-weight: bold;")
        self.status_bar.addWidget(self.status_msg)
        self.status_bar.addStretch()
        engine_tag = QLabel("NATIVE RUST CORE v2.2")
        engine_tag.setStyleSheet("color: #00C3FF; font-size: 10px; font-weight: 800; border: 1px solid #00C3FF; padding: 2px 8px; border-radius: 4px;")
        self.status_bar.addWidget(engine_tag)
        content_layout.addLayout(self.status_bar)

        main_layout.addWidget(content)

    def add_files(self):
        """Imports external image assets into the local session queue."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import Assets", "", 
            "Images (*.png *.jpg *.jpeg *.webp *.arw *.cr2 *.nef *.dng)"
        )
        for p in paths:
            if p not in self.files:
                self.files.append(p)
                item = QListWidgetItem(os.path.basename(p))
                # For standard formats, generate a thumbnail icon
                if not any(p.lower().endswith(ext) for ext in ['.arw', '.cr2', '.nef', '.dng']):
                    item.setIcon(QIcon(p))
                self.file_list.addItem(item)

    def clear_files(self):
        """Resets the current session queue."""
        self.files = []
        self.file_list.clear()
        self.preview_lbl.clear()
        self.preview_lbl.setText("Select an image to preview results")

    def update_preview(self, item):
        """
        Updates the primary viewport based on the selected asset.
        
        Note: High-resolution RAW files display metadata alerts as full-res 
        previews are generated dynamically by the native core during processing.
        """
        path = self.files[self.file_list.row(item)]
        if any(path.lower().endswith(ext) for ext in ['.arw', '.cr2', '.nef', '.dng']):
            self.preview_lbl.setPixmap(QPixmap()) 
            self.preview_lbl.setText(f"RAW ASSET: {os.path.basename(path)}\n(Optimized Native Processing Active)")
        else:
            pix = QPixmap(path)
            if not pix.isNull():
                self.preview_lbl.setPixmap(pix.scaled(self.preview_lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.preview_lbl.setText("Failed to load preview.")

    def start_processing(self):
        """
        Triggers the batch processing pipeline.
        
        Validates environmental dependencies and launches the asynchronous 
        orchestration thread.
        """
        if not self.files: return
        if not self.core_path.exists():
            QMessageBox.critical(self, "Error", "Native core not found. Build it first.")
            return

        out_dir = QFileDialog.getExistingDirectory(self, "Select Output Target")
        if not out_dir: return

        # Configuration Payload
        opts = {
            "brightness": self.bright.value(),
            "contrast": self.contrast.value(),
            "saturation": self.satur.value(),
            "denoise": self.denoise.isChecked(),
            "adaptive_threshold": self.threshold.isChecked()
        }

        self.process_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_msg.setText("PREPARING BATCH...")
        
        # Spawn Orchestrator
        self.thread = ProcessingThread(str(self.core_path), self.files, out_dir, opts)
        self.thread.progress_update.connect(self.on_progress)
        self.error_signal.connect(self.on_error) if hasattr(self, 'error_signal') else None
        self.thread.finished_signal.connect(self.on_done)
        self.thread.start()

    def on_progress(self, data):
        """UI response handler for real-time progress signals."""
        p = int(data.get("progress", 0))
        self.progress_bar.setValue(p)
        cur = data.get('current_file', '').upper()
        status = data.get('status', 'processing')
        self.status_msg.setText(f"{status.upper()}: {cur}")

    def on_error(self, msg):
        """Error notification handler."""
        QMessageBox.critical(self, "Core Error", msg)

    def on_done(self):
        """Clean-up and notification upon batch completion."""
        self.process_btn.setEnabled(True)
        self.status_msg.setText("BATCH EXECUTION COMPLETE")
        self.progress_bar.setValue(100)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Global Modern Dark Palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(10, 10, 12))
    palette.setColor(QPalette.WindowText, QColor(224, 224, 224))
    app.setPalette(palette)
    
    window = ClioBulkX()
    window.show()
    sys.exit(app.exec())
