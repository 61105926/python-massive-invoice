from flask import Flask, render_template, request, send_from_directory, jsonify, send_file
from flask_socketio import SocketIO
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

import os
import time
import threading
import logging
import uuid
import shutil
import zipfile
import glob
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
# Configure CORS for Socket.IO to allow connections from any origin
socketio = SocketIO(app, cors_allowed_origins="*")

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

progress = {"current": 0, "total": 0, "files": [], "error": None}
download_thread = None

def create_driver(output_dir):
    chrome_options = Options()
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": os.path.abspath(output_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.debug(f"Driver creado con éxito. Directorio de descarga: {os.path.abspath(output_dir)}")
        return driver
    except Exception as e:
        logger.error(f"Error al crear el driver: {str(e)}")
        logger.info("Limpiando caché de ChromeDriver y reintentando...")
        shutil.rmtree("/Users/user/.wdm/drivers/chromedriver", ignore_errors=True)
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.debug("Driver reinstalado con éxito.")
        return driver

def find_downloaded_file(output_dir, numero, before_files=None):
    """
    Find a downloaded file in the output directory that matches the invoice number
    or is new since before_files was captured.
    """
    # Check for expected filename patterns
    patterns = [
        f"factura_{numero}.pdf",
        f"{numero}.pdf",
        f"factura-{numero}.pdf",
        f"factura_{numero}*.pdf",  # Wildcard for any suffix
    ]
    
    for pattern in patterns:
        matches = glob.glob(os.path.join(output_dir, pattern))
        if matches:
            return matches[0]
    
    # If we have a list of files from before, check for new files
    if before_files:
        current_files = set(os.listdir(output_dir))
        new_files = current_files - before_files
        pdf_files = [f for f in new_files if f.endswith('.pdf')]
        if pdf_files:
            return os.path.join(output_dir, pdf_files[0])
    
    # Check for any PDF file that might contain the invoice number in the name
    for file in os.listdir(output_dir):
        if file.endswith('.pdf') and str(numero) in file:
            return os.path.join(output_dir, file)
    
    return None

def download_single_invoice(cuf, numero, nit, t, output_dir, index, total):
    global progress
    driver = None
    downloaded_file = f"factura_{numero}.pdf"
    final_path = os.path.join(output_dir, downloaded_file)
    
    try:
        # Get list of files before download
        before_files = set(os.listdir(output_dir))
        
        driver = create_driver(output_dir)
        url = f"https://siat.impuestos.gob.bo/consulta/QR?nit={nit}&cuf={cuf}&numero={numero}&t={t}"
        logger.info(f"Procesando factura {index + 1}/{total} - URL: {url}")
        
        # Emit detailed progress update
        socketio.emit('progress_update', {
            "current": progress["current"],
            "total": progress["total"],
            "message": f"Procesando factura {numero} ({index + 1}/{total})"
        })

        driver.get(url)
        logger.debug(f"Factura {numero} - URL cargada, esperando elementos...")

        wait = WebDriverWait(driver, 15)  # Increased timeout for better reliability
        ver_factura_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[starts-with(@id, 'formQr:')]")))
        ver_factura_btn.click()
        logger.debug(f"Factura {numero} - Botón de descarga clickeado")

        # Increased timeout for download
        timeout = 30  
        start_time = time.time()
        found_path = None
        
        # Wait for file to appear
        while not found_path and (time.time() - start_time) < timeout:
            found_path = find_downloaded_file(output_dir, numero, before_files)
            
            if not found_path:
                time.sleep(1)
                # Emit waiting message every 5 seconds
                if int(time.time() - start_time) % 5 == 0:
                    socketio.emit('progress_update', {
                        "current": progress["current"],
                        "total": progress["total"],
                        "message": f"Esperando descarga de factura {numero}... ({int(time.time() - start_time)}s)"
                    })

        # Final check for any new PDF file
        if not found_path:
            # Check for any new PDF file
            current_files = set(os.listdir(output_dir))
            new_files = current_files - before_files
            pdf_files = [f for f in new_files if f.endswith('.pdf')]
            if pdf_files:
                found_path = os.path.join(output_dir, pdf_files[0])
                logger.info(f"Factura {numero} - Encontrado archivo nuevo: {found_path}")

        if found_path:
            # If the file was found but not at the expected path, move it
            if found_path != final_path:
                try:
                    shutil.copy(found_path, final_path)
                    logger.info(f"Archivo copiado de {found_path} a {final_path}")
                except Exception as e:
                    logger.warning(f"No se pudo copiar el archivo: {str(e)}")
                    # Use the found path instead
                    final_path = found_path
                    downloaded_file = os.path.basename(found_path)
            
            with threading.Lock():
                if downloaded_file not in progress["files"]:
                    progress["files"].append(downloaded_file)
                    progress["current"] += 1
                    socketio.emit('progress_update', {
                        "current": progress["current"],
                        "total": progress["total"],
                        "message": f"Descargado: {downloaded_file} ({progress['current']}/{progress['total']})"
                    })
            logger.info(f"Factura {numero} - PDF descargado: {final_path}")
            return True
        else:
            # One last desperate attempt - check for ANY new PDF file
            all_pdfs = glob.glob(os.path.join(output_dir, "*.pdf"))
            if all_pdfs:
                # Get the most recently modified PDF file
                latest_pdf = max(all_pdfs, key=os.path.getmtime)
                if latest_pdf not in [os.path.join(output_dir, f) for f in progress["files"]]:
                    downloaded_file = os.path.basename(latest_pdf)
                    with threading.Lock():
                        progress["files"].append(downloaded_file)
                        progress["current"] += 1
                        socketio.emit('progress_update', {
                            "current": progress["current"],
                            "total": progress["total"],
                            "message": f"Descargado: {downloaded_file} ({progress['current']}/{progress['total']})"
                        })
                    logger.info(f"Factura {numero} - PDF encontrado (último recurso): {latest_pdf}")
                    return True
            
            raise Exception(f"No se descargó el archivo para factura {numero} tras {timeout} segundos")

    except Exception as e:
        error_msg = f"Error al procesar factura {numero}: {str(e)}"
        with threading.Lock():
            # Don't overwrite existing error if there is one
            if not progress["error"]:
                progress["error"] = error_msg
            socketio.emit('progress_update', {
                "current": progress["current"],
                "total": progress["total"],
                "error": error_msg,
                "message": f"Error en factura {numero}"
            })
        logger.error(error_msg)
        return False
    finally:
        if driver:
            driver.quit()

