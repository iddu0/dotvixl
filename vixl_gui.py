import sys, os, struct, zlib
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
            CHUNK_SIZE = 1024 * 1024  # 1MB
            file_table = b""
            file_data = b""
            offset = 0
            total_size = 0
            file_sizes = []

            # collect file sizes
            for path_str in self.input_paths:
                p = Path(path_str)
                size = p.stat().st_size
                total_size += size
                file_sizes.append((p, size))

            if total_size == 0:
                self.error.emit("No data to pack.")
                return

            processed_size = 0
            for file, orig_size in file_sizes:
                rel_path = str(file).encode("utf-8")
                comp_obj = zlib.compressobj()
                comp_data = b""

                with file.open("rb") as f:
                    while chunk := f.read(CHUNK_SIZE):
                        comp_data += comp_obj.compress(chunk)
                        processed_size += len(chunk)
                        percent = int((processed_size / total_size) * 100)
                        self.progress.emit(percent)

                    comp_data += comp_obj.flush()

                file_table += struct.pack("B", len(rel_path))
                file_table += rel_path
                file_table += struct.pack("<III", offset, orig_size, len(comp_data))
                file_data += comp_data
                offset += len(comp_data)

            header = MAGIC
            header += struct.pack("B", VERSION)
            header += struct.pack("B", FLAG_COMPRESSED)
            header += struct.pack("<H", len(file_sizes))
            header += b"\x00" * 24

            with open(self.archive_path, "wb") as f:
                f.write(header + file_table + file_data)

            self.progress.emit(100)
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
