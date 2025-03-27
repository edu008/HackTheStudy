"""
Zahlungsmodul für den API-Container.
Diese Datei dient als Wrapper für die modulare Finanzstruktur
unter api/finance/*.py und wird nur für Abwärtskompatibilität beibehalten.
"""

from .finance import finance_bp as payment_bp
from .finance.constants import CREDITS, PRICES, calculate_credits

# Reexportiere wichtige Komponenten für Abwärtskompatibilität
__all__ = [
    'payment_bp',
    'PRICES',
    'CREDITS',
    'calculate_credits'
]
