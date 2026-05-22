import io
from contextlib import redirect_stdout
from pathlib import Path

import agent


ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "demo_memory.db"


def run_demo(script_name: str, output_name: str, reset_memory: bool = False) -> None:
    if reset_memory and DB_PATH.exists():
        DB_PATH.unlink()
    memory = agent.MemoryStore(DB_PATH)
    model = agent.ScriptedModelClient()
    session_id = output_name.replace(".txt", "")
    app = agent.Agent(memory=memory, model_client=model, session_id=session_id)
    script_lines = [
        line.strip()
        for line in (ROOT / "demo_inputs" / script_name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        agent.interactive_session(app, scripted_inputs=script_lines)
    (ROOT / output_name).write_text(buffer.getvalue(), encoding="utf-8")
    memory.close()


def main() -> None:
    run_demo("session1.in", "session1.txt", reset_memory=True)
    run_demo("session2.in", "session2.txt", reset_memory=False)


if __name__ == "__main__":
    main()
