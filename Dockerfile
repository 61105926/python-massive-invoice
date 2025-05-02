FROM python:3

# Instala dependencias del sistema para Chromium y el WebDriver
RUN apt-get update && apt-get install -y wget gnupg unzip && \
    wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt install -y ./google-chrome-stable_current_amd64.deb && \
    rm google-chrome-stable_current_amd64.deb

WORKDIR /usr/src/app

# Copia el archivo requirements.txt e instala las dependencias de Python
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del proyecto
COPY . .

# Exponer el puerto
EXPOSE 5001

CMD ["python", "app.py"]
