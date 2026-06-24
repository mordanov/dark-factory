# Contract: nginx auth_request Integration

**Applies to**: `infra/nginx/nginx.conf.template`
**Date**: 2026-06-24

---

## Updated nginx.conf.template Structure

### Changes per application server block (UIM + TM)

```nginx
# Added to EVERY /api/ location block:
location /api/ {
    proxy_pass http://<service>:8000;
    include /etc/nginx/snippets/proxy.conf;

    # NEW: Bearer token validation via oauth2-proxy
    auth_request /oauth2/auth;
    auth_request_set $auth_user $upstream_http_x_auth_request_user;
    auth_request_set $auth_email $upstream_http_x_auth_request_email;

    proxy_set_header X-Auth-User $auth_user;
    proxy_set_header X-Auth-Email $auth_email;

    error_page 401 = @error401;
}

# NEW shared locations (once per server block):
location = /oauth2/auth {
    internal;
    proxy_pass http://oauth2-proxy:4180;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header X-Original-URI $request_uri;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}

location @error401 {
    default_type application/json;
    return 401 '{"detail":"Not authenticated","code":"TOKEN_EXPIRED_OR_INVALID"}';
}

location /oauth2/ {
    proxy_pass http://oauth2-proxy:4180;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### Locations that MUST NOT have auth_request

| Location | Reason |
|----------|--------|
| `location /` | Frontend static files; keycloak-js handles redirect |
| `location /.well-known/` | certbot ACME challenge |
| `location = /oauth2/auth` | Would create infinite loop |
| `location /oauth2/` | oauth2-proxy management endpoints |

---

## oauth2-proxy Configuration: infra/oauth2-proxy/config.cfg

```cfg
provider = "keycloak-oidc"
oidc_issuer_url = "http://keycloak:8080/realms/dark-factory"
client_id = "oauth2-proxy"

set_xauthrequest = true
pass_user_headers = true
pass_access_token = false

email_domains = ["*"]

upstreams = ["http://127.0.0.1:4181"]
http_address = "0.0.0.0:4180"

skip_jwt_bearer_tokens = true

cookie_secure = false
cookie_name = "_oauth2_proxy_df"
```

Secrets injected via docker-compose environment:
- `OAUTH2_PROXY_CLIENT_SECRET` — oauth2-proxy Keycloak client secret
- `OAUTH2_PROXY_COOKIE_SECRET` — 32-byte base64 cookie secret

---

## auth_request Behaviour Contracts

### C-NGINX-01: Valid Bearer token passes through
- Request has `Authorization: Bearer <valid_token>`
- oauth2-proxy validates against Keycloak JWKS → 200
- nginx forwards request to backend with `X-Auth-User` and `X-Auth-Email` headers set

### C-NGINX-02: Invalid/expired token returns 401 JSON
- Request has `Authorization: Bearer <expired_token>` or missing Authorization
- oauth2-proxy returns 401 → nginx routes to `@error401`
- Response: `HTTP 401 {"detail":"Not authenticated","code":"TOKEN_EXPIRED_OR_INVALID"}`
- Response is JSON, NOT an HTML redirect (critical for API clients)

### C-NGINX-03: Frontend routes are unprotected by nginx
- Request to `GET /` or `/projects` → served by frontend container
- No `auth_request` → keycloak-js handles authentication in the browser

### C-NGINX-04: Backend services still validate tokens independently
- nginx auth_request is a defense-in-depth layer, not the authoritative validator
- Each backend's `KeycloakValidator` validates the Bearer token again
- Double validation is intentional (nginx boundary check + application-level claims parsing)
