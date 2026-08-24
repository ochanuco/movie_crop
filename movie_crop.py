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
    image = frame[int(height*y):int(height*(y+h)), int(width*x):int(width*(x+w))]
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


def find_boundaries(path, roi, interval, threshold):
    duration = video_duration(path)
    cap = cv2.VideoCapture(str(path))
    boundaries = [0.0]
    previous_pts = previous_time = None
    pts = 0.0

    while pts < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, pts * 1000)
        ok, frame = cap.read()
        if ok:
            timestamp = read_timestamp(frame, roi)
            if timestamp is not None and previous_time is not None:
                video_delta = pts - previous_pts
                real_delta = (timestamp - previous_time).total_seconds()
                stopped_for = real_delta - video_delta
                if stopped_for >= threshold:
                    boundaries.append(pts)
                    print(f"gap at {pts:.3f}s: recording stopped for about {stopped_for:.1f}s")
            if timestamp is not None:
                previous_pts, previous_time = pts, timestamp
        pts += interval

    cap.release()
    boundaries.append(duration)
    return boundaries


def split_video(path, boundaries, output_dir, reencode):
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]), 1):
        output = output_dir / f"recording_{index:03d}.mp4"
        command = ["ffmpeg", "-y", "-ss", str(start), "-i", str(path), "-t", str(end-start), "-map", "0"]
        command += ["-c:v", "libx264", "-c:a", "aac"] if reencode else ["-c", "copy"]
        subprocess.run(command + [str(output)], check=True)
        print(f"written: {output}")


def main():
    parser = argparse.ArgumentParser(description="Split concatenated recordings when the burned-in timestamp jumps forward.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--scan-interval", type=float, default=1.0)
    parser.add_argument("--gap-threshold", type=float, default=3.0)
    parser.add_argument("--roi", default="0.65,0.85,0.35,0.15")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--reencode", action="store_true")
    args = parser.parse_args()

    roi = tuple(map(float, args.roi.split(",")))
    if len(roi) != 4:
        parser.error("--roi must be x,y,width,height")

    output_dir = args.output_dir or args.input.with_name(f"{args.input.stem}_split")
    boundaries = find_boundaries(args.input, roi, args.scan_interval, args.gap_threshold)
    split_video(args.input, boundaries, output_dir, args.reencode)


if __name__ == "__main__":
    main()
