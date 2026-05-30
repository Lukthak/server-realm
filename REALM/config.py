import os

# Configuración de red del servidor
_IP_LOCAL  = "127.0.0.1"
_IP_SERVER = "159.223.107.32"
_IP_ELO = "159.223.107.32"

# Cambia aquí para alternar: _IP_LOCAL  o  _IP_SERVER
# Si se lanza desde RealmHaven, REALM_SERVER_IP sobreescribe este valor
SERVER_IP   = os.environ.get("REALM_SERVER_IP", _IP_SERVER)
SERVER_PORT = 5555
