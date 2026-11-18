from uuid import UUID

from specton.specification.draft import source_id


def test_source_ids_survive_rename_but_do_not_merge_ids_from_different_runs():
    project, run = UUID(int=1), UUID(int=2)
    key = source_id(project, run, "REQ", "REQ-01")
    # 이름은 ID 입력이 아니다. 다른 프로젝트·실행의 REQ-01은 별도 객체다.
    assert key == source_id(project, run, "REQ", "REQ-01")
    assert key != source_id(project, UUID(int=3), "REQ", "REQ-01")
    assert key != source_id(UUID(int=4), run, "REQ", "REQ-01")
    assert key != source_id(project, run, "REQ", "REQ-02")
