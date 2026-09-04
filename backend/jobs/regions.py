"""City -> state/province enrichment.

OpenAQ v3 gives a location a country and a `locality` (roughly a city).
It does NOT give a reliable state or province. The stations table has a
`state` column, so it has to come from somewhere -- and it is honest
about being a lookup rather than source data.

This is the ONE country-specific thing in the collector. An unknown
country returns None for every city, which leaves stations.state NULL:
a missing label, not a broken collector. That is what keeps the Phase 8
Asia expansion a config change (see collect.py --verify-country-agnostic).
"""
from __future__ import annotations

# India. Covers the cities with CPCB continuous monitors; the long tail
# resolves to None and is reported as such in the data quality report.
_INDIA: dict[str, str] = {
    "delhi": "Delhi", "new delhi": "Delhi",
    "ghaziabad": "Uttar Pradesh", "noida": "Uttar Pradesh",
    "greater noida": "Uttar Pradesh", "kanpur": "Uttar Pradesh",
    "lucknow": "Uttar Pradesh", "varanasi": "Uttar Pradesh",
    "agra": "Uttar Pradesh", "meerut": "Uttar Pradesh",
    "bulandshahr": "Uttar Pradesh", "moradabad": "Uttar Pradesh",
    "baghpat": "Uttar Pradesh", "hapur": "Uttar Pradesh",
    "muzaffarnagar": "Uttar Pradesh", "prayagraj": "Uttar Pradesh",
    "allahabad": "Uttar Pradesh", "gorakhpur": "Uttar Pradesh",
    "jhansi": "Uttar Pradesh", "bareilly": "Uttar Pradesh",
    "gurugram": "Haryana", "gurgaon": "Haryana", "faridabad": "Haryana",
    "rohtak": "Haryana", "panipat": "Haryana", "hisar": "Haryana",
    "karnal": "Haryana", "sonipat": "Haryana", "ambala": "Haryana",
    "yamunanagar": "Haryana", "bahadurgarh": "Haryana",
    "patna": "Bihar", "muzaffarpur": "Bihar", "gaya": "Bihar",
    "hajipur": "Bihar", "darbhanga": "Bihar", "purnia": "Bihar",
    "kolkata": "West Bengal", "howrah": "West Bengal",
    "haldia": "West Bengal", "asansol": "West Bengal",
    "durgapur": "West Bengal", "siliguri": "West Bengal",
    "mumbai": "Maharashtra", "navi mumbai": "Maharashtra",
    "pune": "Maharashtra", "nagpur": "Maharashtra", "nashik": "Maharashtra",
    "thane": "Maharashtra", "aurangabad": "Maharashtra",
    "solapur": "Maharashtra", "kolhapur": "Maharashtra",
    "chandrapur": "Maharashtra", "amravati": "Maharashtra",
    "ahmedabad": "Gujarat", "surat": "Gujarat", "vadodara": "Gujarat",
    "rajkot": "Gujarat", "gandhinagar": "Gujarat", "bhavnagar": "Gujarat",
    "ankleshwar": "Gujarat", "vapi": "Gujarat",
    "jaipur": "Rajasthan", "jodhpur": "Rajasthan", "kota": "Rajasthan",
    "udaipur": "Rajasthan", "ajmer": "Rajasthan", "alwar": "Rajasthan",
    "bhiwadi": "Rajasthan", "pali": "Rajasthan",
    "bhopal": "Madhya Pradesh", "indore": "Madhya Pradesh",
    "gwalior": "Madhya Pradesh", "jabalpur": "Madhya Pradesh",
    "ujjain": "Madhya Pradesh", "sagar": "Madhya Pradesh",
    "bhilai": "Chhattisgarh", "raipur": "Chhattisgarh",
    "korba": "Chhattisgarh", "bilaspur": "Chhattisgarh",
    "chandigarh": "Chandigarh",
    "ludhiana": "Punjab", "amritsar": "Punjab", "jalandhar": "Punjab",
    "patiala": "Punjab", "bathinda": "Punjab", "khanna": "Punjab",
    "dehradun": "Uttarakhand", "rishikesh": "Uttarakhand",
    "haridwar": "Uttarakhand", "kashipur": "Uttarakhand",
    "srinagar": "Jammu & Kashmir", "jammu": "Jammu & Kashmir",
    "hyderabad": "Telangana", "warangal": "Telangana",
    "nizamabad": "Telangana",
    "bengaluru": "Karnataka", "bangalore": "Karnataka",
    "mysuru": "Karnataka", "mysore": "Karnataka",
    "hubballi": "Karnataka", "mangaluru": "Karnataka",
    "kalaburagi": "Karnataka", "belagavi": "Karnataka",
    "chennai": "Tamil Nadu", "coimbatore": "Tamil Nadu",
    "madurai": "Tamil Nadu", "vellore": "Tamil Nadu",
    "tiruchirappalli": "Tamil Nadu", "salem": "Tamil Nadu",
    "thoothukudi": "Tamil Nadu", "hosur": "Tamil Nadu",
    "kochi": "Kerala", "ernakulam": "Kerala",
    "thiruvananthapuram": "Kerala", "kozhikode": "Kerala",
    "kollam": "Kerala", "thrissur": "Kerala",
    "visakhapatnam": "Andhra Pradesh", "amaravati": "Andhra Pradesh",
    "vijayawada": "Andhra Pradesh", "tirupati": "Andhra Pradesh",
    "rajamahendravaram": "Andhra Pradesh", "guntur": "Andhra Pradesh",
    "bhubaneswar": "Odisha", "cuttack": "Odisha", "rourkela": "Odisha",
    "talcher": "Odisha", "angul": "Odisha", "brajrajnagar": "Odisha",
    "guwahati": "Assam", "silchar": "Assam", "nagaon": "Assam",
    "byrnihat": "Assam",
    "ranchi": "Jharkhand", "jamshedpur": "Jharkhand",
    "dhanbad": "Jharkhand",
    "shillong": "Meghalaya", "aizawl": "Mizoram", "imphal": "Manipur",
    "kohima": "Nagaland", "gangtok": "Sikkim", "agartala": "Tripura",
    "itanagar": "Arunachal Pradesh",
    "shimla": "Himachal Pradesh", "baddi": "Himachal Pradesh",
    "damtal": "Himachal Pradesh", "paonta sahib": "Himachal Pradesh",
    "panaji": "Goa", "puducherry": "Puducherry",
}

_BY_COUNTRY: dict[str, dict[str, str]] = {"IN": _INDIA}


def state_for_city(city: str | None, country_code: str = "IN") -> str | None:
    """Best-effort state name, or None.

    None is a legitimate answer and is counted in the data quality
    report -- better an empty column than a guessed one.
    """
    if not city:
        return None
    table = _BY_COUNTRY.get((country_code or "").upper())
    if not table:
        return None
    return table.get(city.strip().lower())


def coverage(country_code: str = "IN") -> int:
    return len(_BY_COUNTRY.get((country_code or "").upper()) or {})
