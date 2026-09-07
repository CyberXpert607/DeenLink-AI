import pytest
from httpx import AsyncClient, ASGITransport
import os
import sys

# Add src/backend/api to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src/backend/api'))

from main import app
from v2.stellar.service import build_payment_transaction, verify_payment
from config import STELLAR_PAYMENTS_ENABLED
import config
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

# Mock JWT token for auth
def mock_verify_jwt():
    return {"user_id": "test_user"}

# Override the dependency in the app for testing
from v2.auth import verify_jwt
app.dependency_overrides[verify_jwt] = mock_verify_jwt

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.asyncio
async def test_stellar_disabled_by_default():
    # Force disable for this test
    original = config.STELLAR_PAYMENTS_ENABLED
    config.STELLAR_PAYMENTS_ENABLED = False
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/config/features")
        assert response.status_code == 200
        assert response.json()["stellar_payments"] is False

        # Attempt to access stellar.toml
        response = await ac.get("/.well-known/stellar.toml")
        assert response.status_code == 404
        
        # Test a stellar route directly (it might not be mounted, giving 404, or if it is mounted but disabled it raises 404)
        response = await ac.get("/api/stellar/wallet/info")
        assert response.status_code == 404
        
    config.STELLAR_PAYMENTS_ENABLED = original

@pytest.mark.asyncio
async def test_stellar_enabled_features():
    original = config.STELLAR_PAYMENTS_ENABLED
    config.STELLAR_PAYMENTS_ENABLED = True
    config.STELLAR_PLATFORM_PUBLIC_KEY = "GDQJUTQYK2MQX2VGDR2FYWLIYAQIEGXTQVTFEMGH2BEWFG4BRCEWE5IL"
    
    # We must ensure the router is mounted. The app initialization already happened, so we test the endpoints directly by calling the router logic or re-importing.
    # To simplify, we can test the service functions directly if the router wasn't mounted during app init.
    
    # Test service logic
    with patch("v2.stellar.service.get_server") as mock_get_server:
        mock_server = MagicMock()
        
        # Mock account response for sequence number
        mock_server.accounts().account_id().call.return_value = {"sequence": "123456789"}
        mock_get_server.return_value = mock_server
        
        # Build TX
        sender_pk = "GA2HGBJIJKI6O4XEM7CZWY5PS6GKSXL6D34ERAJYQSPYA6X6AI7NJW36"
        xdr = await build_payment_transaction(sender_pk, "10", "Test Memo")
        assert xdr is not None
        assert isinstance(xdr, str)
        assert len(xdr) > 20
        
        # Verify Payment
        mock_server.transactions().transaction().call.return_value = {"successful": True}
        mock_server.operations().for_transaction().call.return_value = {
            "_embedded": {
                "records": [
                    {
                        "type": "payment",
                        "to": "GDQJUTQYK2MQX2VGDR2FYWLIYAQIEGXTQVTFEMGH2BEWFG4BRCEWE5IL",
                        "amount": "10.0000000"
                    }
                ]
            }
        }
        
        is_valid = await verify_payment("fake_hash", 10.0)
        assert is_valid is True

        is_valid_fail = await verify_payment("fake_hash", 20.0)
        assert is_valid_fail is False

    config.STELLAR_PAYMENTS_ENABLED = original
