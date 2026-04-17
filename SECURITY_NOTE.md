# SECURITY NOTE — read before reactivating

**Date:** 2026-04-17

This project is currently dormant. Before picking it back up, you MUST create a fresh Brave Search API key. Do NOT reuse the value that used to live in this repo — it was leaked publicly and is compromised.

## What was leaked

| Secret | Where it used to live | Status |
|---|---|---|
| Brave Search `BRAVE_API_KEY` | `mt5/bots/news_guard.py` (HEAD) | Removed from HEAD. Still visible in git history. **Treat as compromised.** |

## Reactivation checklist

1. Revoke the old Brave key at https://api.search.brave.com/app/keys (if not already).
2. Create a fresh key.
3. Put it in a `.env` (gitignored) — never back in source.
4. Required env var for `news_guard.py`: `BRAVE_API_KEY`.

## Optional: scrub git history

The old key is still visible in the commit history of this public repo. Rotation is what saves you, not the scrub — but if you want to remove it from history too, run:

```bash
pip install git-filter-repo
git filter-repo --replace-text <(echo 'BSA6fJYRU5hT2r55TvOgAxmvMfmcbbP==>***REMOVED***')
git push --force origin --all --tags
```

Then open a GitHub Support ticket asking them to purge cached views.
