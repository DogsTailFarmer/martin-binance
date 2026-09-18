#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convertor for last state .json files to the new structure, applied for all saved state created before 3.2.1
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2026 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.2.1"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import json
import jsonpickle
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Union, Optional

from martin_binance import LAST_STATE_PATH
from martin_binance.backup import save2json


def f2d(v: Any) -> Optional[str]:
    """Converts to precise string format for Pydantic's DecimalStr."""
    if v is None or str(v).lower() == "null":
        return None
    return str(Decimal(str(v)))


def get_time() -> float:
    import time
    return time.time() * 1000


def migrate_legacy_file(input_path: Path, output_path: Path, strategy_instance=None):
    """
    Step-by-step conversion of legacy state JSON to the optimized structure.
    Uses native jsonpickle to avoid missing the TP order or any other grid orders.
    """
    print(f"📖 Reading state file: {input_path.name}")

    with open(input_path, "r", encoding="utf-8") as f:  # skipcq: PTC-W6004
        strategy_state = json.load(f)

    legacy_tp_order_id = json.loads(strategy_state.get('tp_order_id'))
    tp_order_id = int(legacy_tp_order_id) if legacy_tp_order_id else None

    ms_orders_raw = strategy_state.get('ms.orders', '{}')
    if ms_orders_raw.startswith('"') and ms_orders_raw.endswith('"'):
        ms_orders_raw = json.loads(ms_orders_raw)

    decoded_ms_orders = jsonpickle.decode(ms_orders_raw, keys=True)  # skipcq: BAN-B301

    grid_items = []
    for key, o in decoded_ms_orders.items():
        o_id = int(getattr(o, 'id', None) or str(key).split('//')[-1])

        amount = f2d(getattr(o, 'amount', 0))
        price = f2d(getattr(o, 'price', 0))
        buy = bool(getattr(o, 'buy', True))
        order_type = str(getattr(o, 'order_type', 'LIMIT'))
        received_amount = f2d(getattr(o, 'received_amount', 0))
        remaining_amount = f2d(getattr(o, 'remaining_amount', amount))
        timestamp = int(getattr(o, 'timestamp', get_time()))

        grid_items.append({
            "id": o_id,
            "buy": buy,
            "amount": amount,
            "order_type": order_type,
            "received_amount": received_amount,
            "price": price,
            "remaining_amount": remaining_amount,
            "timestamp": timestamp
        })

    orders = {
        "tp_order_id": tp_order_id,
        "items": grid_items
    }

    def convert_legacy_orders(raw_list: list) -> list:
        new_list = []
        for _o in raw_list:
            _amount = f2d(_o.get("amount", 0))
            _price = f2d(_o.get("price", 0))
            new_list.append({
                "id": int(_o["id"]), "buy": bool(_o["buy"]), "amount": _amount,
                "order_type": str(_o.get("order_type", "LIMIT")), "received_amount": f2d(_o.get("received_amount", 0)),
                "price": _price, "remaining_amount": f2d(_o.get("remaining_amount", _amount)),
                "timestamp": int(_o.get("timestamp", get_time()))
            })
        return new_list

    def convert_legacy_orders_list(legacy_str: str) -> list:
        cleaned = json.loads(legacy_str) if legacy_str else []
        if isinstance(cleaned, str):
            cleaned = json.loads(cleaned)
        return convert_legacy_orders(cleaned) if isinstance(cleaned, list) else []

    orders_hold = {
        "tp_order_id": None,
        "items": convert_legacy_orders_list(strategy_state.get('orders_hold', '[]'))
    }
    orders_save = {
        "tp_order_id": None,
        "items": convert_legacy_orders_list(strategy_state.get('orders_save', '[]'))
    }

    command = json.loads(strategy_state.get('command'))
    grid_remove = json.loads(strategy_state.get('grid_remove', 'null'))
    grid_update_started = json.loads(strategy_state.get('grid_update_started', 'null'))
    cycle_buy = json.loads(strategy_state.get('cycle_buy'))
    cycle_buy_count = json.loads(strategy_state.get('cycle_buy_count'))
    cycle_sell_count = json.loads(strategy_state.get('cycle_sell_count'))

    cycle_time_raw = json.loads(strategy_state.get('cycle_time'))
    cycle_time = datetime.strptime(cycle_time_raw, '%Y-%m-%d %H:%M:%S.%f').isoformat() if cycle_time_raw else None
    cycle_time_reverse_raw = json.loads(strategy_state.get('cycle_time_reverse'))
    cycle_time_reverse = datetime.strptime(cycle_time_reverse_raw,
                                           '%Y-%m-%d %H:%M:%S.%f').isoformat() if cycle_time_reverse_raw else None

    deposit_first = f2d(json.loads(strategy_state.get('deposit_first')))
    deposit_second = f2d(json.loads(strategy_state.get('deposit_second')))
    martin = f2d(json.loads(strategy_state.get('martin')))
    order_q = json.loads(strategy_state.get('order_q'))
    over_price = f2d(json.loads(strategy_state.get('over_price')))

    part_amount_raw = json.loads(strategy_state.get('part_amount', '"{}"'))
    part_amount = eval(part_amount_raw) if part_amount_raw else {}  # skipcq: PYL-W0123

    initial_first = f2d(json.loads(strategy_state.get('initial_first')))
    initial_second = f2d(json.loads(strategy_state.get('initial_second')))
    initial_reverse_first = f2d(json.loads(strategy_state.get('initial_reverse_first')))
    initial_reverse_second = f2d(json.loads(strategy_state.get('initial_reverse_second')))
    profit_first = f2d(json.loads(strategy_state.get('profit_first')))
    profit_second = f2d(json.loads(strategy_state.get('profit_second')))

    reverse = json.loads(strategy_state.get('reverse'))
    reverse_hold = json.loads(strategy_state.get('reverse_hold'))
    reverse_init_amount = f2d(json.loads(strategy_state.get('reverse_init_amount')))
    reverse_target_amount = f2d(json.loads(strategy_state.get('reverse_target_amount')))

    reverse_price = json.loads(strategy_state.get('reverse_price'))
    if reverse_price:
        reverse_price = f2d(reverse_price)
    elif reverse:
        if cycle_buy:
            reverse_price = str(Decimal(deposit_second) / Decimal(reverse_target_amount))
        else:
            reverse_price = str(Decimal(reverse_target_amount) / Decimal(deposit_first))

    shift_grid_threshold = json.loads(strategy_state.get('shift_grid_threshold'))
    if shift_grid_threshold:
        shift_grid_threshold = f2d(shift_grid_threshold)

    start_after_shift = json.loads(strategy_state.get('start_after_shift', "0"))
    if start_after_shift:
        start_after_shift = f2d(start_after_shift)

    started_balance_detail_raw = json.loads(strategy_state.get('started_balance_detail', "\"()\""))
    started_balance_detail_tuple = eval(started_balance_detail_raw)  # skipcq: PYL-W0123
    started_balance_detail = [str(x) for x in started_balance_detail_tuple] if started_balance_detail_tuple else []

    status_time_raw = json.loads(strategy_state.get('status_time'))
    status_time = int(float(status_time_raw)) if status_time_raw else 0

    sum_amount_first = f2d(json.loads(strategy_state.get('sum_amount_first')))
    sum_amount_second = f2d(json.loads(strategy_state.get('sum_amount_second')))
    sum_profit_first = f2d(json.loads(strategy_state.get('sum_profit_first')))
    sum_profit_second = f2d(json.loads(strategy_state.get('sum_profit_second')))
    tp_amount = f2d(json.loads(strategy_state.get('tp_amount')))
    tp_part_amount_first = f2d(json.loads(strategy_state.get('tp_part_amount_first')))
    tp_part_amount_second = f2d(json.loads(strategy_state.get('tp_part_amount_second')))
    tp_target = f2d(json.loads(strategy_state.get('tp_target')))

    tp_order_raw = json.loads(strategy_state.get('tp_order', '"()"'))
    tp_order_tuple = eval(tp_order_raw) if tp_order_raw else ()  # skipcq: PYL-W0123

    tp_order = []
    if tp_order_tuple:
        tp_order = [
            bool(tp_order_tuple[0]),
            f2d(tp_order_tuple[1]),
            f2d(tp_order_tuple[2]),
            float(tp_order_tuple[3]) if len(tp_order_tuple) > 3 else get_time()
        ]

    order_id = int(json.loads(strategy_state.get('ms.order_id', strategy_state.get('order_id', '0'))))
    start_time_ms = int(json.loads(strategy_state.get('ms_start_time_ms', '0')))

    tp_wait_id = json.loads(strategy_state.get('tp_wait_id'))
    tp_wait_id = int(tp_wait_id) if (tp_wait_id and str(tp_wait_id).lower() != "null") else None

    restore_orders = json.loads(strategy_state.get('restore_orders', 'false'))
    tp_part_free = json.loads(strategy_state.get('tp_part_free', 'false'))

    migrated_dict = {
        "command": command, "grid_remove": grid_remove, "grid_update_started": grid_update_started,
        "cycle_buy": cycle_buy, "cycle_buy_count": cycle_buy_count, "cycle_sell_count": cycle_sell_count,
        "cycle_time": cycle_time, "cycle_time_reverse": cycle_time_reverse,
        "deposit_first": deposit_first, "deposit_second": deposit_second, "martin": martin, "order_q": order_q,
        "orders": orders, "orders_hold": orders_hold, "orders_save": orders_save, "over_price": over_price,
        "part_amount": part_amount, "initial_first": initial_first, "initial_second": initial_second,
        "initial_reverse_first": initial_reverse_first, "initial_reverse_second": initial_reverse_second,
        "profit_first": profit_first, "profit_second": profit_second, "reverse": reverse, "reverse_hold": reverse_hold,
        "reverse_init_amount": reverse_init_amount,
        "reverse_target_amount": reverse_target_amount, "reverse_price": reverse_price,
        "shift_grid_threshold": shift_grid_threshold, "start_after_shift": start_after_shift,
        "started_balance_detail": started_balance_detail, "status_time": status_time,
        "sum_amount_first": sum_amount_first, "sum_amount_second": sum_amount_second,
        "sum_profit_first": sum_profit_first, "sum_profit_second": sum_profit_second, "tp_amount": tp_amount,
        "tp_part_amount_first": tp_part_amount_first, "tp_part_amount_second": tp_part_amount_second,
        "tp_target": tp_target, "tp_order": tp_order, "order_id": order_id, "start_time_ms": start_time_ms,
        "tp_wait_id": tp_wait_id, "restore_orders": restore_orders, "tp_part_free": tp_part_free}

    if strategy_instance and hasattr(strategy_instance, "StateResponse"):
        model_instance = strategy_instance.StateResponse.model_validate(migrated_dict)
        save2json(model_instance, output_path)
    else:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(migrated_dict, f, indent=4, sort_keys=True)

    print(f"✨ Migration successfully completed! File saved: {output_path.name}")


