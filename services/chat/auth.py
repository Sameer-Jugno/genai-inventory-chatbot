"""Cognito authentication helpers (ADR-001 / ADR-011).

- Access-token verification via JWKS (header Bearer auth)
- Email/password login via InitiateAuth (Chainlit browser form)
- First-time visitors: SignUp + admin confirm, then login (self-service POC)
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

import boto3
import jwt
from botocore.exceptions import ClientError
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class AuthenticatedUser:
    sub: str
    username: str | None
    token_use: str
    claims: dict[str, Any]
    access_token: str | None = None


class CognitoJwtVerifier:
    """Verifies Cognito access tokens using the user pool JWKS endpoint."""

    def __init__(self, *, user_pool_id: str, app_client_id: str, region: str) -> None:
        self._user_pool_id = user_pool_id
        self._app_client_id = app_client_id
        self._region = region
        self._issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        self._jwks_url = f"{self._issuer}/.well-known/jwks.json"
        self._jwk_client = PyJWKClient(self._jwks_url, cache_keys=True)
        self._idp = boto3.client("cognito-idp", region_name=region)

    def verify_access_token(self, token: str) -> AuthenticatedUser:
        token = (token or "").strip()
        if not token:
            raise PermissionError("missing bearer token")

        signing_key = self._jwk_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=self._issuer,
            options={
                "require": ["exp", "iss", "sub", "token_use"],
                "verify_aud": False,  # access tokens use client_id, not aud
            },
        )

        token_use = claims.get("token_use")
        if token_use != "access":
            raise PermissionError(f"unexpected token_use={token_use}")

        client_id = claims.get("client_id")
        if client_id != self._app_client_id:
            raise PermissionError("token client_id does not match app client")

        exp = int(claims["exp"])
        if exp < int(time.time()):
            raise PermissionError("token expired")

        return AuthenticatedUser(
            sub=str(claims["sub"]),
            username=claims.get("username"),
            token_use=str(token_use),
            claims=claims,
            access_token=token,
        )

    def authenticate_password(self, username: str, password: str) -> AuthenticatedUser:
        """Browser login. Unknown emails are registered on first successful attempt."""
        username = (username or "").strip()
        password = password or ""
        if not username or not password:
            raise PermissionError("username and password are required")
        if not _EMAIL_RE.match(username):
            raise PermissionError("use an email address as the username")
        _validate_password(password)

        try:
            return self._login(username, password)
        except ClientError as exc:
            if _error_code(exc) not in {
                "NotAuthorizedException",
                "UserNotFoundException",
                "UserNotConfirmedException",
            }:
                raise PermissionError(_error_message(exc)) from exc

        # Existing but unconfirmed → confirm and retry.
        if self._user_exists(username):
            try:
                self._admin_confirm(username)
                return self._login(username, password)
            except ClientError as exc:
                raise PermissionError(
                    "account exists but password is incorrect, or confirmation failed"
                ) from exc

        # Brand-new visitor → create, confirm, login.
        try:
            self._sign_up(username, password)
            self._admin_confirm(username)
            return self._login(username, password)
        except ClientError as exc:
            if _error_code(exc) == "UsernameExistsException":
                raise PermissionError("invalid email or password") from exc
            raise PermissionError(_error_message(exc)) from exc

    def _login(self, username: str, password: str) -> AuthenticatedUser:
        response = self._idp.initiate_auth(
            ClientId=self._app_client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": username,
                "PASSWORD": password,
            },
        )
        result = response.get("AuthenticationResult") or {}
        access_token = result.get("AccessToken")
        if not access_token:
            raise PermissionError("Cognito did not return an access token")
        return self.verify_access_token(access_token)

    def _sign_up(self, username: str, password: str) -> None:
        self._idp.sign_up(
            ClientId=self._app_client_id,
            Username=username,
            Password=password,
            UserAttributes=[
                {"Name": "email", "Value": username},
            ],
        )
        logger.info("cognito_signup_created username=%s", username)

    def _admin_confirm(self, username: str) -> None:
        self._idp.admin_confirm_sign_up(
            UserPoolId=self._user_pool_id,
            Username=username,
        )
        logger.info("cognito_signup_confirmed username=%s", username)

    def _user_exists(self, username: str) -> bool:
        try:
            self._idp.admin_get_user(
                UserPoolId=self._user_pool_id,
                Username=username,
            )
            return True
        except ClientError as exc:
            if _error_code(exc) == "UserNotFoundException":
                return False
            raise

    def ping_jwks(self) -> dict[str, Any]:
        """Connectivity check used by ops; not required on the request path."""
        with urllib.request.urlopen(self._jwks_url, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))


def _error_code(exc: ClientError) -> str:
    return str((exc.response.get("Error") or {}).get("Code") or "")


def _error_message(exc: ClientError) -> str:
    return str((exc.response.get("Error") or {}).get("Message") or exc)


def _validate_password(password: str) -> None:
    """Mirror Cognito pool policy so signup failures are readable in the UI."""
    if len(password) < 8:
        raise PermissionError("password must be at least 8 characters")
    if not re.search(r"[A-Z]", password):
        raise PermissionError("password must include an uppercase letter")
    if not re.search(r"[a-z]", password):
        raise PermissionError("password must include a lowercase letter")
    if not re.search(r"\d", password):
        raise PermissionError("password must include a number")
