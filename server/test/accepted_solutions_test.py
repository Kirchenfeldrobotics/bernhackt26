import httpx

API_URL = "https://bernhackt26.kirchenfeldrobotics.ch/get-accepted-solutions"

# must have been scanned and had at least one conclusion accepted
COMPANY_NAME = "3dMike"

TIMEOUT = 30

# one row per accepted conclusion, whole -- no solution/conclusion pairing, and
# no repetition to regroup: the conclusion is the unit that gets accepted
CONCLUSION_FIELDS = {
    "id", "company_name", "batch", "title", "problem", "solutions",
    "savings_10y_chf", "anchor", "status", "created_at",
}

failures = []


# record a check without stopping, so one run reports everything that is wrong
def check(label, condition):
    print(f"  {'PASS' if condition else 'FAIL'}  {label}")
    if not condition:
        failures.append(label)


print(f"POST {API_URL}")
print(f"  company {COMPANY_NAME}")

response = httpx.post(API_URL, json={"company_name": COMPANY_NAME}, timeout=TIMEOUT)
print(f"\n{response.status_code}")

check("responds 200", response.status_code == 200)
if response.status_code != 200:
    print(response.text[:500])
    raise SystemExit(1)

conclusions = response.json()
check("returns a list", isinstance(conclusions, list))
print(f"\n{len(conclusions)} accepted conclusion(s)")

for i, conclusion in enumerate(conclusions):
    solutions = conclusion.get("solutions") or []
    print(f"\n  [{i}] {conclusion.get('title')!r}")
    print(f"      conclusion id {conclusion.get('id')}")
    print(f"      status        {conclusion.get('status')}")
    print(f"      savings       {conclusion.get('savings_10y_chf')}")
    print(f"      solutions     {len(solutions)}")

    check(f"conclusion {i} has the documented shape", CONCLUSION_FIELDS <= set(conclusion))
    check(f"conclusion {i} has an id", bool(conclusion.get("id")))
    # only accepted ones come back, so anything else here is a filter bug
    check(f"conclusion {i} is accepted", conclusion.get("status") == "accepted")
    check(f"conclusion {i} is this company's", conclusion.get("company_name") == COMPANY_NAME)
    check(f"conclusion {i} carries its solutions", len(solutions) > 0)

    # solutions are the conclusion's detail: named, and deliberately id-less
    for j, solution in enumerate(solutions):
        check(f"conclusion {i} solution {j} has a name", bool(solution.get("name")))
        check(f"conclusion {i} solution {j} has no id of its own", "id" not in solution)

    savings = str(conclusion.get("savings_10y_chf", ""))
    amount = savings.lstrip("|").partition("|")[0]
    check(f"conclusion {i} savings parses to a number", amount.isdigit())

# ids identify one conclusion each, so a repeat means the grouping came back
ids = [c.get("id") for c in conclusions]
check("no conclusion is repeated", len(ids) == len(set(ids)))

# the company name is matched case-insensitively, so this must agree
other_case = COMPANY_NAME.upper() if COMPANY_NAME.islower() else COMPANY_NAME.lower()
mixed = httpx.post(API_URL, json={"company_name": other_case}, timeout=TIMEOUT)
print(f"\nsame query as {other_case!r}: {mixed.status_code}")
check("case-insensitive lookup agrees", mixed.status_code == 200 and len(mixed.json()) == len(conclusions))

# a company nobody scanned is an empty list, not an error
unknown = httpx.post(API_URL, json={"company_name": "No Such Company AG"}, timeout=TIMEOUT)
check("unknown company returns []", unknown.status_code == 200 and unknown.json() == [])

# a blank name is rejected before it reaches the database
blank = httpx.post(API_URL, json={"company_name": "   "}, timeout=TIMEOUT)
check("blank company name rejected", blank.status_code == 422)

print(f"\n{len(failures)} failed" if failures else "\nall checks passed")
raise SystemExit(1 if failures else 0)
