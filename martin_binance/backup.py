"""
On-the-fly backup and restore operational strategy state
"""
__author__ = "Jerry Fedorenko"
__copyright__ = "Copyright © 2026 Jerry Fedorenko aka VM"
__license__ = "MIT"
__version__ = "3.2.1"
__maintainer__ = "Jerry Fedorenko"
__contact__ = "https://github.com/DogsTailFarmer"

import ast
import inspect
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Dict, List, Tuple, Optional, Any, Union
from pydantic import BaseModel, ConfigDict, PlainSerializer, BeforeValidator, create_model
from pydantic.main import ModelT
import logging
import textwrap
import orjson
import os

from martin_binance.lib import Orders
from martin_binance.params import MODE

if MODE == 'S':
    logger = logging.getLogger('logger_S')
else:
    logger = logging.getLogger(f'logger.{__name__}')
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s: %(levelname)s] %(message)s"))
    stream_handler.setLevel(logging.INFO)
    logger.addHandler(stream_handler)

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

def msg2log(msg: str, log_level=logging.INFO) -> None:
    if MODE in ('T', 'TC') or log_level >= logging.ERROR:
        logger.log(log_level, msg)

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
                    msg2log("State backup is available", log_level=logging.INFO)
                else:
                    msg2log(f"🎉 State successfully loaded from: {file_path.name}", log_level=logging.INFO)
                return model_instance
    except orjson.JSONDecodeError as e:
        msg2log(f"⚠️ The main file {file_path.name} failed validation. Error: {e}", log_level=logging.WARNING)
    except Exception as e:
        msg2log(f"⚠️ Main file {file_path.name} is corrupted. Error: {e}", log_level=logging.ERROR)

    if bak_file_path.exists():
        msg2log(
            f"🔄 Starting recovery from backup! Attempting to read copy: {bak_file_path.name}...",
            log_level=logging.INFO
        )
        try:
            model_instance = _try_load(bak_file_path)
            if model_instance:
                msg2log("✅ Success! The state has been restored from the backup (.bak)", log_level=logging.INFO)
                try:
                    file_path.write_bytes(bak_file_path.read_bytes())
                except Exception as ex:
                    msg2log(ex, log_level=logging.ERROR)

                return model_instance
        except Exception as bak_err:
            msg2log(
                f"❌ Critical error: The backup file {bak_file_path.name} is also corrupted: {bak_err}",
                log_level = logging.CRITICAL
            )

    msg2log(
        "❌ Failed to restore state. Starting a clean session (all order pools will be empty)",
        log_level=logging.WARNING
    )
    return None

# =====================================================================
# 1. Utility micro-validators for forced type casting
# =====================================================================

def force_decimal_validator(v: Any) -> Any:
    """Forces string/number conversion to Decimal when reading state, respects None."""
    if v is None or v == "None":
        return None
    try:
        return Decimal(str(v))
    except (ValueError, InvalidOperation):
        return Decimal('0')


def force_int_validator(v: Any) -> Any:
    """Safely converts float/string timestamps to integer by dropping fractions."""
    if v is None or v == "None":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def force_datetime_validator(v: Any) -> Any:
    """Guarantees conversion of ISO strings from JSON back into datetime objects."""
    if v is None or isinstance(v, datetime):
        return v
    try:
        # Очищаем возможные лишние заэкранированные кавычки и парсим ISO-строку
        return datetime.fromisoformat(str(v).replace('"', '').replace("'", ""))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).replace(tzinfo=None)


def force_dict_validator(v: Any) -> dict:
    """Safely intercepts corrupted or legacy string '0' markers, forcing a clean dict."""
    if v is None or v == "0" or v == 0:
        return {}
    if isinstance(v, dict):
        return v
    return {}


def force_tuple_validator(v: Any) -> tuple:
    """Safely intercepts corrupted or legacy string '0' markers, forcing a clean tuple."""
    if v is None or v == "0" or v == 0:
        return ()
    if isinstance(v, (list, tuple)):
        return tuple(v)
    return ()

# =====================================================================
# 2. AUTOMATIC AST PARSER FOR STRATEGY SOURCE CODE
# =====================================================================

def get_init_self_annotations(strategy_instance) -> Dict[str, str]:
    """
    AST Parser with textwrap protection.
    Traverses the class hierarchy and extracts all 'self.attr: Type' definitions
    directly from the source code of __init__ methods.
    """
    annotations = {}

    for cls in strategy_instance.__class__.__mro__:
        if "__init__" in cls.__dict__:
            try:
                raw_source = inspect.getsource(cls.__init__)
                source = textwrap.dedent(raw_source)
                tree = ast.parse(source)

                for node in ast.walk(tree):
                    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Attribute):
                        if isinstance(node.target.value, ast.Name) and node.target.value.id == "self":
                            var_name = node.target.attr
                            var_type_str = ast.unparse(node.annotation)
                            if var_name not in annotations:
                                annotations[var_name] = var_type_str
            except (TypeError, OSError):
                continue

    return annotations


