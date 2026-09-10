"""Compatibility adapter using the common strict segment loader."""
from coding_validation_common import load_segments

def read_segments_from_csv(csv_path: str) -> tuple[list[dict], dict]:
    segments = load_segments(csv_path)
    return ([{"SegmentID": s.segment_id, "text": s.text, "person": s.person} for s in segments],
            {s.segment_id: s.text for s in segments})