def migrate_all_directory_states(directory_path: Union[str, Path], strategy_instance=None) -> None:
    """
    Scans the specified directory and converts all .json files to the new format.
    - The original file is renamed to .old
    - The new file is saved under the original .json filename.
    """
    target_dir = Path(directory_path).resolve()

    if not target_dir.exists() or not target_dir.is_dir():
        print(f"❌ Error: The specified directory does not exist:{target_dir}")
        return

    json_files = [f for f in target_dir.glob("*.json") if not f.name.startswith(".")]

    if not json_files:
        print(f"ℹ️ No .json migration files were found in the {target_dir} directory")
        return

    print(f"🚀 Initiating mass migration in the catalog: {target_dir}")
    print(f"Files found for processing: {len(json_files)}")
    print("=" * 60)

    success_count = 0
    failed_count = 0

    for json_file in json_files:
        old_backup_path = json_file.with_suffix(".old")
        temp_new_path = json_file.with_suffix(".json.new")

        try:
            migrate_legacy_file(json_file, temp_new_path, strategy_instance)
            json_file.replace(old_backup_path)
            temp_new_path.replace(json_file)

            print(
                f"✅ Success: {json_file.name} -> Converted to new format, old version saved as {old_backup_path.name}")
            success_count += 1

        except Exception as e:
            print(f"❌ Error during file migration {json_file.name}: {e}")
            if temp_new_path.exists():
                temp_new_path.unlink()
            failed_count += 1
            continue

    print("=" * 60)
    print(f"🏁 Migration complete! Successful: {success_count}, Failed: {failed_count}")


if __name__ == "__main__":
    migrate_all_directory_states(LAST_STATE_PATH)
