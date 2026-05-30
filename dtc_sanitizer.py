from dtc_database import lookup_dtc

def decode_dtc_bytes(b1, b2):
    """
    Decodes 2 raw bytes from OBD-II Service 03 or 07 response into standard SAE trouble code.
    Returns standard string like 'P0300', or None if it's padding (0x00, 0x00).
    """
    if b1 == 0x00 and b2 == 0x00:
        return None

    # First letter mapping
    prefixes = ['P', 'C', 'B', 'U']
    prefix = prefixes[(b1 & 0xC0) >> 6]
    
    # Second character mapping (0, 1, 2, 3)
    digit2 = str((b1 & 0x30) >> 4)
    
    # Third, fourth and fifth characters are hex digits
    def hex_char(val):
        return f"{val:X}"
        
    digit3 = hex_char(b1 & 0x0F)
    digit4 = hex_char((b2 & 0xF0) >> 4)
    digit5 = hex_char(b2 & 0x0F)
    
    return f"{prefix}{digit2}{digit3}{digit4}{digit5}"

def enrich_dtc(code):
    """
    Enriches a string DTC code with metadata.
    Returns:
    {
        "code": "P0300",
        "description": "...",
        "severity": "...",
        "category": "..."
    }
    """
    code = code.upper().strip()
    description, severity, category = lookup_dtc(code)
    return {
        "code": code,
        "description": description,
        "severity": severity,
        "category": category
    }

def build_scan_summary(mil_active, confirmed_dtcs, pending_dtcs):
    """
    Builds a natural language summary optimized for LLM consumption.
    confirmed_dtcs and pending_dtcs can be lists of strings or enriched dicts.
    """
    # Normalize to lists of dicts
    conf_enriched = [item if isinstance(item, dict) else enrich_dtc(item) for item in confirmed_dtcs]
    pend_enriched = [item if isinstance(item, dict) else enrich_dtc(item) for item in pending_dtcs]
    
    mil_status = "CHECK ENGINE ON." if mil_active else "CHECK ENGINE OFF."
    
    if not conf_enriched and not pend_enriched:
        return f"System healthy. {mil_status} No confirmed or pending Diagnostic Trouble Codes (DTCs) detected."
        
    parts = [mil_status]
    
    if conf_enriched:
        conf_strs = [f"{d['code']} {d['description']} ({d['severity'].capitalize()})" for d in conf_enriched]
        parts.append(f"{len(conf_enriched)} confirmed: " + ", ".join(conf_strs) + ".")
        
    if pend_enriched:
        pend_strs = [f"{d['code']} {d['description']} ({d['severity'].capitalize()})" for d in pend_enriched]
        parts.append(f"{len(pend_enriched)} pending: " + ", ".join(pend_strs) + ".")
        
    # Append high-level advice based on severities
    all_enriched = conf_enriched + pend_enriched
    severities = [d['severity'] for d in all_enriched]
    
    if "critical" in severities:
        parts.append("Critical issue detected. Immediate diagnostic attention and service is highly recommended to prevent engine or vehicle damage.")
    elif "moderate" in severities:
        parts.append("Moderate system warnings detected. Vehicle should be checked at the earliest convenience.")
    else:
        parts.append("Minor codes active. Monitor system status.")
        
    return " ".join(parts)

def has_state_changed(current_scan, last_scan):
    """
    Compares two scans to determine if the DTC state has changed.
    Each scan should be a dict containing:
      - mil_active: bool
      - confirmed_dtcs: list of (strings or dicts)
      - pending_dtcs: list of (strings or dicts)
    """
    if last_scan is None:
        return True
        
    c_mil = current_scan.get("mil_active", False)
    l_mil = last_scan.get("mil_active", False)
    if c_mil != l_mil:
        return True
        
    def get_code_set(dtc_list):
        codes = []
        for item in dtc_list:
            if isinstance(item, dict):
                codes.append(item.get("code"))
            elif isinstance(item, str):
                codes.append(item)
        return set(codes)
        
    c_conf = get_code_set(current_scan.get("confirmed_dtcs", []))
    l_conf = get_code_set(last_scan.get("confirmed_dtcs", []))
    if c_conf != l_conf:
        return True
        
    c_pend = get_code_set(current_scan.get("pending_dtcs", []))
    l_pend = get_code_set(last_scan.get("pending_dtcs", []))
    if c_pend != l_pend:
        return True
        
    return False
