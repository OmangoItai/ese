import os
import tempfile

import pytest

from core.data_layer import OrderFactory, Sequence, WorldBuilder, WorldLoader
from core.entities import Order, OrderSide


class TestSequence:
    def test_next_increments(self):
        seq = Sequence()
        assert seq.next() == "order_1"
        assert seq.next() == "order_2"
        assert seq.next() == "order_3"


class TestOrderFactory:
    def test_from_params_injects_id(self):
        seq = Sequence()
        factory = OrderFactory(seq)
        o = factory.from_params(
            seller_id=1,
            buyer_id=2,
            good_id=3,
            quantity=5.0,
            price=10.0,
            side=OrderSide.SUPPLY,
            description="test",
        )
        assert isinstance(o, Order)
        assert o.order_id == "order_1"
        assert o.seller_id == 1
        assert o.buyer_id == 2
        assert o.good_id == 3
        assert o.quantity == 5.0
        assert o.price == 10.0
        assert o.side == OrderSide.SUPPLY
        assert o.description == "test"

    def test_from_update_uses_params(self):
        seq = Sequence()
        factory = OrderFactory(seq)
        o = factory.from_params(
            seller_id=10,
            buyer_id=20,
            good_id=30,
            quantity=1.0,
            price=100.0,
            side=OrderSide.DEMAND,
        )
        assert o.order_id == "order_1"
        assert o.seller_id == 10
        assert o.buyer_id == 20

    def test_from_params_defaults(self):
        seq = Sequence()
        factory = OrderFactory(seq)
        o = factory.from_params(
            seller_id=1,
            buyer_id=2,
            good_id=1,
            quantity=1.0,
            price=1.0,
        )
        assert o.side == OrderSide.SUPPLY
        assert o.description == ""


class TestWorldBuilder:
    def test_build_mini_world(self):
        wb = WorldBuilder()
        wb.add_good(1, "bread", "food", 1)
        wb.add_firm(
            1,
            1000.0,
            capacity=50.0,
            strategy_label="farm",
            inventory={1: 10.0},
            employees=[1],
        )
        wb.add_household(
            1,
            500.0,
            labor_ask_price=10.0,
            is_employed=True,
            employer_firm_id=1,
            inventory={1: 5.0},
            strategy_label="default",
        )
        wb.add_government(1, 10000.0, tax_rate=0.1, unemployment_benefit=5.0)
        ws = wb.build()

        assert ws.tick == 0
        assert len(ws.goods) == 1
        assert ws.goods[1].name == "bread"
        assert ws.goods[1].good_type == "food"
        assert ws.goods[1].delivery_lag == 1

        assert len(ws.firms) == 1
        assert ws.firms[1].cash == 1000.0
        assert ws.firms[1].capacity == 50.0
        assert ws.firms[1].strategy_label == "farm"
        assert ws.firms[1].inventory == {1: 10.0}
        assert ws.firms[1].employees == [1]

        assert len(ws.households) == 1
        assert ws.households[1].cash == 500.0
        assert ws.households[1].labor_ask_price == 10.0
        assert ws.households[1].is_employed is True
        assert ws.households[1].employer_firm_id == 1
        assert ws.households[1].inventory == {1: 5.0}
        assert ws.households[1].strategy_label == "default"

        assert len(ws.governments) == 1
        assert ws.governments[1].cash == 10000.0
        assert ws.governments[1].tax_rate == 0.1
        assert ws.governments[1].unemployment_benefit == 5.0

    def test_build_chain(self):
        ws = (
            WorldBuilder()
            .add_good(1, "food", "food")
            .add_firm(101, 1000.0)
            .add_household(1, 100.0)
            .add_government(201, 5000.0)
            .build()
        )
        assert len(ws.firms) == 1
        assert len(ws.households) == 1
        assert len(ws.governments) == 1

    def test_save_and_load_roundtrip(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name
        try:
            (
                WorldBuilder()
                .add_good(1, "bread", "food", 2)
                .add_good(2, "tool", "raw_material", 1)
                .add_firm(
                    101,
                    1000.0,
                    capacity=50.0,
                    strategy_label="farm",
                    inventory={1: 10.0, 2: 5.0},
                    employees=[1, 2],
                )
                .add_firm(
                    102,
                    2000.0,
                    capacity=30.0,
                    strategy_label="workshop",
                    inventory={2: 20.0},
                )
                .add_household(
                    1,
                    500.0,
                    labor_ask_price=10.0,
                    is_employed=True,
                    employer_firm_id=101,
                    inventory={1: 5.0},
                )
                .add_household(2, 300.0, is_employed=True, employer_firm_id=101)
                .add_government(201, 10000.0, tax_rate=0.1, unemployment_benefit=5.0)
                .save(db_path)
            )
            ws = WorldLoader.load(db_path)
            assert ws.tick == 0
            assert len(ws.goods) == 2
            assert ws.goods[1].delivery_lag == 2
            assert ws.goods[2].good_type == "raw_material"
            assert len(ws.firms) == 2
            assert ws.firms[101].strategy_label == "farm"
            assert ws.firms[101].inventory == {1: 10.0, 2: 5.0}
            assert ws.firms[101].employees == [1, 2]
            assert ws.firms[102].strategy_label == "workshop"
            assert ws.firms[102].inventory == {2: 20.0}
            assert ws.firms[102].employees == []
            assert len(ws.households) == 2
            assert ws.households[1].is_employed is True
            assert ws.households[1].employer_firm_id == 101
            assert ws.households[1].inventory == {1: 5.0}
            assert ws.households[2].is_employed is True
            assert ws.households[2].employer_firm_id == 101
            assert ws.households[2].inventory == {}
            assert len(ws.governments) == 1
            assert ws.governments[201].cash == 10000.0
            assert ws.governments[201].tax_rate == 0.1
        finally:
            os.unlink(db_path)

    def test_save_overwrites_existing(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name
        try:
            (
                WorldBuilder()
                .add_good(1, "old", "food")
                .add_firm(101, 100.0)
                .add_household(1, 50.0)
                .add_government(201, 1000.0)
                .save(db_path)
            )
            ws1 = WorldLoader.load(db_path)
            assert ws1.goods[1].name == "old"

            (
                WorldBuilder()
                .add_good(1, "new", "raw_material", 3)
                .add_firm(101, 200.0)
                .add_household(1, 100.0)
                .add_government(201, 2000.0)
                .save(db_path)
            )
            ws2 = WorldLoader.load(db_path)
            assert ws2.goods[1].name == "new"
            assert ws2.goods[1].delivery_lag == 3
            assert ws2.firms[101].cash == 200.0
        finally:
            os.unlink(db_path)

    def test_builder_strategy_label_default(self):
        ws = (
            WorldBuilder()
            .add_good(1, "food", "food")
            .add_firm(1, 100.0)
            .add_household(1, 100.0)
            .add_government(1, 1000.0)
            .build()
        )
        assert ws.firms[1].strategy_label == "default"
        assert ws.households[1].strategy_label == "default"
        assert ws.governments[1].strategy_label == "default"
