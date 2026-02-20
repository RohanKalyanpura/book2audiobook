"""Convert screen — main workflow UI.

Contains four cards: Input, Voice & Backend, Output, Conversion Area.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from book2audiobook.ui.components.buttons import PrimaryButton, SecondaryButton, DangerButton
from book2audiobook.ui.components.card import Card
from book2audiobook.ui.components.collapsible import CollapsibleSection
from book2audiobook.ui.components.drag_drop import DragDropZone
from book2audiobook.ui.components.labeled_field import LabeledField
from book2audiobook.ui.components.step_indicator import StepIndicator
from book2audiobook.ui.state import StateManager
from book2audiobook.ui.widgets import LogConsole

logger = logging.getLogger(__name__)


class ConvertScreen(QWidget):
    """Primary conversion workflow screen."""

    # Signals
    import_requested = Signal(str)       # file path
    convert_clicked = Signal()
    cancel_clicked = Signal()
    output_dir_changed = Signal(str)

    def __init__(self, state: StateManager, parent=None):
        super().__init__(parent)
        self._state = state

        # Main scrollable layout
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(24, 20, 24, 20)
        self._content_layout.setSpacing(16)

        # Build cards
        self._build_input_card()
        self._build_voice_card()
        self._build_output_card()
        self._build_conversion_area()

        self._content_layout.addStretch(1)
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Listen to state changes
        state.state_changed.connect(self._on_state_changed)

    # -----------------------------------------------------------------------
    # Input Card
    # -----------------------------------------------------------------------
    def _build_input_card(self):
        card = Card("📚  Input")
        self._input_card = card

        # Drag-drop zone
        self.drop_zone = DragDropZone()
        self.drop_zone.file_selected.connect(self.import_requested.emit)
        card.add_widget(self.drop_zone)

        # Metadata row (hidden until book loaded)
        self._meta_widget = QWidget()
        self._meta_widget.setStyleSheet("background: transparent;")
        meta_layout = QVBoxLayout(self._meta_widget)
        meta_layout.setContentsMargins(0, 8, 0, 0)
        meta_layout.setSpacing(6)

        row1 = QHBoxLayout()
        self.title_label = QLabel("No book loaded")
        self.title_label.setProperty("cssClass", "subtitle")
        self.title_label.setStyleSheet("font-size: 15px; font-weight: 600; background: transparent;")
        row1.addWidget(self.title_label)
        row1.addStretch()
        meta_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.author_label = QLabel("")
        self.author_label.setProperty("cssClass", "muted")
        self.author_label.setStyleSheet("background: transparent;")
        self.chapters_count_label = QLabel("")
        self.chapters_count_label.setProperty("cssClass", "muted")
        self.chapters_count_label.setStyleSheet("background: transparent;")
        row2.addWidget(self.author_label)
        row2.addSpacing(16)
        row2.addWidget(self.chapters_count_label)
        row2.addStretch()
        meta_layout.addLayout(row2)

        # Chapter table (in collapsible)
        self.chapter_section = CollapsibleSection("Chapters", initially_open=False)
        self.chapter_table = QTableView()
        self.chapter_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.chapter_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.chapter_table.setMinimumHeight(150)
        self.chapter_table.setAlternatingRowColors(True)

        # Chapter controls
        ch_controls = QHBoxLayout()
        up_btn = SecondaryButton("▲ Up")
        down_btn = SecondaryButton("▼ Down")
        combine_btn = SecondaryButton("⊕ Combine")
        up_btn.setMaximumWidth(90)
        down_btn.setMaximumWidth(90)
        combine_btn.setMaximumWidth(120)
        self._up_btn = up_btn
        self._down_btn = down_btn
        self._combine_btn = combine_btn
        ch_controls.addWidget(up_btn)
        ch_controls.addWidget(down_btn)
        ch_controls.addWidget(combine_btn)
        ch_controls.addStretch()

        self.chapter_section.add_widget(self.chapter_table)
        self.chapter_section.add_layout(ch_controls)

        meta_layout.addWidget(self.chapter_section)
        self._meta_widget.setVisible(False)
        card.add_widget(self._meta_widget)

        self._content_layout.addWidget(card)

    # -----------------------------------------------------------------------
    # Voice & Backend Card
    # -----------------------------------------------------------------------
    def _build_voice_card(self):
        card = Card("🎙️  Voice & Backend")

        # Voice selector
        self.voice_combo = QComboBox()
        self.voice_combo.setEditable(True)
        self.voice_combo.setMinimumWidth(200)

        voice_field = LabeledField("Voice", self.voice_combo)
        card.add_widget(voice_field)

        # Speed slider
        slider_row = QHBoxLayout()
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setMinimum(50)
        self.speed_slider.setMaximum(150)
        self.speed_slider.setValue(100)
        self.speed_label = QLabel("100%")
        self.speed_label.setFixedWidth(45)
        self.speed_label.setStyleSheet("background: transparent;")
        self.speed_slider.valueChanged.connect(
            lambda v: self.speed_label.setText(f"{v}%")
        )
        slider_row.addWidget(self.speed_slider)
        slider_row.addWidget(self.speed_label)
        speed_field = LabeledField("Speed", QWidget())
        speed_field.widget.setLayout(slider_row)
        # Re-build since LabeledField expects a widget — wrap the row
        speed_container = QWidget()
        speed_container.setStyleSheet("background: transparent;")
        speed_container_layout = QVBoxLayout(speed_container)
        speed_container_layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("Speed")
        lbl.setProperty("cssClass", "fieldLabel")
        speed_container_layout.addWidget(lbl)
        sr = QHBoxLayout()
        sr.addWidget(self.speed_slider)
        sr.addWidget(self.speed_label)
        speed_container_layout.addLayout(sr)
        card.add_widget(speed_container)

        # Advanced voice options (collapsible)
        voice_advanced = CollapsibleSection("Advanced Voice Options")

        prosody_row = QHBoxLayout()
        prosody_lbl = QLabel("Prosody (%)")
        prosody_lbl.setProperty("cssClass", "fieldLabel")
        prosody_lbl.setStyleSheet("background: transparent;")
        self.prosody_spin = QSpinBox()
        self.prosody_spin.setRange(0, 200)
        self.prosody_spin.setValue(100)
        prosody_row.addWidget(prosody_lbl)
        prosody_row.addWidget(self.prosody_spin)
        prosody_row.addStretch()

        pause_row = QHBoxLayout()
        pause_lbl = QLabel("Pause Strength (%)")
        pause_lbl.setProperty("cssClass", "fieldLabel")
        pause_lbl.setStyleSheet("background: transparent;")
        self.pause_spin = QSpinBox()
        self.pause_spin.setRange(0, 200)
        self.pause_spin.setValue(100)
        pause_row.addWidget(pause_lbl)
        pause_row.addWidget(self.pause_spin)
        pause_row.addStretch()

        voice_advanced.add_layout(prosody_row)
        voice_advanced.add_layout(pause_row)
        card.add_widget(voice_advanced)

        # Backend-specific options (collapsible)
        self.backend_section = CollapsibleSection("Backend Options")

        # -- Kokoro options
        self._kokoro_widget = QWidget()
        self._kokoro_widget.setStyleSheet("background: transparent;")
        kl = QVBoxLayout(self._kokoro_widget)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.setSpacing(8)

        self.kokoro_model_dir_edit = QLineEdit()
        kl.addWidget(LabeledField("Model Folder", self.kokoro_model_dir_edit))

        kokoro_dir_btns = QHBoxLayout()
        self.kokoro_browse_btn = SecondaryButton("Browse…")
        self.kokoro_default_btn = SecondaryButton("Use Default")
        kokoro_dir_btns.addWidget(self.kokoro_browse_btn)
        kokoro_dir_btns.addWidget(self.kokoro_default_btn)
        kokoro_dir_btns.addStretch()
        kl.addLayout(kokoro_dir_btns)

        self.kokoro_model_filename_edit = QLineEdit("kokoro-v1_0.pth")
        kl.addWidget(LabeledField("Model Filename", self.kokoro_model_filename_edit))

        self.kokoro_voices_edit = QLineEdit()
        kl.addWidget(LabeledField("Voices (comma-separated)", self.kokoro_voices_edit))

        kokoro_voice_btns = QHBoxLayout()
        self.kokoro_load_voices_btn = SecondaryButton("Load voices.txt")
        self.kokoro_save_voices_btn = SecondaryButton("Save voices.txt")
        kokoro_voice_btns.addWidget(self.kokoro_load_voices_btn)
        kokoro_voice_btns.addWidget(self.kokoro_save_voices_btn)
        kokoro_voice_btns.addStretch()
        kl.addLayout(kokoro_voice_btns)

        self.backend_section.add_widget(self._kokoro_widget)

        # -- OpenRouter options
        self._openrouter_widget = QWidget()
        self._openrouter_widget.setStyleSheet("background: transparent;")
        orl = QVBoxLayout(self._openrouter_widget)
        orl.setContentsMargins(0, 0, 0, 0)
        orl.setSpacing(8)

        self.openrouter_model_edit = QLineEdit("openai/gpt-audio-mini")
        orl.addWidget(LabeledField("Model ID", self.openrouter_model_edit))

        self.openrouter_voices_edit = QLineEdit()
        orl.addWidget(LabeledField("Voices (comma-separated)", self.openrouter_voices_edit))

        self.backend_section.add_widget(self._openrouter_widget)

        # -- OpenAI placeholder
        self._openai_label = QLabel("No additional options for OpenAI backend.")
        self._openai_label.setProperty("cssClass", "muted")
        self._openai_label.setStyleSheet("background: transparent;")
        self.backend_section.add_widget(self._openai_label)

        card.add_widget(self.backend_section)

        self._content_layout.addWidget(card)

    # -----------------------------------------------------------------------
    # Output Card
    # -----------------------------------------------------------------------
    def _build_output_card(self):
        card = Card("📁  Output")

        # Output dir
        dir_row = QHBoxLayout()
        self.output_dir_label = QLabel(str(Path.home()))
        self.output_dir_label.setStyleSheet("background: transparent;")
        self.output_dir_btn = SecondaryButton("Choose Folder…")
        self.output_dir_btn.clicked.connect(self._choose_output_dir)
        dir_row.addWidget(self.output_dir_label, 1)
        dir_row.addWidget(self.output_dir_btn)
        dir_container = QWidget()
        dir_container.setStyleSheet("background: transparent;")
        dir_container.setLayout(dir_row)
        card.add_widget(LabeledField("Output Folder", dir_container))

        # Format + Quality row
        fmt_row = QHBoxLayout()

        self.format_combo = QComboBox()
        self.format_combo.addItem("M4B (Audiobook)", "m4b")
        self.format_combo.addItem("MP3", "mp3")
        self.format_combo.addItem("WAV", "wav")
        fmt_row.addWidget(LabeledField("Format", self.format_combo))

        self.bitrate_combo = QComboBox()
        for kbps in [48, 64, 96, 128, 192]:
            self.bitrate_combo.addItem(f"{kbps} kbps", kbps)
        self.bitrate_combo.setCurrentIndex(1)  # 64 kbps default
        fmt_row.addWidget(LabeledField("Quality", self.bitrate_combo))

        fmt_row.addStretch()

        fmt_container = QWidget()
        fmt_container.setStyleSheet("background: transparent;")
        fmt_container.setLayout(fmt_row)
        card.add_widget(fmt_container)

        self._content_layout.addWidget(card)

    # -----------------------------------------------------------------------
    # Conversion Area
    # -----------------------------------------------------------------------
    def _build_conversion_area(self):
        card = Card("")

        # Button row
        btn_row = QHBoxLayout()
        self.convert_btn = PrimaryButton("▶  Convert")
        self.convert_btn.setMinimumWidth(180)
        self.convert_btn.setMinimumHeight(48)
        self.convert_btn.setStyleSheet(self.convert_btn.styleSheet() + "font-size: 15px;")
        self.convert_btn.clicked.connect(self.convert_clicked.emit)

        self.stop_btn = DangerButton("■  Stop")
        self.stop_btn.setMinimumWidth(100)
        self.stop_btn.setMinimumHeight(48)
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(self.cancel_clicked.emit)

        btn_row.addWidget(self.convert_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addStretch()
        card.add_layout(btn_row)

        # Step indicator
        self.step_indicator = StepIndicator()
        self.step_indicator.setVisible(False)
        card.add_widget(self.step_indicator)

        # Progress bars
        self._progress_widget = QWidget()
        self._progress_widget.setStyleSheet("background: transparent;")
        prog_layout = QVBoxLayout(self._progress_widget)
        prog_layout.setContentsMargins(0, 0, 0, 0)
        prog_layout.setSpacing(8)

        overall_lbl = QLabel("Overall Progress")
        overall_lbl.setProperty("cssClass", "fieldLabel")
        overall_lbl.setStyleSheet("background: transparent;")
        self.overall_bar = QProgressBar()
        self.overall_bar.setMinimum(0)
        self.overall_bar.setMaximum(100)

        chapter_lbl = QLabel("Current Chapter")
        chapter_lbl.setProperty("cssClass", "fieldLabel")
        chapter_lbl.setStyleSheet("background: transparent;")
        self.chapter_bar = QProgressBar()
        self.chapter_bar.setMinimum(0)
        self.chapter_bar.setMaximum(100)

        prog_layout.addWidget(overall_lbl)
        prog_layout.addWidget(self.overall_bar)
        prog_layout.addWidget(chapter_lbl)
        prog_layout.addWidget(self.chapter_bar)
        self._progress_widget.setVisible(False)
        card.add_widget(self._progress_widget)

        # Collapsible log console
        self.log_section = CollapsibleSection("Log Console", initially_open=False)
        self.log_console = LogConsole()
        self.log_console.setMinimumHeight(150)
        self.log_console.setMaximumHeight(300)
        self.log_section.add_widget(self.log_console)
        card.add_widget(self.log_section)

        self._content_layout.addWidget(card)

    # -----------------------------------------------------------------------
    # Public API for the controller
    # -----------------------------------------------------------------------
    def show_book_metadata(self, title: str, author: str, chapter_count: int):
        self.title_label.setText(title)
        self.author_label.setText(f"by {author}" if author else "")
        self.chapters_count_label.setText(f"{chapter_count} chapters")
        self._meta_widget.setVisible(True)

    def set_chapter_model(self, model):
        self.chapter_table.setModel(model)

    def set_converting(self, active: bool):
        self.convert_btn.setVisible(not active)
        self.stop_btn.setVisible(active)
        self.step_indicator.setVisible(active)
        self._progress_widget.setVisible(active)
        if active:
            self.overall_bar.setValue(0)
            self.chapter_bar.setValue(0)
            self.step_indicator.reset()
            if not self.log_section.is_open():
                self.log_section.toggle()

    def update_overall_progress(self, pct: float):
        self.overall_bar.setValue(int(pct * 100))

    def update_chapter_progress(self, pct: float):
        self.chapter_bar.setValue(int(pct * 100))

    def set_step(self, index: int):
        self.step_indicator.set_step(index)

    def sync_backend_panels(self, backend: str):
        """Show/hide backend-specific options."""
        self._kokoro_widget.setVisible(backend == "kokoro")
        self._openrouter_widget.setVisible(backend == "openrouter")
        self._openai_label.setVisible(backend == "openai")

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------
    def _choose_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Output Directory", str(Path.home()))
        if d:
            self.output_dir_label.setText(d)
            self.output_dir_changed.emit(d)

    def _on_state_changed(self, key: str, value):
        if key == "overall_progress":
            self.update_overall_progress(value)
        elif key == "chapter_progress":
            self.update_chapter_progress(value)
        elif key == "conversion_step":
            self.set_step(value)
        elif key == "is_converting":
            self.set_converting(value)
