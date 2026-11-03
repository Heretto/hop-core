"""Tests for hop_core.pagination — paginate() helper and PaginatedResponse."""

import pytest
from sqlalchemy import Column, String, create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from hop_core.pagination import PaginationParams, PaginatedResponse, paginate


# ── Minimal in-memory model ───────────────────────────────────────────────────

class _Base(DeclarativeBase):
    pass


class _Item(_Base):
    __tablename__ = "items"
    id = Column(String, primary_key=True)
    name = Column(String)
    category = Column(String)


@pytest.fixture(scope="module")
def db():
    engine = create_engine("sqlite:///:memory:")
    _Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    rows = [
        _Item(id="1", name="Zebra",   category="animal"),
        _Item(id="2", name="Apple",   category="fruit"),
        _Item(id="3", name="Mango",   category="fruit"),
        _Item(id="4", name="Aardvark",category="animal"),
        _Item(id="5", name="Banana",  category="fruit"),
    ]
    session.add_all(rows)
    session.commit()
    yield session
    session.close()


def _params(**kwargs) -> PaginationParams:
    defaults = dict(page=1, page_size=25, sort_by=None, sort_dir="asc", filter=None)
    defaults.update(kwargs)
    p = PaginationParams.__new__(PaginationParams)
    p.page = defaults["page"]
    p.page_size = defaults["page_size"]
    p.sort_by = defaults["sort_by"]
    p.sort_dir = defaults["sort_dir"]
    p.filter = defaults["filter"] or ""
    return p


SORT_MAP = {"name": _Item.name, "category": _Item.category}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestPaginate:
    def test_returns_all_items_on_single_page(self, db):
        items, total = paginate(db.query(_Item), _params(), SORT_MAP)
        assert total == 5
        assert len(items) == 5

    def test_total_reflects_full_dataset(self, db):
        items, total = paginate(db.query(_Item), _params(page_size=2), SORT_MAP)
        assert total == 5
        assert len(items) == 2

    def test_page_2_returns_correct_slice(self, db):
        p1_items, _ = paginate(db.query(_Item), _params(page=1, page_size=2), SORT_MAP)
        p2_items, _ = paginate(db.query(_Item), _params(page=2, page_size=2), SORT_MAP)
        p1_ids = {i.id for i in p1_items}
        p2_ids = {i.id for i in p2_items}
        assert p1_ids.isdisjoint(p2_ids)

    def test_last_page_returns_remainder(self, db):
        items, total = paginate(db.query(_Item), _params(page=3, page_size=2), SORT_MAP)
        assert total == 5
        assert len(items) == 1

    def test_sort_asc(self, db):
        items, _ = paginate(db.query(_Item), _params(sort_by="name", sort_dir="asc"), SORT_MAP)
        names = [i.name for i in items]
        assert names == sorted(names)

    def test_sort_desc(self, db):
        items, _ = paginate(db.query(_Item), _params(sort_by="name", sort_dir="desc"), SORT_MAP)
        names = [i.name for i in items]
        assert names == sorted(names, reverse=True)

    def test_unknown_sort_by_is_ignored(self, db):
        # Must not raise; just ignores the unknown column.
        items, total = paginate(db.query(_Item), _params(sort_by="nonexistent"), SORT_MAP)
        assert total == 5

    def test_no_sort_map_ignores_sort(self, db):
        items, total = paginate(db.query(_Item), _params(sort_by="name"))
        assert total == 5

    def test_pre_filtered_query(self, db):
        q = db.query(_Item).filter(_Item.category == "fruit")
        items, total = paginate(q, _params(), SORT_MAP)
        assert total == 3
        assert all(i.category == "fruit" for i in items)

    def test_page_beyond_data_returns_empty(self, db):
        items, total = paginate(db.query(_Item), _params(page=99, page_size=25), SORT_MAP)
        assert total == 5
        assert items == []


class TestPaginatedResponse:
    def test_schema_roundtrip(self):
        resp = PaginatedResponse[str](
            items=["a", "b"],
            total=10,
            page=2,
            page_size=2,
        )
        assert resp.total == 10
        assert resp.page == 2
        assert resp.items == ["a", "b"]

    def test_json_serialisable(self):
        resp = PaginatedResponse[dict](
            items=[{"id": 1}],
            total=1,
            page=1,
            page_size=25,
        )
        d = resp.model_dump()
        assert d["total"] == 1
        assert d["page_size"] == 25
