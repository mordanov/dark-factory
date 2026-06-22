# Contract: Nginx Routing Rules

**Config**: `infra/nginx/nginx.conf.template` (rendered via `envsubst` at startup)

## Server Blocks

### Prompt Studio (user-input-manager)

```nginx
server {
    listen 80;
    server_name $UIM_HOST;

    # Certbot ACME challenge (always present)
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # API proxy → backend
    location /api/ {
        proxy_pass http://user-input-manager:8001;
        include /etc/nginx/snippets/proxy.conf;
    }

    # Frontend SPA (fallback to index.html for client-side routing)
    location / {
        root /var/www/uim;
        try_files $uri $uri/ /index.html;
    }

    # SSL (commented — enable after certbot)
    # listen 443 ssl;
    # include /etc/nginx/snippets/ssl.conf;
    # ssl_certificate /etc/letsencrypt/live/$UIM_HOST/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/$UIM_HOST/privkey.pem;
}

# HTTP→HTTPS redirect (commented — enable after certbot)
# server {
#     listen 80;
#     server_name $UIM_HOST;
#     return 301 https://$host$request_uri;
# }
```

### Ticket Manager

Same structure as above, substituting `$TM_HOST` and `ticket-manager:8002`.

## Snippet Files

### `snippets/proxy.conf`

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_read_timeout 60s;
proxy_connect_timeout 10s;
```

### `snippets/ssl.conf`

```nginx
# SSL parameters — referenced by server blocks after certbot setup
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers HIGH:!aNULL:!MD5;
ssl_prefer_server_ciphers on;
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;
```

## Invariants

- DNS names MUST be set via `$UIM_HOST` and `$TM_HOST` env vars — never hardcoded.
- Every server block MUST contain `location /.well-known/acme-challenge/`.
- SSL stanza MUST be present but commented until certbot is configured.
- HTTP→HTTPS redirect block MUST be present but commented.
