from pydantic import BaseModel, field_validator


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def email_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("email must not be empty")
        return v.strip()


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str | None = None
