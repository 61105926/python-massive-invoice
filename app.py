from flask import Flask, render_template, request, send_file, jsonify
from flask_socketio import SocketIO
import os
from modules.downloader import start_download_process
from modules.file_utils import ensure_directories
from config import SECRET_KEY, PORT, DEBUG

# Inicializar la aplicación Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

# Configurar Socket.IO
socketio = SocketIO(app, cors_allowed_origins="*")

# Asegurar que los directorios necesarios existan
ensure_directories(['temp', 'downloads', 'invoices'])

# Variable global para almacenar el progreso
progress = {"current": 0, "total": 0, "files": [], "error": None}
download_thread = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    global download_thread, progress
    
    if 'excel' not in request.files:
        return "Falta el archivo Excel", 400

    excel_file = request.files['excel']
    if not excel_file.filename:
        return "Nombre de archivo inválido", 400
        
    excel_path = os.path.join("temp", excel_file.filename)
    output_dir = "invoices"

    os.makedirs("temp", exist_ok=True)
    excel_file.save(excel_path)

    # Reset progress
    progress = {"current": 0, "total": 0, "files": [], "error": None}

    # Iniciar proceso de descarga en un hilo separado
    download_thread = start_download_process(excel_path, output_dir, socketio, progress)
    
    return "Descarga iniciada", 200

@app.route('/download_zip')
def download_zip():
    zip_path = os.path.join("downloads", "facturas.zip")
    if os.path.exists(zip_path):
        return send_file(zip_path, as_attachment=True, download_name="facturas.zip")
    else:
        return "Archivo ZIP no encontrado", 404

@app.route('/status')
def get_status():
    return jsonify(progress)

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=PORT, debug=DEBUG, allow_unsafe_werkzeug=True)
