from core.dtc_database import lookup_dtc

def decode_dtc_bytes(b1, b2):
    """
    Decodes 2 raw bytes from OBD-II Service 03/07 response into standard SAE trouble code.
    Returns standard string like 'P0300', or None if it's padding (0x00, 0x00).
    """
    if b1 == 0x00 and b2 == 0x00:
        return None

    prefixes = ['P', 'C', 'B', 'U']
    prefix = prefixes[(b1 & 0xC0) >> 6]
    digit2 = str((b1 & 0x30) >> 4)
    return f"{prefix}{digit2}{b1 & 0x0F:X}{(b2 & 0xF0) >> 4:X}{b2 & 0x0F:X}"

def enrich_dtc(code):
    """Enriches a string DTC code with metadata."""
    code = code.upper().strip()
    description, severity, category = lookup_dtc(code)
    return {"code": code, "description": description, "severity": severity, "category": category}

def build_scan_summary(mil_active, confirmed_dtcs, pending_dtcs):
    """Builds a natural language summary optimized for LLM consumption."""
    conf = [d if isinstance(d, dict) else enrich_dtc(d) for d in confirmed_dtcs]
    pend = [d if isinstance(d, dict) else enrich_dtc(d) for d in pending_dtcs]
    
    mil_status = "CHECK ENGINE ON." if mil_active else "CHECK ENGINE OFF."
    if not conf and not pend:
        return f"System healthy. {mil_status} No confirmed or pending Diagnostic Trouble Codes (DTCs) detected."
        
    parts = [mil_status]
    if conf:
        conf_strs = [f"{d['code']} {d['description']} ({d['severity'].capitalize()})" for d in conf]
        parts.append(f"{len(conf)} confirmed: " + ", ".join(conf_strs) + ".")
        
    if pend:
        pend_strs = [f"{d['code']} {d['description']} ({d['severity'].capitalize()})" for d in pend]
        parts.append(f"{len(pend)} pending: " + ", ".join(pend_strs) + ".")
        
    severities = {d['severity'] for d in conf + pend}
    if "critical" in severities:
        parts.append("Critical issue detected. Immediate diagnostic attention and service is highly recommended to prevent engine or vehicle damage.")
    elif "moderate" in severities:
        parts.append("Moderate system warnings detected. Vehicle should be checked at the earliest convenience.")
    else:
        parts.append("Minor codes active. Monitor system status.")
        
    return " ".join(parts)

def has_state_changed(current_scan, last_scan):
    """Compares two scans to determine if the DTC state has changed."""
    if last_scan is None:
        return True
    if current_scan.get("mil_active", False) != last_scan.get("mil_active", False):
        return True
        
    def get_codes(dtc_list):
        return {item.get("code") if isinstance(item, dict) else item for item in dtc_list}
        
    if get_codes(current_scan.get("confirmed_dtcs", [])) != get_codes(last_scan.get("confirmed_dtcs", [])):
        return True
    if get_codes(current_scan.get("pending_dtcs", [])) != get_codes(last_scan.get("pending_dtcs", [])):
        return True
        
    return False
