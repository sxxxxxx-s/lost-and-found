import contextlib
import io
import unittest

from agent import detect_intent, orchestrate, react_agent
from data import APPOINTMENTS, CLAIMS
from services.claim_service import ClaimHandler
import services.handover_service as handover_service
from services.handover_service import HandoverHandler
from services.item_service import ItemHandler
from tests.test_services import running_server
import tools


class ToolIntegrationTests(unittest.TestCase):
    def setUp(self):
        CLAIMS.clear()
        APPOINTMENTS.clear()

    def test_wrappers_call_all_three_microservices(self):
        with running_server(ItemHandler) as item_base, running_server(
            ClaimHandler
        ) as claim_base, running_server(HandoverHandler) as handover_base:
            tools.ITEM_URL = item_base
            tools.CLAIM_URL = claim_base
            tools.HANDOVER_URL = handover_base
            handover_service.CLAIM_URL = claim_base

            items = tools.search_items("耳机", "图书馆")
            item = tools.query_item("LF2026001")
            match = tools.verify_evidence(
                "LF2026001", "蓝牙耳机 图书馆 2026-06-28 盒内刻有ZL"
            )
            claim = tools.create_claim("LF2026001", "u001", match["match_score"])
            queried_claim = tools.query_claim(claim["claim_id"], "u001")
            slots = tools.list_handover_slots("LF2026001")
            approved = tools.approve_claim(claim["claim_id"])
            appointment = tools.create_appointment(
                claim["claim_id"], "LF2026001", "u001", slots[0]
            )
            queried_appointment = tools.query_appointment(claim["claim_id"], "u001")

        self.assertEqual([value["item_id"] for value in items], ["LF2026001"])
        self.assertEqual(item["item_id"], "LF2026001")
        self.assertEqual(match["match_score"], 100)
        self.assertEqual(queried_claim["claim_id"], "CL0001")
        self.assertEqual(approved["status"], "已通过")
        self.assertGreater(len(slots), 0)
        self.assertEqual(appointment["appointment_id"], "AP0001")
        self.assertEqual(queried_appointment["claim_id"], "CL0001")

    def test_model_tool_schema_is_read_only(self):
        names = [entry["function"]["name"] for entry in tools.TOOLS]
        self.assertEqual(
            names,
            [
                "search_items",
                "query_item",
                "query_claim",
                "list_handover_slots",
                "search_policy",
            ],
        )
        self.assertIn("verify_evidence", tools.FUNCS)
        self.assertIn("create_claim", tools.FUNCS)
        self.assertIn("approve_claim", tools.FUNCS)
        self.assertIn("create_appointment", tools.FUNCS)
        self.assertNotIn("verify_evidence", names)
        self.assertNotIn("create_appointment", names)

    def test_unavailable_service_returns_controlled_error(self):
        original = tools.ITEM_URL
        tools.ITEM_URL = "http://127.0.0.1:1"
        try:
            result = tools.query_item("LF2026001")
        finally:
            tools.ITEM_URL = original

        self.assertIn("error", result)
        self.assertIn("失物服务不可用", result["error"])


class IntentTests(unittest.TestCase):
    def test_detects_search_intent_and_description_entities(self):
        result = detect_intent("我在图书馆丢了黑色耳机")

        self.assertEqual(result["intent"], "寻物")
        self.assertEqual(result["entities"]["location"], "图书馆")
        self.assertEqual(result["entities"]["category"], "耳机")
        self.assertEqual(result["entities"]["color"], "黑色")

    def test_detects_claim_intent_and_item_id(self):
        result = detect_intent("我要认领 LF2026001")

        self.assertEqual(result["intent"], "认领")
        self.assertEqual(result["entities"]["item_id"], "LF2026001")

    def test_detects_handover_intent(self):
        result = detect_intent("查看 LF2026001 的交接时段")

        self.assertEqual(result["intent"], "交接")
        self.assertEqual(result["entities"]["item_id"], "LF2026001")

    def test_detects_colloquial_lost_item_request(self):
        result = detect_intent("我在图书馆遗落了一个黑色蓝牙耳机")

        self.assertEqual(result["intent"], "寻物")
        self.assertEqual(result["entities"]["location"], "图书馆")
        self.assertEqual(result["entities"]["category"], "耳机")
        self.assertEqual(result["entities"]["color"], "黑色")

    def test_detects_colloquial_claim_status_query(self):
        result = detect_intent("想查 CL0001 现在处理到哪了")

        self.assertEqual(result["intent"], "认领")
        self.assertEqual(result["entities"]["claim_id"], "CL0001")

    def test_detects_colloquial_handover_request(self):
        result = detect_intent("LF2026001 可以什么时候去取")

        self.assertEqual(result["intent"], "交接")
        self.assertEqual(result["entities"]["item_id"], "LF2026001")

    def test_detects_colloquial_policy_question(self):
        result = detect_intent("电脑这种贵重物品为啥要人工审核")

        self.assertEqual(result["intent"], "规则咨询")
        self.assertEqual(result["entities"]["category"], "笔记本电脑")


class ReactAgentTests(unittest.TestCase):
    def test_react_queries_item_then_handover_slots(self):
        with running_server(ItemHandler) as item_base, running_server(
            HandoverHandler
        ) as handover_base:
            tools.ITEM_URL = item_base
            tools.HANDOVER_URL = handover_base
            trace = io.StringIO()
            with contextlib.redirect_stdout(trace):
                answer = react_agent(
                    "查一下 LF2026001 是什么，并看看有哪些交接时段",
                    verbose=True,
                )

        output = trace.getvalue()
        self.assertIn("query_item", output)
        self.assertIn("list_handover_slots", output)
        self.assertLess(output.index("query_item"), output.index("list_handover_slots"))
        self.assertIn("LF2026001", answer)
        self.assertIn("图书馆服务台", answer)

    def test_react_searches_colloquial_lost_item(self):
        with running_server(ItemHandler) as item_base:
            tools.ITEM_URL = item_base
            trace = io.StringIO()
            with contextlib.redirect_stdout(trace):
                answer = react_agent(
                    "我在图书馆遗落了一个黑色蓝牙耳机",
                    verbose=True,
                )

        output = trace.getvalue()
        self.assertIn("search_items", output)
        self.assertIn("LF2026001", answer)

    def test_react_lists_slots_for_colloquial_pickup_request(self):
        with running_server(ItemHandler) as item_base, running_server(
            HandoverHandler
        ) as handover_base:
            tools.ITEM_URL = item_base
            tools.HANDOVER_URL = handover_base
            trace = io.StringIO()
            with contextlib.redirect_stdout(trace):
                answer = react_agent(
                    "LF2026001 可以什么时候去取",
                    verbose=True,
                )

        output = trace.getvalue()
        self.assertIn("query_item", output)
        self.assertIn("list_handover_slots", output)
        self.assertIn("图书馆服务台", answer)

    def test_orchestrate_answers_colloquial_policy_question(self):
        result = orchestrate("电脑这种贵重物品为啥要人工审核", verbose=False)

        self.assertEqual(result["intent"], "规则咨询")
        self.assertIn("人工复核", result["answer"])


if __name__ == "__main__":
    unittest.main()
