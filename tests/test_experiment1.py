import importlib.util
import os
import unittest
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BPMN_FILE = PROJECT_ROOT / "flows" / "claim_return.bpmn"
BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
CAMUNDA_NS = "http://camunda.org/schema/1.0/bpmn"


def qn(local_name):
    return f"{{{BPMN_NS}}}{local_name}"


class ExperimentOneBpmnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ET.parse(BPMN_FILE).getroot()
        cls.process = cls.root.find(qn("process"))
        cls.flows = cls.process.findall(qn("sequenceFlow"))

    def test_process_is_named_and_executable(self):
        self.assertEqual(self.process.get("id"), "Process_ClaimReturn")
        self.assertEqual(self.process.get("isExecutable"), "true")

    def test_required_node_counts_and_ids(self):
        starts = self.process.findall(qn("startEvent"))
        ends = self.process.findall(qn("endEvent"))
        service_tasks = self.process.findall(qn("serviceTask"))
        user_tasks = self.process.findall(qn("userTask"))
        gateways = self.process.findall(qn("exclusiveGateway"))

        self.assertEqual(len(starts), 1)
        self.assertEqual(len(ends), 1)
        self.assertEqual(len(service_tasks) + len(user_tasks), 7)
        self.assertEqual(len(gateways), 2)
        self.assertEqual(len(self.flows), 12)

        required_ids = {
            "Start_Claim",
            "Task_QueryItem",
            "Task_VerifyEvidence",
            "Gateway_Match",
            "Task_RequestEvidence",
            "Gateway_HighValue",
            "Task_ManualReview",
            "Task_AutoApprove",
            "Task_CreateHandover",
            "Task_Notify",
            "End_Claim",
        }
        actual_ids = {
            node.get("id")
            for node in self.process
            if node.tag != qn("sequenceFlow")
        }
        self.assertTrue(required_ids.issubset(actual_ids))

    def test_service_tasks_have_expected_delegate_expressions(self):
        expected = {
            "Task_QueryItem": "${h_query_item}",
            "Task_VerifyEvidence": "${h_verify_evidence}",
            "Task_RequestEvidence": "${h_request_evidence}",
            "Task_AutoApprove": "${h_auto_approve}",
            "Task_CreateHandover": "${h_create_handover}",
            "Task_Notify": "${h_notify}",
        }
        delegate_key = f"{{{CAMUNDA_NS}}}delegateExpression"
        actual = {
            task.get("id"): task.get(delegate_key)
            for task in self.process.findall(qn("serviceTask"))
        }
        self.assertEqual(actual, expected)

    def test_gateways_have_condition_and_explicit_default(self):
        expected = {
            "Gateway_Match": {
                "default": "Flow_1oi5m9v",
                "condition": "${match_score >= 80}",
                "conditioned_name": "是",
                "fallback_name": "否",
            },
            "Gateway_HighValue": {
                "default": "Flow_0x0ttpa",
                "condition": "${high_value == True}",
                "conditioned_name": "是",
                "fallback_name": "否",
            },
        }

        for gateway_id, spec in expected.items():
            gateway = self.process.find(
                f"{qn('exclusiveGateway')}[@id='{gateway_id}']"
            )
            self.assertIsNotNone(gateway)
            self.assertEqual(gateway.get("default"), spec["default"])

            outgoing = [
                flow for flow in self.flows if flow.get("sourceRef") == gateway_id
            ]
            conditioned = [
                flow for flow in outgoing if flow.find(qn("conditionExpression")) is not None
            ]
            fallback = [
                flow for flow in outgoing if flow.find(qn("conditionExpression")) is None
            ]
            self.assertEqual(len(conditioned), 1)
            self.assertEqual(len(fallback), 1)
            self.assertEqual(conditioned[0].get("name"), spec["conditioned_name"])
            self.assertEqual(fallback[0].get("name"), spec["fallback_name"])
            self.assertEqual(
                conditioned[0].find(qn("conditionExpression")).text.strip(),
                spec["condition"],
            )

    def test_all_sequence_flow_references_are_valid(self):
        node_ids = {
            node.get("id")
            for node in self.process
            if node.tag != qn("sequenceFlow")
        }
        for flow in self.flows:
            self.assertIn(flow.get("sourceRef"), node_ids)
            self.assertIn(flow.get("targetRef"), node_ids)


class ExperimentOneLlmTests(unittest.TestCase):
    def test_mock_greeting_matches_lost_and_found_domain(self):
        module_path = PROJECT_ROOT / "llm.py"
        spec = importlib.util.spec_from_file_location("lost_found_llm", module_path)
        llm = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            spec.loader.exec_module(llm)

        client = llm.MockLLM()
        message = client.chat.completions.create(
            messages=[{"role": "user", "content": "你好"}]
        ).choices[0].message.content

        self.assertIn("失物", message)
        self.assertIn("认领", message)
        self.assertNotIn("订单", message)

    def test_loading_dotenv_closes_the_config_file(self):
        module_path = PROJECT_ROOT / "llm.py"
        spec = importlib.util.spec_from_file_location("lost_found_llm_resource", module_path)
        llm = importlib.util.module_from_spec(spec)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
                spec.loader.exec_module(llm)

        resource_warnings = [
            warning
            for warning in caught
            if issubclass(warning.category, ResourceWarning)
        ]
        self.assertEqual(resource_warnings, [])


if __name__ == "__main__":
    unittest.main()
