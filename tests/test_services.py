import json
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import HTTPServer

from data import APPOINTMENTS, CLAIMS
from services.claim_service import ClaimHandler
import services.handover_service as handover_service
from services.handover_service import HandoverHandler
from services.item_service import ItemHandler


@contextmanager
def running_server(handler_class):
    server = HTTPServer(("127.0.0.1", 0), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request_json(method, url, payload=None):
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            return response.status, data
    except urllib.error.HTTPError as error:
        data = json.loads(error.read().decode("utf-8"))
        return error.code, data


class ItemServiceTests(unittest.TestCase):
    def test_search_returns_only_matching_public_item(self):
        with running_server(ItemHandler) as base:
            status, items = request_json(
                "GET", f"{base}/items?keyword=%E8%80%B3%E6%9C%BA&location=%E5%9B%BE%E4%B9%A6%E9%A6%86"
            )

        self.assertEqual(status, 200)
        self.assertEqual([item["item_id"] for item in items], ["LF2026001"])
        self.assertNotIn("secret_features", items[0])
        self.assertNotIn("secret_keywords", items[0])

    def test_item_detail_is_public_and_unknown_item_is_404(self):
        with running_server(ItemHandler) as base:
            status, item = request_json("GET", f"{base}/items/LF2026002")
            missing_status, missing = request_json("GET", f"{base}/items/UNKNOWN")

        self.assertEqual(status, 200)
        self.assertEqual(item["item_id"], "LF2026002")
        self.assertNotIn("secret_features", item)
        self.assertNotIn("secret_keywords", item)
        self.assertEqual(missing_status, 404)
        self.assertEqual(missing["error"], "失物不存在")

    def test_match_scores_public_and_hidden_evidence(self):
        with running_server(ItemHandler) as base:
            full_status, full = request_json(
                "POST",
                f"{base}/items/LF2026001/match",
                {"evidence": "蓝牙耳机 图书馆 2026-06-28 盒内刻有ZL"},
            )
            public_status, public = request_json(
                "POST",
                f"{base}/items/LF2026001/match",
                {"evidence": "蓝牙耳机 图书馆 2026-06-28"},
            )

        self.assertEqual(full_status, 200)
        self.assertEqual(full["match_score"], 100)
        self.assertEqual(full["matched_features"], 4)
        self.assertFalse(full["high_value"])
        self.assertEqual(public_status, 200)
        self.assertEqual(public["match_score"], 60)
        self.assertEqual(public["matched_features"], 3)


class ClaimServiceTests(unittest.TestCase):
    def setUp(self):
        CLAIMS.clear()

    def test_create_query_authorize_and_reject_duplicate_claim(self):
        with running_server(ClaimHandler) as base:
            status, claim = request_json(
                "POST",
                f"{base}/claims",
                {"item_id": "LF2026001", "user_id": "u001", "match_score": 100},
            )
            duplicate_status, duplicate = request_json(
                "POST",
                f"{base}/claims",
                {"item_id": "LF2026001", "user_id": "u001", "match_score": 100},
            )
            owner_status, owner_claim = request_json(
                "GET", f"{base}/claims/{claim['claim_id']}?user_id=u001"
            )
            forbidden_status, forbidden = request_json(
                "GET", f"{base}/claims/{claim['claim_id']}?user_id=u002"
            )
            missing_status, missing = request_json(
                "GET", f"{base}/claims/CL9999?user_id=u001"
            )

        self.assertEqual(status, 201)
        self.assertEqual(claim["claim_id"], "CL0001")
        self.assertEqual(claim["status"], "待核验")
        self.assertEqual(duplicate_status, 409)
        self.assertIn("重复", duplicate["error"])
        self.assertEqual(owner_status, 200)
        self.assertEqual(owner_claim["user_id"], "u001")
        self.assertEqual(forbidden_status, 403)
        self.assertIn("无权", forbidden["error"])
        self.assertEqual(missing_status, 404)
        self.assertEqual(missing["error"], "认领单不存在")

    def test_status_endpoints_and_invalid_payload(self):
        with running_server(ClaimHandler) as base:
            invalid_status, invalid = request_json("POST", f"{base}/claims", {})
            _, claim = request_json(
                "POST",
                f"{base}/claims",
                {"item_id": "LF2026002", "user_id": "u002", "match_score": 100},
            )
            manual_status, manual = request_json(
                "POST", f"{base}/claims/{claim['claim_id']}/manual-review", {}
            )
            evidence_status, evidence = request_json(
                "POST", f"{base}/claims/{claim['claim_id']}/request-evidence", {}
            )
            approve_status, approved = request_json(
                "POST", f"{base}/claims/{claim['claim_id']}/approve", {}
            )

        self.assertEqual(invalid_status, 400)
        self.assertIn("缺少", invalid["error"])
        self.assertEqual(manual_status, 200)
        self.assertEqual(manual["status"], "待人工复核")
        self.assertEqual(evidence_status, 200)
        self.assertEqual(evidence["status"], "待补充证据")
        self.assertEqual(approve_status, 200)
        self.assertEqual(approved["status"], "已通过")


class HandoverServiceTests(unittest.TestCase):
    def setUp(self):
        CLAIMS.clear()
        APPOINTMENTS.clear()

    def test_slots_create_query_authorize_and_reject_duplicate(self):
        with running_server(ClaimHandler) as claim_base, running_server(
            HandoverHandler
        ) as base:
            handover_service.CLAIM_URL = claim_base
            _, claim = request_json(
                "POST",
                f"{claim_base}/claims",
                {"item_id": "LF2026001", "user_id": "u001", "match_score": 100},
            )
            request_json("POST", f"{claim_base}/claims/{claim['claim_id']}/approve", {})
            slots_status, slots = request_json(
                "GET", f"{base}/slots?item_id=LF2026001"
            )
            status, appointment = request_json(
                "POST",
                f"{base}/appointments",
                {
                    "claim_id": "CL0001",
                    "item_id": "LF2026001",
                    "user_id": "u001",
                    "slot": slots[0],
                },
            )
            duplicate_status, duplicate = request_json(
                "POST",
                f"{base}/appointments",
                {
                    "claim_id": "CL0001",
                    "item_id": "LF2026001",
                    "user_id": "u001",
                    "slot": slots[0],
                },
            )
            owner_status, owner_appointment = request_json(
                "GET", f"{base}/appointments/CL0001?user_id=u001"
            )
            forbidden_status, forbidden = request_json(
                "GET", f"{base}/appointments/CL0001?user_id=u002"
            )

        self.assertEqual(slots_status, 200)
        self.assertGreater(len(slots), 0)
        self.assertEqual(status, 201)
        self.assertEqual(appointment["appointment_id"], "AP0001")
        self.assertEqual(duplicate_status, 409)
        self.assertIn("重复", duplicate["error"])
        self.assertEqual(owner_status, 200)
        self.assertEqual(owner_appointment["claim_id"], "CL0001")
        self.assertEqual(forbidden_status, 403)
        self.assertIn("无权", forbidden["error"])

    def test_rejects_unknown_slot_unapproved_claim_and_missing_appointment(self):
        with running_server(ClaimHandler) as claim_base, running_server(
            HandoverHandler
        ) as base:
            handover_service.CLAIM_URL = claim_base
            request_json(
                "POST",
                f"{claim_base}/claims",
                {"item_id": "LF2026001", "user_id": "u001", "match_score": 60},
            )
            unapproved_status, unapproved = request_json(
                "POST",
                f"{base}/appointments",
                {
                    "claim_id": "CL0001",
                    "item_id": "LF2026001",
                    "user_id": "u001",
                    "slot": "2026-06-30 16:00 图书馆服务台",
                },
            )
            missing_status, missing = request_json(
                "GET", f"{base}/appointments/CL9999?user_id=u001"
            )

        self.assertEqual(unapproved_status, 409)
        self.assertIn("未通过", unapproved["error"])
        self.assertEqual(missing_status, 404)
        self.assertEqual(missing["error"], "交接预约不存在")

    def test_reads_approved_claim_over_http_when_memory_is_isolated(self):
        with running_server(ClaimHandler) as claim_base, running_server(
            HandoverHandler
        ) as handover_base:
            handover_service.CLAIM_URL = claim_base
            _, claim = request_json(
                "POST",
                f"{claim_base}/claims",
                {"item_id": "LF2026001", "user_id": "u001", "match_score": 100},
            )
            request_json("POST", f"{claim_base}/claims/{claim['claim_id']}/approve", {})

            original_claims = getattr(handover_service, "CLAIMS", None)
            handover_service.CLAIMS = {}
            try:
                status, appointment = request_json(
                    "POST",
                    f"{handover_base}/appointments",
                    {
                        "claim_id": claim["claim_id"],
                        "item_id": "LF2026001",
                        "user_id": "u001",
                        "slot": "2026-06-30 16:00 图书馆服务台",
                    },
                )
            finally:
                if original_claims is None:
                    delattr(handover_service, "CLAIMS")
                else:
                    handover_service.CLAIMS = original_claims

        self.assertEqual(status, 201)
        self.assertEqual(appointment["claim_id"], "CL0001")


class HealthEndpointTests(unittest.TestCase):
    def test_all_business_services_report_local_health(self):
        for handler in (ItemHandler, ClaimHandler, HandoverHandler):
            with self.subTest(handler=handler.__name__):
                with running_server(handler) as base:
                    status, payload = request_json("GET", base + "/healthz")
                self.assertEqual(status, 200)
                self.assertEqual(payload, {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
