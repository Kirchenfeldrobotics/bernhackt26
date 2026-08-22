"""Create a sample company through /companies, for testing the pipeline.

Testing only. Start the server and run it:

    python test/company_post_sim.py

The route upserts by name, so running it twice is harmless -- the second run
just updates 3dMike's details. Post this before test/vr_receive_sim.py, which
sends a room scan referencing the same company_name.
"""
import json

import httpx

# --- what to send -----------------------------------------------------------

API_URL = "https://bernhackt26.kirchenfeldrobotics.ch/companies"

COMPANY = {
    "name": "3dMike",
    # Left unset: database/categories.py has no vocabulary decided yet.
    # "category": "Manufacturing",
    "website": "https://3dmike.example.ch",
    "details": (
        "One-man operation run by Mike out of his 14 m2 student dorm room. Six "
        "desktop FDM printers sit on a steel shelf against the long wall and run "
        "more or less around the clock, printing custom parts and small-batch "
        "designs he sells through an online shop. Spools of PLA and PETG are "
        "stacked wherever they fit; failed prints, purge blobs and support "
        "material go in the same bin as everything else. He packs each order at "
        "the desk by the window with cardboard and bubble wrap kept under the "
        "bed, and walks the parcels to the post office every couple of days. "
        "The room has no dedicated ventilation, so he cracks the window when "
        "the smell gets bad, and the printers, a heat gun and two monitors all "
        "hang off one power strip that is never switched off."
    ),
}

TIMEOUT = 30

# --- go ---------------------------------------------------------------------

print(f"POST {API_URL}")
print(f"  {COMPANY['name']}: {len(COMPANY['details'])} chars of description")

response = httpx.post(API_URL, json=COMPANY, timeout=TIMEOUT)

print(f"\n{response.status_code}")
try:
    print(json.dumps(response.json(), indent=2))
except ValueError:
    print(response.text[:2000])
