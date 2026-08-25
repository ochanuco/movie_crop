import argparse
import re
import subprocess
from datetime import datetime
from pathlib import Path

import cv2
import pytesseract

TIMESTAMP_RE = re.compile(r"(\d{4})[/\-](\d{2})[/\-](\d{2})\s+(\d{2}):(\d{2}):(\d{2})")


def read_timestamp(frame, roi):
    height, width = frame.shape[:2]
    x, y, w, h = roi
    image = frame[int(height * y):int(height * (y + h)), int(width * x):int(width * (x + w))]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(binary, config="--psm 7")
    match = TIMESTAMP_RE.search(text)
    if not match:
        return None
    try:
        return datetime(*map(int, match.groups()))
    except ValueError:
        return None


def video_duration(path):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    if fps <= 0:
        raise RuntimeError("Could not determine video FPS")
    return frames / fps


def timestamp_at(cap, pts, roi):
    cap.set(cv2.CAP_PROP_POS_MSEC, pts * 1000)
    ok, frame = cap.read()
    if not ok:
        return None
    return read_timestamp(frame, roi)


def is_gap(previous_pts, previous_time, current_pts, current_time, threshold):
    if previous_time is None or current_time is None:
        return False
    video_delta = current_pts - previous_pts
    real_delta = (current_time - previous_time).total_seconds()
    return real_delta - video_delta >= threshold


def refine_boundary(cap, roi, start_pts, end_pts, threshold, fine_interval):
    previous_pts = start_pts
    previous_time = timestamp_at(cap, previous_pts, roi)
    pts = start_pts + fine_interval

    while pts <= end_pts + 1e-9:
        current_time = timestamp_at(cap, pts, roi)
        if is_gap(previous_pts, previous_time, pts, current_time, threshold):
            return pts
        if current_time is not None:
            previous_pts = pts
            previous_time = current_time
        pts += fine_interval

    return end_pts


def find_boundaries(path, roi, scan_interval, fine_interval, threshold):
    duration = video_duration(path)
    cap = cv2.VideoCapture(str(path))
    boundaries = [0.0]

    previous_pts = 0.0
    previous_time = timestamp_at(cap, previous_pts, roi)
    pts = scan_interval

    while pts < duration:
        current_time = timestamp_at(cap, pts, roi)

        if is_gap(previous_pts, previous_time, pts, current_time, threshold):
            boundary = refine_boundary(
                cap,
                roi,
                previous_pts,
                pts,
                threshold,
                fine_interval,
            )
            if boundary - boundaries[-1] > fine_interval:
                boundaries.append(boundary)
                print(f"gap detected: split at {boundary:.3f}s")

        if current_time is not None:
            previous_pts = pts
            previous_time = current_time

        pts += scan_interval

    cap.release()
    boundaries.append(duration)
    return boundaries


def split_video(path, boundaries, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)

    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]), 1):
        output = output_dir / f"recording_{index:03d}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{start:.6f}",
                "-i",
                str(path),
                "-t",
                f"{end - start:.6f}",
                "-map",
                "0",
                "-c",
                "copy",
                str(output),
            ],
            check=True,
        )
        print(f"written: {output} ({start:.3f}s -> {end:.3f}s)")


def main():
    parser = argparse.ArgumentParser(
        description="Split concatenated recordings when the burned-in timestamp jumps forward."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--scan-interval", type=float, default=1.0)
    parser.add_argument("--fine-interval", type=float, default=0.1)
    parser.add_argument("--gap-threshold", type=float, default=3.0)
    parser.add_argument("--roi", default="0.0,0.0,0.35,0.15")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    roi = tuple(map(float, args.roi.split(",")))
    if len(roi) != 4:
        parser.error("--roi must be x,y,width,height")
    if args.scan_interval <= 0 or args.fine_interval <= 0:
        parser.error("scan intervals must be greater than 0")
    if args.fine_interval > args.scan_interval:
        parser.error("--fine-interval must be less than or equal to --scan-interval")

    output_dir = args.output_dir or args.input.with_name(f"{args.input.stem}_split")
    boundaries = find_boundaries(
        args.input,
        roi,
        args.scan_interval,
        args.fine_interval,
        args.gap_threshold,
    )
    split_video(args.input, boundaries, output_dir)


if __name__ == "__main__":
    main()
