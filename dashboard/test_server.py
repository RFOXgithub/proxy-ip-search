import threading
import time
import unittest
from unittest.mock import patch

from dashboard import server


class DashboardIntegrationTests(unittest.TestCase):
    def test_prefixed_process_environment_overrides_local_provider_env(self):
        with patch.dict("os.environ", {
            "OXY_PROXY_USERNAME": "deployment-user",
            "OXY_PROXY_PASSWORD": "deployment-password",
        }, clear=False):
            values = server.env_config("oxy")
        self.assertEqual(values["proxy_username"], "deployment-user")
        self.assertEqual(values["proxy_password"], "deployment-password")

    def test_all_provider_configs_load_without_exposing_secrets(self):
        public = server.public_methods()
        self.assertEqual({item["id"] for item in public}, set(server.METHODS))
        for item in public:
            self.assertNotIn("proxy_password", item["defaults"])
            self.assertNotIn("proxy_username", item["defaults"])
        for key in server.METHODS:
            settings = server.config_for(key, {})
            self.assertTrue(settings.proxy_username)
            self.assertTrue(settings.proxy_password)

    def test_result_shapes_are_normalized(self):
        impulse_match = server.MODULES["impulse"].find_matching_ip.__globals__["Match"](
            "185.30.88.1", 10001, "Baku", "ISP"
        )
        row = server.normalize_result("impulse", impulse_match, time.time())
        self.assertEqual((row["ip"], row["port"], row["source"]),
                         ("185.30.88.1", 10001, "DataImpulse"))
        for key in ("oxy", "royale"):
            row = server.normalize_result(key, {
                "ip": "1.2.3.4", "session": "session1", "city": "N/A", "isp": "N/A"
            }, time.time())
            self.assertEqual(row["session"], "session1")

    def test_optional_filters_can_be_explicitly_cleared(self):
        for key in server.METHODS:
            supplied = {"country": "", "city": ""}
            if "asn" in server.METHODS[key]["fields"]:
                supplied["asn"] = ""
            settings = server.config_for(key, supplied)
            self.assertEqual(settings.country, "")
            self.assertEqual(settings.city, "")
            if hasattr(settings, "asn"):
                self.assertIsNone(settings.asn)

    def test_partial_and_not_found_results_have_safe_fallbacks(self):
        partial = server.normalize_result("oxy", {
            "ip": "1.2.3.4", "session": "abc", "city": None,
        }, time.time())
        self.assertEqual(partial["status_code"], "partial")
        self.assertEqual(partial["city"], server.UNAVAILABLE)
        self.assertEqual(partial["country"], server.UNAVAILABLE)

        settings = server.config_for("oxy", {})
        missing = server.unmatched_result("oxy", settings)
        self.assertEqual(missing["status_code"], "not_found")
        self.assertEqual(missing["asn"], server.UNAVAILABLE)

    def test_non_matching_ips_are_streamed_with_similarity(self):
        job_id, settings = self.make_job("oxy")

        def finder(_settings, _stop, observer):
            observer({"ip": "88.230.99.1", "session": "near1",
                      "city": "Istanbul", "isp": "AS1", "matched": False})
            observer({"ip": "1.2.3.4", "session": "far1",
                      "city": None, "isp": None, "matched": False})
            return None

        with patch.object(server.MODULES["oxy"], "find_matching_ip",
                          side_effect=finder):
            server.run_job(job_id, "oxy", settings)

        rows = server.JOBS[job_id]["results"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["status_code"] == "not_match" for row in rows))
        self.assertGreater(rows[0]["similarity"], rows[1]["similarity"])

    def make_job(self, key):
        job_id = f"test-{key}-{time.time_ns()}"
        settings = server.config_for(key, {"execution_duration": 1})
        server.JOBS[job_id] = {
            "id": job_id, "method": key, "method_name": server.METHODS[key]["name"],
            "status": "queued", "message": "", "results": [], "started_at": time.time(),
            "finished_at": None, "duration": 1.0, "cancel_requested": False,
            "stop": threading.Event(), "thread": None,
        }
        return job_id, settings

    def test_method_failure_is_isolated(self):
        bad_id, bad_settings = self.make_job("oxy")
        good_id, good_settings = self.make_job("impulse")
        with patch.object(server.MODULES["oxy"], "find_matching_ip", side_effect=RuntimeError("boom")):
            server.run_job(bad_id, "oxy", bad_settings)
        match = server.MODULES["impulse"].find_matching_ip.__globals__["Match"](
            "185.30.88.2", 10002, "Baku", "ISP"
        )
        with patch.object(server.MODULES["impulse"], "find_matching_ip", return_value=[match]):
            server.run_job(good_id, "impulse", good_settings)
        self.assertEqual(server.JOBS[bad_id]["status"], "failed")
        self.assertEqual(server.JOBS[good_id]["status"], "completed")
        self.assertEqual(len(server.JOBS[good_id]["results"]), 1)

    def test_cancel_event_is_forwarded(self):
        job_id, settings = self.make_job("royale")
        job = server.JOBS[job_id]
        job["cancel_requested"] = True
        job["stop"].set()
        with patch.object(server.MODULES["royale"], "find_matching_ip", return_value=None) as finder:
            server.run_job(job_id, "royale", settings)
        self.assertIs(finder.call_args.args[1], job["stop"])
        self.assertEqual(job["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
