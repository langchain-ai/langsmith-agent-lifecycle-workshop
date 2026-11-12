"""Long-term memory namespaces must be strings, whatever type the caller's thread_id is.

Run: uv run python -m unittest tests.test_customer_namespace
"""

import unittest
import uuid
from types import SimpleNamespace

from agents.deep_support_agent import SupportContext, _customer_namespace


def runtime(customer_id=None, thread_id=None):
    return SimpleNamespace(context=SupportContext(customer_id=customer_id), execution_info=SimpleNamespace(thread_id=thread_id))


class CustomerNamespaceTest(unittest.TestCase):
    def test_verified_customer(self):
        self.assertEqual(_customer_namespace(runtime("CUST-003", uuid.uuid4())), ("techhub", "CUST-003"))

    def test_anonymous_with_uuid_thread_id(self):
        thread_id = uuid.uuid4()
        namespace = _customer_namespace(runtime(thread_id=thread_id))
        self.assertEqual(namespace, ("techhub", "anonymous", str(thread_id)))
        self.assertTrue(all(isinstance(part, str) for part in namespace))

    def test_anonymous_without_thread(self):
        self.assertEqual(_customer_namespace(runtime()), ("techhub", "anonymous", "no-thread"))


if __name__ == "__main__":
    unittest.main()
