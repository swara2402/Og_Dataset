from scripts.acquire_og_awc_pararev import paper_components


def test_paper_components_group_linked_article_versions_deterministically():
    rows = [
        {"id_source": "version-a", "id_target": "version-b"},
        {"id_source": "version-b", "id_target": "version-c"},
        {"id_source": "version-x", "id_target": "version-y"},
    ]
    first = paper_components(rows)
    second = paper_components(list(reversed(rows)))

    assert first == second
    assert first["version-a"] == first["version-b"] == first["version-c"]
    assert first["version-x"] == first["version-y"]
    assert first["version-a"] != first["version-x"]


def test_paper_components_ignores_incomplete_version_edges():
    rows = [
        {"id_source": "version-a", "id_target": None},
        {"id_source": "", "id_target": "version-b"},
    ]
    assert paper_components(rows) == {}
