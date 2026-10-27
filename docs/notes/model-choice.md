# Agent model choice (M2)

The agent runs on `openai/gpt-oss-120b` on Groq with `gemini-3.5-flash` as the failover; model IDs live only in
`.env`. In a one-pass manual check on 2026-10-27 (flagship booking, party of 9, UNKNOWN allergen, ambiguous
"pesto"; not an eval), `gpt-oss-120b` was the only candidate with correct tool calls in all four: it asked
which pesto was meant, handed off the party of 9 and booked only after the readback was confirmed.
`gpt-oss-20b` was slightly faster per raw request (0.58 s vs 0.76 s) but answered for Pesto Genovese without
asking and misspelled the confirmation code; `qwen/qwen3.8-27b` failed with HTTP 400 in Groq's chat template
(probably the `developer` role), and `llama-3.3-70b-versatile` is no longer offered. Both Groq models share
the free-tier cap of 8,000 tokens per minute (~2k tokens per request), which dominates latency in
back-to-back turns, and `gemini-3.8-flash` timed out on every request with this key, hence 3.5 Flash.
