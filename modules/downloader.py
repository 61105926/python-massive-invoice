import os
import threading
import logging
import zipfile
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from .selenium_utils import download_single_invoice
from config import MAX_WORKERS, DEFAULT_NIT, DEFAULT_T

# Configurar logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def start_download_process(excel_path, output_dir, socketio, progress):
    """Inicia el proceso de descarga en un hilo separado"""
    
    def run_download():
        try:
            download_invoices(excel_path, output_dir, socketio, progress, max_workers=MAX_WORKERS)
        except Exception as e:
            error_msg = f"Error en el proceso de descarga: {str(e)}"
            progress["error"] = error_msg
            socketio.emit('progress_update', {
                "current": progress["current"],
                "total": progress["total"],
                "error": error_msg
            })
    
    download_thread = threading.Thread(target=run_download)
    download_thread.daemon = True
    download_thread.start()
    
    return download_thread

def download_invoices(excel_path, output_dir, socketio, progress, max_workers=3):
    """Procesa el archivo Excel y descarga las facturas"""
    
    # Reset progress
    progress["current"] = 0
    progress["total"] = 0
    progress["files"] = []
    progress["error"] = None
    
    logger.info(f"Iniciando descarga en: {output_dir}")
    socketio.emit('progress_update', {"current": 0, "total": 0, "message": "Iniciando proceso de descarga..."})

    try:
        # Clear output directory
        if os.path.exists(output_dir):
            import shutil
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
            nit = str(row.get("NIT", DEFAULT_NIT))
            t = str(row.get("t", DEFAULT_T))
            tasks.append((cuf, numero, nit, t, output_dir, index, progress["total"], socketio, progress))
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
    create_zip_file(output_dir, progress, socketio)

def create_zip_file(output_dir, progress, socketio):
    """Crea un archivo ZIP con todas las facturas descargadas"""
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
