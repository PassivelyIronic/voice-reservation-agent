# Agent model choice (M2)

The agent runs on `openai/gpt-oss-120b` on Groq with `gemini-3.5-flash-lite` as the failover; model IDs live only
in `.env`. In a one-pass manual check on 2026-10-27 (flagship booking, party of 9, UNKNOWN allergen, ambiguous
"pesto"; not an eval), `gpt-oss-120b` was the only Groq candidate with correct tool calls in all four, while
`gpt-oss-20b` answered for Pesto Genovese without asking, `qwen/qwen3.8-27b` failed with HTTP 400 in Groq's chat
template, and `llama-3.3-70b-versatile` is no longer offered. Groq's free tier caps both gpt-oss models at
8,000 tokens per minute (~2k per request), so back-to-back turns hit 429 and fail over to Gemini often, which
makes the fallback matter. On Gemini's free tier `gemini-3.5-flash` allows only 20 requests per day (counted as
`gemini-3.6-flash`) and 3.7/3.8 Flash never answered within 45 s, so Flash-Lite (0.6-0.9 s, correct tool calls in
all four checks) is the failover even though it paraphrases allergen answers, which the guard then replaces.
