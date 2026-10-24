import socket
import struct
import time
import colorsys
import msvcrt
import os
import json

from pathlib import Path

import numpy as np
import pyaudiowpatch as pyaudio


# ============================================================
# GRUNDKONFIGURATION
# ============================================================

AWTRIX_IP = "10.10.10.10"       # <-- IP of your AWTRIX-NG
ARTNET_PORT = 6454

WIDTH = 32
HEIGHT = 8

# 1 Pixel Balken + 1 Pixel schwarzer Abstand
BAR_WIDTH = 1
COLUMN_GAP = 1

BANDS = WIDTH // (BAR_WIDTH + COLUMN_GAP)

FREQ_MIN = 25
FREQ_MAX = 14000

FFT_SIZE = 4096
CHUNK = 1024

FPS = 30


# ============================================================
# CONFIG-DATEI
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "awtrix_spectrum.conf.json"


# ============================================================
# STANDARDWERTE
# ============================================================

MODE = "smooth"

GAIN = 1.35
BASS_BOOST = 1.25
NOISE_GATE = 0.015
BRIGHTNESS = 1.0

FLOOR_DB = -70.0
CEIL_DB = -20.0

ATTACK = 0.45
DECAY = 0.075


# ============================================================
# CONFIG LADEN / SPEICHERN
# ============================================================

