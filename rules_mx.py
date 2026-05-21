
RULES_MX_DLOCAL = [
    # Reglas originales Dlocal Mexico
    ("D LOCAL", "Banorte", "1151995728", "AA370"),
    ("EVOPAYMX", "EVO MPGs", "70177702216", "AA376"),
    ("ABONO VENTAS", "Hey Banregio", "220881970023", "AA374"),
    ("MERCADO PAGOREFERENCIA", "Mercadopago", "1151995728", "AA370"),
    ("MERCADO PAGO", "Mercadopago", "1151995728", "AA370"),
    ("OPENMX", "Openpay", "116158803", "AA375"),
    ("CADENA COMERCIAL OXXO SA", "OXXO Pay", "1151995728", "AA370"),
    ("LIQ DLOCALMEXICO", "Kushki", "1151995728", "AA370"),

    # Fallbacks por texto para cuentas nuevas cuando el Account ID no coincide
    ("EVOPAYMX", "EVO MPGs", "", ""),
    ("ABONO VENTAS", "Hey Banregio", "", ""),
    ("MERCADO PAGOREFERENCIA", "Mercadopago", "", ""),
    ("MERCADO PAGO", "Mercadopago", "", ""),
    ("OPENMX", "Openpay", "", ""),
    ("CADENA COMERCIAL OXXO SA", "OXXO Pay", "", ""),
    ("LIQ DLOCALMEXICO", "Kushki", "", ""),
]

RULES_MX_DEMERGE = [
    ("D LOCAL", "Banorte", "1011320992", "AA350"),
    ("EVOPAYMX", "EVO MPGs", "70137911173", "AA358"),
    ("ABONO VENTAS", "Hey Banregio", "220881930013", "AA354"),
    ("MP AGREGADOR", "Mercadopago", "1011320992", "AA350"),
    ("MERCADO PAGO", "Mercadopago", "1011320992", "AA350"),
    ("OPENMX", "Openpay", "111698419", "AA356"),
    ("OPENMX", "Openpay_paynet", "113735494", "AA357"),
    ("CADENA COMERCIAL OXXO SA", "OXXO Pay", "1011320992", "AA350"),
    ("LIQ DEMEREGE BIG PLAYERS", "Kushki", "1011320992", "AA350"),

    # Fallbacks por texto
    ("EVOPAYMX", "EVO MPGs", "", ""),
    ("ABONO VENTAS", "Hey Banregio", "", ""),
    ("MP AGREGADOR", "Mercadopago", "", ""),
    ("MERCADO PAGO", "Mercadopago", "", ""),
    ("OPENMX", "Openpay", "", ""),
    ("CADENA COMERCIAL OXXO SA", "OXXO Pay", "", ""),
    ("LIQ DEMEREGE BIG PLAYERS", "Kushki", "", ""),
