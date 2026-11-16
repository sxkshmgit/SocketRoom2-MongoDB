from backend.app import database


def unique_index_keys(collection):
    return [
        [field for field, _ in index["key"]]
        for index in collection.index_information().values()
        if index.get("unique")
    ]


def test_init_db_creates_unique_indexes(test_db):
    assert ["username"] in unique_index_keys(test_db.users)
    assert ["user_low_id", "user_high_id"] in unique_index_keys(test_db.conversations)
    for name in ("users", "messages", "conversations", "private_messages"):
        assert ["id"] in unique_index_keys(test_db[name])


def test_init_db_can_run_again(test_db):
    database.init_db()

    assert ["username"] in unique_index_keys(test_db.users)


def test_next_id_counts_up_per_collection(test_db):
    assert [database.next_id(test_db, "users") for _ in range(3)] == [1, 2, 3]
    assert database.next_id(test_db, "messages") == 1
