"""
vin_decoder.py
Local VIN decoder using a static WMI (World Manufacturer Identifier) lookup table.
Decodes brand, a model hint, and model year from a 17-character VIN string.
No network calls -- fully offline.
"""

# ---------------------------------------------------------------------------
# SAE J1979 model year character encoding (position 10 of VIN, 1-indexed).
# Characters 'I', 'O', 'Q', 'U', 'Z' are not used by the standard.
# The same letter repeats every 30 years, so this is a list of (char, year)
# pairs rather than a dict -- duplicate keys must be preserved.
# ---------------------------------------------------------------------------
_YEAR_TABLE = [
    ('A', 1980), ('B', 1981), ('C', 1982), ('D', 1983), ('E', 1984),
    ('F', 1985), ('G', 1986), ('H', 1987), ('J', 1988), ('K', 1989),
    ('L', 1990), ('M', 1991), ('N', 1992), ('P', 1993), ('R', 1994),
    ('S', 1995), ('T', 1996), ('V', 1997), ('W', 1998), ('X', 1999),
    ('Y', 2000),
    ('1', 2001), ('2', 2002), ('3', 2003), ('4', 2004), ('5', 2005),
    ('6', 2006), ('7', 2007), ('8', 2008), ('9', 2009),
    # Second 30-year cycle: same letters, +30 years
    ('A', 2010), ('B', 2011), ('C', 2012), ('D', 2013), ('E', 2014),
    ('F', 2015), ('G', 2016), ('H', 2017), ('J', 2018), ('K', 2019),
    ('L', 2020), ('M', 2021), ('N', 2022), ('P', 2023), ('R', 2024),
    ('S', 2025), ('T', 2026), ('V', 2027), ('W', 2028), ('X', 2029),
    ('Y', 2030),
]

# ---------------------------------------------------------------------------
# WMI (first 3 chars of VIN) -> manufacturer brand name.
# Covers the most common global manufacturers.
# ---------------------------------------------------------------------------
_WMI_TABLE = {
    # China
    "LZW": "Wuling",
    "LZG": "SAIC-GM-Wuling",
    "LSY": "Buick (SAIC-GM)",
    "LSG": "Chevrolet (SAIC-GM)",
    "LFV": "Volkswagen (FAW-VW)",
    "LFP": "Toyota (FAW)",
    "LFT": "Toyota (FAW)",
    "LGX": "Honda (GAC)",
    "LGB": "Honda (Dongfeng)",
    "LHG": "Honda (Guangqi)",
    "LB1": "Geely",
    "LBE": "Geely",
    "LDC": "Dongfeng",
    "LDY": "Dongfeng",
    "LS5": "BYD",
    "LS6": "BYD",
    "LVV": "Volvo (Geely)",
    "LVS": "Ford (Jiangling)",
    "LNB": "Nissan (Dongfeng)",
    "LN1": "Nissan (Zhengzhou)",
    "LMC": "Suzuki (Changan)",

    # USA
    "1G1": "Chevrolet",
    "1G6": "Cadillac",
    "1GY": "Cadillac",
    "1FT": "Ford Truck",
    "1FA": "Ford",
    "1FB": "Ford",
    "2FA": "Ford (Canada)",
    "2FT": "Ford Truck (Canada)",
    "1HG": "Honda",
    "1HH": "Honda",
    "2HG": "Honda (Canada)",
    "1N4": "Nissan",
    "1N6": "Nissan Truck",
    "3N1": "Nissan (Mexico)",
    "JN1": "Nissan (Japan)",
    "1VW": "Volkswagen (USA)",
    "1C3": "Chrysler",
    "1C4": "Chrysler/Jeep",
    "1D7": "Dodge Truck",
    "2B3": "Dodge (Canada)",
    "5TD": "Toyota (USA)",
    "4T1": "Toyota",
    "4T3": "Toyota",
    "JT2": "Toyota (Japan)",
    "JT3": "Toyota (Japan)",
    "JT4": "Toyota (Japan)",

    # Japan
    "JHM": "Honda (Japan)",
    "JH4": "Acura (Japan)",
    "JF1": "Subaru",
    "JF2": "Subaru",
    "JS1": "Suzuki",
    "JS2": "Suzuki",
    "JS3": "Suzuki",
    "JM1": "Mazda",
    "JM3": "Mazda",
    "JMB": "Mitsubishi",
    "JA3": "Mitsubishi",
    "JA4": "Mitsubishi",
    "JN8": "Nissan SUV",

    # Korea
    "KMH": "Hyundai",
    "KMF": "Hyundai",
    "KNA": "Kia",
    "KNM": "Renault Samsung",
    "KL4": "Daewoo/GM Korea",

    # Germany
    "WBA": "BMW",
    "WBY": "BMW i",
    "WBS": "BMW M",
    "WDB": "Mercedes-Benz",
    "WDC": "Mercedes-Benz",
    "WDD": "Mercedes-Benz",
    "WMX": "Mercedes-Benz (Van)",
    "WAU": "Audi",
    "WVW": "Volkswagen",
    "WV1": "Volkswagen (Van)",
    "WV2": "Volkswagen (Bus)",
    "WP0": "Porsche",
    "WP1": "Porsche",
    "TRU": "Audi (Hungary)",

    # UK
    "SAL": "Land Rover",
    "SAJ": "Jaguar",
    "SAR": "Rover",
    "SCC": "Lotus",

    # Italy
    "ZAR": "Alfa Romeo",
    "ZFF": "Ferrari",
    "ZHW": "Lamborghini",
    "ZLA": "Lancia",
    "ZCF": "Iveco",

    # France
    "VF1": "Renault",
    "VF3": "Peugeot",
    "VF7": "Citroen",

    # Sweden
    "YV1": "Volvo",
    "YV4": "Volvo",

    # Netherlands
    "XL9": "Spyker",

    # USA Tesla
    "5YJ": "Tesla",
    "7SA": "Tesla",
}