def download_invoices(excel_path, output_dir="invoices", max_workers=3):
    global progress
    default_nit = "1020317028"
    default_t = "2"

    # Reset progress
    progress = {"current": 0, "total": 0, "files": [], "error": None}
    
    logger.info(f"Iniciando descarga en: {output_dir}")
    socketio.emit('progress_update', {"current": 0, "total": 0, "message": "Iniciando proceso de descarga..."})

    try:
        # Clear output directory
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        
        df = pd.read_excel(excel_path)
        progress["total"] = len(df)
        logger.info(f"Total de facturas: {progress['total']}")
        socketio.emit('progress_update', {
            "current": 0,
            "total": progress["total"],
            "message": f"Procesando {progress['total']} facturas"
        })
    except Exception as e:
        error_msg = f"Error al leer el Excel: {str(e)}"
        progress["error"] = error_msg
        socketio.emit('progress_update', {"current": 0, "total": 0, "error": error_msg})
        return None

    tasks = []
    for index, row in df.iterrows():
        try:
            cuf = str(row["CUF"])
            numero = str(row["Numero"])
            nit = str(row.get("NIT", default_nit))
            t = str(row.get("t", default_t))
            tasks.append((cuf, numero, nit, t, output_dir, index, progress["total"]))
        except Exception as e:
            error_msg = f"Error al procesar fila {index}: {str(e)}"
            socketio.emit('progress_update', {"error": error_msg})
            logger.error(error_msg)

    # Limit max_workers to avoid overwhelming the system
    actual_workers = min(max_workers, len(tasks))
    
    socketio.emit('progress_update', {
        "current": 0,
        "total": progress["total"],
        "message": f"Iniciando descarga con {actual_workers} trabajadores simultáneos"
    })

    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        future_to_invoice = {
            executor.submit(download_single_invoice, *task): task[1] 
            for task in tasks
        }
        for future in concurrent.futures.as_completed(future_to_invoice):
            numero = future_to_invoice[future]
            try:
                future.result()
            except Exception as e:
                logger.error(f"Error en factura {numero}: {str(e)}")
    
    # Create ZIP file with all downloaded invoices
    if progress["files"]:
        zip_path = os.path.join("downloads", "facturas.zip")
        os.makedirs("downloads", exist_ok=True)
        
        socketio.emit('progress_update', {
            "current": progress["current"],
            "total": progress["total"],
            "message": "Creando archivo ZIP con todas las facturas..."
        })
        
        try:
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for file in progress["files"]:
                    file_path = os.path.join(output_dir, file)
                    if os.path.exists(file_path):
                        zipf.write(file_path, file)
            
            # Even if we had errors for some invoices, if we have files, consider it a success
            socketio.emit('progress_update', {
                "current": progress["total"],
                "total": progress["total"],
                "message": f"Descarga completada. Se descargaron {len(progress['files'])} de {progress['total']} facturas.",
                "download_url": "/download_zip"
            })
        except Exception as e:
            error_msg = f"Error al crear ZIP: {str(e)}"
            progress["error"] = error_msg
            socketio.emit('progress_update', {"error": error_msg})
    else:
        socketio.emit('progress_update', {
            "current": progress["current"],
            "total": progress["total"],
            "message": "No se descargaron facturas.",
            "error": progress["error"] or "No se pudo descargar ninguna factura."
        })

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

    def run_download():
        try:
            download_invoices(excel_path, output_dir, max_workers=3)
        except Exception as e:
            error_msg = f"Error en el proceso de descarga: {str(e)}"
            progress["error"] = error_msg
            socketio.emit('progress_update', {
                "current": progress["current"],
                "total": progress["total"],
                "error": error_msg
            })

    # Stop previous thread if running
    if download_thread and download_thread.is_alive():
        # We can't really stop the thread, but we can let it run and start a new one
        pass
        
    download_thread = threading.Thread(target=run_download)
    download_thread.daemon = True  # Make thread daemon so it exits when main thread exits
    download_thread.start()
    
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
    # Make sure directories exist
    os.makedirs("temp", exist_ok=True)
    os.makedirs("downloads", exist_ok=True)
    os.makedirs("invoices", exist_ok=True)
    
    socketio.run(app, host='0.0.0.0', port=5001, debug=True, allow_unsafe_werkzeug=True)
