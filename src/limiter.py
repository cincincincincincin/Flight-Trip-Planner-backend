from slowapi import Limiter
from slowapi.util import get_remote_address

# Globalny system ograniczania liczby zapytań służący do ochrony serwera przed nadmiernym obciążeniem
# Konfiguracja mechanizmu Slowapi z wykorzystaniem adresu IP klienta jako głównego klucza identyfikacji użytkownika
limiter = Limiter(key_func=get_remote_address)