def load_config():
    global MODE
    global GAIN
    global BASS_BOOST
    global NOISE_GATE
    global BRIGHTNESS
    global ATTACK
    global DECAY

    if not CONFIG_FILE.exists():
        save_config()
        return

    try:
        with open(
            CONFIG_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            cfg = json.load(f)

        MODE = cfg.get(
            "mode",
            MODE
        )

        GAIN = float(
            cfg.get(
                "gain",
                GAIN
            )
        )

        BASS_BOOST = float(
            cfg.get(
                "bass_boost",
                BASS_BOOST
            )
        )

        NOISE_GATE = float(
            cfg.get(
                "noise_gate",
                NOISE_GATE
            )
        )

        BRIGHTNESS = float(
            cfg.get(
                "brightness",
                BRIGHTNESS
            )
        )

        ATTACK = float(
            cfg.get(
                "attack",
                ATTACK
            )
        )

        DECAY = float(
            cfg.get(
                "decay",
                DECAY
            )
        )

    except Exception:
        # Falls die Datei kaputt ist:
        # Standardwerte verwenden.
        pass


def save_config():

    cfg = {
        "mode": MODE,
        "gain": round(
            GAIN,
            3
        ),
        "bass_boost": round(
            BASS_BOOST,
            3
        ),
        "noise_gate": round(
            NOISE_GATE,
            4
        ),
        "brightness": round(
            BRIGHTNESS,
            3
        ),
        "attack": round(
            ATTACK,
            3
        ),
        "decay": round(
            DECAY,
            3
        )
    }

    try:
        with open(
            CONFIG_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                cfg,
                f,
                indent=4
            )

    except Exception:
        pass


# ============================================================
# ART-NET
# ============================================================

sock = socket.socket(
    socket.AF_INET,
    socket.SOCK_DGRAM
)

sequence = 1


def artdmx(
    universe,
    data,
    seq
):
    return (
        b"Art-Net\0"
        + struct.pack(
            "<H",
            0x5000
        )
        + struct.pack(
            ">H",
            14
        )
        + bytes(
            [seq, 0]
        )
        + struct.pack(
            "<H",
            universe
        )
        + struct.pack(
            ">H",
            len(data)
        )
        + bytes(data)
    )


def send_frame(pixels):
    global sequence

    flat = []

    for r, g, b in pixels:

        flat.extend((
            max(
                0,
                min(
                    255,
                    int(r)
                )
            ),
            max(
                0,
                min(
                    255,
                    int(g)
                )
            ),
            max(
                0,
                min(
                    255,
                    int(b)
                )
            )
        ))

    # Universe 0
    sock.sendto(
        artdmx(
            0,
            flat[:510],
            sequence
        ),
        (
            AWTRIX_IP,
            ARTNET_PORT
        )
    )

    # Universe 1
    sock.sendto(
        artdmx(
            1,
            flat[510:],
            sequence
        ),
        (
            AWTRIX_IP,
            ARTNET_PORT
        )
    )

    sequence += 1

    if sequence > 255:
        sequence = 1


# ============================================================
# FARBEN
# ============================================================

def color_for_position(x):

    pos = (
        x
        / max(
            1,
            WIDTH - 1
        )
    )

    # Bass: Rot -> Orange
    if pos < 0.20:

        local = pos / 0.20

        hue = (
            0.00
            + local * 0.08
        )

    # Orange -> Gelb
    elif pos < 0.40:

        local = (
            pos - 0.20
        ) / 0.20

        hue = (
            0.08
            + local * 0.08
        )

    # Gelb -> Grün/Cyan
    elif pos < 0.60:

        local = (
            pos - 0.40
        ) / 0.20

        hue = (
            0.16
            + local * 0.30
        )

    # Cyan -> Blau
    elif pos < 0.80:

        local = (
            pos - 0.60
        ) / 0.20

        hue = (
            0.46
            + local * 0.20
        )

    # Blau -> Pink
    else:

        local = (
            pos - 0.80
        ) / 0.20

        hue = (
            0.66
            + local * 0.22
        )

    r, g, b = (
        colorsys.hsv_to_rgb(
            hue,
            1.0,
            BRIGHTNESS
        )
    )

    return (
        int(r * 255),
        int(g * 255),
        int(b * 255)
    )


def rebuild_colors():

    return [
        color_for_position(
            band
            * (
                BAR_WIDTH
                + COLUMN_GAP
            )
        )
        for band
        in range(BANDS)
    ]


COLORS = []


# ============================================================
# SMOOTH RENDERER
# ============================================================

def render_smooth(levels):

    pixels = [
        (0, 0, 0)
    ] * (
        WIDTH
        * HEIGHT
    )

    for band in range(BANDS):

        x_start = (
            band
            * (
                BAR_WIDTH
                + COLUMN_GAP
            )
        )

        level = float(
            np.clip(
                levels[band],
                0.0,
                1.0
            )
        )

        level = (
            level ** 0.78
        )

        height_float = (
            level
            * HEIGHT
        )

        full_rows = int(
            height_float
        )

        fraction = (
            height_float
            - full_rows
        )

        r, g, b = (
            COLORS[band]
        )

        for x in range(
            x_start,
            min(
                x_start
                + BAR_WIDTH,
                WIDTH
            )
        ):

            for row in range(
                full_rows
            ):

                y = (
                    HEIGHT
                    - 1
                    - row
                )

                if y >= 0:

                    pixels[
                        y * WIDTH + x
                    ] = (
                        r,
                        g,
                        b
                    )

            # teilweise beleuchteter oberster Pixel
            if (
                full_rows < HEIGHT
                and fraction > 0.03
            ):

                y = (
                    HEIGHT
                    - 1
                    - full_rows
                )

                pixels[
                    y * WIDTH + x
                ] = (
                    int(
                        r * fraction
                    ),
                    int(
                        g * fraction
                    ),
                    int(
                        b * fraction
                    )
                )

    return pixels


# ============================================================
# PARTY RENDERER
# ============================================================

def render_party(levels):

    pixels = [
        (0, 0, 0)
    ] * (
        WIDTH
        * HEIGHT
    )

    for band in range(BANDS):

        x_start = (
            band
            * (
                BAR_WIDTH
                + COLUMN_GAP
            )
        )

        level = float(
            np.clip(
                levels[band],
                0.0,
                1.0
            )
        )

        # kräftige direkte Reaktion
        level = (
            level ** 0.58
        )

        height = int(
            round(
                level
                * HEIGHT
            )
        )

        height = max(
            0,
            min(
                HEIGHT,
                height
            )
        )

        r, g, b = (
            COLORS[band]
        )

        for x in range(
            x_start,
            min(
                x_start
                + BAR_WIDTH,
                WIDTH
            )
        ):

            for row in range(
                height
            ):

                y = (
                    HEIGHT
                    - 1
                    - row
                )

                pixels[
                    y * WIDTH + x
                ] = (
                    r,
                    g,
                    b
                )

    return pixels


# ============================================================
# MATRIX TEST
# ============================================================

def test_matrix():

    end = (
        time.time()
        + 2.0
    )

    while (
        time.time()
        < end
    ):

        pixels = [
            (0, 0, 0)
        ] * (
            WIDTH
            * HEIGHT
        )

        for band in range(
            BANDS
        ):

            x_start = (
                band
                * (
                    BAR_WIDTH
                    + COLUMN_GAP
                )
            )

            r, g, b = (
                COLORS[band]
            )

            for x in range(
                x_start,
                min(
                    x_start
                    + BAR_WIDTH,
                    WIDTH
                )
            ):

                for y in range(
                    HEIGHT
                ):

                    pixels[
                        y * WIDTH + x
                    ] = (
                        r,
                        g,
                        b
                    )

        send_frame(
            pixels
        )

        time.sleep(
            1 / FPS
        )


# ============================================================
# KONSOLE / MENÜ
# ============================================================

def draw_menu(
    audio_name="Initialisierung..."
):

    os.system(
        "cls"
    )

    print(
        "╔══════════════════════════════════════════════════════╗"
    )
    print(
        "║              AWTRIX MUSIC SPECTRUM                 ║"
    )
    print(
        "╠══════════════════════════════════════════════════════╣"
    )

    print(
        f"║ AWTRIX : {AWTRIX_IP:<43}║"
    )

    print(
        f"║ Audio  : {audio_name[:43]:<43}║"
    )

    print(
        "╠══════════════════════════════════════════════════════╣"
    )

    print(
        f"║ Modus       : {MODE.upper():<37}║"
    )

    print(
        f"║ Gain        : {GAIN:<6.2f}x"
        f"{'':<30}║"
    )

    print(
        f"║ Bass Boost  : {BASS_BOOST:<6.2f}x"
        f"{'':<30}║"
    )

    print(
        f"║ Noise Gate  : {NOISE_GATE:<6.3f}"
        f"{'':<31}║"
    )

    print(
        f"║ Helligkeit  : {BRIGHTNESS * 100:<6.0f}%"
        f"{'':<30}║"
    )

    print(
        f"║ Attack      : {ATTACK:<6.3f}"
        f"{'':<31}║"
    )

    print(
        f"║ Decay       : {DECAY:<6.3f}"
        f"{'':<31}║"
    )

    print(
        "╠══════════════════════════════════════════════════════╣"
    )

    print(
        "║  [1] Smooth              [2] Party                  ║"
    )

    print(
        "║  [+] Gain +              [-] Gain -                 ║"
    )

    print(
        "║  [B] Bass +              [N] Bass -                 ║"
    )

    print(
        "║  [G] Noise Gate +        [H] Noise Gate -           ║"
    )

    print(
        "║  [U] Helligkeit +        [J] Helligkeit -           ║"
    )

    print(
        "║  [A] Attack +            [Z] Attack -               ║"
    )

    print(
        "║  [D] Decay +             [C] Decay -                ║"
    )

    print(
        "║                                                      ║"
    )

    print(
        "║  [T] LED-Test            [Q] Beenden                ║"
    )

    print(
        "╠══════════════════════════════════════════════════════╣"
    )

    print(
        f"║ Config: {CONFIG_FILE.name:<43}║"
    )

    print(
        "╚══════════════════════════════════════════════════════╝"
    )


# ============================================================
# TASTATUR
# ============================================================

def handle_keyboard(
    audio_name
):
    global MODE
    global GAIN
    global BASS_BOOST
    global NOISE_GATE
    global BRIGHTNESS
    global ATTACK
    global DECAY
    global COLORS

    if not msvcrt.kbhit():
        return True

    key = (
        msvcrt
        .getwch()
        .lower()
    )

    changed = False

    # --------------------------------------------------------
    # MODE
    # --------------------------------------------------------

    if key == "1":

        MODE = "smooth"
        changed = True

    elif key == "2":

        MODE = "party"
        changed = True

    # --------------------------------------------------------
    # GAIN
    # --------------------------------------------------------

    elif key == "+":

        GAIN = min(
            5.0,
            GAIN + 0.10
        )

        changed = True

    elif key == "-":

        GAIN = max(
            0.1,
            GAIN - 0.10
        )

        changed = True

    # --------------------------------------------------------
    # BASS
    # --------------------------------------------------------

    elif key == "b":

        BASS_BOOST = min(
            3.0,
            BASS_BOOST + 0.10
        )

        changed = True

    elif key == "n":

        BASS_BOOST = max(
            0.5,
            BASS_BOOST - 0.10
        )

        changed = True

    # --------------------------------------------------------
    # NOISE GATE
    # --------------------------------------------------------

    elif key == "g":

        NOISE_GATE = min(
            0.25,
            NOISE_GATE + 0.005
        )

        changed = True

    elif key == "h":

        NOISE_GATE = max(
            0.0,
            NOISE_GATE - 0.005
        )

        changed = True

    # --------------------------------------------------------
    # HELLIGKEIT
    # --------------------------------------------------------

    elif key == "u":

        BRIGHTNESS = min(
            1.0,
            BRIGHTNESS + 0.05
        )

        COLORS = rebuild_colors()

        changed = True

    elif key == "j":

        BRIGHTNESS = max(
            0.05,
            BRIGHTNESS - 0.05
        )

        COLORS = rebuild_colors()

        changed = True

    # --------------------------------------------------------
    # ATTACK
    # --------------------------------------------------------

    elif key == "a":

        ATTACK = min(
            1.0,
            ATTACK + 0.025
        )

        changed = True

    elif key == "z":

        ATTACK = max(
            0.01,
            ATTACK - 0.025
        )

        changed = True

    # --------------------------------------------------------
    # DECAY
    # --------------------------------------------------------

    elif key == "d":

        DECAY = min(
            1.0,
            DECAY + 0.01
        )

        changed = True

    elif key == "c":

        DECAY = max(
            0.001,
            DECAY - 0.01
        )

        changed = True

    # --------------------------------------------------------
    # TEST
    # --------------------------------------------------------

    elif key == "t":

        test_matrix()

        draw_menu(
            audio_name
        )

    # --------------------------------------------------------
    # QUIT
    # --------------------------------------------------------

    elif key == "q":

        save_config()

        return False

    # --------------------------------------------------------
    # KONFIG SPEICHERN
    # --------------------------------------------------------

    if changed:

        save_config()

        draw_menu(
            audio_name
        )

    return True


# ============================================================
# AUDIO
# ============================================================

def main():
    global COLORS

    # Config vom letzten Lauf laden
    load_config()

    COLORS = rebuild_colors()

    draw_menu()

    with pyaudio.PyAudio() as p:

        device = (
            p.get_default_wasapi_loopback()
        )

        rate = int(
            device[
                "defaultSampleRate"
            ]
        )

        channels = int(
            device[
                "maxInputChannels"
            ]
        )

        audio_name = (
            device["name"]
        )

        draw_menu(
            audio_name
        )

        stream = p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            frames_per_buffer=CHUNK,
            input=True,
            input_device_index=device[
                "index"
            ]
        )

        audio_buffer = np.zeros(
            FFT_SIZE,
            dtype=np.float32
        )

        window = np.hanning(
            FFT_SIZE
        )

        frequencies = (
            np.fft.rfftfreq(
                FFT_SIZE,
                1.0 / rate
            )
        )

        # logarithmische Frequenzbänder
        band_edges = np.geomspace(
            FREQ_MIN,
            min(
                FREQ_MAX,
                rate / 2
            ),
            BANDS + 1
        )

        band_masks = []

        for band in range(
            BANDS
        ):

            low = (
                band_edges[
                    band
                ]
            )

            high = (
                band_edges[
                    band + 1
                ]
            )

            mask = (
                (
                    frequencies
                    >= low
                )
                &
                (
                    frequencies
                    < high
                )
            )

            band_masks.append(
                mask
            )

        smoothed = np.zeros(
            BANDS,
            dtype=np.float32
        )

        frame_interval = (
            1.0 / FPS
        )

        running = True

        try:

            while running:

                started = (
                    time.perf_counter()
                )

                running = (
                    handle_keyboard(
                        audio_name
                    )
                )

                if not running:
                    break

                raw = stream.read(
                    CHUNK,
                    exception_on_overflow=False
                )

                samples = (
                    np.frombuffer(
                        raw,
                        dtype=np.int16
                    )
                    .astype(
                        np.float32
                    )
                )

                samples /= (
                    32768.0
                )

                # Stereo -> Mono
                if channels > 1:

                    samples = (
                        samples.reshape(
                            -1,
                            channels
                        )
                    )

                    samples = (
                        np.mean(
                            samples,
                            axis=1
                        )
                    )

                count = len(
                    samples
                )

                # ----------------------------------------------------
                # Rolling Buffer
                # ----------------------------------------------------

                if count >= FFT_SIZE:

                    audio_buffer[:] = (
                        samples[
                            -FFT_SIZE:
                        ]
                    )

                else:

                    audio_buffer[
                        :-count
                    ] = (
                        audio_buffer[
                            count:
                        ]
                    )

                    audio_buffer[
                        -count:
                    ] = (
                        samples
                    )

                # ----------------------------------------------------
                # FFT
                # ----------------------------------------------------

                signal = (
                    audio_buffer
                    - np.mean(
                        audio_buffer
                    )
                )

                signal *= window

                fft = (
                    np.fft.rfft(
                        signal
                    )
                )

                magnitude = (
                    np.abs(
                        fft
                    )
                )

                magnitude /= max(
                    np.sum(
                        window
                    ) / 2.0,
                    1e-9
                )

                magnitude = (
                    np.maximum(
                        magnitude,
                        1e-10
                    )
                )

                db = (
                    20.0
                    * np.log10(
                        magnitude
                    )
                )

                levels = np.zeros(
                    BANDS,
                    dtype=np.float32
                )

                # ----------------------------------------------------
                # Bänder
                # ----------------------------------------------------

                for band in range(
                    BANDS
                ):

                    mask = (
                        band_masks[
                            band
                        ]
                    )

                    if not np.any(
                        mask
                    ):
                        continue

                    band_db = (
                        np.percentile(
                            db[mask],
                            82
                        )
                    )

                    level = (
                        (
                            band_db
                            - FLOOR_DB
                        )
                        /
                        (
                            CEIL_DB
                            - FLOOR_DB
                        )
                    )

                    level *= GAIN

                    # ------------------------------------------------
                    # Bass Boost
                    # ------------------------------------------------

                    bass_weight = (
                        1.0
                        - (
                            band
                            / max(
                                1,
                                BANDS - 1
                            )
                        )
                    )

                    boost = (
                        1.0
                        + (
                            BASS_BOOST
                            - 1.0
                        )
                        * (
                            bass_weight
                            ** 2
                        )
                    )

                    level *= boost

                    level = float(
                        np.clip(
                            level,
                            0.0,
                            1.0
                        )
                    )

                    if (
                        level
                        < NOISE_GATE
                    ):

                        level = 0.0

                    levels[
                        band
                    ] = level

                # ====================================================
                # SMOOTH MODE
                # ====================================================

                if MODE == "smooth":

                    for i in range(
                        BANDS
                    ):

                        target = (
                            levels[i]
                        )

                        if (
                            target
                            > smoothed[i]
                        ):

                            alpha = (
                                ATTACK
                            )

                        else:

                            alpha = (
                                DECAY
                            )

                        smoothed[i] += (
                            target
                            - smoothed[i]
                        ) * alpha

                    pixels = (
                        render_smooth(
                            smoothed
                        )
                    )

                # ====================================================
                # PARTY MODE
                # ====================================================

                else:

                    # Party:
                    # kein Attack/Decay
                    # kein Nachziehen
                    # sofortige Pixeländerung

                    smoothed[:] = (
                        levels
                    )

                    pixels = (
                        render_party(
                            levels
                        )
                    )

                send_frame(
                    pixels
                )

                # ----------------------------------------------------
                # FPS LIMIT
                # ----------------------------------------------------

                elapsed = (
                    time.perf_counter()
                    - started
                )

                remaining = (
                    frame_interval
                    - elapsed
                )

                if remaining > 0:

                    time.sleep(
                        remaining
                    )

        except KeyboardInterrupt:
            pass

        finally:

            save_config()

            stream.stop_stream()
            stream.close()

            # Matrix schwarz machen
            black = [
                (0, 0, 0)
            ] * (
                WIDTH
                * HEIGHT
            )

            send_frame(
                black
            )

            sock.close()

            os.system(
                "cls"
            )

            print(
                "AWTRIX Spectrum beendet."
            )

            print(
                f"Einstellungen gespeichert in:"
            )

            print(
                CONFIG_FILE
            )


if __name__ == "__main__":
    main()
