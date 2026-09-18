"""Shared core for the Riders picks league.

Imported by the Vercel API functions, the Discord bot, and the cron scripts so
there is exactly one definition of a pick, one team resolver, and one grader.
"""

__all__ = ["teams", "schema", "grading", "espn", "db"]
