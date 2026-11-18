import hashlib

from specton.implementation.comparison import file_changes, semantic_changes


def test_diff_includes_removed_added_modified_and_unchanged():
    changes = file_changes(
        {"gone": b"x", "same": b"ok", "edit": b"old"}, {"new": b"n", "same": b"ok", "edit": b"new"}
    )
    assert {c["path"]: c["change"] for c in changes} == {
        "gone": "removed",
        "new": "added",
        "edit": "modified",
    }
    assert "-old" in changes[0]["diff"] and "+new" in changes[0]["diff"]
    assert changes[0]["before_hash"] == hashlib.sha256(b"old").hexdigest()


def test_diff_bounded_without_losing_file_hashes():
    files = {str(i): ("x" * 60 + "\n").encode() * 800 for i in range(30)}
    files["large"] = b"x" * 100000
    files["binary"] = b"\xff"
    changes = file_changes({}, files)
    assert len(changes) == len(files)
    assert sum(len(c["diff"] or "") for c in changes) <= 65536
    assert all(len(c["after_hash"]) == 64 for c in changes)
    assert any(c["truncated"] for c in changes)


def test_semantic_diff_tracks_ids_and_policies():
    result = semantic_changes(
        {"requirements": [{"id": "R1", "text": "old"}, {"id": "R2"}]},
        {
            "requirements": [{"id": "R1", "text": "new"}, {"id": "R3"}],
            "inventory": {"mode": "ledger"},
        },
    )
    assert result["requirements"] == {"added": ["R3"], "removed": ["R2"], "modified": ["R1"]}
    assert result["inventory_changed"] is True
