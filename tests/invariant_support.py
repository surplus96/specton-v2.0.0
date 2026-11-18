from specton.contracts.specification import SpecBundle


def quantity_bounds(spec):
    """Independent declared business example: 0 <= amount <= sequence."""
    data = spec.model_dump(mode="json")
    entity = next(e for e in data["entities"] if any(f["name"] == "amount" for f in e["fields"]))
    fields = {
        f["name"]: {"kind": "field", "entity_id": entity["id"], "field_id": f["id"]}
        for f in entity["fields"]
    }
    data["invariants"] = [
        {
            "id": "INV-bounds",
            "req_ids": [data["requirements"][0]["id"]],
            "description": "수량은 0 이상이고 해당 행의 한도 이하이다.",
            "match": "all",
            "layers": ["api"],
            "comparisons": [
                {
                    "operator": "ge",
                    "left": fields["amount"],
                    "right": {"kind": "number", "value": "0"},
                },
                {"operator": "le", "left": fields["amount"], "right": fields["sequence"]},
            ],
        }
    ]
    return SpecBundle.model_validate(data)
