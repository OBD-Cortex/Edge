# Diagnostic Trouble Code (DTC) database mapping generic SAE J2012 codes
# format: "CODE": (description, severity, category)
# severity: "critical", "moderate", "minor"
# category: "engine", "fuel", "emission", "transmission", "electrical", "body", "network", "chassis"

DTC_LOOKUP = {
    # Fuel & Air Metering (P01xx)
    "P0100": ("Mass Air Flow (MAF) Circuit Malfunction", "moderate", "fuel"),
    "P0101": ("Mass Air Flow (MAF) Circuit Range/Performance Problem", "moderate", "fuel"),
    "P0102": ("Mass Air Flow (MAF) Circuit Low Input", "moderate", "fuel"),
    "P0103": ("Mass Air Flow (MAF) Circuit High Input", "moderate", "fuel"),
    "P0104": ("Mass Air Flow (MAF) Circuit Intermittent", "moderate", "fuel"),
    "P0105": ("Manifold Absolute Pressure (MAP) Barometric Pressure Sensor Circuit Malfunction", "moderate", "fuel"),
    "P0106": ("Manifold Absolute Pressure (MAP) Sensor Circuit Range/Performance", "moderate", "fuel"),
    "P0107": ("Manifold Absolute Pressure (MAP) Sensor Circuit Low Input", "moderate", "fuel"),
    "P0108": ("Manifold Absolute Pressure (MAP) Sensor Circuit High Input", "moderate", "fuel"),
    "P0109": ("Manifold Absolute Pressure (MAP) Sensor Circuit Intermittent", "moderate", "fuel"),
    "P0110": ("Intake Air Temperature (IAT) Sensor 1 Circuit Malfunction", "minor", "fuel"),
    "P0111": ("Intake Air Temperature (IAT) Sensor 1 Circuit Range/Performance", "minor", "fuel"),
    "P0112": ("Intake Air Temperature (IAT) Sensor 1 Circuit Low Input", "minor", "fuel"),
    "P0113": ("Intake Air Temperature (IAT) Sensor 1 Circuit High Input", "minor", "fuel"),
    "P0115": ("Engine Coolant Temperature (ECT) Circuit Malfunction", "critical", "engine"),
    "P0116": ("Engine Coolant Temperature (ECT) Circuit Range/Performance", "critical", "engine"),
    "P0117": ("Engine Coolant Temperature (ECT) Circuit Low Input", "moderate", "engine"),
    "P0118": ("Engine Coolant Temperature (ECT) Circuit High Input", "moderate", "engine"),
    "P0120": ("Throttle/Pedal Position Sensor/Switch 'A' Circuit Malfunction", "critical", "engine"),
    "P0121": ("Throttle/Pedal Position Sensor/Switch 'A' Circuit Range/Performance", "critical", "engine"),
    "P0122": ("Throttle/Pedal Position Sensor/Switch 'A' Circuit Low Input", "moderate", "engine"),
    "P0123": ("Throttle/Pedal Position Sensor/Switch 'A' Circuit High Input", "moderate", "engine"),
    "P0125": ("Insufficient Coolant Temperature for Closed Loop Fuel Control", "moderate", "engine"),
    "P0128": ("Coolant Thermostat (Coolant Temp Below Thermostat Regulating Temp)", "moderate", "engine"),
    "P0130": ("O2 Sensor Circuit Malfunction (Bank 1 Sensor 1)", "moderate", "emission"),
    "P0131": ("O2 Sensor Circuit Low Voltage (Bank 1 Sensor 1)", "moderate", "emission"),
    "P0132": ("O2 Sensor Circuit High Voltage (Bank 1 Sensor 1)", "moderate", "emission"),
    "P0133": ("O2 Sensor Circuit Slow Response (Bank 1 Sensor 1)", "moderate", "emission"),
    "P0134": ("O2 Sensor Circuit No Activity Detected (Bank 1 Sensor 1)", "moderate", "emission"),
    "P0135": ("O2 Sensor Heater Circuit Malfunction (Bank 1 Sensor 1)", "minor", "emission"),
    "P0136": ("O2 Sensor Circuit Malfunction (Bank 1 Sensor 2)", "moderate", "emission"),
    "P0137": ("O2 Sensor Circuit Low Voltage (Bank 1 Sensor 2)", "minor", "emission"),
    "P0138": ("O2 Sensor Circuit High Voltage (Bank 1 Sensor 2)", "minor", "emission"),
    "P0140": ("O2 Sensor Circuit No Activity Detected (Bank 1 Sensor 2)", "minor", "emission"),
    "P0141": ("O2 Sensor Heater Circuit Malfunction (Bank 1 Sensor 2)", "minor", "emission"),
    "P0171": ("System Too Lean (Bank 1)", "critical", "fuel"),
    "P0172": ("System Too Rich (Bank 1)", "critical", "fuel"),
    "P0173": ("Fuel Trim Malfunction (Bank 2)", "moderate", "fuel"),
    "P0174": ("System Too Lean (Bank 2)", "critical", "fuel"),
    "P0175": ("System Too Rich (Bank 2)", "critical", "fuel"),
    "P0190": ("Fuel Rail Pressure Sensor 'A' Circuit", "critical", "fuel"),
    "P0191": ("Fuel Rail Pressure Sensor 'A' Circuit Range/Performance", "critical", "fuel"),

    # Fuel & Air Metering - Injector (P02xx)
    "P0200": ("Injector Circuit Malfunction", "critical", "fuel"),
    "P0201": ("Injector Circuit Malfunction - Cylinder 1", "critical", "fuel"),
    "P0202": ("Injector Circuit Malfunction - Cylinder 2", "critical", "fuel"),
    "P0203": ("Injector Circuit Malfunction - Cylinder 3", "critical", "fuel"),
    "P0204": ("Injector Circuit Malfunction - Cylinder 4", "critical", "fuel"),
    "P0205": ("Injector Circuit Malfunction - Cylinder 5", "critical", "fuel"),
    "P0206": ("Injector Circuit Malfunction - Cylinder 6", "critical", "fuel"),
    "P0217": ("Engine Overtemperature Condition", "critical", "engine"),
    "P0219": ("Engine Overspeed Condition", "critical", "engine"),
    "P0230": ("Fuel Pump Primary Circuit Malfunction", "critical", "fuel"),
    "P0234": ("Engine Overboost Condition", "critical", "engine"),
    "P0299": ("Turbocharger/Supercharger Underboost", "moderate", "engine"),

    # Ignition System & Misfires (P03xx)
    "P0300": ("Random/Multiple Cylinder Misfire Detected", "critical", "engine"),
    "P0301": ("Cylinder 1 Misfire Detected", "critical", "engine"),
    "P0302": ("Cylinder 2 Misfire Detected", "critical", "engine"),
    "P0303": ("Cylinder 3 Misfire Detected", "critical", "engine"),
    "P0304": ("Cylinder 4 Misfire Detected", "critical", "engine"),
    "P0305": ("Cylinder 5 Misfire Detected", "critical", "engine"),
    "P0306": ("Cylinder 6 Misfire Detected", "critical", "engine"),
    "P0307": ("Cylinder 7 Misfire Detected", "critical", "engine"),
    "P0308": ("Cylinder 8 Misfire Detected", "critical", "engine"),
    "P0320": ("Ignition/Distributor Engine Speed Input Circuit Malfunction", "critical", "engine"),
    "P0321": ("Ignition/Distributor Engine Speed Input Circuit Range/Performance", "critical", "engine"),
    "P0325": ("Knock Sensor 1 Circuit Malfunction (Bank 1 or Single Sensor)", "moderate", "engine"),
    "P0327": ("Knock Sensor 1 Circuit Low Input (Bank 1 or Single Sensor)", "moderate", "engine"),
    "P0328": ("Knock Sensor 1 Circuit High Input (Bank 1 or Single Sensor)", "moderate", "engine"),
    "P0330": ("Knock Sensor 2 Circuit Malfunction (Bank 2)", "moderate", "engine"),
    "P0335": ("Crankshaft Position Sensor A Circuit Malfunction", "critical", "engine"),
    "P0336": ("Crankshaft Position Sensor A Circuit Range/Performance", "critical", "engine"),
    "P0340": ("Camshaft Position Sensor A Circuit Malfunction (Bank 1 or Single Sensor)", "critical", "engine"),
    "P0341": ("Camshaft Position Sensor A Circuit Range/Performance (Bank 1)", "critical", "engine"),

    # Auxiliary Emissions Control (P04xx)
    "P0400": ("Exhaust Gas Recirculation (EGR) Flow Malfunction", "moderate", "emission"),
    "P0401": ("Exhaust Gas Recirculation (EGR) Flow Insufficient Detected", "moderate", "emission"),
    "P0402": ("Exhaust Gas Recirculation (EGR) Flow Excessive Detected", "moderate", "emission"),
    "P0410": ("Secondary Air Injection System Malfunction", "minor", "emission"),
    "P0420": ("Catalyst System Efficiency Below Threshold (Bank 1)", "moderate", "emission"),
    "P0421": ("Warm Up Catalyst Efficiency Below Threshold (Bank 1)", "moderate", "emission"),
    "P0430": ("Catalyst System Efficiency Below Threshold (Bank 2)", "moderate", "emission"),
    "P0440": ("Evaporative Emission Control System (EVAP) Malfunction", "minor", "emission"),
    "P0441": ("Evaporative Emission Control System (EVAP) Incorrect Purge Flow", "minor", "emission"),
    "P0442": ("Evaporative Emission Control System (EVAP) Leak Detected (Small Leak)", "minor", "emission"),
    "P0443": ("Evaporative Emission Control System (EVAP) Purge Control Valve Circuit Malfunction", "minor", "emission"),
    "P0446": ("Evaporative Emission Control System (EVAP) Vent Control Circuit Malfunction", "minor", "emission"),
    "P0455": ("Evaporative Emission Control System (EVAP) System Leak Detected (Gross Leak)", "moderate", "emission"),
    "P0456": ("Evaporative Emission Control System (EVAP) System Leak Detected (Very Small Leak)", "minor", "emission"),

    # Speed & Idle Controls (P05xx)
    "P0500": ("Vehicle Speed Sensor 'A' Malfunction", "critical", "chassis"),
    "P0501": ("Vehicle Speed Sensor 'A' Range/Performance", "moderate", "chassis"),
    "P0505": ("Idle Control System Malfunction", "moderate", "engine"),
    "P0506": ("Idle Control System RPM Lower Than Expected", "minor", "engine"),
    "P0507": ("Idle Control System RPM Higher Than Expected", "minor", "engine"),
    "P0551": ("Power Steering Pressure Sensor/Switch Circuit Range/Performance", "minor", "chassis"),
    "P0560": ("System Voltage Malfunction", "critical", "electrical"),
    "P0562": ("System Voltage Low", "critical", "electrical"),
    "P0563": ("System Voltage High", "critical", "electrical"),
    "P0571": ("Brake Switch 'A' Circuit Malfunction", "critical", "chassis"),

    # ECU / Computer Circuits (P06xx)
    "P0600": ("Serial Communication Link Malfunction", "critical", "network"),
    "P0601": ("Internal Control Module Memory Check Sum Error", "critical", "electrical"),
    "P0602": ("Control Module Programming Error", "critical", "electrical"),
    "P0603": ("Internal Control Module Keep Alive Memory (KAM) Error", "critical", "electrical"),
    "P0604": ("Internal Control Module Random Access Memory (RAM) Error", "critical", "electrical"),
    "P0605": ("Internal Control Module Read Only Memory (ROM) Error", "critical", "electrical"),
    "P0606": ("PCM Processor Fault", "critical", "electrical"),
    "P0650": ("Malfunction Indicator Lamp (MIL) Control Circuit Malfunction", "critical", "electrical"),

    # Transmission Controls (P07xx & P08xx)
    "P0700": ("Transmission Control System Malfunction (MIL Request)", "critical", "transmission"),
    "P0705": ("Transmission Range Sensor Circuit Malfunction (PRNDL Input)", "critical", "transmission"),
    "P0706": ("Transmission Range Sensor Circuit Range/Performance", "moderate", "transmission"),
    "P0715": ("Input/Turbine Speed Sensor 'A' Circuit Malfunction", "critical", "transmission"),
    "P0720": ("Output Speed Sensor Circuit Malfunction", "critical", "transmission"),
    "P0730": ("Incorrect Gear Ratio", "critical", "transmission"),
    "P0731": ("Gear 1 Incorrect Ratio", "critical", "transmission"),
    "P0732": ("Gear 2 Incorrect Ratio", "critical", "transmission"),
    "P0733": ("Gear 3 Incorrect Ratio", "critical", "transmission"),
    "P0734": ("Gear 4 Incorrect Ratio", "critical", "transmission"),
    "P0740": ("Torque Converter Clutch Circuit Malfunction", "critical", "transmission"),
    "P0750": ("Shift Solenoid 'A' Malfunction", "critical", "transmission"),
    "P0751": ("Shift Solenoid 'A' Performance or Stuck Off", "critical", "transmission"),
    "P0753": ("Shift Solenoid 'A' Electrical Malfunction", "critical", "transmission"),
    "P0801": ("Reverse Inhibit Control Circuit Malfunction", "moderate", "transmission"),

    # Chassis Codes (C0xxx)
    "C0035": ("Left Front Wheel Speed Sensor Malfunction", "critical", "chassis"),
    "C0040": ("Right Front Wheel Speed Sensor Malfunction", "critical", "chassis"),
    "C0300": ("Rear Speed Sensor Circuit Malfunction", "critical", "chassis"),

    # Body Codes (B0xxx)
    "B0001": ("Driver Frontal Stage 1 Airbag Deployment Control", "critical", "body"),
    "B0081": ("Passenger Presence System Malfunction", "critical", "body"),
    "B1201": ("Fuel Sender Circuit Failure", "moderate", "body"),

    # Network Codes (U0xxx)
    "U0001": ("High Speed CAN Communication Bus Malfunction", "critical", "network"),
    "U0100": ("Lost Communication with ECM/PCM", "critical", "network"),
    "U0101": ("Lost Communication with TCM (Transmission Control Module)", "critical", "network"),
    "U0115": ("Lost Communication with Engine Control Module (ECM) - Alternative", "critical", "network"),
    "U0155": ("Lost Communication with Instrument Panel Cluster (IPC) Control Module", "critical", "network"),
    "U0300": ("Internal Software Incompatibility with ECM/PCM", "critical", "network"),
}