# =====================================================================
# 3. DYNAMIC PYDANTIC V2 MODEL GENERATOR
# =====================================================================

def init_dynamic_model(strategy_instance, attributes_to_backup: List[str]):
    """
    Builds the Pydantic model 'StateResponse' on-the-fly at startup.
    Uses an elegant unified pipeline combining AST-parsing and runtime inference.
    """
    base_fields = {}
    ast_annotations = get_init_self_annotations(strategy_instance)

    for attr_name in attributes_to_backup:
        default_value = getattr(strategy_instance, attr_name, None)
        hint_type = None

        # Step 3.1: If the type is found in the source code's AST annotations
        if attr_name in ast_annotations:
            type_str = ast_annotations[attr_name]
            is_complex_collection = any(kw in type_str for kw in ("Dict", "List", "Tuple", "dict", "list", "tuple"))

            if ("Decimal" in type_str or "DecimalStr" in type_str) and not is_complex_collection:
                hint_type = Annotated[Optional[Decimal], BeforeValidator(force_decimal_validator)] if (
                            "Optional" in type_str or "None" in type_str) else Annotated[
                    Decimal, BeforeValidator(force_decimal_validator)]
            elif "int" in type_str and not is_complex_collection:
                hint_type = Annotated[Optional[int], BeforeValidator(force_int_validator)] if (
                            "Optional" in type_str or "None" in type_str) else Annotated[
                    int, BeforeValidator(force_int_validator)]
            elif "datetime" in type_str and not is_complex_collection:
                hint_type = Annotated[Optional[datetime], BeforeValidator(force_datetime_validator)] if (
                            "Optional" in type_str or "None" in type_str) else Annotated[
                    datetime, BeforeValidator(force_datetime_validator)]
            elif is_complex_collection:
                if "Dict" in type_str or "dict" in type_str:
                    hint_type = Annotated[Dict[Any, Any], BeforeValidator(force_dict_validator)]
                else:
                    hint_type = Annotated[Tuple[Any, ...], BeforeValidator(force_tuple_validator)]
            else:
                # noinspection broad-exception
                try:
                    context = {
                        'Optional': Optional, 'Dict': Dict, 'Tuple': Tuple, 'List': List, 'Any': Any, 'Union': Union,
                        'datetime': datetime, 'DecimalStr': DecimalStr, 'Decimal': Decimal,
                        'int': int, 'float': float, 'str': str, 'bool': bool
                    }
                    hint_type = eval(type_str, {}, context)
                except Exception:
                    hint_type = Any

        # Step 3.2: Fall back to the dynamic type if the annotation is missing from the source code
        if hint_type is None:
            if isinstance(default_value, Orders):
                hint_type = PydanticOrdersField
            elif isinstance(default_value, Decimal):
                hint_type = Annotated[Decimal, BeforeValidator(force_decimal_validator)]
            elif isinstance(default_value, dict):
                hint_type = Annotated[
                    Dict[int, Tuple[DecimalStr, DecimalStr]], BeforeValidator(force_dict_validator)] if (
                            default_value and any(
                        isinstance(v, (Decimal, tuple, list)) for v in default_value.values())) else Annotated[
                    Dict[Any, Any], BeforeValidator(force_dict_validator)]
            elif isinstance(default_value, (tuple, list)):
                hint_type = Annotated[Tuple[DecimalStr, ...], BeforeValidator(force_tuple_validator)] if (
                            default_value and any(isinstance(v, Decimal) for v in default_value)) else Annotated[
                    Tuple[Any, ...], BeforeValidator(force_tuple_validator)]
            else:
                hint_type = type(default_value) if default_value is not None else Any

        # Step 3.3: Assembling Pydantic fields (Safe factory capture)
        if isinstance(default_value, Orders):
            base_fields[attr_name] = (hint_type, lambda factory=Orders: factory())
        elif isinstance(default_value, dict) and not default_value:
            base_fields[attr_name] = (hint_type, lambda factory=dict: factory())
        elif isinstance(default_value, (list, tuple)) and not default_value:
            base_fields[attr_name] = (hint_type, lambda factory=type(default_value): factory())
        else:
            base_fields[attr_name] = (hint_type, default_value)

    return create_model(
        "StateResponse",
        __config__=ConfigDict(arbitrary_types_allowed=True),
        **base_fields
    )
