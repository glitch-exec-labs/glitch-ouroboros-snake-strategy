# MT5 Track

This folder contains the current MT5-oriented implementation of Ouroboros Snake Strategy.

## Included

- six snake bot entrypoints
- Oracle
- shared modules
- sanitized config templates

## Intent

This is the current executable reference implementation of the flagship ensemble.

## Layout Note

The bot entrypoints preserve their original runtime expectations:

- `mt5/bots/` contains the executable bot files
- `mt5/bots/pro_modules/` contains the runtime support modules those bots import directly
- `mt5/shared/` mirrors the shared module set for reference and architecture visibility
