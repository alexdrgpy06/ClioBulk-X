"""
---------------------------------------------------------------------------------------
ClioBulk-X: Legacy Edition GUI
---------------------------------------------------------------------------------------
A robust, PySide6-based graphical interface for the ClioBulk-X native image engine.
This edition focuses on stable, linear batch processing for standard professional 
photography workflows.

DESIGN PATTERN:
- Uses a background QThread to manage the native subprocess without blocking the UI.
- Implements real-time JSON-based IPC for progress monitoring.
- Styled with a dark-themed, modern aesthetic for low-light editing environments.

@author Alejandro Ramírez
@version 1.5.0
@license MIT
---------------------------------------------------------------------------------------
"""

import sys
import os
import json
import subprocess
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QListWidget, QFileDialog, QSlider, QLabel, 
                             QCheckBox, QProgressBar, QFrame)
from PySide6.QtCore import Qt, QThread, Signal, QProcess

class ProcessingThread(QThread):
    """
    Background worker thread responsible for orchestrating the native Rust core.
    
    Reads stdout from the core process in real-time to parse JSON progress packets
    and emit signals to the main UI thread.
    """
    progress_update = Signal(dict)
    finished_signal = Signal()

    def __init__(self, core_path, inputs, output_dir, options):
        """
        Initializes the processing orchestrator.
        
        Args:
            core_path (str): Absolute path to the cliobulk-core executable.
            inputs (list): List of absolute paths to source images.
            output_dir (str): Target directory for processed outputs.
            options (dict): Dictionary of filters and image adjustments.
        """
        super().__init__()
        self.core_path = core_path
        self.inputs = inputs
        self.output_dir = output_dir
        self.options = options

    def run(self):
        """
        Execution entry point for the thread. Spawns the subprocess.
        """
        cmd = [
            self.core_path,
            "--inputs", ",".join(self.inputs),
            "--output", self.output_dir,
            "--options", json.dumps(self.options)
        ]
        
        # Spawn native process with hidden window on Windows
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                 text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        # Parse real-time progress updates from the core's stdout
        for line in process.stdout:
            try:
                data = json.loads(line.strip())
                self.progress_update.emit(data)
            except (json.JSONDecodeError, ValueError):
                # Ignore non-JSON output (e.g., debug logs)
                pass
        
        process.wait()
        self.finished_signal.emit()

