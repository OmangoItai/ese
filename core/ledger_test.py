from core.ledger import Ledger, TradeRecord
from core.entities import Order


class TestTradeRecord:
    def test_creation(self):
        tr = TradeRecord(
            tick=5,
            order_id="o1",
            seller_id=1,
            buyer_id=2,
            good_id=3,
            quantity=10.0,
            price=5.5,
            status="FULFILLED",
        )
        assert tr.tick == 5
        assert tr.order_id == "o1"
        assert tr.seller_id == 1
        assert tr.buyer_id == 2
        assert tr.good_id == 3
        assert tr.quantity == 10.0
        assert tr.price == 5.5
        assert tr.status == "FULFILLED"


class TestLedger:
    def test_record_trade_appends(self):
        ledger = Ledger()
        o = Order(
            order_id="o1",
            seller_id=1,
            buyer_id=2,
            good_id=1,
            quantity=10.0,
            price=5.0,
            status="OPEN",
        )
        ledger.record_trade(o)
        assert len(ledger.records) == 1
        assert ledger.records[0].order_id == "o1"
        assert ledger.records[0].status == "OPEN"

    def test_record_trade_multiple_states(self):
        ledger = Ledger()
        o = Order(
            order_id="o1",
            seller_id=1,
            buyer_id=2,
            good_id=1,
            quantity=10.0,
            price=5.0,
            status="OPEN",
        )
        ledger.record_trade(o)
        o.status = "ALLOCATED"
        ledger.record_trade(o)
        o.status = "FULFILLED"
        ledger.record_trade(o)
        assert len(ledger.records) == 3
        statuses = [r.status for r in ledger.records]
        assert statuses == ["OPEN", "ALLOCATED", "FULFILLED"]

    def test_get_trades_by_agent(self):
        ledger = Ledger()
        for i in range(10):
            o = Order(
                order_id=f"o{i}",
                seller_id=1,
                buyer_id=2,
                good_id=1,
                quantity=1.0,
                price=1.0,
                status="FULFILLED",
            )
            ledger.record_trade(o)
        for i in range(10):
            o = Order(
                order_id=f"x{i}",
                seller_id=3,
                buyer_id=4,
                good_id=1,
                quantity=1.0,
                price=1.0,
                status="FULFILLED",
            )
            ledger.record_trade(o)

        agent1_trades = ledger.get_trades_by_agent(1)
        assert len(agent1_trades) == 10
        assert all(r.seller_id == 1 for r in agent1_trades)

        agent2_trades = ledger.get_trades_by_agent(2)
        assert len(agent2_trades) == 10
        assert all(r.buyer_id == 2 for r in agent2_trades)

    def test_get_trades_by_agent_limit_n(self):
        ledger = Ledger()
        for i in range(20):
            o = Order(
                order_id=f"o{i}",
                seller_id=1,
                buyer_id=2,
                good_id=1,
                quantity=1.0,
                price=1.0,
                status="FULFILLED",
            )
            ledger.record_trade(o)

        recent = ledger.get_trades_by_agent(1, n=5)
        assert len(recent) == 5
        assert recent[-1].order_id == "o19"

    def test_get_avg_price_by_good(self):
        ledger = Ledger()
        goods_1_fulfilled = []
        for i in range(5):
            price = 10.0 + i
            o = Order(
                order_id=f"a{i}",
                seller_id=1,
                buyer_id=2,
                good_id=1,
                quantity=1.0,
                price=price,
                status="FULFILLED",
            )
            ledger.record_trade(o)
            goods_1_fulfilled.append(price)
        for i in range(3):
            o = Order(
                order_id=f"b{i}",
                seller_id=1,
                buyer_id=2,
                good_id=1,
                quantity=1.0,
                price=99.0,
                status="DEFAULTED",
            )
            ledger.record_trade(o)
        expected_avg = sum(goods_1_fulfilled) / len(goods_1_fulfilled)
        assert ledger.get_avg_price_by_good(1) == expected_avg

    def test_get_avg_price_by_good_empty(self):
        ledger = Ledger()
        assert ledger.get_avg_price_by_good(99) == 0.0

    def test_get_avg_price_by_good_limit_n(self):
        ledger = Ledger()
        for i in range(10):
            o = Order(
                order_id=f"o{i}",
                seller_id=1,
                buyer_id=2,
                good_id=1,
                quantity=1.0,
                price=10.0 + i,
                status="FULFILLED",
            )
            ledger.record_trade(o)
        avg_recent_3 = ledger.get_avg_price_by_good(1, n=3)
        expected = (17.0 + 18.0 + 19.0) / 3.0
        assert avg_recent_3 == expected

    def test_get_all_recent_prices(self):
        ledger = Ledger()
        for i in range(3):
            o = Order(
                order_id=f"g1_{i}",
                seller_id=1,
                buyer_id=2,
                good_id=1,
                quantity=1.0,
                price=10.0,
                status="FULFILLED",
            )
            ledger.record_trade(o)
        for i in range(2):
            o = Order(
                order_id=f"g2_{i}",
                seller_id=1,
                buyer_id=2,
                good_id=2,
                quantity=1.0,
                price=20.0,
                status="FULFILLED",
            )
            ledger.record_trade(o)
        result = ledger.get_all_recent_prices()
        assert 1 in result
        assert 2 in result
        assert len(result[1]) == 3
        assert len(result[2]) == 2
        assert all(p == 10.0 for p in result[1])
        assert all(p == 20.0 for p in result[2])

    def test_get_all_recent_prices_excludes_non_fulfilled(self):
        ledger = Ledger()
        o = Order(
            order_id="f",
            seller_id=1,
            buyer_id=2,
            good_id=1,
            quantity=1.0,
            price=10.0,
            status="FULFILLED",
        )
        ledger.record_trade(o)
        o2 = Order(
            order_id="d",
            seller_id=1,
            buyer_id=2,
            good_id=1,
            quantity=1.0,
            price=10.0,
            status="DEFAULTED",
        )
        ledger.record_trade(o2)
        result = ledger.get_all_recent_prices()
        assert len(result[1]) == 1

    def test_mixed_records_avg_price_correct(self):
        ledger = Ledger()
        prices = []
        for i in range(20):
            o = Order(
                order_id=f"o{i}",
                seller_id=i % 3,
                buyer_id=i % 5,
                good_id=1,
                quantity=1.0,
                price=float(i),
                status="FULFILLED",
            )
            ledger.record_trade(o)
            prices.append(float(i))
        assert ledger.get_avg_price_by_good(1) == sum(prices) / len(prices)
