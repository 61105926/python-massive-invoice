import os
import glob
import shutil
import logging

# Configurar logging
logger = logging.getLogger(__name__)

def ensure_directories(directories):
    """Asegura que los directorios necesarios existan"""
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        logger.debug(f"Directorio asegurado: {directory}")

def find_downloaded_file(output_dir, numero, before_files=None):
    """
    Encuentra un archivo descargado en el directorio de salida que coincida con el número de factura
    o sea nuevo desde que se capturó before_files.
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

def copy_file_with_new_name(source_path, target_path):
    """Copia un archivo a una nueva ubicación con un nuevo nombre"""
    try:
        shutil.copy(source_path, target_path)
        logger.info(f"Archivo copiado de {source_path} a {target_path}")
        return True
    except Exception as e:
        logger.warning(f"No se pudo copiar el archivo: {str(e)}")
        return False

def find_latest_pdf(output_dir, existing_files=None):
    """Encuentra el archivo PDF más reciente en el directorio"""
    all_pdfs = glob.glob(os.path.join(output_dir, "*.pdf"))
    
    if not all_pdfs:
        return None
        
    # Si tenemos una lista de archivos existentes, filtramos
    if existing_files:
        existing_paths = [os.path.join(output_dir, f) for f in existing_files]
        new_pdfs = [pdf for pdf in all_pdfs if pdf not in existing_paths]
        if new_pdfs:
            return max(new_pdfs, key=os.path.getmtime)
    
    # Si no hay filtro o no encontramos nuevos, devolvemos el más reciente
    return max(all_pdfs, key=os.path.getmtime)
