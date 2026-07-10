import unittest
import contextlib
import io

from agent import orchestrate, router
from bpmn_engine import BpmnExecutionError, load_bpmn, run_bpmn
from bpmn_handlers import run_claim
from data import APPOINTMENTS, CLAIMS
from memory import Memory
from rag import retrieve, retrieve_scored
from services.claim_service import ClaimHandler
import services.handover_service as handover_service
from services.handover_service import HandoverHandler
from services.item_service import ItemHandler
from tests.test_services import running_server
import tools


class RagTests(unittest.TestCase):
    def test_high_value_policy_ranks_first_with_score(self):
        results = retrieve_scored("高价值电脑认领", k=3)

        self.assertGreater(len(results), 0)
        self.assertEqual(results[0][0], "高价值物品")
        self.assertIsInstance(results[0][2], float)
        self.assertGreater(results[0][2], 0.0)

    def test_privacy_policy_is_retrieved_without_exposing_item_secrets(self):
        policies = retrieve("隐藏特征能公开吗", k=2)

        self.assertTrue(any("不得" in policy and "隐藏特征" in policy for policy in policies))

    def test_unknown_query_returns_an_empty_list(self):
        self.assertEqual(retrieve("xyzxyzxyz", k=2), [])


class MemoryTests(unittest.TestCase):
    def test_window_summary_profile_and_recent_item_recall(self):
        memory = Memory(window=2)
        memory.add("user", "我想找失物 LF2026001")
        memory.add("assistant", "收到，我先记录编号。")
        memory.add("user", "它是在图书馆发现的吗？")
        memory.add("assistant", "是的，公开地点是图书馆。")
        memory.remember("preferred_handover", "下午")

        built = memory.build("系统提示")

        self.assertEqual(len(memory.history), 2)
        self.assertIn("LF2026001", memory.summary)
        self.assertEqual(memory.recall_item(), "LF2026001")
        self.assertEqual(built[0], {"role": "system", "content": "系统提示"})
        self.assertTrue(any("preferred_handover" in msg["content"] for msg in built))

    def test_profile_rejects_hidden_evidence_values(self):
        memory = Memory()

        with self.assertRaises(ValueError):
            memory.remember("hidden_evidence", "盒内刻有ZL")


class BpmnEngineTests(unittest.TestCase):
    BPMN_FILE = "flows/claim_return.bpmn"

    def test_loads_delegate_expression_and_default_flow(self):
        nodes, flows, start = load_bpmn(self.BPMN_FILE)

        self.assertEqual(start, "Start_Claim")
        self.assertEqual(nodes["Task_QueryItem"]["impl"], "h_query_item")
        match_gateway = nodes["Gateway_Match"]
        self.assertEqual(match_gateway["default"], "Flow_1oi5m9v")
        self.assertEqual(len([flow for flow in flows if flow["src"] == "Gateway_Match"]), 2)

    def test_executes_all_three_claim_paths(self):
        def marker(name, **values):
            def handle(context):
                context.update(values)
                context.setdefault("visited", []).append(name)
                return name

            return handle

        handlers = {
            "h_query_item": marker("query"),
            "h_verify_evidence": marker("verify"),
            "h_request_evidence": marker("request", result="待补充证据"),
            "Task_ManualReview": marker("manual", result="待人工复核"),
            "h_auto_approve": marker("approve", result="已通过"),
            "h_create_handover": marker("handover", appointment="AP0001"),
            "h_notify": marker("notify", notified=True),
        }
        cases = [
            (
                {"match_score": 100, "high_value": False},
                "已通过",
                True,
                ["选择分支「是」", "选择分支「否」"],
            ),
            (
                {"match_score": 100, "high_value": True},
                "待人工复核",
                False,
                ["选择分支「是」", "选择分支「是」"],
            ),
            (
                {"match_score": 60, "high_value": False},
                "待补充证据",
                False,
                ["选择分支「否」"],
            ),
        ]

        for initial, expected_result, has_appointment, branch_fragments in cases:
            with self.subTest(initial=initial):
                context = dict(initial)
                trace = []
                result = run_bpmn(
                    self.BPMN_FILE, handlers, context, log=trace.append
                )

                self.assertIs(result, context)
                self.assertEqual(context["result"], expected_result)
                self.assertEqual("appointment" in context, has_appointment)
                self.assertTrue(context["notified"])
                joined = "\n".join(trace)
                for fragment in branch_fragments:
                    self.assertIn(fragment, joined)

    def test_missing_handler_is_reported_as_execution_error(self):
        with self.assertRaises(BpmnExecutionError):
            run_bpmn(
                self.BPMN_FILE,
                {},
                {"match_score": 0, "high_value": False},
                log=lambda _message: None,
            )


