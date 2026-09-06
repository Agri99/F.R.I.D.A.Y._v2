"""
cli.py — Master CLI Router for F.R.I.D.A.Y. v2

Routes commands like:
  friday doctor
  friday test-fault
  friday (starts the main loop)
"""
import sys
from pathlib import Path

# Ensure src/ and root are in sys.path when invoked directly
_SRC_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _SRC_DIR.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "doctor":
            from scripts.doctor import run_diagnostics
            # Remove "doctor" from argv so underlying script doesn't parse it
            sys.argv.pop(1)
            run_diagnostics()
            sys.exit(0)
            
        elif cmd == "test-fault":
            from scripts.test_fault import parser, run_fault_injection
            sys.argv.pop(1)
            args = parser.parse_args()
            sys.exit(run_fault_injection(args))

    # Default route: Start the main app
    from friday.app import main as app_main
    app_main()


if __name__ == "__main__":
    main()
