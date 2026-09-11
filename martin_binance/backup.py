import inspect
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Dict, List, Tuple, Optional, Any, Union
from pydantic import BaseModel, ConfigDict, PlainSerializer, BeforeValidator, create_model
from pydantic.main import ModelT

import orjson
import os

from martin_binance.lib import Orders

BACKUP_REGISTRY = [
    "command", "cycle_buy", "cycle_buy_count", "cycle_sell_count", "cycle_time",
    "cycle_time_reverse", "deposit_first", "deposit_second", "grid_remove",
    "grid_update_started", "initial_first", "initial_reverse_first", "initial_reverse_second",
    "initial_second", "martin", "order_id", "order_q", "orders", "orders_hold",
    "orders_save", "over_price", "part_amount", "profit_first", "profit_second",
    "restore_orders", "reverse", "reverse_hold", "reverse_init_amount", "reverse_price",
    "reverse_target_amount", "shift_grid_threshold", "start_after_shift", "start_time_ms",
    "started_balance_detail", "status_time", "sum_amount_first", "sum_amount_second",
    "sum_profit_first", "sum_profit_second", "tp_amount", "tp_order", "tp_part_amount_first",
    "tp_part_amount_second", "tp_part_free", "tp_target", "tp_wait_id"
]

DecimalStr = Annotated[
    Decimal,
    PlainSerializer(lambda v: str(v), return_type=str, when_used='json')
]

class PydanticOrderSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    buy: bool
    amount: DecimalStr
    order_type: str
    received_amount: DecimalStr
    price: DecimalStr
    remaining_amount: DecimalStr
    timestamp: int


def serialize_orders_to_json(orders_manager: Orders) -> Dict[str, Any]:
    """
    Converts the Orders object into a JSON-compatible dictionary.
    Preserves the list of orders and the tp_order_id attribute.
    """
    return {
        "items": [PydanticOrderSchema.model_validate(o).model_dump(mode='json') for o in orders_manager],
        "tp_order_id": orders_manager.tp_order_id
    }


def deserialize_json_to_orders(v: Any) -> Orders:
    """
    Restores a live Orders object from a saved state
    """
    manager = Orders()

    # If a ready-made object was received (in memory during data validation)
    if isinstance(v, Orders):
        return v

    # If we are reading new structured data from a JSON file
    if isinstance(v, dict) and "items" in v:
        manager.restore(v["items"])
        manager.tp_order_id = v.get("tp_order_id")

    # Backward compatibility scenario: if the file was saved with an older version
    elif isinstance(v, list):
        manager.restore(v)
        manager.tp_order_id = None

    return manager


# Create a Pydantic type for the 'orders' field with custom packing/unpacking logic
PydanticOrdersField = Annotated[
    Orders,
    PlainSerializer(serialize_orders_to_json, when_used='json'),
    BeforeValidator(deserialize_json_to_orders)
]


def save2json(model_instance, file_path: Path) -> None:
    """
    Universally formats a Pydantic model into JSON with keys sorted alphabetically.
    Uses ultra-fast orjson to serialize nested structures.
    Performs an ATOMIC (safe) overwrite of the file on disk
    """
    data = model_instance.model_dump(mode='json')

    lines = ["{"]
    sorted_keys = sorted(data.keys())

    for idx, key in enumerate(sorted_keys):
        value = data[key]
        is_last = (idx == len(sorted_keys) - 1)
        comma = "" if is_last else ","

        if key.startswith("orders") and isinstance(value, dict):
            lines.append(f'    "{key}": {{')

            tp_val = orjson.dumps(value.get("tp_order_id")).decode('utf-8')
            lines.append(f'        "tp_order_id": {tp_val},')

            lines.append('        "items": [')
            orders_lines = []
            for order in value.get("items", []):
                order_str = orjson.dumps(order).decode('utf-8')
                orders_lines.append(f'            {order_str}')

            lines.append(",\n".join(orders_lines))
            lines.append('        ]')
            lines.append(f'    }}{comma}')

        elif isinstance(value, str):
            lines.append(f'    "{key}": "{value}"{comma}')

        else:
            val_str = orjson.dumps(value).decode('utf-8')
            lines.append(f'    "{key}": {val_str}{comma}')

    lines.append("}")
    pretty_json_str = "\n".join(lines)

    # =====================================================================
    # Atomic overwrite block with backup creation (.bak)
    # =====================================================================
    file_path = file_path.resolve()
    temp_file_path = file_path.parent / f".{file_path.name}.tmp"
    bak_file_path = file_path.with_suffix(file_path.suffix + ".bak")

    try:
        temp_file_path.write_bytes(pretty_json_str.encode('utf-8'))

        with open(temp_file_path, "ab") as f:
            os.fsync(f.fileno())

        if file_path.exists():
            file_path.replace(bak_file_path)

        temp_file_path.replace(file_path)

    except Exception as e:
        if temp_file_path.exists():
            temp_file_path.unlink()
        raise OSError(f"Critical error during atomic file write {file_path}: {e}")


