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
            file_entries = []
            total_files = len(self.input_paths)
            if total_files == 0:
                self.error.emit("No files to pack.")
                return

            with open(self.archive_path, "wb") as f:
                # write placeholder header (will come back and update later)
                f.write(b"\x00" * 32)
                file_table_pos = f.tell()

                # reserve space for file table
                file_table = []
                offset = 0

                for i, path_str in enumerate(self.input_paths):
                    file = Path(path_str)
                    data = file.read_bytes()
                    comp = zlib.compress(data)
                    rel_path = str(file).encode("utf-8")
                    file_table.append((rel_path, offset, len(data), len(comp)))

                    f.write(comp)
                    offset += len(comp)
                    self.progress.emit(int((i + 1) / total_files * 100))

                # write file table after all data
                file_table_data = b""
                for rel_path, offset, size, comp_size in file_table:
                    file_table_data += struct.pack("B", len(rel_path))
                    file_table_data += rel_path
                    file_table_data += struct.pack("<III", offset, size, comp_size)

                file_table_offset = f.tell()
                f.write(file_table_data)

                # write final header at the beginning
                f.seek(0)
                header = MAGIC
                header += struct.pack("B", VERSION)
                header += struct.pack("B", FLAG_COMPRESSED)
                header += struct.pack("<H", len(file_table))
                header += struct.pack("<I", file_table_offset)
                header += b"\x00" * (32 - len(header))
                f.write(header)

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
        file_table_offset = struct.unpack("<I", f.read(4))[0]
        f.read(24)

        f.seek(file_table_offset)
        files = []
        for _ in range(num_files):
            path_len = struct.unpack("B", f.read(1))[0]
            path = f.read(path_len).decode()
            offset, size, comp_size = struct.unpack("<III", f.read(12))
            files.append((path, offset, size, comp_size))

        for path, offset, size, comp_size in files:
            f.seek(32 + offset)
            comp_data = f.read(comp_size)
            raw = zlib.decompress(comp_data)
            out_path = Path(output_dir) / path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(raw)


class VixlWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("\ud83d\udce6 VIXL Archiver")
        self.setFixedSize(400, 550)
        self.setAcceptDrops(True)

        self.layout = QVBoxLayout(self)

        self.label = QLabel("Drag in files or use the buttons")
        self.layout.addWidget(self.label)

        self.file_list = QListWidget()
        self.layout.addWidget(self.file_list)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.layout.addWidget(self.progress)

        self.add_button = QPushButton("➕ Add Files/Folders")
        self.add_button.clicked.connect(self.add_files)
        self.layout.addWidget(self.add_button)

        self.pack_button = QPushButton("📦 Pack to .vixl")
        self.pack_button.clicked.connect(self.pack_archive)
        self.layout.addWidget(self.pack_button)

        self.unpack_button = QPushButton("📤 Unpack .vixl Archive")
        self.unpack_button.clicked.connect(self.unpack_archive)
        self.layout.addWidget(self.unpack_button)

        self.files = []

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Files")
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
            QMessageBox.warning(self, "No files", "Add some files first.")
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Archive", filter="VIXL Archives (*.vixl)")
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
        QMessageBox.information(self, "Success", f"Packed into {path}")

    def on_pack_error(self, err):
        self.pack_button.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Error", err)

    def unpack_archive(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open .vixl Archive", filter="VIXL Archives (*.vixl)")
        if file_path:
            out_dir = QFileDialog.getExistingDirectory(self, "Select Output Folder")
            if out_dir:
                try:
                    unpack_vixl(file_path, out_dir)
                    QMessageBox.information(self, "Success", f"Unpacked to {out_dir}")
                except Exception as e:
                    QMessageBox.critical(self, "Error", str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VixlWindow()
    window.show()
    sys.exit(app.exec())
