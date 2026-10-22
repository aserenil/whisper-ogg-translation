from whisper_gui.segments import Segment
from whisper_gui.timed_transcript_panel import TimedTranscriptPanel


def _segs():
    return [
        Segment(start_ms=0, end_ms=1000, text="Hola"),
        Segment(start_ms=1000, end_ms=2000, text="Mundo"),
    ]


def test_set_segments_then_update_position_highlights_matching_row(qapp):
    panel = TimedTranscriptPanel()
    panel.set_segments(_segs())
    panel.update_position(1500)
    assert panel.list_widget.currentRow() == 1


def test_update_position_outside_any_segment_clears_highlight(qapp):
    panel = TimedTranscriptPanel()
    panel.set_segments(_segs())
    panel.update_position(1500)
    panel.update_position(50000)
    assert panel.list_widget.currentRow() == -1


def test_clicking_a_line_emits_seek_requested_and_line_activated(qapp):
    panel = TimedTranscriptPanel()
    panel.set_segments(_segs())
    seeks = []
    activations = []
    panel.seek_requested.connect(seeks.append)
    panel.line_activated.connect(lambda s, e: activations.append((s, e)))
    panel._on_item_clicked(panel.list_widget.item(1))
    assert seeks == [1000]
    assert activations == [(1000, 2000)]


def test_set_plain_text_shows_note_and_ignores_update_position(qapp):
    panel = TimedTranscriptPanel()
    panel.set_plain_text("some text without timing")
    panel.update_position(500)
    assert panel.list_widget.currentRow() == -1
