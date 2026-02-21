"""
Main orchestrator — runs FastAPI server + Telegram bot.
Stub for Phase 1; will be fully implemented in Phase 2.
"""

import os


APP_NAME = os.getenv("BRG_APP_NAME", "KidsTube")


def main():
    print(f"Starting {APP_NAME} server...")


if __name__ == "__main__":
    main()
