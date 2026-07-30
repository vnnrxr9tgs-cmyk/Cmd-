"""
АУДИОМОДЕМ QPSK — ТОЛЬКО ОДНА МОДУЛЯЦИЯ
python modem.py encode файл вывод.wav
python modem.py decode ввод.wav вывод.файл
"""

import struct
import wave
import os
import sys
import zlib
import math

# ============================================================
# НАСТРОЙКИ (ТОЛЬКО QPSK)
# ============================================================
SAMPLE_RATE = 8000
SYMBOLS_PER_SECOND = 4000
CARRIER_FREQ = 2000
SILENCE_DURATION = 1.0
SYNC_PATTERN = b'\xAA\x55\xAA\x55'
SYNC_REPEATS = 8

# QPSK: 2 бита на символ, 4 фазы
BITS_PER_SYMBOL = 2
PHASES = [315, 225, 135, 45]  # QPSK созвездие
SYNC_PHASES = [0, 180]        # Синхро BPSK

SAMPLES_PER_SYMBOL = SAMPLE_RATE // SYMBOLS_PER_SECOND  # 8
SYNC_BYTES = len(SYNC_PATTERN) * SYNC_REPEATS           # 32
SYNC_BITS = SYNC_BYTES * 8                              # 256
SYNC_SAMPLES = SYNC_BITS * SAMPLES_PER_SYMBOL           # 2048
BYTES_PER_SECOND = SYMBOLS_PER_SECOND * BITS_PER_SYMBOL // 8  # 250

print(f"⚙️  QPSK, {SYMBOLS_PER_SECOND} симв/сек, {SAMPLES_PER_SYMBOL} спс")
print(f"⚙️  Скорость: {BYTES_PER_SECOND} байт/сек")
print(f"📏 Синхро: {SYNC_BYTES} байт = {SYNC_SAMPLES} сэмплов")


# ============================================================
# СИГНАЛЫ
# ============================================================

def make_symbol(phase_deg):
    """Создаёт один символ (8 сэмплов) с фазой phase_deg"""
    n = SAMPLES_PER_SYMBOL
    r = math.radians(phase_deg)
    return [int(16000 * math.cos(2 * math.pi * CARRIER_FREQ * i / SAMPLE_RATE + r)) for i in range(n)]


def make_sync():
    """Синхросигнал BPSK: 0° и 180°"""
    samples = []
    for _ in range(SYNC_REPEATS):
        for byte in SYNC_PATTERN:
            for bit_pos in range(8):
                phase = SYNC_PHASES[(byte >> bit_pos) & 1]
                samples.extend(make_symbol(phase))
    return samples


def make_silence(sec):
    return [0] * int(SAMPLE_RATE * sec)


# ============================================================
# КОДЕР
# ============================================================

