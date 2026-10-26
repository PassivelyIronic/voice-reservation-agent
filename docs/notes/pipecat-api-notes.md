# Pipecat API notes

Pipecat **1.14.0**, checked with the Pipecat Context Hub on 2026-10-26. All imports below pass
`check_deprecation`.

## (a) Function-call handlers
- Preferred: list tools in `LLMContext(tools=[...])`. Each tool is a `FunctionSchema(name, description,
  properties, required, handler=...)` with the handler bundled, so `register_function` is not needed.
  Handler: `async def h(params: FunctionCallParams)`, result via `await params.result_callback(dict)`.
- We use `FunctionSchema`, not direct functions: the direct-function schema generator does not map
  `Literal` to a JSON-schema `enum`, and 05-tools-spec relies on enums.
- `run_in_parallel=True` and `group_parallel_tools=True` are the defaults: several tool calls in one
  step run together and the LLM is triggered once afterwards (multi-intent, E17).
- Tools listed in the context work on whichever LLM is active in an `LLMSwitcher`.
- Docs: https://docs.pipecat.ai/pipecat/learn/function-calling.md

## (b) Text mode without STT/TTS (no ADR-0006 fallback needed)
- Pipeline: `user_aggregator → LLMSwitcher → AllergenClaimGuard → TextOutput → assistant_aggregator`,
  no transport. Run with `PipelineWorker` + `WorkerRunner` (`PipelineTask` is a deprecated alias).
- User input: `worker.queue_frame(LLMMessagesTransformFrame(transform=..., run_llm=True))`. The transform
  drops the previous `BOOKING STATE` developer message and appends the fresh one plus the user message.
  `LLMMessagesAppendFrame` would also work, but it cannot replace the old state message.
- `LLMAssistantAggregator._handle_text` aggregates any `TextFrame` (including `LLMTextFrame`), so with no
  TTS the context records the text **after** the guard.
- End of a bot reply: a `LLMFullResponseEndFrame` from a response that did not start function calls
  (`FunctionCallsStartedFrame` means another LLM response with the results follows).
- System prompt: `system_instruction` in the service `Settings` (a `"system"` message in the context is
  deprecated since 1.9.0). Per-turn state goes in a `"developer"` message instead.
- Docs: https://docs.pipecat.ai/api-reference/server/pipeline/pipeline-worker.md,
  https://docs.pipecat.ai/pipecat/learn/context-management.md

## (c) Failover
- `LLMSwitcher(llms=[groq, gemini], strategy_type=...)`.
- The built-in `ServiceSwitcherStrategyFailover` switches **only** when the active service becomes
  unusable (`is_usable=False`: rejected key, unknown model). A 429 does not switch.
- E5 needs failover on 429s, so `providers/llm.py` subclasses it (`FailoverOnTransientErrors`) and
  also switches on `ErrorFrame.category` in `RATE_LIMIT`, `QUOTA`, `CONNECTIVITY`, `SERVER`
  (`pipecat.utils.errors.ErrorCategory`). It uses the base class's `_set_active_if_available`.
- Docs: https://docs.pipecat.ai/api-reference/server/utilities/service-switchers/service-switcher.md,
  https://docs.pipecat.ai/api-reference/server/utilities/service-switchers/llm-switcher.md

## (d) Custom FrameProcessor (the guard)
- Subclass `FrameProcessor`; call `super().__init__()` and `await super().process_frame(frame, direction)`;
  push every frame on.
- `InterruptionFrame` is a `SystemFrame`, handled immediately: the guard clears its buffer without
  emitting it. Text that never reached the output does not reach the context either.
- Tests: `pipecat.tests.utils.run_test(processor, frames_to_send=[...])` returns the frames pushed
  downstream/upstream. System frames overtake queued data frames there, so put a `SleepFrame` between
  text and an `InterruptionFrame` to reproduce real ordering.
- Docs: https://docs.pipecat.ai/pipecat/fundamentals/custom-frame-processor.md,
  https://docs.pipecat.ai/pipecat/fundamentals/interruptions.md

## Gaps
- Pipecat ships no mock LLM service. An offline test of the full text pipeline needs the replay
  cassettes planned for M3.
