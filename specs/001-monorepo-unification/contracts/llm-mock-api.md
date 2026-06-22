# Contract: LLM Mock Server API

**Service name in compose**: `llm-mock`
**Port**: 11434
**Purpose**: Intercept all OpenAI API calls during integration tests

## Endpoints

### POST /v1/chat/completions

Accepts any valid OpenAI chat completions request body and returns a canned response.

**Request**: OpenAI `CreateChatCompletionRequest` (any valid body accepted)

**Response** (always 200):
```json
{
  "id": "mock-chatcmpl-001",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "gpt-4o-mock",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Mock LLM response for integration test"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 8,
    "total_tokens": 18
  }
}
```

### GET /health

**Response** (always 200): `{"status": "ok"}`

## Configuration

Services override `OPENAI_BASE_URL=http://llm-mock:11434/v1` in `docker-compose.test.yml`.
The `openai` Python client respects this environment variable automatically.

## Implementation

Minimal FastAPI application at `integration-tests/llm-mock/main.py`. No authentication
required — test-only service on internal Docker network.
