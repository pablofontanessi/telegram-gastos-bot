FROM python:3.12-slim

# Crear directorio de la app
WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el bot
COPY . .

# Fly.io no exige exponer puertos para procesos de background
CMD ["python", "bot_gastos.py"]
