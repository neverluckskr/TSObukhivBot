# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код приложения
COPY . .

# Создаем директорию для логов и данных
RUN mkdir -p /app/logs /data

# Устанавливаем права на запись для /data (для SQLite на volume)
RUN chmod 777 /data

# Запускаем бота
CMD ["python", "bot.py"]