def encode_file(input_file, output_wav):
    print("=" * 60)
    print("КОДИРОВАНИЕ QPSK")
    print("=" * 60)
    print(f"📁 {input_file} → {output_wav}")

    with open(input_file, 'rb') as f:
        data = f.read()

    size = len(data)
    crc = zlib.crc32(data) & 0xFFFFFFFF

    print(f"📏 {size:,} байт, CRC={crc:08X}")

    # Заголовок: CRC(4) + размер(8) = 12 байт
    header = struct.pack('<IQ', crc, size)
    packet = header + data

    # Модуляция
    samples = []
    bits_buf = []

    for byte in packet:
        for bp in range(8):
            bits_buf.append((byte >> bp) & 1)
            while len(bits_buf) >= 2:
                idx = (bits_buf[0] << 1) | bits_buf[1]
                samples.extend(make_symbol(PHASES[idx]))
                bits_buf = bits_buf[2:]

    if bits_buf:
        bits_buf.append(0)
        idx = (bits_buf[0] << 1) | bits_buf[1]
        samples.extend(make_symbol(PHASES[idx]))

    actual_duration = len(samples) / SAMPLE_RATE
    print(f"⏱️  Данные: {actual_duration:.1f} сек")

    # Собираем WAV
    wav_samples = []
    wav_samples.extend(make_silence(SILENCE_DURATION))
    wav_samples.extend(make_sync())
    wav_samples.extend(make_silence(0.1))
    wav_samples.extend(samples)
    wav_samples.extend(make_silence(SILENCE_DURATION))

    total_duration = len(wav_samples) / SAMPLE_RATE
    print(f"⏱️  Всего: {total_duration:.1f} сек")

    with wave.open(output_wav, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(struct.pack(f'<{len(wav_samples)}h', *wav_samples))

    print(f"✅ {output_wav} ({os.path.getsize(output_wav):,} байт)")
    return output_wav


# ============================================================
# ДЕКОДЕР
# ============================================================

def detect_phase(chunk):
    """Определяет фазу символа (когерентный детектор).
    Сигнал = cos(ωt + φ) → I ~ cosφ, Q нужно с минусом sin,
    иначе фаза получается инвертированной (atan2 даёт −φ).
    """
    I = Q = 0.0
    for i, s in enumerate(chunk):
        t = i / SAMPLE_RATE
        I += s * math.cos(2 * math.pi * CARRIER_FREQ * t)
        Q += s * (-math.sin(2 * math.pi * CARRIER_FREQ * t))  # знак критичен!
    deg = math.degrees(math.atan2(Q, I)) % 360

    # Ищем ближайшую QPSK фазу
    best = 0
    best_dist = 999.0
    for idx, p in enumerate(PHASES):
        d = min(abs(deg - p), 360 - abs(deg - p))
        if d < best_dist:
            best_dist = d
            best = idx
    return best  # 0, 1, 2 или 3


def decode_bytes(samples, start, n_bytes):
    """Декодирует n_bytes байт начиная с позиции start"""
    pos = start
    result = bytearray()
    bits = []  # очередь бит (старший бит символа первым)

    for _ in range(n_bytes):
        byte = 0
        for bp in range(8):
            # Нужен хотя бы один бит; если остался 1 — не затираем его
            while len(bits) < 1:
                if pos + SAMPLES_PER_SYMBOL > len(samples):
                    return None
                idx = detect_phase(samples[pos:pos + SAMPLES_PER_SYMBOL])
                bits.extend([(idx >> 1) & 1, idx & 1])
                pos += SAMPLES_PER_SYMBOL

            if bits.pop(0):
                byte |= (1 << bp)

        result.append(byte)

    return bytes(result), pos


def decode_file(input_wav, output_file):
    print("=" * 60)
    print("ДЕКОДИРОВАНИЕ QPSK")
    print("=" * 60)
    print(f"🎵 {input_wav} → {output_file}")

    if not os.path.exists(input_wav):
        print("❌ Файл не найден!")
        return None

    with wave.open(input_wav, 'r') as w:
        frames = w.readframes(w.getnframes())

    samples = list(struct.unpack(f'<{len(frames) // 2}h', frames))
    print(f"📊 {len(samples):,} сэмплов, {len(samples) / SAMPLE_RATE:.1f} сек")

    mx = max(abs(s) for s in samples)
    if mx > 32000:
        samples = [int(s * 16000 / mx) for s in samples]
    elif mx < 8000 and mx > 0:
        samples = [int(s * 16000 / mx) for s in samples]

    # Ищем начало сигнала по энергии
    sig_start = 0
    for i in range(0, len(samples) - 100, 10):
        if sum(abs(s) for s in samples[i:i + 50]) / 50 > 5000:
            sig_start = i
            break

    print(f"📡 Сигнал: сэмпл {sig_start}")

    # Поиск начала данных после синхро + паузы
    guard_samples = int(0.1 * SAMPLE_RATE)
    search_start = sig_start + SYNC_SAMPLES + guard_samples
    search_end = search_start + 200

    print(f"🔍 Поиск данных: {search_start} → {search_end}")

    found = False
    for data_start in range(search_start, search_end):
        res = decode_bytes(samples, data_start, 12)
        if res is None:
            continue

        header, pos = res
        try:
            crc, size = struct.unpack('<IQ', header)
        except Exception:
            continue

        # Реалистичный размер
        if 10 < size < 10_000_000:
            print(f"   Кандидат: сэмпл {data_start}, размер={size:,}, CRC={crc:08X}")

            res2 = decode_bytes(samples, pos, size)
            if res2 is None:
                continue

            data, _ = res2
            crc2 = zlib.crc32(data) & 0xFFFFFFFF

            if crc == crc2:
                print(f"✅ НАЙДЕНО! сэмпл {data_start}, размер={size:,}, CRC OK!")
                with open(output_file, 'wb') as f:
                    f.write(data)
                print(f"💾 {output_file}")
                found = True
                break

    if not found:
        print("\n❌ Данные не найдены!")
        return None

    return output_file


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("АУДИОМОДЕМ QPSK")
    print("=" * 60)

    if len(sys.argv) < 3:
        print("\nИспользование:")
        print("  python modem.py encode <файл> [выход.wav]")
        print("  python modem.py decode <вход.wav> [выход.файл]")
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode in ['encode', 'e']:
        encode_file(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else sys.argv[2] + ".wav")
    elif mode in ['decode', 'd']:
        result = decode_file(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "output.bin")
        print(f"\n{'✅ Успешно!' if result else '❌ Ошибка!'}")
    else:
        print(f"❌ Неизвестный режим: {mode}")