def lookup_dtc(code):
    """
    Looks up a DTC code. If not found, returns a fallback based on standard code classifications.
    Returns: (description, severity, category)
    """
    code = code.upper().strip()
    if code in DTC_LOOKUP:
        return DTC_LOOKUP[code]

    # Category analysis based on prefix letter
    category = "engine"
    if code.startswith("P"):
        category = "engine"
    elif code.startswith("C"):
        category = "chassis"
    elif code.startswith("B"):
        category = "body"
    elif code.startswith("U"):
        category = "network"

    # Distinguish generic (0 or 2) vs manufacturer specific (1 or 3)
    if len(code) >= 2:
        is_manufacturer = code[1] in ("1", "3")
    else:
        is_manufacturer = False

    # Default severities and descriptions based on ranges
    severity = "moderate"
    if code.startswith("P03"):
        severity = "critical" # Misfires/ignition
        description = "Ignition/Misfire Diagnostics Fault"
    elif code.startswith("P01"):
        description = "Fuel or Air Metering System Fault"
        if "ECT" in code or "115" in code or "116" in code:
            severity = "critical"
    elif code.startswith("P02"):
        description = "Fuel Injector or Turbo/Supercharger Fault"
        severity = "critical"
    elif code.startswith("P04"):
        description = "Auxiliary Emissions Controls Fault"
        severity = "moderate"
    elif code.startswith("P05"):
        description = "Vehicle Speed Control or Idle System Fault"
    elif code.startswith("P06"):
        description = "Internal Control Module / Computer Outputs Fault"
        severity = "critical"
    elif code.startswith("P07") or code.startswith("P08"):
        description = "Transmission Control System Fault"
        severity = "critical"
        category = "transmission"
    elif code.startswith("U"):
        description = "CAN Bus / Network Communication Failure"
        severity = "critical"
        category = "network"
    elif is_manufacturer:
        description = f"Manufacturer-Specific {category.capitalize()} Fault"
        severity = "moderate"
    else:
        description = f"Generic {category.capitalize()} Diagnostics Code"
        severity = "moderate"

    return description, severity, category
