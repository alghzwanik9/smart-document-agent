from pathlib import Path
import runpy

target = Path(__file__).resolve().parent.parent / "frontend" / "views" / "1_Document_Details.py"
runpy.run_path(str(target), run_name="__main__")
