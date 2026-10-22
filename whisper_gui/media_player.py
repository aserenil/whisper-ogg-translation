from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

SPEED_OPTIONS: tuple[float, ...] = (0.5, 0.75, 1.0, 1.25, 1.5)


def clamp_rewind(position_ms: int, rewind_ms: int = 5000) -> int:
    return max(0, position_ms - rewind_ms)


class MediaPlayerWidget(QWidget):
    position_changed = Signal(int)

    def __init__(self, parent=None, player: QMediaPlayer | None = None):
        super().__init__(parent)

        self.player = player if player is not None else QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self._audio_output)

        self.video_widget = QVideoWidget(self)
        self.player.setVideoOutput(self.video_widget)
        self.video_widget.setVisible(False)
        self.player.hasVideoChanged.connect(self.video_widget.setVisible)

        self._repeat_target: tuple[int, int] | None = None
        self._scrub_dragging = False

        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self._on_play_clicked)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)

        self.rewind_button = QPushButton("Rewind 5s")
        self.rewind_button.clicked.connect(self.rewind)

        self.repeat_checkbox = QCheckBox("Repeat line")

        self.speed_box = QComboBox()
        for speed in SPEED_OPTIONS:
            self.speed_box.addItem(f"{speed}x", speed)
        self.speed_box.setCurrentIndex(SPEED_OPTIONS.index(1.0))
        self.speed_box.currentIndexChanged.connect(self._on_speed_changed)

        self.scrub_bar = QSlider(Qt.Orientation.Horizontal)
        self.player.durationChanged.connect(self.scrub_bar.setMaximum)
        self.scrub_bar.sliderPressed.connect(self._on_scrub_pressed)
        self.scrub_bar.sliderReleased.connect(self._on_scrub_released)
        self.scrub_bar.sliderMoved.connect(self.seek)

        self.player.positionChanged.connect(self._on_position_changed)
        self.player.errorOccurred.connect(self._on_error)

        self.status_label = QLabel("")

        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.rewind_button)
        controls.addWidget(self.repeat_checkbox)
        controls.addWidget(self.speed_box)

        layout = QVBoxLayout(self)
        layout.addWidget(self.video_widget)
        layout.addLayout(controls)
        layout.addWidget(self.scrub_bar)
        layout.addWidget(self.status_label)

    def _on_scrub_pressed(self) -> None:
        self._scrub_dragging = True

    def _on_scrub_released(self) -> None:
        self._scrub_dragging = False

    def _on_play_clicked(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_playback_state_changed(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_button.setText("Pause")
        else:
            self.play_button.setText("Play")

    def _on_speed_changed(self, _index: int) -> None:
        self.player.setPlaybackRate(self.speed_box.currentData())

    def _on_position_changed(self, position_ms: int) -> None:
        if not self._scrub_dragging:
            self.scrub_bar.setValue(position_ms)

        if (
            self.repeat_checkbox.isChecked()
            and self._repeat_target is not None
            and position_ms >= self._repeat_target[1]
        ):
            self.seek(self._repeat_target[0])

        self.position_changed.emit(position_ms)

    def _on_error(self, error, error_string: str) -> None:
        self.status_label.setText(error_string)

    def load(self, path: Path) -> None:
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self._repeat_target = None
        self.status_label.setText("")

    def seek(self, position_ms: int) -> None:
        self.player.setPosition(position_ms)

    def rewind(self) -> None:
        self.player.setPosition(clamp_rewind(self.player.position()))

    def stop(self) -> None:
        self.player.stop()

    def set_repeat_target(self, start_ms: int, end_ms: int) -> None:
        self._repeat_target = (start_ms, end_ms)
