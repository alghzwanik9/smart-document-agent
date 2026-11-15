from pathlib import Path
import runpy

target = Path(__file__).resolve().parent.parent / "frontend" / "views" / "3_Yahya_Intake.py"
runpy.run_path(str(target), run_name="__main__")