def load_state(file_path: Path, response:  type[ModelT], probe: bool = False) -> Optional[object]:
    """
    Safely and ultra-fast loads the strategy state from disk.
    Automatically restores data from the .bak copy if the main file is corrupted.
    """
    file_path = file_path.resolve()
    bak_file_path = file_path.with_suffix(file_path.suffix + ".bak")

    def _try_load(path: Path) -> Optional[object]:
        if not path.exists():
            return None
        raw_bytes = path.read_bytes()
        parsed_dict = orjson.loads(raw_bytes)
        return response.model_validate(parsed_dict)

    try:
        if file_path.exists():
            model_instance = _try_load(file_path)
            if model_instance:
                if probe:
                    print("State backup is available")
                else:
                    print(f"🎉 State successfully loaded from: {file_path.name}")
                return model_instance
    except orjson.JSONDecodeError as e:
        print(f"⚠️ Warning: The main file {file_path.name} failed validation. Error: {e}")
    except Exception as e:
        print(f"⚠️ Warning: Main file {file_path.name} is corrupted. Error: {e}")

    if bak_file_path.exists():
        print(f"🔄 Starting recovery from backup! Attempting to read copy: {bak_file_path.name}...")
        try:
            model_instance = _try_load(bak_file_path)
            if model_instance:
                print("✅ Success! The state has been restored from the backup (.bak)")
                try:
                    file_path.write_bytes(bak_file_path.read_bytes())
                except Exception as ex:
                    print(ex)

                return model_instance
        except Exception as bak_err:
            print(f"❌ Critical error: The backup file {bak_file_path.name} is also corrupted: {bak_err}")

    print("❌ Failed to restore state. Starting a clean session (all order pools will be empty)")
    return None


def init_dynamic_model(strategy_instance, attributes_to_backup: List[str]):
    """
    Builds the Pydantic model 'StateResponse' on-the-fly at startup.
    Extracts types from __init__ annotations.
    If a field is missing in an old JSON, Pydantic inserts its default value from __init__.
    """
    base_fields = {}

    # Extract annotations from the __init__ method
    init_annotations = inspect.get_annotations(strategy_instance.__init__)

    for attr_name in attributes_to_backup:
        # Get the current default/live value from the strategy instance
        default_value = getattr(strategy_instance, attr_name, None)

        # Step 1: If the field has an explicit type annotation in __init__
        if attr_name in init_annotations:
            hint_type = init_annotations[attr_name]

            # Use lambda factories for mutable structures to avoid shared references
            if isinstance(default_value, Orders):
                base_fields[attr_name] = (hint_type, lambda: Orders())
            elif isinstance(default_value, dict) and not default_value:
                base_fields[attr_name] = (hint_type, lambda: {})
            else:
                # For primitive types (int, float, str, bool, Decimal)
                base_fields[attr_name] = (hint_type, default_value)
            continue

        # Step 2: Fallback logic based on the live default_value if no annotation is found
        if isinstance(default_value, Orders):
            base_fields[attr_name] = (PydanticOrdersField, lambda: Orders())

        elif isinstance(default_value, Decimal):
            base_fields[attr_name] = (DecimalStr, default_value)

        elif isinstance(default_value, dict):
            if default_value and any(isinstance(v, (Decimal, tuple, list)) for v in default_value.values()):
                base_fields[attr_name] = (Dict[int, Tuple[DecimalStr, DecimalStr]], lambda: {})
            else:
                base_fields[attr_name] = (Dict[Any, Any], lambda: {})

        elif isinstance(default_value, (tuple, list)):
            if default_value and any(isinstance(v, Decimal) for v in default_value):
                base_fields[attr_name] = (Tuple[DecimalStr, ...], default_value)
            else:
                base_fields[attr_name] = (List[Any], default_value)

        else:
            # Fallback for other types, default value acts as the field default
            base_fields[attr_name] = (type(default_value) if default_value is not None else Any, default_value)

    # Generate the finalized StateResponse class
    return create_model(
        "StateResponse",
        __config__=ConfigDict(arbitrary_types_allowed=True),
        **base_fields
    )
