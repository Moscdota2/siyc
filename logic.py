def calculate_beer_price(total_units, product_ref):
    """Calculates the best price for beers by mixing units, half-tobos, and tobos."""
    
    # 1. SPECIAL PROMO: 14 units for $12 (only for specific Polar brands)
    # Applies to: Solera Azul, Polarcita, Polar Light
    promo_14_active = getattr(product_ref, 'has_promo_14', False)
    
    # We use a greedy approach for the best price
    # First, try to fit blocks of 14 if promo is active
    price_14 = 12.0
    
    # Standard prices from model
    price_tobo = float(getattr(product_ref, 'price_tobo_usd') or 10.0) # Default to 10
    price_half_tobo = float(getattr(product_ref, 'price_half_tobo_usd') or 5.0)
    price_unit = float(getattr(product_ref, 'price_unit_usd') or getattr(product_ref, 'price_usd') or 1.0)

    # Optimization: If total_units is small, just use standard logic
    if not promo_14_active or total_units < 14:
        tobos = total_units // 12
        rem = total_units % 12
        half_tobos = rem // 6
        units = rem % 6
        return (tobos * price_tobo) + (half_tobos * price_half_tobo) + (units * price_unit)

    # If promo 14 is active:
    # We should calculate if it's better than standard 12-tobo logic
    # Usually, 14 for $12 ($0.85/unit) vs 12 for $10 ($0.83/unit)
    # Actually, 12 for $10 is slightly better per unit, but 14 for $12 is a fixed package.
    # User said "hay la opcion de vender 14 por 12$", implying we should offer it.
    
    # Greedy: Use as many blocks of 14 as possible
    blocks_14 = total_units // 14
    remaining_after_14 = total_units % 14
    
    # For the remaining, use standard logic
    tobos = remaining_after_14 // 12
    rem = remaining_after_14 % 12
    half_tobos = rem // 6
    units = rem % 6
    
    return (blocks_14 * price_14) + (tobos * price_tobo) + (half_tobos * price_half_tobo) + (units * price_unit)

def calculate_inventory_investment(product_type, boxes, units, currency, purchase_price, distributor, current_rate):
    """Calculates total USD investment for an inventory entry based on business rules."""
    if purchase_price and purchase_price > 0:
        if currency == 'bs':
            if current_rate <= 0: return 0.0
            return purchase_price / current_rate
        return purchase_price
    
    # Fallback to defaults
    if currency == 'bs':
        if current_rate <= 0: return 0.0
        if product_type == 'cerveza':
            usd_price_per_box = 20.80 if distributor == 'polar' else 19.50
            return boxes * usd_price_per_box
        else:
            return 0.0 # Default fallback
    else:
        if product_type == 'cerveza':
            usd_price_per_box = 17.00 if distributor == 'polar' else 19.00
            return boxes * usd_price_per_box
        else:
            # For other products in USD, if no purchase_price, use 0 or some default
            return 0.0
    return 0.0
