"""Windows frozen entry point; supports hidden --background operation."""

from yuanjian_app.application import run_application


if __name__ == "__main__":
    raise SystemExit(run_application())