class BpmnHandlerTests(unittest.TestCase):
    def setUp(self):
        CLAIMS.clear()
        APPOINTMENTS.clear()

    def _run_with_services(self, item_id, user_id, evidence):
        with running_server(ItemHandler) as item_base, running_server(
            ClaimHandler
        ) as claim_base, running_server(HandoverHandler) as handover_base:
            tools.ITEM_URL = item_base
            tools.CLAIM_URL = claim_base
            tools.HANDOVER_URL = handover_base
            handover_service.CLAIM_URL = claim_base
            return run_claim(item_id, user_id, evidence)

    def test_ordinary_item_is_approved_and_scheduled(self):
        final, trace = self._run_with_services(
            "LF2026001",
            "u001",
            "蓝牙耳机 图书馆 2026-06-28 盒内刻有ZL",
        )

        joined = "\n".join(trace)
        self.assertIn("已通过", final)
        self.assertIn("图书馆服务台", final)
        self.assertNotIn("。。", final)
        self.assertIn("网关「证据匹配度≥80？」→ 选择分支「是」", joined)
        self.assertIn("网关「是否高价值物品？」→ 选择分支「否」", joined)
        self.assertIn("impl=h_create_handover", joined)

    def test_high_value_item_goes_to_manual_review(self):
        final, trace = self._run_with_services(
            "LF2026002",
            "u002",
            "笔记本电脑 教学楼 2026-06-27 序列号后四位A7C9",
        )

        joined = "\n".join(trace)
        self.assertIn("待人工复核", final)
        self.assertNotIn("已预约", final)
        self.assertIn("网关「是否高价值物品？」→ 选择分支「是」", joined)
        self.assertIn("任务「人工复核」", joined)

    def test_insufficient_evidence_requests_more_information(self):
        final, trace = self._run_with_services(
            "LF2026003", "u003", "校园卡 食堂 2026-06-29"
        )

        joined = "\n".join(trace)
        self.assertIn("待补充证据", final)
        self.assertNotIn("已预约", final)
        self.assertIn("网关「证据匹配度≥80？」→ 选择分支「否」", joined)
        self.assertIn("impl=h_request_evidence", joined)

    def test_supplemental_evidence_reuses_existing_claim(self):
        with running_server(ItemHandler) as item_base, running_server(
            ClaimHandler
        ) as claim_base, running_server(HandoverHandler) as handover_base:
            tools.ITEM_URL = item_base
            tools.CLAIM_URL = claim_base
            tools.HANDOVER_URL = handover_base
            handover_service.CLAIM_URL = claim_base

            first, _ = run_claim(
                "LF2026001",
                "u001",
                "认领LF2026001 黑色蓝牙耳机(图书馆)",
            )
            second, trace = run_claim(
                "LF2026001",
                "u001",
                '蓝牙耳机 图书馆 盒内刻有ZL", "左耳有划痕',
            )

        joined = "\n".join(trace)
        self.assertIn("待补充证据", first)
        self.assertIn("已通过", second)
        self.assertIn("图书馆服务台", second)
        self.assertIn("复用已有认领单", joined)


class MultiAgentTests(unittest.TestCase):
    def setUp(self):
        CLAIMS.clear()
        APPOINTMENTS.clear()

    def test_policy_tool_and_four_router_destinations(self):
        self.assertIn("search_policy", tools.FUNCS)
        self.assertIn(
            "search_policy", [entry["function"]["name"] for entry in tools.TOOLS]
        )
        self.assertEqual(router("我在图书馆丢了耳机"), "寻物")
        self.assertEqual(router("我要认领 LF2026001"), "认领")
        self.assertEqual(router("查看 LF2026001 的交接时段"), "交接")
        self.assertEqual(router("高价值物品有什么规定"), "规则咨询")

    def test_policy_expert_returns_retrieved_rule(self):
        result = orchestrate("高价值物品有什么规定", verbose=False)

        self.assertEqual(result["intent"], "规则咨询")
        self.assertIn("【规则专家·RAG】", result["answer"])
        self.assertIn("人工复核", result["answer"])

    def test_claim_expert_executes_bpmn_and_services(self):
        with running_server(ItemHandler) as item_base, running_server(
            ClaimHandler
        ) as claim_base, running_server(HandoverHandler) as handover_base:
            tools.ITEM_URL = item_base
            tools.CLAIM_URL = claim_base
            tools.HANDOVER_URL = handover_base
            handover_service.CLAIM_URL = claim_base
            trace = io.StringIO()
            with contextlib.redirect_stdout(trace):
                result = orchestrate(
                    "我要认领 LF2026001，蓝牙耳机在图书馆遗失，"
                    "日期2026-06-28，盒内刻有ZL",
                    user_id="u001",
                    verbose=True,
                )

        output = trace.getvalue()
        self.assertEqual(result["intent"], "认领")
        self.assertIn("【认领专家·BPMN流程】", result["answer"])
        self.assertIn("已通过", result["answer"])
        self.assertIn("h_auto_approve", output)
        self.assertIn("h_create_handover", output)


if __name__ == "__main__":
    unittest.main()
