# Скрипт для интерактивного ввода пароля, проверки прокси и запуска Python exe с использованием прокси
#Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# Жестко заданные значения (измените на свои)
$proxyUri = "http://proxy.example.com:8080"  # Адрес прокси-сервера
$userName = "your_username"  # Имя пользователя для прокси

# Запрос пароля у пользователя (вводится скрытно)
$password = Read-Host -Prompt "Введите пароль для прокси-сервера" -AsSecureString

# Создаем объект учетных данных
$credential = New-Object System.Management.Automation.PSCredential ($userName, $password)

# 2. Попытка подключения и выполнения тестового веб-запроса

$testUri = "http://google.com/"
Write-Host "Пытаюсь выполнить тестовый запрос к $testUri через прокси $proxyUri..." -ForegroundColor Cyan

try {
    # Используем Invoke-WebRequest с явным указанием прокси и учетных данных
    $response = Invoke-WebRequest -Uri $testUri -Proxy $proxyUri -ProxyCredential $credential -UseBasicParsing -TimeoutSec 10
    
    Write-Host "✅ Подключение через прокси успешно!" -ForegroundColor Green
    Write-Host "Статус ответа: $($response.StatusCode) $($response.StatusDescription)" -ForegroundColor Green
    
} catch [System.Net.WebException] {
    # Если прокси недоступен, неверные учетные данные, бан или другие сетевые ошибки
    Write-Error "❌ Ошибка подключения к прокси или доступа к сайту."
    Write-Error "Сообщение об ошибке: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        Write-Error "Статус ответа сервера: $($_.Exception.Response.StatusCode) $($_.Exception.Response.StatusDescription)"
    }
    exit  # Выход из скрипта при ошибке
} catch {
    # Обработка других возможных ошибок PowerShell
    Write-Error "❌ Произошла непредвиденная ошибка: $($_.Exception.Message)"
    exit  # Выход из скрипта при ошибке
}

# 3. Установка прокси по умолчанию для текущей сессии PowerShell и переменных окружения для Python

Write-Host "`nУстановка глобальных настроек прокси для текущей сессии..." -ForegroundColor Yellow

# Устанавливаем прокси по умолчанию для всех последующих Invoke-WebRequest/Invoke-RestMethod в этой сессии
[System.Net.WebRequest]::DefaultWebProxy = New-Object System.Net.WebProxy($proxyUri)
[System.Net.WebRequest]::DefaultWebProxy.Credentials = $credential

# Устанавливаем переменные окружения для HTTP/HTTPS прокси (с учетными данными), чтобы Python (requests) их использовал
$proxyWithCred = "http://$($credential.UserName):$($credential.GetNetworkCredential().Password)@$($proxyUri -replace '^http://', '')"
$env:HTTP_PROXY = $proxyWithCred
$env:HTTPS_PROXY = $proxyWithCred

Write-Host "Глобальные настройки прокси обновлены." -ForegroundColor Green
Write-Host "Переменные окружения HTTP_PROXY и HTTPS_PROXY установлены для использования в Python." -ForegroundColor Green

# 4. Запуск Python exe (предполагаем, что exe называется rss_parser.exe и находится в той же директории)
$exePath = Join-Path -Path $PSScriptRoot -ChildPath "parshabr.exe"
if (Test-Path $exePath) {
    Write-Host "`nЗапускаю Python exe: $exePath" -ForegroundColor Cyan
    try {
        & $exePath
        Write-Host "✅ Python exe выполнен успешно." -ForegroundColor Green
    } catch {
        Write-Error "❌ Ошибка при запуске Python exe: $($_.Exception.Message)"
    }
} else {
    Write-Error "❌ Файл $exePath не найден. Убедитесь, что exe находится в той же директории, что и скрипт."
}