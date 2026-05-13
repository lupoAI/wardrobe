import sqlite3

from wardrobe.db import SCHEMA, get_item, insert_item, update_item_metadata


def memory_db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def sample_item():
    return {
        "id": "item_test",
        "original_filename": "shirt.jpg",
        "image_path": "/tmp/shirt.jpg",
        "embedding_path": "/tmp/shirt.npy",
        "category": "tops",
        "subcategory": "shirt",
        "colors": ["blue"],
        "tags": ["solid"],
        "notes": "Blue shirt",
    }


def test_update_item_metadata_round_trip():
    con = memory_db()
    insert_item(con, sample_item())

    updated = update_item_metadata(
        con,
        "item_test",
        {
            "category": "outerwear",
            "subcategory": "jacket",
            "colors": ["navy", "white"],
            "tags": ["smart", "layer"],
            "notes": "Navy chore jacket",
        },
    )

    assert updated["category"] == "outerwear"
    assert updated["subcategory"] == "jacket"
    assert updated["colors"] == ["navy", "white"]
    assert updated["tags"] == ["smart", "layer"]
    assert updated["notes"] == "Navy chore jacket"
    assert get_item(con, "item_test") == updated


def test_update_item_metadata_rejects_unknown_fields():
    con = memory_db()
    insert_item(con, sample_item())

    try:
        update_item_metadata(con, "item_test", {"image_path": "/etc/passwd"})
    except ValueError as exc:
        assert "Unsupported item fields" in str(exc)
    else:
        raise AssertionError("expected ValueError")
