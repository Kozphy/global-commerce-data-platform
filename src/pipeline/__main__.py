"""Allow ``python -m pipeline`` and ``python -m pipeline.run``."""

from pipeline.run import main

if __name__ == "__main__":
    raise SystemExit(main())
