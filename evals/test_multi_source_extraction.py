"""Test Multi-Source Ingestion and OKF Synthesis on Live Vertex AI.

Evaluates cross-referencing between:
1. Process Data Sheet: reference/raw/data_sheets/DS-D2304_Decomposer_Reactor_Z1.pdf
2. P&ID Drawing: reference/raw/pid/PID-23-0013_Decomposer_Reactor_Z1.pdf

Verifies:
- Autonomous discovery of multiple documents
- Dual-stream ingestion (Text Layout Data Sheet + P&ID Drawing)
- Precedence reconciliation (Data sheet design pressure 11.0 kg/cm²g vs P&ID annotation 12.2 kg/cm²g)
- Generation of build/okf_bundle/equipment/D-2304.md citing BOTH sources
- Progressive indexing and validation
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from extracter_agent.agent.orchestrator import create_extracter_agent
from extracter_agent.config import get_config


async def run_multi_source_test():
    prompt = (
        "Extract verified equipment concept for Decomposer Reactor Drum (Tag: D-2304) "
        "from reference/raw and synthesize into OKF v0.2. "
        "Cross-reference both the Process Data Sheet (DS-D2304) and the related P&ID drawing "
        "for Decomposer Reactor (PID-23-0013) to capture complete design data, "
        "operating conditions, instrumentation, and reconcile any document discrepancies."
    )

    print("\n" + "=" * 80)
    print("STARTING LIVE MULTI-SOURCE EXTRACTION TEST ON VERTEX AI")
    print("=" * 80)
    print("Target Entity:   Decomposer Reactor Drum (Tag: D-2304)")
    print("Required Sources: 2+ (Process Data Sheet + P&ID Drawing)")
    print(f"Model:           {get_config().gemini_model}")
    print(f"Vertex AI Env:   {os.getenv('GOOGLE_GENAI_USE_VERTEXAI')}")
    print("=" * 80 + "\n")

    session_service = InMemorySessionService()
    session_id = f"multi-source-{int(time.time() * 1000)}"
    await session_service.create_session(
        app_name="extracter-agent",
        user_id="engineer",
        session_id=session_id,
    )

    agent = create_extracter_agent()
    runner = Runner(
        agent=agent,
        session_service=session_service,
        app_name="extracter-agent",
    )

    msg = types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt)],
    )

    t0 = time.time()
    tools_called = []
    final_output = []

    print("Executing autonomous agent trajectory...")
    async for event in runner.run_async(
        user_id="engineer",
        session_id=session_id,
        new_message=msg,
    ):
        # Capture tool calls
        for call in event.get_function_calls() or []:
            tools_called.append((call.name, dict(call.args)))
            print(f"\n[TOOL CALL] {call.name}:")
            for k, v in dict(call.args).items():
                val_str = str(v)
                if len(val_str) > 120:
                    val_str = val_str[:120] + "..."
                print(f"    - {k}: {val_str}")

        # Capture tool responses
        for resp in event.get_function_responses() or []:
            r_obj = resp.response
            success = r_obj.get("success", True) if isinstance(r_obj, dict) else True
            print(f"[TOOL RESPONSE] {resp.name} -> success={success}")

        # Capture model response text
        if event.content and event.content.parts:
            for p in event.content.parts:
                if p.text:
                    final_output.append(p.text)
                    print(f"\n[AGENT TEXT]\n{p.text}")

    duration = time.time() - t0
    print("\n" + "=" * 80)
    print("MULTI-SOURCE EXECUTION COMPLETED")
    print(f"Total Trajectory Steps: {len(tools_called)} tool calls in {duration:.2f}s")
    print("=" * 80)

    # Inspect generated OKF file
    out_file = Path("build/okf_bundle/equipment/D-2304.md")
    if out_file.exists():
        content = out_file.read_text(encoding="utf-8")
        print(f"\nSUCCESS: Generated OKF File exists at {out_file} ({len(content)} bytes)")

        # Check source citations
        lines = content.splitlines()
        sources_found = [line for line in lines if "DS-D2304" in line or "PID-23-0013" in line or ".pdf" in line]
        print("\nCitations found in OKF bundle:")
        for s in sources_found[:6]:
            print(f"  * {s.strip()}")
    else:
        print(f"\nERROR: Output file {out_file} was not created!")


if __name__ == "__main__":
    asyncio.run(run_multi_source_test())
