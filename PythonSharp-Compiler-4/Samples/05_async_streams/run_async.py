"""Sample 05: Consuming PythonSharp async generators and streams from Python asyncio."""

import asyncio
import sys
from pathlib import Path

out_dir = Path(__file__).parent / "dist"
sys.path.insert(0, str(out_dir))

from streaming import EventStreamService  # noqa: E402


async def main() -> None:
    print("--- Initializing PythonSharp Async Stream Service ---")
    service = EventStreamService(service_name="TelemetryGateway")

    print(f"Service Name: {service.service_name}")
    print("\nStreaming 5 events over channel 'system-health':")

    async for event in service.stream_events("system-health", 5):
        print(f"  Received: {event}")
        await asyncio.sleep(0.05)

    print("\nAsync stream processing complete.")


if __name__ == "__main__":
    asyncio.run(main())
