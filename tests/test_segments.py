from whisper_gui.segments import Segment, segment_at, segments_to_srt, parse_srt


def test_segments_to_srt_formats_two_lines():
    segs = [
        Segment(start_ms=0, end_ms=3420, text="Hola mundo"),
        Segment(start_ms=3420, end_ms=5100, text="Segunda linea"),
    ]
    srt = segments_to_srt(segs)
    assert srt == (
        "1\n00:00:00,000 --> 00:00:03,420\nHola mundo\n\n"
        "2\n00:00:03,420 --> 00:00:05,100\nSegunda linea\n\n"
    )


def test_parse_srt_round_trips_segments_to_srt_output():
    segs = [
        Segment(start_ms=0, end_ms=3420, text="Hola mundo"),
        Segment(start_ms=3420, end_ms=5100, text="Segunda linea"),
    ]
    assert parse_srt(segments_to_srt(segs)) == segs


def test_segment_at_returns_index_of_containing_segment():
    segs = [
        Segment(start_ms=0, end_ms=3420, text="a"),
        Segment(start_ms=3420, end_ms=5100, text="b"),
    ]
    assert segment_at(segs, 1000) == 0
    assert segment_at(segs, 3420) == 1
    assert segment_at(segs, 5099) == 1


def test_segment_at_returns_none_outside_all_segments():
    segs = [Segment(start_ms=1000, end_ms=2000, text="a")]
    assert segment_at(segs, 500) is None
    assert segment_at(segs, 2000) is None
