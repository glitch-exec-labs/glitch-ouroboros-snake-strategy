"""
MT5 Broker - Safe Wrapper
Connects to existing MT5 without forcing logout
"""
import MetaTrader5 as mt5
import time
import logging

logger = logging.getLogger(__name__)


class MT5Broker:
    """MT5 Broker that works with existing MT5 session"""

    def __init__(self, account, password, server, mt5_path=None, owner_tag=''):
        self.account = account
        self.password = password
        self.server = server
        self.mt5_path = mt5_path
        self.owner_tag = str(owner_tag or '')[:31]
        self.connected = False
        self._already_initialized = False

        # Check if MT5 is already initialized in this process
        try:
            terminal = mt5.terminal_info()
            if terminal is not None:
                logger.info("MT5 already initialized, using existing connection")
                self._already_initialized = True
                self.connected = True
                acc = mt5.account_info()
                if acc and acc.login == account:
                    logger.info(f"Already logged into correct account {account}")
                    return
                elif acc:
                    # A DIFFERENT account is active — never force re-login, that logs out the terminal
                    raise RuntimeError(
                        f"MT5 terminal is logged into account {acc.login}, expected {account}. "
                        f"Please log into account {account} manually in MT5 and restart the bot."
                    )
                else:
                    # Terminal connected but no account — safe to login
                    if not self._login():
                        raise RuntimeError(f"Failed to login to account {account}")
                return
        except RuntimeError:
            raise
        except Exception:
            pass

        # MT5 not initialized in this process yet — initialize then check account
        self._initialize()

        # Give MT5 a moment to settle before checking account
        time.sleep(0.5)
        acc = mt5.account_info()
        if acc and acc.login == account:
            logger.info(f"Connected to correct account {account}")
            return
        elif acc:
            # Already on a different account — do NOT call mt5.login(), it logs out the terminal
            raise RuntimeError(
                f"MT5 terminal is logged into account {acc.login}, expected {account}. "
                f"Please log into account {account} manually in MT5 and restart the bot."
            )
        else:
            # No account active at all — safe to login
            if not self._login():
                raise RuntimeError(f"Failed to login to account {account}")

    def _initialize(self):
        """Initialize MT5"""
        try:
            if self.mt5_path:
                result = mt5.initialize(path=self.mt5_path)
            else:
                result = mt5.initialize()
            
            if result:
                self.connected = True
                logger.info("MT5 initialized successfully")
            else:
                error = mt5.last_error()
                raise RuntimeError(f"MT5 init failed: {error}")
        except Exception as e:
            logger.error(f"Failed to initialize MT5: {e}")
            raise

    def _login(self):
        """Login to account — only called when no account is currently active."""
        try:
            acc = mt5.account_info()
            if acc and acc.login == self.account:
                logger.info(f"Already logged into correct account {self.account}")
                return True
            if acc and acc.login != self.account:
                # Different account is active — never force re-login
                logger.error(
                    f"Cannot login: terminal already has account {acc.login} active, "
                    f"expected {self.account}. Log in manually and restart."
                )
                return False
            # No account active — safe to call mt5.login()
            if mt5.login(self.account, self.password, self.server):
                logger.info(f"Logged into account {self.account}")
                return True
            else:
                error = mt5.last_error()
                logger.error(f"Login failed for account {self.account}: {error}")
                return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    def disconnect(self):
        """Don't shutdown MT5 if we didn't initialize it"""
        if self.connected and not self._already_initialized:
            # Only shutdown if we initialized
            mt5.shutdown()
            logger.info("MT5 shutdown")
        elif self._already_initialized:
            logger.info("Leaving MT5 running (was already initialized)")

    def normalize_price(self, symbol, price):
        info = mt5.symbol_info(symbol)
        if info is None:
            raise ValueError(f"Symbol {symbol} not found")
        return round(price, info.digits)

    def get_symbol_info(self, symbol):
        info = mt5.symbol_info(symbol)
        if info is None:
            raise ValueError(f"Symbol {symbol} not found")
        return {
            'point': info.point,
            'digits': info.digits,
            'spread': info.spread,
            'stops_level': info.trade_stops_level,
            'volume_min': info.volume_min,
            'volume_max': info.volume_max,
            'volume_step': info.volume_step,
            'tick_value': info.trade_tick_value,
            'tick_size': info.trade_tick_size,
        }

    def normalize_volume(self, symbol, volume):
        info = mt5.symbol_info(symbol)
        if info is None:
            raise ValueError(f"Symbol {symbol} not found")
        volume = round(volume / info.volume_step) * info.volume_step
        volume = max(info.volume_min, min(volume, info.volume_max))
        return volume

    def send_order(self, request, max_retries=3):
        for attempt in range(max_retries):
            result = mt5.order_send(request)
            if result is None:
                error = mt5.last_error()
                logger.error(f"Order failed: {error}")
                time.sleep(0.5)
                continue
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                return result
            time.sleep(0.5)
        raise RuntimeError("Order failed after retries")

    def open_position(self, symbol, side, volume, sl=None, tp=None, comment=""):
        side = side.lower()
        if side in ("buy", "long"):
            order_type = mt5.ORDER_TYPE_BUY
        elif side in ("sell", "short"):
            order_type = mt5.ORDER_TYPE_SELL
        else:
            raise ValueError(f"Invalid side: {side}")

        info = self.get_symbol_info(symbol)
        volume = self.normalize_volume(symbol, volume)

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"No tick data for {symbol}")

        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid

        if sl is not None:
            sl = self.normalize_price(symbol, sl)
        if tp is not None:
            tp = self.normalize_price(symbol, tp)

        comment = (comment or self.owner_tag or "")[:31]

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": self.account,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        if sl:
            request["sl"] = sl
        if tp:
            request["tp"] = tp

        return self.send_order(request)

    def _is_owned_position(self, position, include_legacy=True):
        comment = str(getattr(position, 'comment', '') or '')
        magic = int(getattr(position, 'magic', 0) or 0)

        if self.owner_tag and comment.startswith(self.owner_tag):
            return True
        if include_legacy and magic == int(self.account) and not comment:
            return True
        return False

    def get_positions(self, symbol=None, ticket=None, as_dict=True, owned_only=True, include_legacy=True):
        if ticket:
            positions = mt5.positions_get(ticket=ticket)
        elif symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        if positions is None:
            return []

        positions = list(positions)
        if owned_only:
            positions = [p for p in positions if self._is_owned_position(p, include_legacy=include_legacy)]

        if as_dict:
            return [
                {
                    'ticket': p.ticket,
                    'symbol': p.symbol,
                    'type': 'BUY' if p.type == mt5.ORDER_TYPE_BUY else 'SELL',
                    'volume': p.volume,
                    # Keep legacy aliases so older bot code paths keep working.
                    'price_open': p.price_open,
                    'price': p.price_open,
                    'time': p.time,
                    'open_price': p.price_open,
                    'current_price': p.price_current,
                    'sl': p.sl,
                    'tp': p.tp,
                    'profit': p.profit,
                    'swap': p.swap,
                    'comment': p.comment,
                    'magic': p.magic,
                }
                for p in positions
            ]
        return positions

    def close_position(self, ticket=None):
        if ticket:
            positions = [p for p in mt5.positions_get(ticket=ticket) or []]
        else:
            positions = [p for p in mt5.positions_get() or []]
            positions = [p for p in positions if self._is_owned_position(p, include_legacy=True)]

        closed = 0
        for pos in positions:
            try:
                tick = mt5.symbol_info_tick(pos.symbol)
                if tick is None:
                    continue

                if pos.type == mt5.ORDER_TYPE_BUY:
                    close_type = mt5.ORDER_TYPE_SELL
                    close_price = tick.bid
                else:
                    close_type = mt5.ORDER_TYPE_BUY
                    close_price = tick.ask

                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": pos.ticket,
                    "symbol": pos.symbol,
                    "volume": pos.volume,
                    "type": close_type,
                    "price": close_price,
                    "deviation": 20,
                    "magic": pos.magic,
                    "comment": "Close",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }

                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    closed += 1
            except Exception as e:
                logger.error(f"Close error: {e}")

        return closed

    def modify_position(self, ticket, sl=None, tp=None):
        position = mt5.positions_get(ticket=ticket)
        if not position:
            raise ValueError(f"Position {ticket} not found")

        pos = position[0]
        
        # Determine new SL/TP values
        new_sl = sl if sl is not None else pos.sl
        new_tp = tp if tp is not None else pos.tp
        
        # Skip if no change
        if new_sl == pos.sl and new_tp == pos.tp:
            return None
        
        # Validate SL movement direction
        if sl is not None:
            if pos.type == mt5.ORDER_TYPE_BUY and sl <= pos.sl:
                return None  # SL not improving
            if pos.type == mt5.ORDER_TYPE_SELL and sl >= pos.sl:
                return None  # SL not improving

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": pos.symbol,
            "sl": new_sl,
            "tp": new_tp,
        }

        try:
            result = mt5.order_send(request)
            if result is None:
                raise RuntimeError(f"Modify failed: {mt5.last_error()}")
            if result.retcode == 10025:  # No changes - not an error
                logger.debug(f"Modify skipped for {ticket}: No changes needed")
                return None
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                raise RuntimeError(f"Modify failed: {result.retcode}")
            return result
        except Exception as e:
            logger.error(f"Modify error: {e}")
            raise

    def get_account_info(self):
        info = mt5.account_info()
        if info is None:
            raise RuntimeError("Failed to get account info")

        return {
            'login': info.login,
            'balance': info.balance,
            'equity': info.equity,
            'margin': info.margin,
            'free_margin': info.margin_free,
            'margin_level': info.margin_level if info.margin > 0 else 0,
            'profit': info.profit,
        }
    
    def get_account(self):
        """Alias for get_account_info for compatibility"""
        return self.get_account_info()
    
    def get_tick(self, symbol):
        """Get current tick data for symbol"""
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {
            'bid': tick.bid,
            'ask': tick.ask,
            'last': tick.last,
            'time': tick.time,
            'volume': tick.volume
        }

