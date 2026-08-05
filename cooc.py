import browser_cookie3
from http.cookiejar import Cookie


def get_local_cookies(domain='127.0.0.1', port='5000'):
    """
    Получает cookies для локального сервера
    domain: 127.0.0.1 или localhost
    """
    try:
        # Пробуем разные варианты
        domains = [
            '127.0.0.1',
            'localhost',
            f'127.0.0.1:{port}',
            f'localhost:{port}',
        ]

        all_cookies = []
        for d in domains:
            try:
                cj = browser_cookie3.firefox(domain_name=d)
                if len(cj) > 0:
                    print(f"✅ Найдены cookies для {d}")
                    all_cookies.extend(cj)
            except:
                pass

        return all_cookies

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return []


# Получаем cookies
cookies = get_local_cookies()

if cookies:
    print(f"\n🍪 Найдено {len(cookies)} cookies")
    print("=" * 60)
    for cookie in cookies:
        print(f"{cookie.name:20} = {cookie.value[:50]}...")
else:
    print("\n❌ Cookies не найдены!")
    print("\nВозможные причины:")
    print("1. Вы не заходили на http://127.0.0.1:5000 в Firefox")
    print("2. Сервер не установил cookies")
    print("3. Cookies для локального домена не сохраняются")
#####
import browser_cookie3
import sys


def get_chrome_cookie(cookie_name, domain='127.0.0.1'):
    """
    Получает cookie из Chrome
    Работает с Chrome версии 126 и ниже
    """
    try:
        # Пробуем разные домены
        domains = [
            domain,
            'localhost',
            '127.0.0.1',
            'localhost:5000',
            '127.0.0.1:5000',
        ]

        for d in domains:
            try:
                cj = browser_cookie3.chrome(domain_name=d)
                if cj:
                    for cookie in cj:
                        if cookie.name == cookie_name:
                            return cookie.value
            except:
                continue

        return None

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None


# Использование
session = get_chrome_cookie('session')
if session:
    print(f"✅ session = {session}")

    # Сохраняем
    with open('session_cookie.txt', 'w') as f:
        f.write(session)
    print("💾 Сохранено в session_cookie.txt")
else:
    print("❌ Cookie не найден")
    print("\nПроверьте:")
    print("1. Вы зашли на http://127.0.0.1:5000 в Chrome")
    print("2. Chrome версии 126 или ниже")
    print("3. Chrome закрыт")
######
import browser_cookie3
import os
import webbrowser


def get_cookie_from_chrome(cookie_name='session', domain='127.0.0.1'):
    """
    Пытается получить cookie из Chrome
    Работает с версиями до 126 включительно
    """
    try:
        print(f"🔍 Ищем cookie '{cookie_name}' для {domain}")

        # Закрываем Chrome если открыт
        print("⚠️ Убедитесь, что Chrome закрыт!")
        input("Нажмите Enter, если Chrome закрыт...")

        # Пробуем загрузить
        cj = browser_cookie3.chrome(domain_name=domain)

        # Ищем нужный cookie
        for cookie in cj:
            if cookie.name == cookie_name:
                print(f"✅ Найден: {cookie_name}")
                return cookie.value

        print(f"❌ Cookie '{cookie_name}' не найден")
        return None

    except Exception as e:
        print(f"❌ Ошибка: {e}")

        if "Unable to get key for cookie decryption" in str(e):
            print("\n⚠️ Ваш Chrome обновлен до версии 127+")
            print("   browser-cookie3 НЕ РАБОТАЕТ с новым шифрованием!")
            print("\n👉 Решения:")
            print("   1. Используйте Firefox")
            print("   2. Используйте Selenium")
            print("   3. Скачайте старую версию Chrome (не рекомендуется)")

        return None


# Запуск
if __name__ == "__main__":
    cookie = get_cookie_from_chrome('session', '127.0.0.1')

    if cookie:
        print(f"\n🍪 {cookie}")
        with open('chrome_cookie.txt', 'w') as f:
            f.write(cookie)
        print("💾 Сохранено в chrome_cookie.txt")