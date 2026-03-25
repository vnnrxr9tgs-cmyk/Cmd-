import asyncio
import json
import psutil
import time

TOKEN = "12345"
PORT = 9000

def format_uptime(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02}"

async def handle_client(reader, writer):
    try:
        data = await reader.readline()
        cmd = json.loads(data.decode("utf-8", errors="ignore").strip())

        if cmd.get("token") != TOKEN:
            resp = {"error": "Неверный токен"}

        else:
            action = cmd.get("cmd")
            monitor_list = cmd.get("processes", [])

            if action == "list":
                processes = {}

                for proc in psutil.process_iter(['pid', 'name', 'create_time']):
                    try:
                        name = proc.info['name']
                        if not name:
                            continue

                        if monitor_list and name.lower() not in [p.lower() for p in monitor_list]:
                            continue

                        uptime_sec = time.time() - proc.info['create_time']

                        entry = {
                            "pid": proc.info['pid'],
                            "uptime": format_uptime(uptime_sec)
                        }

                        processes.setdefault(name, []).append(entry)

                    except Exception:
                        continue

                resp = {"processes": processes}

            elif action == "kill_by_pid":
                pid = cmd.get("pid")
                try:
                    proc = psutil.Process(pid)
                    proc.kill()
                    resp = {"status": "success", "killed": 1}
                except Exception as e:
                    resp = {"error": str(e)}

            else:
                resp = {"error": "Неизвестная команда"}

        writer.write((json.dumps(resp) + "\n").encode("utf-8"))
        await writer.drain()

    except Exception as e:
        try:
            writer.write((json.dumps({"error": str(e)}) + "\n").encode("utf-8"))
            await writer.drain()
        except:
            pass

    finally:
        writer.close()
        await writer.wait_closed()

async def main():
    server = await asyncio.start_server(handle_client, "0.0.0.0", PORT)
    print(f"Agent started on port {PORT}")

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())