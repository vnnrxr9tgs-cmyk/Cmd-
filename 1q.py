import soundfile as sf
import numpy as np
from scipy.signal import resample
import os
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('audio_processing.log'),  # Лог в файл
        logging.StreamHandler()  # Лог в консоль
    ]
)

TARGET_SR = 9600
TARGET_SUBTYPE = "PCM_16"


def process_file(path, out_dir):
    try:
        data, sr = sf.read(path)
        info = sf.info(path)

        # Проверка на пустой файл
        if len(data) == 0:
            logging.warning(f"Файл {os.path.basename(path)} пустой, пропускаю.")
            return False

        logging.info(f"Обработка файла: {os.path.basename(path)}")
        logging.info(f"  Каналы: {info.channels}")
        logging.info(f"  Частота: {sr} Гц")
        logging.info(f"  Битность: {info.subtype}")

        # Стерео → моно
        if info.channels > 1:
            data = np.mean(data, axis=1)

        # Ресемплинг
        if sr != TARGET_SR:
            new_len = int(len(data) * TARGET_SR / sr)
            data = resample(data, new_len)

        # Расчет длительности и SNR
        duration = len(data) / TARGET_SR  # Длительность в секундах
        if np.std(data) > 0:  # Избегать деления на ноль
            snr = 20 * np.log10(np.max(np.abs(data)) / np.std(data))
        else:
            snr = float('inf')  # Если сигнал постоянный (без шума)

        logging.info(f"  Длительность: {duration:.2f} сек")
        logging.info(f"  SNR: {snr:.2f} dB")

        out_path = os.path.join(
            out_dir,
            os.path.splitext(os.path.basename(path))[0] + "_9600.wav"
        )

        sf.write(out_path, data, TARGET_SR, subtype=TARGET_SUBTYPE)
        logging.info("  Файл успешно обработан и сохранен.")
        return True  # Успешно обработан

    except Exception as e:
        logging.error(f"Ошибка при обработке файла {os.path.basename(path)}: {str(e)}")
        return False  # Не удалось обработать


def main():
    # Фиксированный путь к входной папке (замените на свой)
    in_dir = "out"  # Пример: "/home/user/audio_files"

    # Фиксированный путь к выходной папке (замените на свой, например, "/home/user/output_audio")
    out_dir = "ou2t"  # Пример: "/home/user/converted_audio"

    if not os.path.isdir(in_dir):
        logging.error("Указанная входная папка не существует")
        return

    os.makedirs(out_dir, exist_ok=True)  # Создаем выходную папку, если не существует

    files = [f for f in os.listdir(in_dir) if f.lower().endswith(".wav")]

    if not files:
        logging.warning("В папке нет WAV-файлов")
        return

    logging.info(f"Найдено файлов: {len(files)}")

    processed_count = 0
    for f in files:
        path = os.path.join(in_dir, f)
        if process_file(path, out_dir):
            # Удаляем файл из исходной директории только после успешной обработки
            try:
                os.remove(path)
                logging.info(f"  Исходный файл {f} удален.")
                processed_count += 1
            except Exception as e:
                logging.error(f"Не удалось удалить файл {f}: {str(e)}")

    logging.info(f"\nОбработано и удалено файлов: {processed_count}")
    logging.info(f"Результат в папке: {out_dir}")


if __name__ == "__main__":
    main()