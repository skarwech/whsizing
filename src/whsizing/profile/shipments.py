"""F3 step 8: shipment split, parcel vs pallet orders (I8)."""

from __future__ import annotations

import numpy as np
import polars as pl

from whsizing.errors import WhsizingError
from whsizing.schemas import Flows, ShipmentSplit


def split_orders(orders: pl.DataFrame, flows: Flows) -> pl.DataFrame:
    """Pallet order if weight > pallet_order_weight_kg or cube > pallet_order_cube_m3: 1 pallet,
    0 parcels (I8); otherwise max(1, ceil(weight / parcel_max_weight_kg)) parcels. The division
    runs in numpy: polars divides by a scalar with a reciprocal multiply, except on a length-1
    chunk, so the parcels of an order on a ceil boundary changed with the thread count."""
    pallet = (pl.col("weight_kg") > flows.pallet_order_weight_kg) | (
        pl.col("cube_m3") > flows.pallet_order_cube_m3
    )
    w = orders["weight_kg"].to_numpy()
    parcels = pl.Series(np.maximum(np.ceil(w / flows.parcel_max_weight_kg), 1), dtype=pl.Int64)
    return orders.with_columns(
        is_pallet=pallet,
        pallets=pallet.cast(pl.Int64),
        parcels=pl.when(pallet).then(0).otherwise(parcels),
    )


def shipment_split(orders: pl.DataFrame) -> ShipmentSplit:
    """Shares by orders and by lines; mean parcels over parcel orders (0 if there are none)."""
    if orders.is_empty():  # unreachable from build_profile: shipped_lines raises first
        raise WhsizingError("shipment_split needs at least one shipped order")
    pal = orders.filter("is_pallet")
    parcel_orders = orders.filter(~pl.col("is_pallet"))
    share_orders = pal.height / orders.height
    share_lines = int(pal["n_lines"].sum()) / int(orders["n_lines"].sum())
    mean_parcels = float(parcel_orders["parcels"].mean() or 0.0)  # pyright: ignore[reportArgumentType]
    return ShipmentSplit(
        parcel_share_orders=1 - share_orders,
        pallet_share_orders=share_orders,
        parcel_share_lines=1 - share_lines,
        pallet_share_lines=share_lines,
        mean_parcels_per_order=mean_parcels,
    )
