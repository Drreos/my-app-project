FROM python:3.11-slim

WORKDIR /app

# Копируем requirements.txt сначала для кеширования слоя
COPY requirements.txt .

# Устанавливаем зависимости (включая OpenAI для ИИ-ассистента)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

# Копируем остальные файлы приложения
COPY . .

# Запускаем бота
CMD ["python", "main.py"]