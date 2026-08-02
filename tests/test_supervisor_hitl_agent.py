# tests/test_supervisor_hitl_agent.py
"""Tests for customer verification in the supervisor HITL agent."""

import pytest
from langchain_community.utilities import SQLDatabase
from sqlalchemy import create_engine, text

from agents.supervisor_hitl_agent import CustomerInfo, validate_customer_email


@pytest.fixture
def db() -> SQLDatabase:
    """In-memory customers table with a single known customer."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE customers (customer_id TEXT, email TEXT, name TEXT)")
        )
        connection.execute(
            text(
                "INSERT INTO customers VALUES ('CUST-001', 'alice@example.com', 'Alice')"
            )
        )
    return SQLDatabase(engine)


def test_validate_customer_email_returns_customer(db: SQLDatabase) -> None:
    assert validate_customer_email("alice@example.com", db) == CustomerInfo(
        customer_id="CUST-001", customer_name="Alice"
    )


@pytest.mark.parametrize(
    "email",
    [
        "anything@example.com' OR '1'='1",
        "' OR '1'='1' --@example.com",
        "alice@example.com'; DROP TABLE customers; --",
    ],
)
def test_validate_customer_email_rejects_sql_injection(
    email: str, db: SQLDatabase
) -> None:
    assert validate_customer_email(email, db) is None


def test_validate_customer_email_rejects_unknown_email(db: SQLDatabase) -> None:
    assert validate_customer_email("mallory@example.com", db) is None
