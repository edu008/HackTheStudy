"""
Konstanten für das Finanzmodul.
Enthält Preis- und Kreditdefinitionen sowie Berechnungsfunktionen.
"""

import logging

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Definiere Preise in Rappen (CHF)
PRICES = {
    'standard': 1990,  # 19,90 CHF
    'premium': 2990,   # 29,90 CHF
    'ultimate': 4990   # 49,90 CHF
}

# Definiere Credits pro Paket
CREDITS = {
    'standard': 300,
    'premium': 500,
    'ultimate': 1000
}

# Token-Credits-Konversionen
TOKEN_CREDITS = {
    'gpt-3.5-turbo': {
        'input': 0.001,    # 1 Credit pro 1000 Input-Token
        'output': 0.002    # 2 Credits pro 1000 Output-Token
    },
    'gpt-4': {
        'input': 0.01,     # 10 Credits pro 1000 Input-Token
        'output': 0.02     # 20 Credits pro 1000 Output-Token
    },
    'gpt-4-turbo': {
        'input': 0.01,     # 10 Credits pro 1000 Input-Token
        'output': 0.02     # 20 Credits pro 1000 Output-Token
    }
}


def calculate_credits(amount_in_cents):
    """
    Berechnet die Credits basierend auf dem Betrag in Rappen.

    Args:
        amount_in_cents (int): Der Betrag in Rappen

    Returns:
        int: Die Anzahl der Credits
    """
    if amount_in_cents == PRICES['standard']:
        return CREDITS['standard']
    if amount_in_cents == PRICES['premium']:
        return CREDITS['premium']
    if amount_in_cents == PRICES['ultimate']:
        return CREDITS['ultimate']
    # Fallback für unbekannte Beträge: 10 Credits pro Franken
    return amount_in_cents // 100 * 10


def token_to_credits(model, input_tokens, output_tokens):
    """
    Berechnet die Credits basierend auf Token-Nutzung und Modell.

    Args:
        model (str): Das verwendete Modell
        input_tokens (int): Die Anzahl der Input-Token
        output_tokens (int): Die Anzahl der Output-Token

    Returns:
        float: Die Anzahl der Credits
    """
    model_rates = TOKEN_CREDITS.get(model, TOKEN_CREDITS['gpt-3.5-turbo'])
    input_cost = (input_tokens / 1000) * model_rates['input']
    output_cost = (output_tokens / 1000) * model_rates['output']
    return round(input_cost + output_cost, 2)


def credits_to_token(model, credit_amount, is_output=True):
    """
    Berechnet die maximale Anzahl von Token, die mit den angegebenen Credits generiert werden können.

    Args:
        model (str): Das verwendete Modell
        credit_amount (float): Die Anzahl der verfügbaren Credits
        is_output (bool): True, wenn Output-Token berechnet werden sollen

    Returns:
        int: Die maximale Anzahl von Token
    """
    model_rates = TOKEN_CREDITS.get(model, TOKEN_CREDITS['gpt-3.5-turbo'])
    token_type = 'output' if is_output else 'input'
    tokens_per_credit = 1000 / model_rates[token_type]
    return int(credit_amount * tokens_per_credit)
