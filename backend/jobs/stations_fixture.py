"""Real station identities for the synthetic fixture.

Coordinates, names and cities are genuine CPCB / OpenAQ monitoring sites,
so the map, the nearest-station query and the distance arithmetic are all
exercised against real geography. Only the MEASUREMENTS are generated --
see synth.py, and the banner every output carries.

openaq_id values here are the negative of a counter, deliberately: a real
OpenAQ id is positive, so a fixture row can never be mistaken for, or
collide with, a collected one in the stations table.
"""
from __future__ import annotations

# (name, city, state, lat, lon)
STATIONS: list[tuple[str, str, str, float, float]] = [
    # --- Delhi NCR: the Indo-Gangetic Plain, worst winter loading -------
    ("Anand Vihar",                 "Delhi",      "Delhi",          28.6469, 77.3152),
    ("Civil Lines",                 "Delhi",      "Delhi",          28.6774, 77.2216),
    ("R K Puram",                   "Delhi",      "Delhi",          28.5645, 77.1670),
    ("Punjabi Bagh",                "Delhi",      "Delhi",          28.6740, 77.1310),
    ("ITO",                         "Delhi",      "Delhi",          28.6285, 77.2410),
    ("Dwarka Sector 8",             "Delhi",      "Delhi",          28.5710, 77.0710),
    ("Jahangirpuri",                "Delhi",      "Delhi",          28.7328, 77.1707),
    ("Vasundhara",                  "Ghaziabad",  "Uttar Pradesh",  28.6603, 77.3572),
    ("Loni",                        "Ghaziabad",  "Uttar Pradesh",  28.7570, 77.2780),
    ("Sector 62",                   "Noida",      "Uttar Pradesh",  28.6245, 77.3576),
    ("Sector 116",                  "Noida",      "Uttar Pradesh",  28.5700, 77.3900),
    ("Sector 51",                   "Gurugram",   "Haryana",        28.4230, 77.0700),
    ("Vikas Sadan",                 "Gurugram",   "Haryana",        28.4500, 77.0260),
    ("Sector 16A",                  "Faridabad",  "Haryana",        28.4089, 77.3178),

    # --- Rest of the Gangetic plain -------------------------------------
    ("Nehru Nagar",                 "Kanpur",     "Uttar Pradesh",  26.4499, 80.3319),
    ("Talkatora",                   "Lucknow",    "Uttar Pradesh",  26.8390, 80.8930),
    ("Lalbagh",                     "Lucknow",    "Uttar Pradesh",  26.8467, 80.9462),
    ("Bulandshahr",                 "Bulandshahr","Uttar Pradesh",  28.4038, 77.8582),
    ("Ardhali Bazar",               "Varanasi",   "Uttar Pradesh",  25.3505, 82.9080),
    ("Samanpura",                   "Patna",      "Bihar",          25.5941, 85.1376),
    ("Rajbansi Nagar",              "Patna",      "Bihar",          25.6200, 85.1050),
    ("Dampier Park",                "Muzaffarpur","Bihar",          26.1197, 85.3910),
    ("Chhoti Gwaltoli",             "Gaya",       "Bihar",          24.7914, 85.0002),

    # --- East ------------------------------------------------------------
    ("Victoria Memorial",           "Kolkata",    "West Bengal",    22.5448, 88.3426),
    ("Rabindra Bharati University", "Kolkata",    "West Bengal",    22.6200, 88.3800),
    ("Ballygunge",                  "Kolkata",    "West Bengal",    22.5260, 88.3640),
    ("Ghusuri",                     "Howrah",     "West Bengal",    22.6000, 88.3400),
    ("Zoo Park",                    "Guwahati",   "Assam",          26.1445, 91.7362),

    # --- West ------------------------------------------------------------
    ("Bandra",                      "Mumbai",     "Maharashtra",    19.0620, 72.8350),
    ("Colaba",                      "Mumbai",     "Maharashtra",    18.9100, 72.8150),
    ("Powai",                       "Mumbai",     "Maharashtra",    19.1180, 72.9060),
    ("Chhatrapati Shivaji Airport", "Mumbai",     "Maharashtra",    19.1000, 72.8740),
    ("Airoli",                      "Navi Mumbai","Maharashtra",    19.1500, 72.9990),
    ("Karve Road",                  "Pune",       "Maharashtra",    18.5010, 73.8290),
    ("Shivajinagar",                "Pune",       "Maharashtra",    18.5300, 73.8500),
    ("Civil Lines Nagpur",          "Nagpur",     "Maharashtra",    21.1530, 79.0810),
    ("Maninagar",                   "Ahmedabad",  "Gujarat",        23.0030, 72.6010),
    ("Raikhad",                     "Ahmedabad",  "Gujarat",        23.0100, 72.5800),
    ("GIDC",                        "Surat",      "Gujarat",        21.1900, 72.8300),
    ("Police Commissioner Office",  "Vadodara",   "Gujarat",        22.3072, 73.1812),
    ("Adarsh Nagar",                "Jaipur",     "Rajasthan",      26.9020, 75.8230),
    ("Shastri Nagar",               "Jaipur",     "Rajasthan",      26.9400, 75.7900),
    ("Collectorate",                "Jodhpur",    "Rajasthan",      26.2540, 73.0230),

    # --- Central ---------------------------------------------------------
    ("TT Nagar",                    "Bhopal",     "Madhya Pradesh", 23.2330, 77.4000),
    ("Vijay Nagar",                 "Indore",     "Madhya Pradesh", 22.7500, 75.8900),
    ("Sector 7",                    "Bhilai",     "Chhattisgarh",   21.2100, 81.3800),

    # --- North / hills ---------------------------------------------------
    ("Sector 25",                   "Chandigarh", "Chandigarh",     30.7420, 76.7680),
    ("Model Town",                  "Ludhiana",   "Punjab",         30.9010, 75.8570),
    ("Golden Temple",               "Amritsar",   "Punjab",         31.6200, 74.8760),
    ("Rajpur Road",                 "Dehradun",   "Uttarakhand",    30.3400, 78.0500),
    ("Rambagh",                     "Srinagar",   "Jammu & Kashmir",34.0700, 74.7900),

    # --- South -----------------------------------------------------------
    ("Sanathnagar",                 "Hyderabad",  "Telangana",      17.4550, 78.4400),
    ("Zoo Park Hyderabad",          "Hyderabad",  "Telangana",      17.3500, 78.4500),
    ("BTM Layout",                  "Bengaluru",  "Karnataka",      12.9120, 77.6100),
    ("Hebbal",                      "Bengaluru",  "Karnataka",      13.0290, 77.5850),
    ("Peenya",                      "Bengaluru",  "Karnataka",      13.0330, 77.5190),
    ("Silk Board",                  "Bengaluru",  "Karnataka",      12.9170, 77.6230),
    ("Alandur Fire Station",        "Chennai",    "Tamil Nadu",     13.0050, 80.2000),
    ("Manali",                      "Chennai",    "Tamil Nadu",     13.1640, 80.2600),
    ("Velachery",                   "Chennai",    "Tamil Nadu",     12.9800, 80.2200),
    ("Gandhi Nagar Vellore",        "Vellore",    "Tamil Nadu",     12.9200, 79.1300),
    ("Kacheripady",                 "Kochi",      "Kerala",          9.9950, 76.2830),
    ("Plammoodu",                   "Thiruvananthapuram","Kerala",   8.5060, 76.9490),
    ("PWD Grounds",                 "Visakhapatnam","Andhra Pradesh",17.7300, 83.3050),
    ("Gaddiannaram",                "Amaravati",  "Andhra Pradesh", 16.5150, 80.5180),
]

# Cities whose loading is driven by the Indo-Gangetic Plain winter
# inversion. Used only to shape the generated seasonality.
NORTH_PLAIN_CITIES = {
    "Delhi", "Ghaziabad", "Noida", "Gurugram", "Faridabad", "Kanpur",
    "Lucknow", "Bulandshahr", "Varanasi", "Patna", "Muzaffarpur", "Gaya",
    "Chandigarh", "Ludhiana", "Amritsar", "Jaipur", "Dehradun",
}
