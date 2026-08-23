import json

import httpx

API_URL = "https://bernhackt26.kirchenfeldrobotics.ch/get-accepted-solutions"

# must have been scanned and had at least one solution accepted
COMPANY_NAME = "3dMike"

TIMEOUT = 30

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

entries = response.json()
check("returns a list", isinstance(entries, list))
print(f"\n{len(entries)} accepted solution(s)")

# each entry pairs one solution with the conclusion it was proposed for
for i, entry in enumerate(entries):
    solution = entry.get("solution", {})
    conclusion = entry.get("conclusion", {})
    print(f"\n  [{i}] {solution.get('name')}")
    print(f"      solution id   {solution.get('id')}")
    print(f"      conclusion    {conclusion.get('title')!r} ({conclusion.get('id')})")
    print(f"      savings       {conclusion.get('savings_10y_chf')}")
    check(f"entry {i} has both halves", bool(solution) and bool(conclusion))
    check(f"entry {i} solution has an id", bool(solution.get("id")))
    check(f"entry {i} conclusion has an id", bool(conclusion.get("id")))
    # the response carries no company_name, so scoping is proven by the
    # unknown-company check below rather than per entry
    check(
        f"entry {i} has the documented shape",
        {"id", "batch", "title", "problem", "savings_10y_chf", "anchor", "created_at"}
        <= set(conclusion),
    )
    savings = str(conclusion.get("savings_10y_chf", ""))
    amount = savings.lstrip("|").partition("|")[0]
    check(f"entry {i} savings parses to a number", amount.isdigit())

# the company name is matched case-insensitively, so this must agree
other_case = COMPANY_NAME.upper() if COMPANY_NAME.islower() else COMPANY_NAME.lower()
mixed = httpx.post(API_URL, json={"company_name": other_case}, timeout=TIMEOUT)
print(f"\nsame query as {other_case!r}: {mixed.status_code}")
check("case-insensitive lookup agrees", mixed.status_code == 200 and len(mixed.json()) == len(entries))

# a company nobody scanned is an empty list, not an error
unknown = httpx.post(API_URL, json={"company_name": "No Such Company AG"}, timeout=TIMEOUT)
check("unknown company returns []", unknown.status_code == 200 and unknown.json() == [])

# a blank name is rejected before it reaches the database
blank = httpx.post(API_URL, json={"company_name": "   "}, timeout=TIMEOUT)
check("blank company name rejected", blank.status_code == 422)

print(f"\n{len(failures)} failed" if failures else "\nall checks passed")
raise SystemExit(1 if failures else 0)