class ClioBulkX(QMainWindow):
    """
    Main Application Window for the Legacy Edition.
    
    Provides controls for image adjustments (Brightness, Contrast, Saturation)
    and batch management tools.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClioBulk X - Pro Native Edition")
        self.setMinimumSize(800, 600)
        
        # Apply Global Dark Theme Styling
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #121212; color: #E0E0E0; font-family: 'Segoe UI', Arial; }
            QPushButton { background-color: #2E74B5; border: none; padding: 10px; border-radius: 5px; font-weight: bold; }
            QPushButton:hover { background-color: #3E84C5; }
            QPushButton:disabled { background-color: #444; }
            QListWidget { background-color: #1E1E1E; border: 1px solid #333; border-radius: 10px; padding: 5px; }
            QSlider::handle:horizontal { background: #2E74B5; width: 18px; border-radius: 9px; }
            QFrame#Sidebar { background-color: #1A1A1A; border-right: 1px solid #333; }
        """)

        self.files = []
        # Path resolution for the native binary
        self.core_path = os.path.join(os.path.dirname(__file__), "cliobulk-core", "target", "release", "cliobulk-core.exe")

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)

        # ---------------------------------------------------------
        # Sidebar: Adjustment Controls
        # ---------------------------------------------------------
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(250)
        sidebar_layout = QVBoxLayout(sidebar)
        
        sidebar_layout.addWidget(QLabel("ADJUSTMENTS"))
        
        # Brightness Control
        self.brightness_label = QLabel("Brightness: 0%")
        sidebar_layout.addWidget(self.brightness_label)
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setRange(-100, 100)
        self.brightness_slider.setValue(0)
        self.brightness_slider.valueChanged.connect(lambda v: self.brightness_label.setText(f"Brightness: {v}%"))
        sidebar_layout.addWidget(self.brightness_slider)

        # Contrast Control
        self.contrast_label = QLabel("Contrast: 1.0x")
        sidebar_layout.addWidget(self.contrast_label)
        self.contrast_slider = QSlider(Qt.Horizontal)
        self.contrast_slider.setRange(0, 30)
        self.contrast_slider.setValue(10)
        self.contrast_slider.valueChanged.connect(lambda v: self.contrast_label.setText(f"Contrast: {v/10:.1f}x"))
        sidebar_layout.addWidget(self.contrast_slider)

        # Saturation Control
        self.saturation_label = QLabel("Saturation: 1.0x")
        sidebar_layout.addWidget(self.saturation_label)
        self.saturation_slider = QSlider(Qt.Horizontal)
        self.saturation_slider.setRange(0, 20)
        self.saturation_slider.setValue(10)
        self.saturation_slider.valueChanged.connect(lambda v: self.saturation_label.setText(f"Saturation: {v/10:.1f}x"))
        sidebar_layout.addWidget(self.saturation_slider)

        # Filter Toggles
        self.denoise_cb = QCheckBox("Enable Denoise")
        sidebar_layout.addWidget(self.denoise_cb)

        self.threshold_cb = QCheckBox("Adaptive Threshold")
        sidebar_layout.addWidget(self.threshold_cb)

        sidebar_layout.addStretch()
        
        self.process_btn = QPushButton("PROCESS IMAGES")
        self.process_btn.clicked.connect(self.start_processing)
        sidebar_layout.addWidget(self.process_btn)

        layout.addWidget(sidebar)

        # ---------------------------------------------------------
        # Main Area: File Queue and Progress
        # ---------------------------------------------------------
        content_layout = QVBoxLayout()
        
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("INPUT FILES"))
        add_btn = QPushButton("ADD FILES")
        add_btn.clicked.connect(self.add_files)
        header_layout.addWidget(add_btn)
        clear_btn = QPushButton("CLEAR")
        clear_btn.clicked.connect(self.clear_files)
        header_layout.addWidget(clear_btn)
        content_layout.addLayout(header_layout)

        self.file_list = QListWidget()
        content_layout.addWidget(self.file_list)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        content_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Ready")
        content_layout.addWidget(self.status_label)

        layout.addLayout(content_layout)

    def add_files(self):
        """Opens a file dialog to append images to the processing queue."""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Images", "", 
            "Images (*.png *.jpg *.jpeg *.webp *.arw *.cr2 *.nef *.dng)"
        )
        if files:
            self.files.extend(files)
            self.file_list.addItems(files)

    def clear_files(self):
        """Clears the entire input queue."""
        self.files = []
        self.file_list.clear()

    def start_processing(self):
        """
        Initializes the batch processing sequence.
        Collects UI parameters and launches the background thread.
        """
        if not self.files: return
        
        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not output_dir: return

        # Map UI state to Core-compatible options
        options = {
            "brightness": self.brightness_slider.value() / 100.0,
            "contrast": self.contrast_slider.value() / 10.0,
            "saturation": self.saturation_slider.value() / 10.0,
            "denoise": self.denoise_cb.isChecked(),
            "adaptive_threshold": self.threshold_cb.isChecked()
        }

        self.process_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Start background orchestration
        self.thread = ProcessingThread(self.core_path, self.files, output_dir, options)
        self.thread.progress_update.connect(self.update_ui)
        self.thread.finished_signal.connect(self.on_finished)
        self.thread.start()

    def update_ui(self, data):
        """Callback for real-time progress updates from the background thread."""
        self.progress_bar.setValue(int(data.get("progress", 0)))
        self.status_label.setText(f"Processing: {data.get('current_file', '')}")

    def on_finished(self):
        """Handles post-processing UI restoration."""
        self.process_btn.setEnabled(True)
        self.status_label.setText("Batch Complete!")
        self.progress_bar.setValue(100)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ClioBulkX()
    window.show()
    sys.exit(app.exec())
