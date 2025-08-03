import sys
import os
import struct
import zlib
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QFileDialog,
    QListWidget, QMessageBox, QLabel, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# === VIXL CORE ===

MAGIC = b"VIXL"
VERSION = 1
FLAG_COMPRESSED = 0x01

class VixlPacker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, archive_path, input_paths):
        super().__init__()
        self.archive_path = archive_path
        self.input_paths = input_paths

    def run(self):
        try:
            file_table = b""
            offset = 0
            total_files = len(self.input_paths)
            if total_files == 0:
                self.error.emit("no files to pack")
                return

            with open(self.archive_path, "wb") as out_file:
                out_file.write(b"\x00" * 32)  # placeholder for header

                for i, path_str in enumerate(self.input_paths):
                    file = Path(path_str)
                    data = file.read_bytes()
                    comp = zlib.compress(data)

                    rel_path = str(file).encode("utf-8")
                    file_table += struct.pack("B", len(rel_path))
                    file_table += rel_path
                    file_table += struct.pack("<III", offset, len(data), len(comp))

                    out_file.write(comp)
                    offset += len(comp)

                    percent = int((i + 1) / total_files * 100)
                    self.progress.emit(percent)
                    QApplication.processEvents()

                # write header + file_table at start
                out_file.seek(0)
                header = MAGIC
                header += struct.pack("B", VERSION)
                header += struct.pack("B", FLAG_COMPRESSED)
                header += struct.pack("<H", total_files)
                header += b"\x00" * 24
                out_file.write(header + file_table)

            self.finished.emit(self.archive_path)
        except Exception as e:
            self.error.emit(str(e))


def unpack_vixl(archive_path, output_dir):
    with open(archive_path, "rb") as f:
        if f.read(4) != MAGIC:
            raise ValueError("not a valid .vixl archive")

        f.read(1)  # version
        f.read(1)  # flags
        num_files = struct.unpack("<H", f.read(2))[0]
        f.read(24)

        files = []
        for _ in range(num_files):
            path_len = struct.unpack("B", f.read(1))[0]
            path = f.read(path_len).decode()
            offset, size, comp_size = struct.unpack("<III", f.read(12))
            files.append((path, offset, size, comp_size))

        base = f.tell()
        for path, offset, size, comp_size in files:
            f.seek(base + offset)
            comp_data = f.read(comp_size)
            raw = zlib.decompress(comp_data)
            out_path = Path(output_dir) / path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(raw)

# === GUI ===

class VixlWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📦 VIXL Archiver")
        self.setFixedSize(400, 550)
        self.setAcceptDrops(True)

        self.layout = QVBoxLayout(self)

        self.label = QLabel("drag in files or use the buttons")
        self.layout.addWidget(self.label)

        self.file_list = QListWidget()
        self.layout.addWidget(self.file_list)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.layout.addWidget(self.progress)

        self.add_button = QPushButton("➕ add files/folders")
        self.add_button.clicked.connect(self.add_files)
        self.layout.addWidget(self.add_button)

        self.pack_button = QPushButton("📦 pack to .vixl")
        self.pack_button.clicked.connect(self.pack_archive)
        self.layout.addWidget(self.pack_button)

        self.unpack_button = QPushButton("📤 unpack .vixl")
        self.unpack_button.clicked.connect(self.unpack_archive)
        self.layout.addWidget(self.unpack_button)

        self.files = []

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "select files")
        for f in files:
            self._add_file(f)

    def _add_file(self, file):
        if file not in self.files:
            self.files.append(file)
            self.file_list.addItem(file)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                self._add_file(path)
            elif os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for file in files:
                        self._add_file(os.path.join(root, file))

    def pack_archive(self):
        if not self.files:
            QMessageBox.warning(self, "no files", "add some files first.")
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "save archive", filter="VIXL Archives (*.vixl)")
        if save_path:
            self.progress.setVisible(True)
            self.progress.setValue(0)
            self.pack_button.setEnabled(False)

            file_entries = []
            for entry in self.files:
                p = Path(entry)
                if p.is_dir():
                    for f in p.rglob("*"):
                        if f.is_file():
                            file_entries.append(str(f))
                else:
                    file_entries.append(str(p))

            self.thread = VixlPacker(save_path, file_entries)
            self.thread.progress.connect(self.progress.setValue)
            self.thread.finished.connect(self.on_pack_done)
            self.thread.error.connect(self.on_pack_error)
            self.thread.start()

    def on_pack_done(self, path):
        self.pack_button.setEnabled(True)
        self.progress.setVisible(False)
        self.progress.setValue(100)
        QMessageBox.information(self, "done", f"packed into:\n{path}")

    def on_pack_error(self, err):
        self.pack_button.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "error", err)

    def unpack_archive(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "open .vixl archive", filter="VIXL Archives (*.vixl)")
        if file_path:
            out_dir = QFileDialog.getExistingDirectory(self, "select output folder")
            if out_dir:
                try:
                    unpack_vixl(file_path, out_dir)
                    QMessageBox.information(self, "done", f"unpacked to:\n{out_dir}")
                except Exception as e:
                    QMessageBox.critical(self, "error", str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VixlWindow()
    window.show()
    sys.exit(app.exec())
