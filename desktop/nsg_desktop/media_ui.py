"""Desktop UI extension for cover artwork and MP4 export.

Kept separate from app.py so the existing Create/Diagnostics/Settings surface is
preserved while media export remains independently testable.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
)

from .app import MainWindow


class EnhancedMainWindow(MainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("नेपाली AI Song Generator — Windows Studio")
        self.length.setItemText(1, "Full (~2.5–3 min)")
        self._add_media_panel()

    def _add_media_panel(self):
        create_widget = self.tabs.widget(0)
        layout = create_widget.layout()
        box = QGroupBox("Cover photo + video output")
        grid = QGridLayout(box)

        self.cover_path = QLineEdit(str(self.q.value("cover_path", "") or ""))
        self.cover_path.setReadOnly(True)
        choose = QPushButton("Upload / choose cover…")
        choose.clicked.connect(self.choose_cover)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_cover)
        self.make_video = QCheckBox("Create MP4 video with this song")
        self.make_video.setChecked(str(self.q.value("make_video", "true")).lower() not in ("0", "false", "no"))
        self.cover_preview = QLabel("No cover selected")
        self.cover_preview.setAlignment(Qt.AlignCenter)
        self.cover_preview.setMinimumSize(180, 100)
        self.cover_preview.setMaximumHeight(150)
        self.cover_preview.setStyleSheet("border:1px solid #666; padding:4px;")
        export_video = QPushButton("Export MP4 as…")
        export_video.clicked.connect(self.export_video)

        grid.addWidget(QLabel("Artwork"), 0, 0)
        grid.addWidget(self.cover_path, 0, 1, 1, 3)
        grid.addWidget(choose, 1, 1)
        grid.addWidget(clear, 1, 2)
        grid.addWidget(self.make_video, 1, 3)
        grid.addWidget(self.cover_preview, 0, 4, 2, 1)
        grid.addWidget(export_video, 2, 3)
        grid.setColumnStretch(1, 1)

        layout.addWidget(box)
        self._refresh_cover_preview()

    def choose_cover(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose cover photo",
            str(Path.home()),
            "Images (*.jpg *.jpeg *.png *.webp)",
        )
        if path:
            self.cover_path.setText(path)
            self.q.setValue("cover_path", path)
            self._refresh_cover_preview()

    def clear_cover(self):
        self.cover_path.clear()
        self.q.setValue("cover_path", "")
        self.cover_preview.setPixmap(QPixmap())
        self.cover_preview.setText("No cover selected")

    def _refresh_cover_preview(self):
        p = Path(self.cover_path.text()) if self.cover_path.text().strip() else None
        if not p or not p.is_file():
            self.cover_preview.setPixmap(QPixmap())
            self.cover_preview.setText("No cover selected")
            return
        pix = QPixmap(str(p))
        if pix.isNull():
            self.cover_preview.setText(p.name)
            return
        self.cover_preview.setText("")
        self.cover_preview.setPixmap(pix.scaled(240, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def request(self, with_lyrics=True):
        q = super().request(with_lyrics)
        cover = self.cover_path.text().strip()
        q["cover_path"] = cover or None
        q["make_video"] = self.make_video.isChecked()
        self.q.setValue("cover_path", cover)
        self.q.setValue("make_video", "true" if self.make_video.isChecked() else "false")
        return q

    def render_ready(self, x):
        super().render_ready(x)
        if getattr(x, "video", None):
            self.status.setText(f"Done in {x.seconds:.1f}s · MP3 + MP4 ready")
        elif getattr(x, "cover", None):
            self.status.setText(f"Done in {x.seconds:.1f}s · cover embedded in MP3")

    def export_video(self):
        if not self.result or not getattr(self.result, "video", None):
            return self.err("No MP4 has been generated yet. Enable ‘Create MP4 video’ and sing the song first.")
        src = Path(self.result.video)
        dest, _ = QFileDialog.getSaveFileName(self, "Export MP4", src.name, "MP4 video (*.mp4)")
        if dest:
            shutil.copy2(src, dest)
            self.status.setText(f"Video exported: {Path(dest).name}")
