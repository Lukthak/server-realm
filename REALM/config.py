import os

# Configuración de red del servidor
_IP_LOCAL  = "127.0.0.1"
_IP_SERVER = "159.223.107.32"

# Si se lanza desde RealmHaven, REALM_SERVER_IP sobreescribe este valor
SERVER_IP   = os.environ.get("REALM_SERVER_IP", _IP_SERVER)
SERVER_PORT = 5555

# Dimensiones de ventana y bucle
WIDTH, HEIGHT   = 350, 350
MAP_WIDTH       = WIDTH * 4
MAP_HEIGHT      = HEIGHT * 4
FPS             = 60
ICONO_PATH      = os.path.join(os.path.dirname(__file__), "ICONO.ico")
