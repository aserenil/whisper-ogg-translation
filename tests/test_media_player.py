from unittest.mock import MagicMock

from PySide6.QtMultimedia import QMediaPlayer

from whisper_gui.media_player import SPEED_OPTIONS, MediaPlayerWidget, clamp_rewind


def test_clamp_rewind_subtracts_five_seconds_by_default():
    assert clamp_rewind(12000) == 7000


def test_clamp_rewind_floors_at_zero():
    assert clamp_rewind(2000) == 0


def test_widget_constructs_with_default_speed_one_x(qapp):
    widget = MediaPlayerWidget()
    assert widget.speed_box.currentData() == 1.0
    assert list(SPEED_OPTIONS) == sorted(SPEED_OPTIONS)
    assert 1.0 in SPEED_OPTIONS


def test_rewind_seeks_player_to_clamped_position(qapp):
    fake_player = MagicMock(spec=QMediaPlayer)
    fake_player.position.return_value = 12000
    widget = MediaPlayerWidget(player=fake_player)
    widget.rewind()
    fake_player.setPosition.assert_called_once_with(7000)


def test_repeat_checked_with_no_target_set_does_not_seek(qapp):
    fake_player = MagicMock(spec=QMediaPlayer)
    widget = MediaPlayerWidget(player=fake_player)
    widget.repeat_checkbox.setChecked(True)
    widget._on_position_changed(9999)
    fake_player.setPosition.assert_not_called()


def test_repeat_checked_seeks_back_to_target_start_past_end(qapp):
    fake_player = MagicMock(spec=QMediaPlayer)
    widget = MediaPlayerWidget(player=fake_player)
    widget.set_repeat_target(1000, 2000)
    widget.repeat_checkbox.setChecked(True)
    widget._on_position_changed(2000)
    fake_player.setPosition.assert_called_once_with(1000)


def test_load_stops_playback_before_loading_new_source(qapp, tmp_path):
    fake_player = MagicMock(spec=QMediaPlayer)
    widget = MediaPlayerWidget(player=fake_player)
    path = tmp_path / "b.ogg"
    widget.load(path)
    call_names = [c[0] for c in fake_player.method_calls]
    assert call_names.index("stop") < call_names.index("setSource")


def test_player_error_shows_in_status_label(qapp):
    fake_player = MagicMock(spec=QMediaPlayer)
    widget = MediaPlayerWidget(player=fake_player)
    widget._on_error(QMediaPlayer.Error.FormatError, "codec not supported")
    assert widget.status_label.text() == "codec not supported"
