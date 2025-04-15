import os
import time
import logging
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from .file_utils import find_downloaded_file, copy_file_with_new_name, find_latest_pdf
from config import DOWNLOAD_TIMEOUT, WAIT_TIMEOUT

# Configurar logging
logger = logging.getLogger(__name__)

def create_driver(output_dir):
    """Crea y configura un driver de Selenium Chrome"""
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
        import shutil
        shutil.rmtree("/Users/user/.wdm/drivers/chromedriver", ignore_errors=True)
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.debug("Driver reinstalado con éxito.")
        return driver

def download_single_invoice(cuf, numero, nit, t, output_dir, index, total, socketio, progress):
    """Descarga una factura individual usando Selenium"""
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

        wait = WebDriverWait(driver, WAIT_TIMEOUT)  # Timeout configurable
        ver_factura_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[starts-with(@id, 'formQr:')]")))
        ver_factura_btn.click()
        logger.debug(f"Factura {numero} - Botón de descarga clickeado")

        # Timeout configurable para la descarga
        timeout = DOWNLOAD_TIMEOUT  
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
            # If the file was found but not at the expected path, copy it
            if found_path != final_path:
                copy_file_with_new_name(found_path, final_path)
                downloaded_file = os.path.basename(final_path)
            else:
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
            latest_pdf = find_latest_pdf(output_dir, progress["files"])
            if latest_pdf:
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
