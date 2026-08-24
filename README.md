# movie_crop

結合済みの録画動画を、映像左上に焼き込まれた実日時の不連続から検出して、録画停止・再開ごとの MP4 に分割します。

想定している入力は次の状態です。

```text
実時間:       録画1 -> 停止 -> 録画2 -> 停止 -> 録画3
入力MP4:      録画1 --------> 録画2 --------> 録画3
出力:         recording_001.mp4
              recording_002.mp4
              recording_003.mp4
```

動画上の経過時間に対して焼き込み時計が大きく進んだ地点を、録画停止からの再開地点として扱います。

## Requirements

- Python 3.10+
- FFmpeg
- Tesseract OCR

Python dependencies:

- OpenCV
- pytesseract

## Setup

### macOS

```bash
brew install ffmpeg tesseract

git clone git@github.com:ochanuco/movie_crop.git
cd movie_crop

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install ffmpeg tesseract-ocr python3-venv

git clone git@github.com:ochanuco/movie_crop.git
cd movie_crop

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python movie_crop.py input.mp4
```

デフォルトでは `input_split/` に以下のように出力します。

```text
input_split/
├── recording_001.mp4
├── recording_002.mp4
└── recording_003.mp4
```

## Timestamp ROI

OCR対象はデフォルトで左上付近です。

```text
--roi x,y,width,height
```

値は動画サイズに対する 0.0〜1.0 の比率です。

デフォルト:

```bash
--roi 0.0,0.0,0.35,0.15
```

日時表示位置や余白に合わせて調整してください。

```bash
python movie_crop.py input.mp4 --roi 0.02,0.02,0.30,0.10
```

認識対象の日時フォーマットは現在以下を想定しています。

```text
2026/08/24 18:32:15
2026-08-24 18:32:15
```

## Gap detection

デフォルトでは1秒ごとにOCRします。

```bash
python movie_crop.py input.mp4 --scan-interval 1
```

動画時間と実時間の差が3秒以上になった場合、録画停止があったと判定します。

```bash
python movie_crop.py input.mp4 --gap-threshold 3
```

例えば動画上では1秒しか進んでいないのに、焼き込み時計が31秒進んでいれば、およそ30秒間録画が停止していたと判定します。

## Accurate cuts

通常は高速な stream copy を使用します。

```bash
python movie_crop.py input.mp4
```

MP4のキーフレーム位置によって分割位置にズレが出る場合は再エンコードできます。

```bash
python movie_crop.py input.mp4 --reencode
```

再エンコードは遅くなりますが、分割位置をより正確にできます。

## Notes

OCRが失敗したフレームはスキップします。日時表示の背景やフォントによって認識精度が低い場合は、まず `--roi` を日時部分だけに絞るのが有効です。

現在の境界検出精度は `--scan-interval` に依存します。1秒指定の場合、停止・再開位置は概ね1秒単位です。境界をより正確にしたい場合は値を小さくできます。

```bash
python movie_crop.py input.mp4 --scan-interval 0.25 --reencode
```
