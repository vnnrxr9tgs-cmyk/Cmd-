from flask import Flask, Response, render_template, stream_with_context
import subprocess
import signal

app = Flask(__name__)

FFMPEG_COMMAND = [
    'ffmpeg',
    '-f', 'dshow',
    '-rtbufsize', '3M',
    #ffmpeg -list_devices true -f dshow -i dummy
    '-i', 'audio=Стерео микшер (IDT High Definition Audio CODEC)',  # Корректное имя устройства
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
        stderr=None,  # Можно выводить ошибки отдельно
        bufsize=10**6
    )

@app.route('/stream')
def stream_audio():
    process = run_ffmpeg_process()

    def generate():
        try:
            while True:
                data = process.stdout.read(4096)  # Считывать небольшими порциями
                if not data:
                    break
                yield data
        except GeneratorExit:
            pass
        finally:
            # Останавливаем процесс плавно сначала
            process.terminate()
            try:
                process.wait(timeout=5)  # Ждать завершение в течение 5 секунд
            except subprocess.TimeoutExpired:
                process.kill()  # Принудительно завершить, если не вышло дождаться
            process.stdout.close()

    headers = {
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Accept-Ranges': 'bytes'
    }

    return Response(stream_with_context(generate()), mimetype='audio/mpeg', headers=headers)

@app.route('/')
def index():
    return render_template('index.html')  # Использовать существующий шаблон

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)