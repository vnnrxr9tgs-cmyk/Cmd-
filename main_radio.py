from flask import Flask, Response, render_template, stream_with_context
import subprocess
import signal

app = Flask(__name__)

# ВАЖНО: Правильный синтаксис - audio= перед именем устройства
# Имя должно быть точно таким, как в выводе FFmpeg
MICROPHONE_NAME = "Onboard MIC (Технология Intel® Smart Sound для цифровых микрофонов)"

FFMPEG_COMMAND = [
    'ffmpeg',
    '-f', 'dshow',
    '-rtbufsize', '3M',
    '-i', f'audio={MICROPHONE_NAME}',  # КЛЮЧЕВОЙ МОМЕНТ: audio= перед именем
    '-ac', '1',
    '-ar', '44100',
    '-f', 'mp3',
    '-b:a', '192k',
    '-'
]


def run_ffmpeg_process():
    """Запустить FFmpeg-процесс."""
    return subprocess.Popen(
        FFMPEG_COMMAND,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,  # Захватываем stderr для отладки
        bufsize=10 ** 6
    )


@app.route('/stream')
def stream_audio():
    process = run_ffmpeg_process()

    # Опционально: выводим ошибки FFmpeg в консоль для отладки
    import threading
    def log_errors():
        while True:
            error = process.stderr.readline()
            if error:
                print(f"[FFmpeg] {error.decode('utf-8', errors='ignore').strip()}")
            else:
                break

    error_thread = threading.Thread(target=log_errors, daemon=True)
    error_thread.start()

    def generate():
        try:
            while True:
                data = process.stdout.read(4096)
                if not data:
                    break
                yield data
        except GeneratorExit:
            pass
        finally:
            # Останавливаем процесс
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            process.stdout.close()
            process.stderr.close()

    headers = {
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Accept-Ranges': 'bytes'
    }

    return Response(stream_with_context(generate()), mimetype='audio/mpeg', headers=headers)


@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
