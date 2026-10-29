"""MCP transport adapter using the same maintained editing engine as the CLI."""
import json
import sys
from candidate_runtime import activate, identity

def main():
    activate()
    if sys.argv[1:] == ['--runtime-info']:
        print(json.dumps(identity(), ensure_ascii=False))
        return
    from hwpx_automation.mcp_cli import main as serve
    serve()

if __name__ == '__main__':
    main()
