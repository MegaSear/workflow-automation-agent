import argparse

import uvicorn

from react_agent.backend.logging_config import get_logging_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "react_agent.backend.api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=args.reload,
        log_config=get_logging_config(),
    )


if __name__ == "__main__":
    main()