def decode_year(vin: str) -> int:
    """
    Decodes the model year from position 10 (0-indexed: index 9) of the VIN.
    The year character cycles every 30 years; returns the most recent match
    that is not in the future (relative to 2026).
    Returns 0 if the character is unrecognised.
    """
    if len(vin) < 10:
        return 0

    year_char = vin[9].upper()

    # Collect all years mapped to this character (can be two: 30 years apart)
    matches = [y for c, y in _YEAR_TABLE if c == year_char]
    if not matches:
        return 0

    # Return the latest year that does not exceed the current calendar year
    current_year = 2026
    valid = [y for y in matches if y <= current_year]
    return max(valid) if valid else max(matches)


def decode_wmi(vin: str) -> str:
    """
    Returns the manufacturer brand name from the first 3 characters of the VIN.
    Falls back to the raw WMI string if not found in the table.
    """
    if len(vin) < 3:
        return "Unknown"
    wmi = vin[:3].upper()
    return _WMI_TABLE.get(wmi, f"Unknown (WMI: {wmi})")


def decode_vin(vin: str) -> dict:
    """
    Decodes a full 17-character VIN into structured vehicle metadata.
    Returns a dict with keys: wmi, brand, year, region.

    VIN structure (SAE J1979):
      Positions 1-3  (idx 0-2):  WMI  - World Manufacturer Identifier
      Positions 4-9  (idx 3-8):  VDS  - Vehicle Descriptor Section
      Positions 10   (idx 9):    Year character
      Positions 11   (idx 10):   Plant code
      Positions 12-17 (idx 11-16): Production sequence number
    """
    vin = vin.strip().upper()

    if len(vin) != 17:
        return {"wmi": "?", "brand": "Unknown", "model": "Unknown", "year": 0, "region": "Unknown"}

    wmi = vin[:3]
    brand = decode_wmi(vin)
    year = decode_year(vin)

    # Rough region from first character of WMI
    region_map = {
        '1': "USA", '2': "Canada", '3': "Mexico",
        '4': "USA", '5': "USA",
        '6': "Australia", '7': "New Zealand",
        '8': "Argentina", '9': "Brazil",
        'A': "South Africa", 'B': "Angola",
        'C': "Benin", 'D': "Egypt",
        'E': "Ethiopia", 'F': "Ghana",
        'G': "Ivory Coast", 'H': "Morocco",
        'J': "Japan", 'K': "South Korea",
        'L': "China", 'M': "India",
        'N': "Indonesia", 'P': "Philippines",
        'R': "Taiwan", 'S': "United Kingdom",
        'T': "Switzerland", 'U': "Denmark",
        'V': "France / Austria", 'W': "Germany",
        'X': "Russia", 'Y': "Sweden / Finland",
        'Z': "Italy",
    }
    region = region_map.get(vin[0], "Unknown")

    # Local model resolution table for testing/development
    model_table = {
        # Tesla
        "5YJ3": ("Tesla", "Model 3"),
        "5YJS": ("Tesla", "Model S"),
        "5YJX": ("Tesla", "Model X"),
        "5YJY": ("Tesla", "Model Y"),
        "7SAY": ("Tesla", "Model Y"),
        "7G2C": ("Tesla", "Cybertruck"),

        # General Motors (Chevrolet / Cadillac / Buick)
        "1G1FY6": ("Chevrolet", "Bolt EV/EUV"),
        "1G11Y": ("Chevrolet", "Corvette"),
        "1G1RC": ("Chevrolet", "Volt"),
        "1G6": ("Cadillac", "CTS/ATS"),
        "1GY": ("Cadillac", "Escalade"),
        "LSY": ("Buick", "Envision"),
        "LSG": ("Chevrolet", "Equinox"),

        # BMW / Mini
        "WBA8E1C5": ("BMW", "330e"),
        "WBA3R1C": ("BMW", "4 Series"),
        "WBA5A": ("BMW", "5 Series"),
        "WBA1A": ("BMW", "1 Series"),
        "WBY1Z": ("BMW", "i3"),
        "WBS": ("BMW M", "Performance Model"),

        # Mercedes-Benz
        "WDD205": ("Mercedes-Benz", "C-Class"),
        "WDD213": ("Mercedes-Benz", "E-Class"),
        "WDD222": ("Mercedes-Benz", "S-Class"),
        "WDC166": ("Mercedes-Benz", "GLE-Class"),

        # Audi / Volkswagen
        "WAU8W": ("Audi", "A4"),
        "WAU4G": ("Audi", "A6"),
        "WAU1V": ("Audi", "Q5"),
        "1VW": ("Volkswagen", "Jetta/Passat"),
        "WVW": ("Volkswagen", "Golf/Passat"),

        # Porsche
        "WP0AB2": ("Porsche", "911 Carrera"),
        "WP1AA2": ("Porsche", "Cayenne"),

        # Toyota / Lexus
        "JT2KB20U": ("Toyota", "Prius"),
        "4T1BF1FK": ("Toyota", "Camry"),
        "5TDKR4FH": ("Toyota", "Highlander"),
        "JT32U": ("Toyota", "RAV4"),

        # Honda / Acura
        "1HGCP2": ("Honda", "Accord"),
        "1HGFC2": ("Honda", "Civic"),
        "2HGFC2": ("Honda", "Civic (Canada)"),
        "JHMRE4": ("Honda", "CR-V"),

        # Ford / Lincoln
        "1FTFW1EF": ("Ford", "F-150"),
        "1FA6P8CF": ("Ford", "Mustang"),
        "1FM5K8": ("Ford", "Explorer"),
        "1FMCU0": ("Ford", "Escape"),

        # Nissan / Infiniti
        "1N4AL3AP": ("Nissan", "Altima"),
        "JN1AZ4EH": ("Nissan", "370Z"),
        "1N4AZ1CP": ("Nissan", "Leaf"),

        # Hyundai / Kia
        "KMHBD4AE": ("Hyundai", "Elantra"),
        "KMHD34LF": ("Hyundai", "Sonata"),
        "KNAFX415": ("Kia", "Sportage"),
        "KNAGT4A3": ("Kia", "Optima"),

        # Volvo
        "YV1A": ("Volvo", "S60/V60"),
        "YV4A": ("Volvo", "XC90/XC60"),

        # Land Rover / Jaguar
        "SALWR2V": ("Land Rover", "Range Rover"),
        "SALWS2V": ("Land Rover", "Range Rover Sport"),

        # Subaru
        "JF1SJ": ("Subaru", "Forester"),
        "JF1SH": ("Subaru", "Forester"),
        "4S4BS": ("Subaru", "Outback"),

        # Jeep / Dodge / Fiat
        "1C4HJ": ("Jeep", "Wrangler"),
        "1C4RJ": ("Jeep", "Grand Cherokee"),
        "1C6": ("RAM", "1500"),
        "3C6": ("RAM", "2500/3500"),
        "ZFA150": ("Fiat", "500"),

        # Mazda / Mitsubishi / Suzuki
        "JM1BM": ("Mazda", "Mazda 3"),
        "JM1KF": ("Mazda", "Mazda CX-5"),
        "JA4JW": ("Mitsubishi", "Outlander"),
        "JS1ZC": ("Suzuki", "Swift"),

        # BYD / Geely
        "LC0": ("BYD", "Dolphin/Atto 3"),
        "LGX": ("BYD", "Atto 3"),
        "LB3G": ("Geely", "Coolray"),

        # Renault / Peugeot
        "VF15": ("Renault", "Renault Clio"),
        "VF3U": ("Peugeot", "Peugeot 208"),

        # Wuling / SAIC / Rebadges
        "LZWADAGA2": ("Chevrolet", "New Optra"),
        "LZWADAGA5": ("Wuling", "Hongguang"),
    }
    model = "Unknown"
    for prefix, value in model_table.items():
        if vin.startswith(prefix):
            if isinstance(value, tuple):
                brand = value[0]
                model = value[1]
            else:
                model = value
            break

    return {
        "wmi": wmi,
        "brand": brand,
        "model": model,
        "year": year,
        "region": region,
    }
