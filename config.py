# Configuración de la aplicación

# Clave secreta para Flask
SECRET_KEY = 'secret!'

# Puerto para la aplicación
PORT = 5001

# Modo debug
DEBUG = True

# Configuración de descarga
MAX_WORKERS = 3
DOWNLOAD_TIMEOUT = 30
WAIT_TIMEOUT = 15

# Valores por defecto para facturas
DEFAULT_NIT = "1020317028"
DEFAULT_T = "2"

# Directorios
TEMP_DIR = "temp"
DOWNLOADS_DIR = "downloads"
INVOICES_DIR = "invoices"
