FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org aiogram asyncpg python-dotenv

CMD ["python", "main.py"]